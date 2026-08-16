"""Experiment 7 -- group versus groupoid speaker variation.

Two worlds:

  Dataset A (group)     one chart per speaker:              g_{r,q} = g_r
  Dataset B (groupoid)  one chart per (speaker, phone):     g_{r,q} depends on q

and two models fitted to each:

  Model G     one affine speaker map, shared across phones
  Model Gpd   one affine speaker map per phone

The prediction is that Model G fails *systematically* on groupoid data while both do fine
on group data. The quantity reported is the held-out error ratio G / Gpd on each dataset,
which is the synthetic analogue of an empirical 1.70x versus 1.13x.

Two controls keep the comparison honest:
  * Model Gpd has three times the parameters, so its advantage on *group* data measures
    how much of any ratio is simply extra capacity.
  * The groupoid world is built with phone deviations that are zero-mean across phones,
    so the two worlds share a speaker-average chart and differ in exactly one respect.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import MUTED, PALETTE, caption, parse_args, save

from analysis.metrics import IDENTIFIABLE, PARTIAL
from analysis.recording import ExperimentRun
from config import SequenceConfig, WorldConfig, noise_world, speaker_world
from generator import generate

N_SPEAKERS = 12


def speaker_templates(ds, mask):
    """Per (speaker, transition) mean acoustic trajectory over the given segment subset."""
    out = {}
    for s in range(ds.config.speaker.n_speakers):
        for ti, (q, r) in enumerate(ds.transitions):
            sel = mask & ds.mask(q, r, speaker=s)
            if sel.sum() >= 2:
                out[(s, ti)] = ds.observed[sel].mean(axis=0)
    return out


def fit_affine(X: np.ndarray, Y: np.ndarray):
    """Least-squares affine map X -> Y; returns (coefficients, in-sample rmse)."""
    Xa = np.hstack([X, np.ones((X.shape[0], 1))])
    coef, *_ = np.linalg.lstsq(Xa, Y, rcond=None)
    return coef, float(np.sqrt(np.mean((Y - Xa @ coef) ** 2)))


def apply_affine(coef, X):
    return np.hstack([X, np.ones((X.shape[0], 1))]) @ coef


def evaluate(ds, seed: int):
    """Fit Model G and Model Gpd on a train split and score both on a held-out split."""
    rng = np.random.default_rng(seed)
    train = rng.random(ds.n_segments) < 0.5
    tr, te = speaker_templates(ds, train), speaker_templates(ds, ~train)
    n_trans = len(ds.transitions)
    source_of = {ti: ds.phone_index(q) for ti, (q, _) in enumerate(ds.transitions)}

    # reference template per transition: the speaker-averaged trajectory on the train split
    ref = {}
    for ti in range(n_trans):
        stack = [v for (s, t), v in tr.items() if t == ti]
        if stack:
            ref[ti] = np.mean(stack, axis=0)

    errs = {"G": [], "Gpd": []}
    n_params = {"G": 0, "Gpd": 0}
    per_speaker = {"G": [], "Gpd": []}
    d_s = ds.config.d_acoustic

    for s in range(ds.config.speaker.n_speakers):
        keys = [ti for ti in range(n_trans) if (s, ti) in tr and (s, ti) in te and ti in ref]
        if not keys:
            continue

        # Model G: one map for the whole speaker
        X = np.concatenate([ref[ti] for ti in keys])
        Y = np.concatenate([tr[(s, ti)] for ti in keys])
        coef, _ = fit_affine(X, Y)
        n_params["G"] += coef.size
        Xte = np.concatenate([ref[ti] for ti in keys])
        Yte = np.concatenate([te[(s, ti)] for ti in keys])
        e_g = float(np.sqrt(np.mean((Yte - apply_affine(coef, Xte)) ** 2)))

        # Model Gpd: one map per source phone
        res, tot = [], 0
        for ph in sorted({source_of[ti] for ti in keys}):
            sub = [ti for ti in keys if source_of[ti] == ph]
            Xp = np.concatenate([ref[ti] for ti in sub])
            Yp = np.concatenate([tr[(s, ti)] for ti in sub])
            cp, _ = fit_affine(Xp, Yp)
            n_params["Gpd"] += cp.size
            res.append((np.concatenate([te[(s, ti)] for ti in sub]) - apply_affine(cp, Xp)) ** 2)
            tot += 1
        e_gpd = float(np.sqrt(np.mean(np.concatenate(res))))

        errs["G"].append(e_g)
        errs["Gpd"].append(e_gpd)
        per_speaker["G"].append(e_g)
        per_speaker["Gpd"].append(e_gpd)

    _ = d_s
    return dict(
        rmse_G=float(np.mean(errs["G"])),
        rmse_Gpd=float(np.mean(errs["Gpd"])),
        ratio=float(np.mean(errs["G"]) / np.mean(errs["Gpd"])),
        per_speaker_G=per_speaker["G"],
        per_speaker_Gpd=per_speaker["Gpd"],
        n_params=n_params,
    )


def main() -> None:
    args = parse_args(__doc__)
    n_seq = 900 if args.quick else 6000
    run = ExperimentRun(name="07_speaker_variation", title="Experiment 7 -- group versus groupoid")

    base = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    base = noise_world("correlated", 0.1, base)
    worlds = {
        "A: group": speaker_world("group", N_SPEAKERS, base),
        "B: groupoid": speaker_world("groupoid", N_SPEAKERS, base),
    }
    run.scalar("n_sequences", n_seq)
    run.scalar("n_speakers", N_SPEAKERS)
    run.scalar("noise_scale", 0.1)

    results = {}
    datasets = {}
    for label, w in worlds.items():
        ds = generate(w, seed=args.seed)
        datasets[label] = ds
        results[label] = evaluate(ds, args.seed)
        run.table(label, {k: v for k, v in results[label].items() if not k.startswith("per_speaker")})

    # ---- ground truth about how different the two worlds are ---------------------------
    gp = datasets["B: groupoid"].speakers  # GT: the charts that generated the data
    gr = datasets["A: group"].speakers  # GT
    phone_spread = float(np.mean(np.abs(gp.A - gp.A.mean(axis=1, keepdims=True))))  # GT
    speaker_spread = float(np.mean(np.abs(gp.A.mean(axis=1) - np.eye(base.d_art))))  # GT
    run.scalar("groupoid_phone_deviation_mean_abs", phone_spread)
    run.scalar("speaker_deviation_mean_abs", speaker_spread)
    run.scalar("group_world_phone_deviation (should be 0)",
               float(np.max(np.abs(gr.A - gr.A.mean(axis=1, keepdims=True)))))  # GT

    ratio_group = results["A: group"]["ratio"]
    ratio_groupoid = results["B: groupoid"]["ratio"]
    excess = ratio_groupoid / ratio_group

    # ---- noise / sample-size robustness -------------------------------------------------
    robustness = {}
    for scale in ([0.1, 0.3] if args.quick else [0.03, 0.1, 0.3, 1.0]):
        row = {}
        for label, w in worlds.items():
            ds = generate(noise_world("correlated", scale, w), seed=args.seed)
            row[label] = evaluate(ds, args.seed)["ratio"]
        row["excess"] = row["B: groupoid"] / row["A: group"]
        robustness[scale] = row
    run.table("ratio_vs_noise", robustness)

    # ---- findings -------------------------------------------------------------------------
    run.record(
        question="Does a global-group speaker model fail systematically on groupoid data?",
        ground_truth={
            "dataset A": "g_{r,q} = g_r for every phone",
            "dataset B": "g_{r,q} varies by phone, with deviations zero-mean across phones",
        },
        estimate={
            "held-out error ratio G/Gpd on group data": round(ratio_group, 4),
            "held-out error ratio G/Gpd on groupoid data": round(ratio_groupoid, 4),
            "excess": round(excess, 4),
        },
        error=float(abs(excess - 1.0)),
        error_label="excess ratio above the group-data baseline",
        status=IDENTIFIABLE if excess > 1.05 else PARTIAL,
        control=(
            f"the same comparison on group data gives {ratio_group:.3f}, which is what Gpd's "
            f"{results['A: group']['n_params']['Gpd'] // max(results['A: group']['n_params']['G'], 1)}x "
            "parameter count buys on its own"
        ),
        notes=(
            f"Model G's held-out error is {ratio_groupoid:.2f}x Model Gpd's on groupoid data "
            f"against {ratio_group:.2f}x on group data. The gap is the phone-local part "
            "of the chart, and it cannot be absorbed by a per-speaker map at any sample size, because "
            "the phone deviations are constructed to average to zero across phones."
        ),
    )
    stable = all(v["excess"] > 1.05 for v in robustness.values())
    run.record(
        question="Does that conclusion survive changes in observation noise?",
        ground_truth={"phone deviation magnitude": phone_spread},
        estimate={s: round(v["excess"], 3) for s, v in robustness.items()},
        error=None,
        error_label="n/a (ratio by noise level)",
        status=IDENTIFIABLE if stable else PARTIAL,
        control="the group world is re-fitted at every noise level as its own baseline",
        notes=(
            "the excess ratio shrinks as noise grows: at high noise the residual is dominated by "
            "observation noise that neither model can explain, so the *ratio* compresses towards 1 "
            "even though the structural mismatch is unchanged. A ratio reported without its noise "
            "level is not interpretable."
        ),
    )

    # ---- figure ---------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.7))

    ax = axes[0]
    labels = list(results)
    x = np.arange(len(labels))
    ax.bar(x - 0.19, [results[k]["rmse_G"] for k in labels], width=0.36, color=PALETTE[0], label="Model G")
    ax.bar(x + 0.19, [results[k]["rmse_Gpd"] for k in labels], width=0.36, color=PALETTE[1], label="Model Gpd")
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("held-out rmse")
    ax.set_title("Held-out error by model and world")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7)
    for xi, k in zip(x, labels, strict=True):
        ax.annotate(f"×{results[k]['ratio']:.2f}", xy=(xi, max(results[k]['rmse_G'], results[k]['rmse_Gpd'])),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8, color=MUTED)

    ax = axes[1]
    for i, k in enumerate(labels):
        ax.scatter(results[k]["per_speaker_Gpd"], results[k]["per_speaker_G"], s=26,
                   color=PALETTE[i], marker=["o", "s"][i], label=k, zorder=3)
    lim = max(max(results[k]["per_speaker_G"]) for k in labels) * 1.1
    ax.plot([0, lim], [0, lim], color=MUTED, linestyle=":", linewidth=1.2, zorder=1)
    ax.annotate("equal error", xy=(lim * 0.62, lim * 0.62), xytext=(3, -10),
                textcoords="offset points", fontsize=7, color=MUTED)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Model Gpd held-out rmse")
    ax.set_ylabel("Model G held-out rmse")
    ax.set_title("Per speaker")
    ax.legend(fontsize=7, loc="upper left")

    ax = axes[2]
    scales = sorted(robustness)
    ax.plot(scales, [robustness[s]["A: group"] for s in scales], color=PALETTE[0], marker="o",
            label="group data")
    ax.plot(scales, [robustness[s]["B: groupoid"] for s in scales], color=PALETTE[1], linestyle="--",
            marker="s", label="groupoid data")
    ax.axhline(1.0, color=MUTED, linestyle=":", linewidth=1.2)
    ax.set_xscale("log")
    ax.set_xlabel("noise scale")
    ax.set_ylabel("held-out ratio G / Gpd")
    ax.set_title("Ratio against noise")
    ax.legend(fontsize=7)

    caption(
        fig,
        "Model G is the correct model for dataset A and a mis-specified one for dataset B. The "
        "gap between the two ratios is the measurable signature of groupoid structure; the group-data "
        "ratio is the baseline that Gpd's larger parameter count buys anyway.",
    )
    fig.tight_layout()
    save(fig, "group_vs_groupoid", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
