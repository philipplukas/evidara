"""Experiment 2 -- is the transition-dependent temporal structure low-dimensional?

Builds the contrast design matrix and takes its SVD, reporting R_k = sum_{i<=k} s_i^2 / sum_i s_i^2.

Two designs are used because they answer different questions:

  per-contrast   X is (T, d_s) as in the spec. Its rank is capped by the *acoustic*
                 dimension, so R_3 = 1 is arithmetic, not evidence.
  pooled         X is (T, P * d_s) over every within-source contrast. No such ceiling,
                 so this is the sharper test: does ONE low-dimensional temporal subspace
                 serve every transition?

The control is a null design built by permuting the following-phone label, which gives
the singular spectrum that noise alone produces at this sample size. A component is only
"real" if it clears that floor.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import GRID, INK_2, MUTED, PALETTE, caption, parse_args, save

from analysis.metrics import IDENTIFIABLE, PARTIAL
from analysis.recording import ExperimentRun
from analysis.svd import all_contrasts, stack_contrasts, temporal_rank
from config import SequenceConfig, WorldConfig, dimension_world, noise_world
from generator import generate

NOISE_SCALES = [0.03, 0.1, 0.3, 1.0]


def null_spectra(ds, n_null: int, seed: int = 0):
    """Singular spectra of contrast designs built from permuted following-phone labels.

    Under permutation the two groups are exchangeable, so every singular value is noise.
    A *single* null draw is itself noisy -- at low SNR the second signal component and
    the top null value land within a few percent of each other, and one draw will
    sometimes rank them the wrong way round. The detection threshold below is therefore
    the 95th percentile of the top null singular value over ``n_null`` permutations.
    """
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_null):
        shuffled = replace(ds)
        shuffled.following = ds.following.copy()
        for q in range(len(ds.phones)):
            m = ds.source == q
            shuffled.following[m] = rng.permutation(ds.following[m])
        out.append(temporal_rank(stack_contrasts(all_contrasts(shuffled))))
    return out


def main() -> None:
    args = parse_args(__doc__)
    n_seq = 400 if args.quick else 3000
    run = ExperimentRun(name="02_temporal_rank", title="Experiment 2 -- is the temporal structure low-dimensional?")

    base = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))

    # ---- ground truth -----------------------------------------------------------------
    d_art = base.d_art
    run.scalar("ground_truth_articulatory_modes", d_art)
    run.scalar("n_sequences", n_seq)

    # noiseless reference: the rank the generative mechanism actually has
    clean_ds = generate(noise_world("correlated", 1e-6, base), seed=args.seed)
    pooled_clean = temporal_rank(stack_contrasts(all_contrasts(clean_ds, field="clean")))  # GT
    latent_pooled = temporal_rank(
        np.concatenate(
            [
                clean_ds.latent_u[clean_ds.mask(q, r1)].mean(0)  # GT: latent rank reference
                - clean_ds.latent_u[clean_ds.mask(q, r2)].mean(0)  # GT
                for q in clean_ds.phones
                for r1 in clean_ds.phones
                for r2 in clean_ds.phones
                if r1 < r2 and (q, r1) in clean_ds.transitions and (q, r2) in clean_ds.transitions
            ],
            axis=1,
        )
    )
    run.scalar("latent_R_k (ground truth)", latent_pooled.ratios(3))
    run.scalar("clean_acoustic_R_k", pooled_clean.ratios(4))
    run.scalar("clean_sigma2_over_sigma1", float(pooled_clean.singular_values[1] / pooled_clean.singular_values[0]))
    run.scalar("clean_sigma3_over_sigma1", float(pooled_clean.singular_values[2] / pooled_clean.singular_values[0]))

    # ---- noise sweep ------------------------------------------------------------------
    sweep = {}
    n_null = 8 if args.quick else 20
    for scale in NOISE_SCALES:
        ds = generate(noise_world("correlated", scale, base), seed=args.seed)
        cs = all_contrasts(ds)
        spec = temporal_rank(stack_contrasts(cs))
        nulls = null_spectra(ds, n_null, seed=args.seed + 1)
        null = nulls[0]
        top_null = np.array([n.singular_values[0] for n in nulls])
        threshold = float(np.quantile(top_null, 0.95))
        per_contrast = temporal_rank(cs[0].delta)
        sweep[scale] = dict(
            spec=spec,
            null=null,
            R=spec.ratios(4),
            R_per_contrast=per_contrast.ratios(3),
            s_ratio_2=float(spec.singular_values[1] / spec.singular_values[0]),
            s_ratio_3=float(spec.singular_values[2] / spec.singular_values[0]),
            null_top_ratio=float(threshold / spec.singular_values[0]),
            modes_above_null=int(np.sum(spec.singular_values > threshold)),
            snr=ds.snr()["snr_db"],  # GT: diagnostic
        )
        run.table(
            f"noise_scale={scale}",
            {k: v for k, v in sweep[scale].items() if k not in ("spec", "null")},
        )

    # ---- does rank track the articulatory dimension? ----------------------------------
    dim_check = {}
    for d in ([2, 5] if args.quick else [2, 3, 5]):
        w = dimension_world(d, max(3 * d, 6), base)
        w = replace(w, sequence=replace(w.sequence, n_sequences=max(n_seq // 2, 200)))
        dsd = generate(noise_world("correlated", 1e-6, w), seed=args.seed)
        sp = temporal_rank(stack_contrasts(all_contrasts(dsd, field="clean")))  # GT: noiseless probe
        ratios = np.asarray([sp.ratio(k) for k in range(1, min(d + 3, sp.singular_values.size) + 1)])
        s_rel = sp.singular_values / sp.singular_values[0]
        dim_check[d] = dict(
            R_k=[float(x) for x in ratios],
            components_above_1e_3=int(np.sum(s_rel > 1e-3)),
            components_above_1e_6=int(np.sum(s_rel > 1e-6)),
            sigma_ratios=[float(x) for x in s_rel[: d + 2]],
        )
    run.table("rank_vs_articulatory_dimension", dim_check)

    # ---- findings ---------------------------------------------------------------------
    ref = sweep[0.1]
    run.record(
        question="Is the transition-dependent temporal variation low-dimensional?",
        ground_truth={"latent rank": d_art, "latent R_1": latent_pooled.ratios(2)[1]},
        estimate={"R_1": ref["R"][1], "R_2": ref["R"][2], "R_3": ref["R"][3]},
        error=abs(1.0 - ref["R"][2]),
        error_label="1 - R_2",
        status=IDENTIFIABLE,
        control=f"permuted-label null: top null singular value is {ref['null_top_ratio']:.3f} of s_1",
        notes=(
            f"R_1 = {ref['R'][1]:.5f} already at noise scale 0.1 -- one temporal component carries "
            f"almost everything. The generative rank is {d_art}, but the second mode holds only "
            f"{sweep[0.1]['s_ratio_2'] ** 2 * 100:.3f}% of the energy because the two damped "
            "responses are nearly collinear curves."
        ),
    )
    detect = {s: sweep[s]["modes_above_null"] for s in NOISE_SCALES}
    correct = [s for s in NOISE_SCALES if detect[s] == d_art]
    run.record(
        question="How many temporal components are detectable above the noise floor?",
        ground_truth={"generative modes": d_art},
        estimate=detect,
        error=None,
        error_label="n/a (count)",
        status=PARTIAL,
        control=f"95th percentile of the top singular value over {n_null} label permutations",
        notes=(
            f"detected counts by noise scale: {detect}; the true count {d_art} is recovered at "
            f"{correct if correct else 'no'} noise scale(s). Low-dimensionality is easy to confirm; "
            "the exact dimension is not, because a near-collinear second mode becomes statistically "
            "invisible long before it becomes physically absent."
        ),
    )
    matched_1e3 = [d for d, v in dim_check.items() if v["components_above_1e_3"] == d]
    matched_1e6 = [d for d, v in dim_check.items() if v["components_above_1e_6"] == d]
    run.record(
        question="Does the recovered temporal rank track the articulatory dimension d_art?",
        ground_truth={d: d for d in dim_check},
        estimate={d: v["components_above_1e_3"] for d, v in dim_check.items()},
        error=None,
        error_label="n/a (count)",
        status=PARTIAL,
        control="noiseless data, so any shortfall is collinearity rather than noise",
        notes=(
            "counted on clean acoustics as the number of singular values above 1e-3 of the first: "
            + ", ".join(f"d_art={d} -> {v['components_above_1e_3']}" for d, v in dim_check.items())
            + f" (exact at d_art in {matched_1e3 or 'none'}). Dropping the threshold to 1e-6 gives "
            + ", ".join(f"{d} -> {v['components_above_1e_6']}" for d, v in dim_check.items())
            + f" (exact at d_art in {matched_1e6 or 'none'}), which OVER-counts at small d_art "
            "because the acoustic nonlinearity leaks energy into components the dynamics never "
            "produced. The count is threshold-dependent in both directions, so 'how many temporal "
            "modes' is not answerable by a variance rule alone."
        ),
    )

    # ---- figure -----------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))

    ax = axes[0]
    k = np.arange(1, 7)
    ax.semilogy(k, pooled_clean.singular_values[:6] / pooled_clean.singular_values[0],
                color=PALETTE[0], marker="o", markersize=5, label="clean acoustics")
    for i, scale in enumerate([0.1, 1.0]):
        sp = sweep[scale]["spec"]
        ax.semilogy(k, sp.singular_values[:6] / sp.singular_values[0], color=PALETTE[i + 1],
                    linestyle=["--", "-."][i], marker=["s", "^"][i], markersize=5,
                    label=f"observed, noise {scale}")
    nl = sweep[0.1]["null"]
    ax.semilogy(k, nl.singular_values[:6] / sweep[0.1]["spec"].singular_values[0], color=MUTED,
                linestyle=":", marker="x", markersize=5, label="permuted-label null (noise 0.1)")
    ax.set_xlabel("component k")
    ax.set_ylabel("$\\sigma_k / \\sigma_1$")
    ax.set_title("Singular spectrum of the pooled contrast")
    # floor the axis: the clean spectrum falls to ~1e-13 (numerical zero) past component 4,
    # and letting that set the range compresses everything that carries information
    ax.set_ylim(bottom=1e-6)
    ax.legend(loc="lower left", fontsize=7)

    ax = axes[1]
    t_ms = clean_ds.t * 1000.0
    for i in range(3):
        comp = pooled_clean.component(i + 1)
        ax.plot(t_ms, comp / np.max(np.abs(comp)), color=PALETTE[i], linestyle=["-", "--", "-."][i],
                label=f"component {i + 1}")
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("normalised temporal component")
    ax.set_title("Leading temporal components (clean)")
    ax.legend(loc="lower left", fontsize=7.5)
    ax.axhline(0, color=GRID, linewidth=0.8)

    ax = axes[2]
    scales = NOISE_SCALES
    # R_1 is not plotted here: it sits at ~0.99 and would flatten everything else against the
    # axis. Two measures of different scale belong on two charts, not two y-axes.
    ax.loglog(scales, [sweep[s]["s_ratio_2"] for s in scales], color=PALETTE[1], linestyle="--",
              marker="s", label="$\\sigma_2/\\sigma_1$ observed")
    ax.loglog(scales, [sweep[s]["null_top_ratio"] for s in scales], color=MUTED, linestyle=":",
              marker="x", label="permuted-label null floor")
    true_ratio = float(pooled_clean.singular_values[1] / pooled_clean.singular_values[0])
    ax.axhline(true_ratio, color=PALETTE[2], linestyle="-.", linewidth=1.4)
    ax.annotate("true $\\sigma_2/\\sigma_1$", xy=(scales[0], true_ratio), xytext=(2, 4),
                textcoords="offset points", fontsize=7.5, color=INK_2)
    ax.set_xlabel("noise scale")
    ax.set_ylabel("$\\sigma_2/\\sigma_1$")
    ax.set_title("Second mode against the noise floor")
    ax.legend(fontsize=7.5, loc="upper left")

    caption(
        fig,
        "The generative temporal rank is 2 (two articulatory modes), but the second mode carries "
        f"only {float(pooled_clean.singular_values[1] / pooled_clean.singular_values[0]) ** 2 * 100:.3f}% "
        "of the contrast energy, so it drops below the permuted-label null as soon as noise is "
        "non-trivial. Low-dimensionality is robust; the exact dimension is not.",
    )
    fig.tight_layout()
    save(fig, "temporal_rank", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
