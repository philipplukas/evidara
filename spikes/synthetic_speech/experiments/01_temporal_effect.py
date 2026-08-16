"""Experiment 1 -- is there a temporal effect at all?

Compares E[S(t) | A -> B] against E[S(t) | A -> C] and asks whether the difference is
distinguishable from zero, with a bootstrap over segments.

Four conditions, and the controls matter more than the positive result:

  III transition   the hypothesis: alpha depends on the transition
  II  shared       anticipation exists but is the same for every transition
  I   static       alpha = 0 with segments reset -- the trajectory is *constant*, so
                   Delta S = 0 trivially
  I   dynamic      alpha = 0 with the state carried across segments -- the trajectory
                   moves a lot, and Delta S is *still* exactly 0. This is the control
                   that matters: it rules out "any moving signal produces a contrast".
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import INK_2, MUTED, PALETTE, caption, ms, parse_args, save, zero_line

from analysis.identifiability import permutation_test_mean_trajectory
from analysis.metrics import IDENTIFIABLE, NON_IDENTIFIABLE
from analysis.recording import ExperimentRun
from analysis.svd import bootstrap_contrast_ci, contrast, simultaneous_band
from config import SequenceConfig, WorldConfig, condition_world, noise_world
from generator import generate

DIM_LABELS = ["S1", "S2", "S3"]


def build_conditions(n_seq: int, noise_scale: float):
    base = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    base = noise_world("correlated", noise_scale, base)
    static_control = condition_world("none", base)
    dynamic_control = replace(
        static_control, sequence=replace(static_control.sequence, initial_condition="continue")
    )
    return [
        ("III transition-dependent", condition_world("transition", base)),
        ("II shared anticipation", condition_world("shared", base)),
        ("I no anticipation (static)", static_control),
        ("I no anticipation (dynamic)", dynamic_control),
    ]


def main() -> None:
    args = parse_args(__doc__, noise_scale=dict(type=float, default=0.3))
    n_seq = 300 if args.quick else 2000
    run = ExperimentRun(name="01_temporal_effect", title="Experiment 1 -- is there a temporal effect?")

    conditions = build_conditions(n_seq, args.noise_scale)
    datasets = {name: generate(w, seed=args.seed) for name, w in conditions}
    results = {}
    n_boot = 200 if args.quick else 600
    for name, ds in datasets.items():
        point, lo_pw, hi_pw = bootstrap_contrast_ci(ds, "A", "B", "C", n_boot=n_boot, seed=args.seed)
        _, lo, hi, crit = simultaneous_band(ds, "A", "B", "C", n_boot=n_boot, seed=args.seed)
        c = contrast(ds, "A", "B", "C")
        # a permutation test on the B/C label is the exact null here: under no
        # anticipation the two sets of segments are genuinely exchangeable
        perm = permutation_test_mean_trajectory(
            ds.observed[ds.mask("A", "B")], ds.observed[ds.mask("A", "C")],
            n_perm=200 if args.quick else 500, seed=args.seed,
        )
        any_frame = np.any((lo > 0) | (hi < 0), axis=1)
        first = int(np.argmax(any_frame)) if any_frame.any() else -1
        results[name] = dict(
            point=point, lo=lo, hi=hi, lo_pw=lo_pw, hi_pw=hi_pw, contrast=c, crit=crit,
            peak=c.peak_abs(), peak_z=float(np.max(np.abs(c.z()))),
            frac_frames_significant=float(any_frame.mean()),
            first_significant_ms=float(ds.t[first] * 1000.0) if first >= 0 else None,
            perm_statistic=perm.statistic, perm_p=perm.p_value,
            perm_null_q95=perm.null_quantile_95,
            n=(c.n1, c.n2),
        )

    ds0 = datasets["III transition-dependent"]
    run.scalar("n_sequences", n_seq)
    run.scalar("noise_scale", args.noise_scale)
    run.scalar("snr", ds0.snr())  # GT: diagnostic only, reported alongside every result
    run.scalar("segments_per_transition", results["III transition-dependent"]["n"])
    for name, res in results.items():
        run.table(name, {k: v for k, v in res.items()
                         if k not in ("point", "lo", "hi", "lo_pw", "hi_pw", "contrast")})

    # ---- ground truth -----------------------------------------------------------------
    d_theta = ds0.config.theta("A", "B") - ds0.config.theta("A", "C")  # GT
    alpha_ab = ds0.config.anticipation.alpha("A", "B")  # GT
    alpha_ac = ds0.config.anticipation.alpha("A", "C")  # GT
    j = ds0.phi.Dphi(ds0.config.articulatory.target("A"))  # GT: local acoustic sensitivity at u_A
    predicted_peak = float(np.max(np.abs(j @ d_theta)))
    run.scalar("ground_truth_alpha_AB_AC", [alpha_ab, alpha_ac])
    run.scalar("ground_truth_delta_theta", d_theta)
    run.scalar("predicted_asymptotic_peak_|DPhi . dtheta|", predicted_peak)

    # ---- findings ---------------------------------------------------------------------
    hyp = results["III transition-dependent"]
    run.record(
        question="Does a transition-dependent target produce a measurable acoustic contrast?",
        ground_truth={"alpha_AB": alpha_ab, "alpha_AC": alpha_ac, "delta_theta": d_theta.tolist()},
        estimate={"peak_|dS|": hyp["peak"], "peak_z": hyp["peak_z"]},
        error=abs(hyp["peak"] - predicted_peak) / predicted_peak,
        error_label="relative error of peak vs DPhi . dtheta",
        status=IDENTIFIABLE,
        control="condition I (dynamic): peak |dS| = "
        f"{results['I no anticipation (dynamic)']['peak']:.4f} with a moving trajectory",
        notes=(
            f"permutation p = {hyp['perm_p']:.4f}; the sup-t band (simultaneous over all 201 "
            f"frames and 3 dimensions) excludes zero on {hyp['frac_frames_significant']:.0%} of "
            f"frames, first at {hyp['first_significant_ms']:.0f} ms -- long before the target is reached"
        ),
    )
    for label in ("I no anticipation (static)", "I no anticipation (dynamic)"):
        res = results[label]
        run.record(
            question=f"Control -- does the contrast vanish under {label}?",
            ground_truth={"delta_theta": [0.0, 0.0]},
            estimate={"peak_|dS|": res["peak"], "peak_z": res["peak_z"]},
            error=res["peak"] / hyp["peak"],
            error_label="peak relative to the hypothesis condition",
            status="NO EFFECT (as designed)" if res["perm_p"] > 0.05 else "UNEXPECTED SIGNAL",
            control="this is the control",
            notes=(
                f"permutation p = {res['perm_p']:.3f}; sup-t band flags "
                f"{res['frac_frames_significant']:.1%} of frames. The residual peak is the noise "
                f"floor: max of {ds0.n_frames * 3} correlated mean-differences at this sample size."
            ),
        )
    shared = results["II shared anticipation"]
    run.record(
        question="Can a shared-alpha world be told apart from a transition-dependent one by the contrast alone?",
        ground_truth={"alpha_shared": ds0.config.anticipation.shared_alpha},  # GT
        estimate={"peak_|dS| shared": shared["peak"], "peak_|dS| transition": hyp["peak"]},
        error=abs(shared["peak"] - hyp["peak"]) / hyp["peak"],
        error_label="relative peak difference",
        status="PARTIALLY IDENTIFIABLE",
        control="condition I",
        notes=(
            "a non-zero contrast proves anticipation, not transition-specific anticipation: "
            "condition II also produces one, because theta_qB and theta_qC differ whenever "
            "alpha > 0 even with alpha held constant"
        ),
    )

    # ---- figure -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 5.4), sharex=True)
    t = ms(ds0.t)
    rows = [("III transition-dependent", 0), ("I no anticipation (dynamic)", 1)]
    ylim = max(np.abs(results["III transition-dependent"]["hi"]).max(), 0.05) * 1.15
    _ = NON_IDENTIFIABLE
    for name, r in rows:
        res = results[name]
        for k in range(3):
            ax = axes[r, k]
            zero_line(ax)
            ax.fill_between(t, res["lo"][:, k], res["hi"][:, k], color=PALETTE[k], alpha=0.16, linewidth=0)
            ax.fill_between(t, res["lo_pw"][:, k], res["hi_pw"][:, k], color=PALETTE[k], alpha=0.3, linewidth=0)
            ax.plot(t, res["point"][:, k], color=PALETTE[k], linestyle=["-", "--", "-."][k], label=DIM_LABELS[k])
            ax.set_ylim(-ylim, ylim)
            if r == 0:
                ax.set_title(f"{DIM_LABELS[k]}")
            if r == 1:
                ax.set_xlabel("time within segment (ms)")
            if k == 0:
                ax.set_ylabel(f"{name}\nΔS(t)", fontsize=8)
            # no legend: one series per panel, and the column title already names it
    caption(
        fig,
        "ΔS(t) = E[S(t) | A→B] − E[S(t) | A→C]. Dark band: pointwise 95% bootstrap. Pale band: "
        "sup-t band with simultaneous coverage over all frames and dimensions. Top: "
        "transition-dependent anticipation. Bottom: the dynamic no-anticipation control — the "
        "trajectory moves throughout the segment, yet the contrast is zero by construction.",
    )
    fig.suptitle("Transition contrast under anticipation and under its control", y=1.0, fontsize=11)
    fig.tight_layout()
    save(fig, "temporal_effect", run)

    # summary panel across all four conditions
    fig2, ax = plt.subplots(figsize=(7.2, 3.2))
    names = list(results)
    peaks = [results[n]["peak"] for n in names]
    colors = [PALETTE[0], PALETTE[1], MUTED, MUTED]
    bars = ax.barh(range(len(names)), peaks, color=colors, height=0.55)
    ax.set_yticks(range(len(names)), names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("peak |ΔS(t)| over the segment")
    ax.grid(axis="y", visible=False)
    for b, n in zip(bars, names, strict=True):
        ax.annotate(
            f"{results[n]['peak']:.4f}  (z={results[n]['peak_z']:.1f})",
            xy=(b.get_width(), b.get_y() + b.get_height() / 2),
            xytext=(5, 0), textcoords="offset points", va="center", fontsize=8, color=INK_2,
        )
    ax.set_xlim(0, max(peaks) * 1.45)
    ax.set_title("Peak contrast by condition")
    caption(fig2, "Both no-anticipation controls sit at the noise floor; z is the peak standardised contrast.")
    fig2.tight_layout()
    save(fig2, "temporal_effect_conditions", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
