"""Experiment 5 -- recover the articulatory dynamics.

Given the ORACLE-inverted articulation, estimate

    u'' = A_u u + A_v u' + c_g   with   A_u = -M^-1 K,  A_v = -M^-1 C

and compare against ground truth. Three estimators are run side by side, because the
answer to "are the dynamics recoverable?" turns out to depend far more on the estimator
than on the data:

  accel        Savitzky-Golay smoothing, then regress the numerically estimated u''
               (the route the spec describes). Two derivatives.
  discrete     regress the one-step state map x_{k+1} on x_k, then A_c = log(A_d)/dt.
               One derivative.
  trajectory   fit the forward model to the trajectories by nonlinear least squares.
               No derivatives at all.

Every smoothing setting is swept and reported, since a single undocumented choice of
window and polynomial order can move the accel estimator's error by an order of magnitude.

Controls: a deliberately mis-specified first-order fit, and the noiseless limit, which
separates estimator bias from observation noise.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import GRID, MUTED, PALETTE, caption, parse_args, save

from analysis.identifiability import spectral_invariants
from analysis.metrics import IDENTIFIABLE, NON_IDENTIFIABLE, PARTIAL, relative_error
from analysis.recording import ExperimentRun
from analysis.system_id import (
    fit_discrete_state_space,
    fit_first_order_dynamics,
    fit_second_order_dynamics,
    fit_trajectory_second_order,
    invert_nonlinear,
    smooth_and_differentiate,
)
from config import SequenceConfig, WorldConfig, noise_world
from generator import generate

NOISE_SCALES = [0.001, 0.03, 0.1, 0.3, 1.0]
SMOOTHERS = [(21, 3), (41, 4), (61, 4), (81, 5)]
MARGIN = 25


def oracle_inverted_trajectories(ds):
    """Mean acoustic trajectory per transition, inverted with the true Phi (ORACLE)."""
    U, U0, thetas = [], [], []
    for q, r in ds.transitions:
        S = ds.observed[ds.mask(q, r)].mean(axis=0)
        u0 = ds.config.articulatory.target(q)
        U.append(invert_nonlinear(S, ds.phi.Phi, u0, ds.phi.Dphi))  # ORACLE: true acoustic map
        U0.append(u0)
        thetas.append(ds.config.theta(q, r))  # GT: scoring only
    return np.stack(U), np.stack(U0), np.stack(thetas)


def main() -> None:
    args = parse_args(__doc__)
    n_seq = 500 if args.quick else 4000
    run = ExperimentRun(name="05_dynamics_identification", title="Experiment 5 -- recover the dynamics")

    world = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    dt = world.grid.dt
    A_u_true = -np.linalg.inv(world.dynamics.M) @ world.dynamics.K  # GT
    A_v_true = -np.linalg.inv(world.dynamics.M) @ world.dynamics.C  # GT
    poles_true = spectral_invariants(A_u_true, A_v_true)
    run.scalar("n_sequences", n_seq)
    run.scalar("ground_truth_A_u", A_u_true)
    run.scalar("ground_truth_A_v", A_v_true)
    run.scalar("ground_truth_poles", [complex(z).real for z in poles_true])
    run.scalar("smoothing_swept", [f"window={w}, polyorder={p}" for w, p in SMOOTHERS])
    run.scalar("edge_margin_frames", MARGIN)

    results = {name: {} for name in ("accel", "discrete", "trajectory")}
    smoothing_sensitivity = {}
    first_order_r2 = {}

    for scale in NOISE_SCALES:
        ds = generate(noise_world("correlated", scale, world), seed=args.seed)
        U, U0, theta_true = oracle_inverted_trajectories(ds)
        n_g, T, d = U.shape
        group = np.repeat(np.arange(n_g), T - 2 * MARGIN)

        best = {"accel": None, "discrete": None}
        per_smoother = {}
        for win, poly in SMOOTHERS:
            u0s, u1s, u2s = smooth_and_differentiate(U, dt, window=win, polyorder=poly)
            uc, vc, ac = (a[:, MARGIN:-MARGIN] for a in (u0s, u1s, u2s))
            f_acc = fit_second_order_dynamics(uc, vc, ac, group)
            f_dis = fit_discrete_state_space(uc, vc, dt)
            e_acc = max(relative_error(f_acc.A_u, A_u_true), relative_error(f_acc.A_v, A_v_true))  # GT
            e_dis = max(relative_error(f_dis.A_u, A_u_true), relative_error(f_dis.A_v, A_v_true))  # GT
            per_smoother[f"{win}/{poly}"] = {"accel": e_acc, "discrete": e_dis}
            if best["accel"] is None or e_acc < best["accel"][0]:
                best["accel"] = (e_acc, f_acc, (win, poly))
            if best["discrete"] is None or e_dis < best["discrete"][0]:
                best["discrete"] = (e_dis, f_dis, (win, poly))
        smoothing_sensitivity[scale] = per_smoother

        f_traj = fit_trajectory_second_order(U, dt, U0)
        e_traj = max(relative_error(f_traj.A_u, A_u_true), relative_error(f_traj.A_v, A_v_true))  # GT

        acc_err, f_acc, acc_smoother = best["accel"]
        dis_err, f_dis, dis_smoother = best["discrete"]
        results["accel"][scale] = dict(
            A_u_err=relative_error(f_acc.A_u, A_u_true),  # GT
            A_v_err=relative_error(f_acc.A_v, A_v_true),  # GT
            theta_err=relative_error(f_acc.implied_targets(), theta_true),  # GT
            pole_err=relative_error(np.real(spectral_invariants(f_acc.A_u, f_acc.A_v)), np.real(poles_true)),  # GT
            best_smoother=f"{acc_smoother[0]}/{acc_smoother[1]}",
            worst_over_smoothers=max(v["accel"] for v in per_smoother.values()),
            r2=f_acc.r2,
        )
        results["discrete"][scale] = dict(
            A_u_err=relative_error(f_dis.A_u, A_u_true),  # GT
            A_v_err=relative_error(f_dis.A_v, A_v_true),  # GT
            theta_err=None,
            pole_err=relative_error(np.real(f_dis.poles()), np.real(poles_true)),  # GT
            best_smoother=f"{dis_smoother[0]}/{dis_smoother[1]}",
            worst_over_smoothers=max(v["discrete"] for v in per_smoother.values()),
            r2=f_dis.r2,
        )
        results["trajectory"][scale] = dict(
            A_u_err=relative_error(f_traj.A_u, A_u_true),  # GT
            A_v_err=relative_error(f_traj.A_v, A_v_true),  # GT
            theta_err=relative_error(f_traj.targets, theta_true),  # GT
            pole_err=relative_error(np.real(f_traj.poles()), np.real(poles_true)),  # GT
            best_smoother="none (no differentiation)",
            worst_over_smoothers=e_traj,
            residual_rmse=f_traj.residual_rmse,
        )

        # control: the wrong model order
        u0s, u1s, _ = smooth_and_differentiate(U, dt, window=41, polyorder=4)
        _, _, r2_first = fit_first_order_dynamics(
            u0s[:, MARGIN:-MARGIN], u1s[:, MARGIN:-MARGIN], group
        )
        first_order_r2[scale] = r2_first
        _ = acc_err, dis_err

    for name, rows in results.items():
        run.table(f"estimator_{name}", rows)
    run.table("smoothing_sensitivity", smoothing_sensitivity)
    run.table("control_first_order_r2", first_order_r2)

    # ---- findings ---------------------------------------------------------------------
    ref = 0.1
    traj, acc, dis = results["trajectory"][ref], results["accel"][ref], results["discrete"][ref]
    run.record(
        question="Are A_u = -M^-1 K and A_v = -M^-1 C recoverable from acoustics (with Phi known)?",
        ground_truth={"A_u": A_u_true.tolist(), "A_v": A_v_true.tolist()},
        estimate={
            "trajectory fit": {"A_u": traj["A_u_err"], "A_v": traj["A_v_err"]},
            "discrete state map": {"A_u": dis["A_u_err"], "A_v": dis["A_v_err"]},
            "acceleration regression": {"A_u": acc["A_u_err"], "A_v": acc["A_v_err"]},
        },
        error=float(max(traj["A_u_err"], traj["A_v_err"])),
        error_label="max relative error, trajectory fit at noise 0.1",
        status=IDENTIFIABLE if max(traj["A_u_err"], traj["A_v_err"]) < 0.05 else PARTIAL,
        control=f"noiseless limit: trajectory fit reaches {results['trajectory'][0.001]['A_u_err']:.1e}",
        notes=(
            "the dynamics are identifiable; the standard recipe is what fails. At noise 0.1 the "
            f"acceleration regression is off by {acc['A_u_err']:.0%} and the trajectory fit by "
            f"{traj['A_u_err']:.1%} on the same data. Each numerical derivative multiplies noise by "
            "~1/dt and biases the regression by errors-in-variables, so a method that never "
            "differentiates is not a refinement here -- it is the difference between an answer and no answer."
        ),
    )
    spread = {
        s: max(v["accel"] for v in smoothing_sensitivity[s].values())
        / max(min(v["accel"] for v in smoothing_sensitivity[s].values()), 1e-12)
        for s in NOISE_SCALES
    }
    run.record(
        question="How much does the smoothing choice move the acceleration-regression answer?",
        ground_truth={"A_u": A_u_true.tolist()},
        estimate={f"noise {s}": f"best {min(v['accel'] for v in smoothing_sensitivity[s].values()):.3f}, "
                               f"worst {max(v['accel'] for v in smoothing_sensitivity[s].values()):.3f}"
                  for s in NOISE_SCALES},
        error=float(max(spread.values())),
        error_label="worst/best ratio across the four smoothers",
        status=PARTIAL,
        control="the trajectory fit, which has no smoothing parameter at all",
        notes=(
            f"across Savitzky-Golay settings {[f'{w}/{p}' for w, p in SMOOTHERS]} the error varies by "
            f"up to {max(spread.values()):.1f}x. Reported numbers above use the *best* setting per "
            "noise level, which flatters the method; an honest single-shot user would have to pick "
            "blind. This is why the smoothing sweep is part of the result and not an appendix."
        ),
    )
    run.record(
        question="Are the transition targets theta recovered as a by-product?",
        ground_truth={"theta": "6 transition targets, from alpha and the phone targets"},
        estimate={"trajectory fit": traj["theta_err"], "acceleration regression": acc["theta_err"]},
        error=float(traj["theta_err"]),
        error_label="relative error at noise 0.1",
        status=IDENTIFIABLE if traj["theta_err"] < 0.05 else PARTIAL,
        control="the per-transition intercept is the only place theta can enter, so a single shared "
        "intercept would bias A_u -- that variant is not fitted here for exactly that reason",
        notes=(
            "theta is far better determined than A_u: it is a location parameter read off where the "
            "trajectory is heading, while A_u is a curvature parameter read off how fast it gets there."
        ),
    )
    run.record(
        question="Control -- does a first-order model fit the data?",
        ground_truth={"model order": 2},
        estimate={f"noise {s}": round(v, 4) for s, v in first_order_r2.items()},
        error=None,
        error_label="n/a (R^2 of the wrong model)",
        status=NON_IDENTIFIABLE,
        control="this is the control",
        notes=(
            f"a first-order law reaches R^2 = {first_order_r2[0.001]:.4f} in the noiseless limit. It is "
            "not a *bad* fit by R^2, which is the point: goodness of fit does not diagnose model order "
            "here. The residual poles do."
        ),
    )

    # ---- figure -----------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.7))

    ax = axes[0]
    for i, name in enumerate(("trajectory", "discrete", "accel")):
        ax.loglog(NOISE_SCALES, [results[name][s]["A_u_err"] for s in NOISE_SCALES],
                  color=PALETTE[i], linestyle=["-", "--", "-."][i], marker=["o", "s", "^"][i],
                  markersize=4, label=f"{name}: $A_u$")
    ax.axhline(0.05, color=MUTED, linestyle=":", linewidth=1.2)
    ax.annotate("5%", xy=(NOISE_SCALES[0], 0.05), xytext=(2, 3), textcoords="offset points",
                fontsize=7, color=MUTED)
    ax.set_xlabel("noise scale")
    ax.set_ylabel("relative error of $A_u$")
    ax.set_title("Three estimators, same data")
    ax.legend(fontsize=7, loc="lower right")

    ax = axes[1]
    labels = [f"{w}/{p}" for w, p in SMOOTHERS]
    for i, s in enumerate([0.03, 0.1, 0.3]):
        ax.semilogy(labels, [smoothing_sensitivity[s][k]["accel"] for k in labels],
                    color=PALETTE[i], linestyle=["-", "--", "-."][i], marker="o", markersize=4,
                    label=f"noise {s}")
    ax.set_xlabel("Savitzky-Golay window / polyorder")
    ax.set_ylabel("relative error of $A_u$")
    ax.set_title("Smoothing sensitivity (accel route)")
    ax.legend(fontsize=7)

    ax = axes[2]
    for i, name in enumerate(("trajectory", "discrete", "accel")):
        ax.loglog(NOISE_SCALES, [results[name][s]["pole_err"] for s in NOISE_SCALES],
                  color=PALETTE[i], linestyle=["-", "--", "-."][i], marker=["o", "s", "^"][i],
                  markersize=4, label=name)
    ax.set_xlabel("noise scale")
    ax.set_ylabel("relative error of the pole set")
    ax.set_title("Poles: the basis-invariant target")
    ax.legend(fontsize=7, loc="lower right")
    ax.axhline(0, color=GRID, linewidth=0.8)

    caption(
        fig,
        "The dynamics are identifiable in this world; whether you recover them depends on whether "
        "the estimator differentiates the data. The acceleration route also carries a smoothing "
        "knob that moves its answer by up to an order of magnitude.",
    )
    fig.tight_layout()
    save(fig, "dynamics_recovery", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
