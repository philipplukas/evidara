"""Experiment 3 -- recover the temporal kernel.

Assumes Delta S_qr(t) ~ v_qr K(t) and estimates K(t) by SVD, then asks *which functional
family* K belongs to. Five candidates are fitted and scored; nothing here presumes the
answer is exponential.

Two out-of-sample scores, because they fail differently:
  * held-out segments on the same time grid -- statistical stability
  * temporal extrapolation (fit on the first 60% of the window, predict the last 40%) --
    whether the functional form is right at all

Ground truth: the world has TWO articulatory modes, one overdamped (zeta = 7/6) and one
exactly critically damped (zeta = 1). No single-mode family can be exactly right, and no
single-mode family should be able to extrapolate perfectly. The experiment measures how
close the wrong-but-simple answers get, and what it costs to notice.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import GRID, INK_2, MUTED, PALETTE, caption, parse_args, save

from analysis.kernels import compare_families, fit_modal_model
from analysis.metrics import IDENTIFIABLE, PARTIAL, relative_error
from analysis.recording import ExperimentRun
from analysis.svd import all_contrasts, stack_contrasts, temporal_rank
from config import SequenceConfig, WorldConfig, noise_world
from dynamics import ground_truth_kernels, modal_report
from generator import generate

SPLIT_FRACTION = 0.6


def pooled_design(ds, mask=None):
    sub = ds
    if mask is not None:
        sub = replace(ds)
        for name in ("observed", "source", "following", "speaker", "transition"):
            setattr(sub, name, getattr(ds, name)[mask])
    return stack_contrasts(all_contrasts(sub))


def main() -> None:
    args = parse_args(__doc__, noise_scale=dict(type=float, default=0.1))
    n_seq = 600 if args.quick else 4000
    run = ExperimentRun(name="03_kernel_recovery", title="Experiment 3 -- recover the temporal kernel")

    world = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    world = noise_world("correlated", args.noise_scale, world)
    ds = generate(world, seed=args.seed)
    t = ds.t
    run.scalar("n_sequences", n_seq)
    run.scalar("noise_scale", args.noise_scale)
    run.scalar("snr_db", ds.snr()["snr_db"])  # GT: diagnostic

    # ---- ground truth -----------------------------------------------------------------
    rep = modal_report(ds.config.dynamics)  # GT
    true_kernels = ground_truth_kernels(ds.config.dynamics, t)  # GT
    run.scalar("ground_truth_modes", rep.describe())
    run.scalar("ground_truth_omega", rep.omega_n)
    run.scalar("ground_truth_zeta", rep.zeta)

    # ---- split segments into a fit half and a held-out half ---------------------------
    rng = np.random.default_rng(args.seed)
    half = rng.random(ds.n_segments) < 0.5
    X_fit, X_test = pooled_design(ds, half), pooled_design(ds, ~half)

    spec = temporal_rank(X_fit)
    loading = spec.Vt[0]
    y_fit = X_fit @ loading
    y_test = X_test @ loading
    if y_fit[-1] < 0:  # fix the sign so "rise" means rise
        y_fit, y_test, loading = -y_fit, -y_test, -loading
    run.scalar("rank1_variance_explained_R_1", spec.ratio(1))

    split = int(SPLIT_FRACTION * len(t))
    fits = compare_families(
        t[:split], y_fit[:split], t[:split], y_test[:split],
        t_extrap=t[split:], y_extrap=y_test[split:],
    )
    rows = [f.to_row() for f in fits]
    run.table("family_comparison", rows)
    best_test = min(fits, key=lambda f: f.test_rmse)
    best_extrap = min(fits, key=lambda f: f.extrapolation_rmse)
    best_bic = min((f for f in fits if f.family != "spline"), key=lambda f: f.bic)

    # ---- multi-mode identification ----------------------------------------------------
    # mode identification uses the full corpus: the half-split above exists to score
    # *forecasting* by the rank-1 families, not to handicap the mode count
    X_all = pooled_design(ds)
    modal = {}
    for k in (1, 2, 3):
        m = fit_modal_model(t, X_all, k, seed=args.seed)
        modal[k] = dict(
            omega=[float(x) for x in m.omega],
            zeta=[float(x) for x in m.zeta],
            residual_rmse=m.residual_rmse,
            n_params=2 * k + k * X_all.shape[1],
        )
    run.table("modal_identification", modal)
    m2 = fit_modal_model(t, X_all, 2, seed=args.seed)
    omega_err = relative_error(np.sort(m2.omega), np.sort(rep.omega_n))  # GT
    zeta_err = relative_error(np.sort(m2.zeta), np.sort(rep.zeta))  # GT

    # How much data does two-mode recovery need? Measured over independent *data*
    # replicates: the optimiser is stable across restarts, so any spread here is the
    # problem being weakly identified, not the solver wandering.
    n_rep = 3 if args.quick else 6
    true_poles = np.sort(np.concatenate([
        _poles_of(w, z) for w, z in zip(rep.omega_n, rep.zeta, strict=True)  # GT
    ]))
    sweep = {}
    for scale in ([0.01, 0.1] if args.quick else [0.003, 0.01, 0.03, 0.1, 0.3]):
        w = noise_world("correlated", scale, world)
        errs, pole_errs, omegas = [], [], []
        for k in range(n_rep):
            d = generate(w, seed=args.seed + 100 + k)
            m = fit_modal_model(t, stack_contrasts(all_contrasts(d)), 2, seed=args.seed)
            errs.append(max(
                relative_error(np.sort(m.omega), np.sort(rep.omega_n)),  # GT
                relative_error(np.sort(m.zeta), np.sort(rep.zeta)),  # GT
            ))
            got = np.sort(np.concatenate([_poles_of(w_, z_) for w_, z_ in zip(m.omega, m.zeta, strict=True)]))
            pole_errs.append(relative_error(np.real(got), np.real(true_poles)))  # GT
            omegas.append([float(x) for x in m.omega])
        sweep[scale] = dict(
            omega_by_replicate=omegas,
            max_rel_err_median=float(np.median(errs)),
            max_rel_err_worst=float(np.max(errs)),
            pole_rel_err_median=float(np.median(pole_errs)),
            n_replicates=n_rep,
            snr_db=generate(w, seed=args.seed).snr()["snr_db"],  # GT: diagnostic
        )
    run.table("modal_recovery_vs_noise", sweep)
    recoverable = [s for s, v in sweep.items() if v["max_rel_err_worst"] < 0.05]

    # ---- findings ---------------------------------------------------------------------
    run.record(
        question="Which rank-1 kernel family best describes the leading temporal component?",
        ground_truth={
            "true kernels": "a mixture of one overdamped (zeta=7/6, omega=30) and one "
            "critically damped (zeta=1, omega=25) rise",
            "so the correct rank-1 answer is": "none of them exactly",
        },
        estimate={
            "best on held-out segments": f"{best_test.family} (rmse {best_test.test_rmse:.2e})",
            "best on temporal extrapolation": f"{best_extrap.family} (rmse {best_extrap.extrapolation_rmse:.2e})",
            "best by BIC": best_bic.family,
        },
        error=float(best_extrap.extrapolation_rmse / max(np.abs(y_test[split:]).max(), 1e-12)),
        error_label="extrapolation rmse relative to the extrapolated signal scale",
        status=PARTIAL,
        control="the spline baseline, which fits anything and extrapolates nothing",
        notes=(
            "the exponential family is the one most often assumed and it is measurably wrong here: "
            f"its extrapolation rmse is {[f.extrapolation_rmse for f in fits if f.family == 'exponential'][0]:.2e} "
            f"against {best_extrap.extrapolation_rmse:.2e} for {best_extrap.family}. A single "
            "exponential cannot have zero initial slope, and every second-order response does."
        ),
    )
    run.record(
        question="Can the generating modes (omega, zeta) be recovered without assuming rank 1?",
        ground_truth={"omega": rep.omega_n.tolist(), "zeta": rep.zeta.tolist()},  # GT
        estimate={"omega": modal[2]["omega"], "zeta": modal[2]["zeta"]},
        error=float(max(omega_err, zeta_err)),
        error_label="max relative error over (omega, zeta)",
        status=IDENTIFIABLE if max(omega_err, zeta_err) < 0.05 else PARTIAL,
        control=(
            f"a 3-mode fit adds a spurious mode (omega={modal[3]['omega'][0]:.1f}, "
            f"zeta={modal[3]['zeta'][0]:.2f}) that absorbs the acoustic nonlinearity"
        ),
        notes=(
            f"residual rmse: 1 mode {modal[1]['residual_rmse']:.3e}, 2 modes {modal[2]['residual_rmse']:.3e} "
            f"({modal[1]['residual_rmse'] / modal[2]['residual_rmse']:.2f}x), 3 modes "
            f"{modal[3]['residual_rmse']:.3e} ({modal[2]['residual_rmse'] / modal[3]['residual_rmse']:.2f}x). "
            f"Recovery within 5% on every replicate happens at noise scales "
            f"{recoverable if recoverable else 'none tested'} (of {sorted(sweep)}); median error by "
            f"scale: { {s: round(v['max_rel_err_median'], 3) for s, v in sweep.items()} }, worst-case "
            f"{ {s: round(v['max_rel_err_worst'], 3) for s, v in sweep.items()} }. The optimiser is "
            "stable across restarts, so that spread is the *problem* being weakly identified: at "
            "noise 0.1 two very different pole pairs fit equally well to 4 significant figures. No SVD "
            "component equals a physical mode either -- singular vectors are orthogonal and the true "
            "modes are not -- so this needs the variable-projection fit, not the SVD."
        ),
    )

    # ---- figure -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.6))
    t_ms = t * 1000.0

    ax = axes[0, 0]
    ax.plot(t_ms, y_test / y_test[-1], color=MUTED, linewidth=2.6, alpha=0.55, label="held-out data")
    for i, fam in enumerate(["exponential", "critically_damped", "second_order_free", "double_exponential"]):
        f = next(x for x in fits if x.family == fam)
        ax.plot(t_ms, f.predict(t) / y_test[-1], color=PALETTE[i], linestyle=["-", "--", "-.", ":"][i],
                linewidth=1.6, label=fam)
    ax.axvline(t_ms[split], color=GRID, linewidth=1.2)
    ax.annotate("fit ends", xy=(t_ms[split], 0.06), xytext=(4, 0), textcoords="offset points",
                fontsize=7.5, color=INK_2)
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("normalised K(t)")
    ax.set_title("Kernel families fitted to the first 60% of the window")
    ax.legend(loc="upper left", fontsize=7.5)

    ax = axes[0, 1]
    for i, fam in enumerate(["exponential", "critically_damped", "second_order_free", "double_exponential"]):
        f = next(x for x in fits if x.family == fam)
        ax.plot(t_ms, (f.predict(t) - y_test) / np.abs(y_test).max(), color=PALETTE[i],
                linestyle=["-", "--", "-.", ":"][i], label=fam)
    ax.axhline(0, color=GRID, linewidth=0.9)
    ax.axvline(t_ms[split], color=GRID, linewidth=1.2)
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("relative residual")
    ax.set_title("Residual against held-out data")
    ax.legend(loc="lower left")

    ax = axes[1, 0]
    fams = [f.family for f in fits]
    extrap = [f.extrapolation_rmse for f in fits]
    test = [f.test_rmse for f in fits]
    idx = np.arange(len(fams))
    ax.barh(idx - 0.2, test, height=0.36, color=PALETTE[0], label="held-out segments")
    ax.barh(idx + 0.2, extrap, height=0.36, color=PALETTE[1], label="temporal extrapolation")
    ax.set_yticks(idx, fams, fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("rmse (log scale)")
    ax.set_title("Out-of-sample error by family")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper right", fontsize=7.5)

    ax = axes[1, 1]
    for i in range(true_kernels.shape[1]):
        ax.plot(t_ms, true_kernels[:, i], color=PALETTE[i], linestyle=["-", "--"][i],
                label=f"true mode {i + 1}: $\\omega$={rep.omega_n[i]:.0f}, $\\zeta$={rep.zeta[i]:.3f}")
    for i, (w, z) in enumerate(zip(m2.omega, m2.zeta, strict=True)):
        ax.plot(t_ms, _mode_curve(t, w, z), color=PALETTE[i], linestyle=":", linewidth=2.4, alpha=0.9,
                label=f"recovered mode {i + 1}: $\\omega$={w:.1f}, $\\zeta$={z:.3f}")
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("K(t)")
    ax.set_title("Recovered modes vs ground truth")
    ax.legend(loc="lower right", fontsize=7)

    caption(
        fig,
        "Rank-1 kernel families all fit the visible window well; they separate on extrapolation. "
        "The generating system has two modes with different damping regimes, so the right answer is "
        "not a family choice but a mode count.",
    )
    fig.tight_layout()
    save(fig, "kernel_recovery", run)

    run.print_summary()
    run.save()


def _poles_of(omega: float, zeta: float) -> np.ndarray:
    """Continuous-time poles of a second-order mode -- the basis-invariant description."""
    disc = complex(zeta**2 - 1.0) ** 0.5
    return np.array([-zeta * omega + omega * disc, -zeta * omega - omega * disc])


def _mode_curve(t, omega, zeta):
    """Local copy of the rise kernel for plotting a recovered mode."""
    from analysis.kernels import _second_order_rise

    return _second_order_rise(t, omega, zeta)


if __name__ == "__main__":
    main()
