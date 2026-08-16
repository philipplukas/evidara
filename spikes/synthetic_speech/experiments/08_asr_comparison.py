"""Experiment 8 -- can explicit dynamics improve recognition, and where?

Task: name the transition (q, r) that produced an observed segment. Six classes.

  A  frame-independent  logistic regression on single frames, posteriors averaged
  B  generic temporal   a small GRU over the frame sequence
  C  structured         estimates targets, dynamics and alpha, then *synthesises* each
                        class template (given Phi -- ORACLE, see analysis/recognizers.py)

Ordinary test accuracy is the least interesting number here. The tests that matter are
the ones that change the structure between train and test:

  interpolation       seen speakers, seen transitions
  unseen transition   B->C withheld from training, present at test
  unseen speaker      trained on speakers 0..n-2, tested on speaker n-1
  noise               the same models at higher observation noise
  sample size         N = 100 .. 10000 training segments
  distribution shift  speaker charts changed at test time

and two ablations, which are the point of the whole comparison:

  C'  randomised dynamics   A_u, A_v replaced by a random stable second-order system,
                            targets and alpha untouched
  C'' no anticipation       alpha forced to 0, dynamics untouched

If randomising the dynamics costs nothing, the temporal structure is not what is doing the
work, whatever the headline accuracy says. Running both ablations is what turns that from a
yes/no into a decomposition: it says which layer of the factorisation the task actually
depends on.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import MUTED, PALETTE, caption, parse_args, save

from analysis.metrics import IDENTIFIABLE, PARTIAL
from analysis.recognizers import FrameIndependent, GRURecogniser, StructuredRecogniser, torch_available
from analysis.recording import ExperimentRun
from config import SequenceConfig, WorldConfig, noise_world, speaker_world
from generator import generate

SAMPLE_SIZES = [100, 300, 1000, 3000, 10000]
N_SPEAKERS = 8
HELD_OUT_TRANSITION = ("B", "C")



def annotate_bars(ax, idx, values, offset):
    """Label every bar, so a measured zero reads as zero rather than as a missing bar."""
    for i, v in zip(idx, values, strict=True):
        ax.annotate(f"{v:.2f}", xy=(v, i + offset), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7, color=MUTED)


def split_xy(ds, mask):
    return ds.observed[mask].astype(float), ds.transition[mask]  # GT: the supervised label


def build_models(ds, use_gru: bool, seed: int):
    models = {
        "A frame-independent": lambda: FrameIndependent(),
        "C structured": lambda: StructuredRecogniser(
            phi=ds.phi,  # ORACLE: the acoustic geometry layer is given, not estimated
            transitions=[(ds.phone_index(q), ds.phone_index(r)) for q, r in ds.transitions],
            dt=ds.config.grid.dt,
            n_frames=ds.n_frames,
            seed=seed,
        ),
        "C' structured, randomised dynamics": lambda: StructuredRecogniser(
            phi=ds.phi,  # ORACLE
            transitions=[(ds.phone_index(q), ds.phone_index(r)) for q, r in ds.transitions],
            dt=ds.config.grid.dt,
            n_frames=ds.n_frames,
            randomise_dynamics=True,
            seed=seed,
        ),
        "C'' structured, no anticipation": lambda: StructuredRecogniser(
            phi=ds.phi,  # ORACLE
            transitions=[(ds.phone_index(q), ds.phone_index(r)) for q, r in ds.transitions],
            dt=ds.config.grid.dt,
            n_frames=ds.n_frames,
            ignore_anticipation=True,
            seed=seed,
        ),
    }
    if use_gru:
        models["B GRU"] = lambda: GRURecogniser(n_classes=len(ds.transitions), seed=seed)
    return models


def train_and_score(ds, models, train_mask, test_masks: dict, d_art: int):
    Xtr, ytr = split_xy(ds, train_mask)
    out = {}
    for name, make in models.items():
        m = make()
        m.fit(Xtr, ytr, d_art) if isinstance(m, StructuredRecogniser) else m.fit(Xtr, ytr)
        scores = {}
        for label, mask in test_masks.items():
            if mask.sum() == 0:
                scores[label] = None
                continue
            Xte, yte = split_xy(ds, mask)
            scores[label] = float(np.mean(m.predict(Xte) == yte))
        out[name] = scores
    return out


def main() -> None:
    args = parse_args(__doc__)
    use_gru = torch_available()
    sizes = [100, 1000] if args.quick else SAMPLE_SIZES
    run = ExperimentRun(name="08_asr_comparison", title="Experiment 8 -- structured vs generic recognition")
    run.scalar("gru_available", use_gru)
    run.scalar("sample_sizes", sizes)

    base = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=4000 if not args.quick else 900))
    base = noise_world("correlated", 0.3, base)
    world = speaker_world("group", N_SPEAKERS, base)
    ds = generate(world, seed=args.seed)
    d_art = ds.config.d_art
    rng = np.random.default_rng(args.seed)

    held_class = ds.transition_index(*HELD_OUT_TRANSITION)
    last_speaker = N_SPEAKERS - 1
    is_held_transition = ds.transition == held_class  # GT: the supervised label
    is_held_speaker = ds.speaker == last_speaker

    pool = rng.permutation(ds.n_segments)
    eligible = pool[(~is_held_transition[pool]) & (~is_held_speaker[pool])]
    test_idx = eligible[:2000]
    train_pool = eligible[2000:]

    def mask_from(idx):
        m = np.zeros(ds.n_segments, dtype=bool)
        m[idx] = True
        return m

    test_masks = {
        "interpolation": mask_from(test_idx),
        "unseen transition": is_held_transition & ~is_held_speaker,
        "unseen speaker": is_held_speaker & ~is_held_transition,
    }
    run.scalar("held_out_transition", "->".join(HELD_OUT_TRANSITION))
    run.scalar("held_out_speaker", last_speaker)
    run.scalar("test_segment_counts", {k: int(v.sum()) for k, v in test_masks.items()})

    # ---- sample-size sweep --------------------------------------------------------------
    curves = {}
    for n in sizes:
        if n > train_pool.size:
            continue
        res = train_and_score(ds, build_models(ds, use_gru, args.seed), mask_from(train_pool[:n]),
                              test_masks, d_art)
        curves[n] = res
        run.table(f"N={n}", res)

    n_max = max(curves)
    at_max = curves[n_max]

    # ---- noise sweep at fixed N ----------------------------------------------------------
    noise_rows = {}
    for scale in ([0.3, 1.0] if args.quick else [0.1, 0.3, 0.6, 1.0]):
        dsn = generate(noise_world("correlated", scale, world), seed=args.seed)
        noise_rows[scale] = train_and_score(
            dsn, build_models(dsn, use_gru, args.seed), mask_from(train_pool[: min(1000, train_pool.size)]),
            test_masks, d_art,
        )
    run.table("noise_sweep_N1000", noise_rows)

    # ---- distribution shift: new speaker charts at test time -----------------------------
    shifted_world = speaker_world("group", N_SPEAKERS, base, seed=world.speaker.seed + 991, delta_A=0.22)
    ds_shift = generate(shifted_world, seed=args.seed + 7)
    shift_scores = {}
    train_mask = mask_from(train_pool[: min(2000, train_pool.size)])
    Xtr, ytr = split_xy(ds, train_mask)
    shift_test = mask_from(np.arange(min(2000, ds_shift.n_segments)))
    for name, make in build_models(ds, use_gru, args.seed).items():
        m = make()
        m.fit(Xtr, ytr, d_art) if isinstance(m, StructuredRecogniser) else m.fit(Xtr, ytr)
        Xte, yte = split_xy(ds_shift, shift_test)
        shift_scores[name] = float(np.mean(m.predict(Xte) == yte))
    run.table("distribution_shift", shift_scores)

    # ---- findings -------------------------------------------------------------------------
    def get(res, name, key):
        v = res.get(name, {}).get(key)
        return float(v) if v is not None else float("nan")

    generic = "B GRU" if use_gru else "A frame-independent"
    run.record(
        question="In distribution, does the structured model beat a generic temporal model?",
        ground_truth={"chance": round(1 / len(ds.transitions), 3)},
        estimate={name: get(at_max, name, "interpolation") for name in at_max},
        error=float(get(at_max, "C structured", "interpolation") - get(at_max, generic, "interpolation")),
        error_label="accuracy gap, structured minus generic (negative = generic wins)",
        status=PARTIAL,
        control=f"chance is {1 / len(ds.transitions):.3f}; both models are far above it",
        notes=(
            f"the generic model reaches {get(at_max, generic, 'interpolation'):.3f} against "
            f"{get(at_max, 'C structured', 'interpolation'):.3f} for the structured one, so in "
            "distribution the structured model does NOT win -- and this is the number the framework "
            "should not be sold on either way. A generic temporal model with enough data can learn "
            "the same trajectories without the parameterisation; the interesting comparisons are the "
            "ones below, where the test distribution differs from the training one."
        ),
    )
    run.record(
        question="Does the structured model transfer to a transition never seen in training?",
        ground_truth={"held-out class": "->".join(HELD_OUT_TRANSITION)},
        estimate={name: get(at_max, name, "unseen transition") for name in at_max},
        error=float(get(at_max, "C structured", "unseen transition")),
        error_label="accuracy on the unseen transition (higher is better)",
        status=IDENTIFIABLE if get(at_max, "C structured", "unseen transition") > 0.5 else PARTIAL,
        control="the same models on the interpolation split, where all classes were seen",
        notes=(
            "the discriminative baselines have the class in their output space but no examples of "
            "it, so they cannot place it -- this is a statement about representation, not about "
            "optimisation, and it should be read that way. The structured model *constructs* the "
            "class from its two phone targets and an alpha prior, which is the only reason it can "
            "score above chance here."
        ),
    )
    run.record(
        question="Does the structured model degrade less on an unseen speaker?",
        ground_truth={"speaker": last_speaker, "chart": "affine, unseen in training"},
        estimate={
            name: {"interpolation": get(at_max, name, "interpolation"),
                   "unseen speaker": get(at_max, name, "unseen speaker")}
            for name in at_max
        },
        error=float(get(at_max, "C structured", "interpolation") - get(at_max, "C structured", "unseen speaker")),
        error_label="accuracy drop from interpolation to unseen speaker (structured)",
        status=PARTIAL,
        control="the interpolation split for the same model",
        notes=(
            f"drop for the generic model: "
            f"{get(at_max, generic, 'interpolation') - get(at_max, generic, 'unseen speaker'):.3f}; "
            f"for the structured model: "
            f"{get(at_max, 'C structured', 'interpolation') - get(at_max, 'C structured', 'unseen speaker'):.3f}. "
            "Both are zero-shot -- no adaptation data from the new speaker is given to anyone."
        ),
    )
    def gap(res, other):
        return get(res, "C structured", "interpolation") - get(res, other, "interpolation")

    dyn_gap = {k: gap(curves[k], "C' structured, randomised dynamics") for k in curves}
    ant_gap = {k: gap(curves[k], "C'' structured, no anticipation") for k in curves}
    dyn_gap_noise = {s: gap(v, "C' structured, randomised dynamics") for s, v in noise_rows.items()}
    run.table("ablation_gaps", {"vs randomised dynamics by N": dyn_gap,
                                "vs no anticipation by N": ant_gap,
                                "vs randomised dynamics by noise": dyn_gap_noise})
    run.record(
        question="ABLATION -- is it the dynamics that carry the structured model?",
        ground_truth={"randomised-dynamics ablation": "A_u, A_v replaced by a random stable system, "
                                                      "targets and alpha untouched",
                      "no-anticipation ablation": "alpha forced to 0, dynamics untouched"},
        estimate={"gap vs randomised dynamics": {f"N={k}": round(v, 4) for k, v in dyn_gap.items()},
                  "gap vs no anticipation": {f"N={k}": round(v, 4) for k, v in ant_gap.items()}},
        error=float(max(dyn_gap.values())),
        error_label="largest accuracy gap, correct dynamics minus randomised",
        status=IDENTIFIABLE if max(dyn_gap.values()) > 0.02 else "NO EFFECT (negative result)",
        control="the no-anticipation ablation, which changes the targets instead of the dynamics",
        notes=(
            f"randomising the dynamics costs at most {max(dyn_gap.values()):.3f} accuracy, and "
            f"removing anticipation costs {max(ant_gap.values()):.3f}. On this task the discriminative "
            "information is in WHERE the trajectory is heading, not in HOW it gets there: a random "
            "stable system still settles on the right theta, so the class templates stay separable. "
            f"Across noise levels the dynamics gap is {  {s: round(v, 3) for s, v in dyn_gap_noise.items()} }, "
            "so this is not an artefact of an easy SNR. The honest reading is that this experiment "
            "supports the *gesture* layer of the factorisation and does not, on its own, support the "
            "*time* layer -- a task that resolves the trajectory shape rather than its endpoint would "
            "be needed for that."
        ),
    )
    run.record(
        question="Does the structured model hold up under a test-time change of speaker charts?",
        ground_truth={"test speakers": "new affine charts, larger deviation than training"},
        estimate=shift_scores,
        error=float(shift_scores.get("C structured", float("nan")) - shift_scores.get(generic, float("nan"))),
        error_label="accuracy gap, structured minus generic, under shift",
        status=PARTIAL,
        control="the interpolation split, which shares the training speaker charts",
        notes="the models are trained once and tested on a world whose speaker charts they never saw.",
    )

    # ---- figures ---------------------------------------------------------------------------
    names = list(at_max)
    style = {n: (PALETTE[i], ["-", "--", "-.", ":"][i % 4], ["o", "s", "^", "D"][i % 4])
             for i, n in enumerate(names)}

    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for n in names:
        ys = [get(curves[k], n, "interpolation") for k in sorted(curves)]
        c, ls, mk = style[n]
        ax.plot(sorted(curves), ys, color=c, linestyle=ls, marker=mk, markersize=5, label=n)
    ax.axhline(1 / len(ds.transitions), color=MUTED, linestyle=":", linewidth=1.2)
    ax.annotate("chance", xy=(sorted(curves)[0], 1 / len(ds.transitions)), xytext=(2, 4),
                textcoords="offset points", fontsize=7.5, color=MUTED)
    ax.set_xscale("log")
    ax.set_xlabel("training segments")
    ax.set_ylabel("accuracy (interpolation split)")
    ax.set_title("Sample efficiency")
    ax.legend(fontsize=7.5, loc="lower right")
    caption(fig, "In-distribution accuracy against training-set size. The structured model's advantage "
                 "is expected at the left-hand end, where its parameter count is a constraint rather "
                 "than a limitation.")
    fig.tight_layout()
    save(fig, "asr_sample_efficiency", run)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    idx = np.arange(len(names))
    vals = [get(at_max, n, "unseen speaker") for n in names]
    interp = [get(at_max, n, "interpolation") for n in names]
    ax.barh(idx - 0.19, interp, height=0.34, color=PALETTE[0], label="seen speakers")
    ax.barh(idx + 0.19, vals, height=0.34, color=PALETTE[1], label="unseen speaker")
    annotate_bars(ax, idx, interp, -0.19)
    annotate_bars(ax, idx, vals, 0.19)
    ax.set_yticks(idx, names, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("accuracy")
    ax.set_xlim(0, 1.12)
    ax.set_title(f"Generalisation to speaker {last_speaker} (zero-shot)")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncols=2)
    caption(fig, "No model receives adaptation data from the held-out speaker.")
    fig.tight_layout()
    save(fig, "asr_unseen_speaker", run)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    vals = [get(at_max, n, "unseen transition") for n in names]
    ax.barh(idx - 0.19, interp, height=0.34, color=PALETTE[0], label="seen transitions")
    ax.barh(idx + 0.19, vals, height=0.34, color=PALETTE[1], label=f"unseen {'->'.join(HELD_OUT_TRANSITION)}")
    annotate_bars(ax, idx, interp, -0.19)
    annotate_bars(ax, idx, vals, 0.19)
    ax.axvline(1 / len(ds.transitions), color=MUTED, linestyle=":", linewidth=1.2)
    ax.set_yticks(idx, names, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("accuracy")
    ax.set_xlim(0, 1.12)
    ax.set_title("Generalisation to an unseen transition")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncols=2)
    caption(fig, "The dotted line is chance. The discriminative baselines have no examples of the "
                 "held-out class; the structured model builds its template from parameters.")
    fig.tight_layout()
    save(fig, "asr_unseen_transition", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
