"""Experiment 6 -- the identifiability test.

Two latent models related by a change of coordinates h(u) = P u + p:

    Phi_2 . h = Phi_1        (acoustics agree)
    h . F_1  = F_2 . h       (dynamics are conjugate)

Both worlds are generated and an acoustic-only estimator is asked to tell them apart.
It should not be able to -- but the test only means something if it *can* separate
worlds that genuinely differ, so a positive control (a world with different anticipation)
is run through the identical machinery.

What survives the transformation is then measured: the latent coordinates do not, the
poles of the dynamics do.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import MUTED, PALETTE, caption, parse_args, save

from analysis.identifiability import (
    latent_gap_report,
    permutation_test_mean_trajectory,
    spectral_invariants,
)
from analysis.metrics import IDENTIFIABLE, NON_IDENTIFIABLE, PARTIAL, relative_error
from analysis.recording import ExperimentRun
from analysis.system_id import fit_trajectory_second_order, invert_nonlinear
from config import SequenceConfig, WorldConfig, condition_world, noise_world
from generator import affine_twin_world, generate


def transition_conditioned_test(ds_a, ds_b, n_perm: int, seed: int, max_per_group: int = 800):
    """Permutation test on the *transition-conditioned* mean trajectories.

    Comparing marginal means would be the wrong statistic: two worlds can have different
    anticipation per transition and still agree on the average over transitions, because
    the alpha differences cancel. The corpus label is permuted within each transition and
    the statistic is the largest per-transition, per-frame mean difference.
    """
    rng = np.random.default_rng(seed)

    def stat(groups):
        return max(
            float(np.max(np.linalg.norm(a.mean(0) - b.mean(0), axis=-1))) for a, b in groups
        )

    real, pooled = [], []
    for q, r in ds_a.transitions:
        a = ds_a.observed[ds_a.mask(q, r)]
        b = ds_b.observed[ds_b.mask(q, r)]
        # cap the per-transition sample: the permutation cost is linear in it and the test
        # is already far above the power it needs at this size
        n = min(a.shape[0], b.shape[0], max_per_group)
        real.append((a[:n], b[:n]))
        pooled.append((np.concatenate([a[:n], b[:n]]), n))
    obs = stat(real)
    null = np.empty(n_perm)
    for i in range(n_perm):
        shuffled = []
        for pool, n in pooled:
            perm = rng.permutation(pool.shape[0])
            shuffled.append((pool[perm[:n]], pool[perm[n:]]))
        null[i] = stat(shuffled)
    return dict(
        statistic=obs,
        p_value=float((1.0 + np.sum(null >= obs)) / (1.0 + n_perm)),
        null_q95=float(np.quantile(null, 0.95)),
        distinguishable=bool((1.0 + np.sum(null >= obs)) / (1.0 + n_perm) < 0.05),
    )


def inverted(ds):
    """ORACLE inversion of the per-transition mean trajectories under that world's own Phi."""
    U, U0 = [], []
    for q, r in ds.transitions:
        S = ds.observed[ds.mask(q, r)].mean(axis=0)
        u0 = ds.config.articulatory.target(q)
        U.append(invert_nonlinear(S, ds.phi.Phi, u0, ds.phi.Dphi))  # ORACLE: each model's own map
        U0.append(u0)
    return np.stack(U), np.stack(U0)


def main() -> None:
    args = parse_args(__doc__)
    n_seq = 400 if args.quick else 2500
    n_perm = 200 if args.quick else 800
    run = ExperimentRun(name="06_identifiability", title="Experiment 6 -- the identifiability test")

    world = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    world = noise_world("correlated", 0.3, world)

    rng = np.random.default_rng(args.seed + 31)
    P = np.eye(2) + 0.4 * rng.normal(size=(2, 2))
    p = rng.normal(scale=0.25, size=2)
    twin_world, phi2, h = affine_twin_world(world, P, p)
    run.scalar("P", P)
    run.scalar("p", p)
    run.scalar("n_sequences", n_seq)

    # independent noise draws: the two corpora must be independent samples of whatever
    # distribution each world defines, not the same numbers twice
    ds1 = generate(world, seed=args.seed)
    ds2 = generate(twin_world, seed=args.seed + 1000, phi_override=phi2)
    ds_alt = generate(  # positive control: a genuinely different world
        condition_world("shared", world), seed=args.seed + 3000
    )

    # ---- exactness of the construction --------------------------------------------------
    u_probe = rng.uniform(-1.5, 1.5, size=(400, 2))
    compose_err = float(np.max(np.abs(phi2.Phi(h(u_probe)) - ds1.phi.Phi(u_probe))))  # GT: construction check
    per_transition_gap = float(np.max([
        np.max(np.abs(ds1.clean[ds1.mask(q, r)][0] - ds2.clean[ds2.mask(q, r)][0]))  # GT: construction check
        for q, r in ds1.transitions
    ]))
    run.scalar("max|Phi_2(h(u)) - Phi_1(u)|", compose_err)
    run.scalar("max|clean_1 - clean_2| per transition", per_transition_gap)

    # ---- can an acoustic-only test separate them? ---------------------------------------
    # A single permutation p-value is one draw from a distribution, so a lone p = 0.01 on a
    # pair that is identical by construction is a false positive waiting to be over-read.
    # Each comparison is therefore repeated over independent corpora and reported as a
    # rejection *rate*: the twin should reject at roughly the nominal 5%, the control always.
    n_rep = 5 if args.quick else 12
    tests = {}
    for label, builder in (
        ("twin (model 1 vs model 2)",
         lambda s: (generate(world, seed=s), generate(twin_world, seed=s + 1000, phi_override=phi2))),
        ("same world, different sample",
         lambda s: (generate(world, seed=s), generate(world, seed=s + 2000))),
        ("positive control (shared alpha)",
         lambda s: (generate(world, seed=s), generate(condition_world("shared", world), seed=s + 3000))),
    ):
        rows = [transition_conditioned_test(*builder(args.seed + k), n_perm, args.seed + k)
                for k in range(n_rep)]
        pv = np.array([r["p_value"] for r in rows])
        tests[label] = dict(
            median_p=float(np.median(pv)),
            min_p=float(pv.min()),
            rejection_rate_at_0_05=float(np.mean(pv < 0.05)),
            median_statistic=float(np.median([r["statistic"] for r in rows])),
            median_null_q95=float(np.median([r["null_q95"] for r in rows])),
            n_replicates=n_rep,
        )
    run.table("two_sample_tests", tests)
    # the marginal (transition-blind) statistic, kept to show why it is the wrong one
    marginal = permutation_test_mean_trajectory(
        ds1.observed[: ds_alt.n_segments], ds_alt.observed[: ds1.n_segments],
        n_perm=n_perm, seed=args.seed,
    )
    run.scalar("positive_control_marginal_test_p", marginal.p_value)

    # ---- what differs, and what survives ------------------------------------------------
    U1, U01 = inverted(ds1)
    U2, U02 = inverted(ds2)

    # The invariance claim is about the *models*, so it is measured in the low-noise limit
    # where estimator variance cannot be mistaken for a violation. The two-sample test above
    # stays at the working noise level, where it is a claim about finite samples.
    quiet, quiet_twin = noise_world("correlated", 0.01, world), noise_world("correlated", 0.01, twin_world)
    q1, q01 = inverted(generate(quiet, seed=args.seed))
    q2, q02 = inverted(generate(quiet_twin, seed=args.seed + 1000, phi_override=phi2))
    fit1 = fit_trajectory_second_order(q1, world.grid.dt, q01)
    fit2 = fit_trajectory_second_order(q2, twin_world.grid.dt, q02)
    poles1, poles2 = fit1.poles(), fit2.poles()

    gap = latent_gap_report(
        latent_1=U1.reshape(-1, 2),
        latent_2=U2.reshape(-1, 2),
        observable_1=np.stack([ds1.clean[ds1.mask(q, r)][0] for q, r in ds1.transitions]),  # GT
        observable_2=np.stack([ds2.clean[ds2.mask(q, r)][0] for q, r in ds2.transitions]),  # GT
        spectral=relative_error(np.real(poles1), np.real(poles2)),
        tol=1e-8,
    )
    run.scalar("latent_relative_gap", gap.latent_relative_gap)
    run.scalar("affine_reparam_residual", gap.affine_reparam_residual)
    run.scalar("recovered_poles_model_1", [complex(z).real for z in poles1])
    run.scalar("recovered_poles_model_2", [complex(z).real for z in poles2])
    run.scalar("A_u_model_1", fit1.A_u)
    run.scalar("A_u_model_2", fit2.A_u)
    run.scalar("A_u_relative_difference", relative_error(fit2.A_u, fit1.A_u))
    true_poles = spectral_invariants(
        -np.linalg.inv(world.dynamics.M) @ world.dynamics.K,  # GT
        -np.linalg.inv(world.dynamics.M) @ world.dynamics.C,  # GT
    )

    # ---- findings ------------------------------------------------------------------------
    twin_test = tests["twin (model 1 vs model 2)"]
    ctrl_test = tests["positive control (shared alpha)"]
    run.record(
        question="Can an acoustic-only estimator distinguish two models related by a latent change of coordinates?",
        ground_truth={"the two worlds are observationally identical by construction":
                      f"max|clean_1 - clean_2| = {per_transition_gap:.2e}"},
        estimate={"median permutation p": twin_test["median_p"],
                  "rejection rate at 0.05": twin_test["rejection_rate_at_0_05"],
                  "replicates": twin_test["n_replicates"]},
        error=per_transition_gap,
        error_label="max absolute difference of the clean acoustics",
        status=NON_IDENTIFIABLE,
        control=(
            f"positive control (shared-alpha world): rejects on "
            f"{ctrl_test['rejection_rate_at_0_05']:.0%} of replicates, median statistic "
            f"{ctrl_test['median_statistic']:.3f} vs null 95th pct {ctrl_test['median_null_q95']:.3f} "
            "-- the same test separates worlds that genuinely differ"
        ),
        notes=(
            f"the twin rejects on {twin_test['rejection_rate_at_0_05']:.0%} of replicates and the "
            f"same-world calibrator on {tests['same world, different sample']['rejection_rate_at_0_05']:.0%}, "
            "both at the nominal 5% level. The two worlds are not merely hard to tell apart; they are "
            "the same distribution. Any estimator that reports 'the' latent coordinates is reporting "
            "its own initialisation. Note also that the transition-*blind* version of this test has no "
            f"power at all against the positive control (p = {marginal.p_value:.2f}): conditioning on "
            "the transition is what makes the comparison informative."
        ),
    )
    run.record(
        question="Are the latent coordinates themselves recoverable?",
        ground_truth={"latent_2 = h(latent_1)": f"P = {np.round(P, 3).tolist()}, p = {np.round(p, 3).tolist()}"},
        estimate={"latent relative gap": gap.latent_relative_gap,
                  "residual after best affine reparam": gap.affine_reparam_residual},
        error=float(gap.latent_relative_gap),
        error_label="relative gap between the two latents",
        status=PARTIAL,
        control="the affine reparameterisation residual, which is the same quantity modulo h",
        notes=(
            f"the two latents differ by {gap.latent_relative_gap:.0%} and agree to "
            f"{gap.affine_reparam_residual:.2e} once an affine map is allowed. The recoverable object "
            "is the equivalence class (Phi, F) / coordinate changes -- Hypothesis 2, measured."
        ),
    )
    run.record(
        question="What IS invariant -- do the two models share a recoverable quantity?",
        ground_truth={"true poles": [round(float(np.real(z)), 3) for z in true_poles]},
        estimate={"model 1": [round(float(np.real(z)), 3) for z in poles1],
                  "model 2": [round(float(np.real(z)), 3) for z in poles2]},
        error=float(relative_error(np.real(poles2), np.real(poles1))),
        error_label="relative difference between the two recovered pole sets",
        status=IDENTIFIABLE,
        control=f"the state matrices themselves differ by {relative_error(fit2.A_u, fit1.A_u):.0%}",
        notes=(
            "a change of latent basis conjugates the state matrix, and conjugation preserves the "
            "spectrum. So the poles are the right thing to report, and A_u is not -- two estimators "
            "disagreeing about A_u may be describing exactly the same dynamics."
        ),
    )

    # ---- figure ---------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.7))
    t_ms = ds1.t * 1000.0

    ax = axes[0]
    for k in range(2):
        ax.plot(t_ms, U1[0][:, k], color=PALETTE[k], linewidth=2.4, alpha=0.55,
                label=f"model 1: $u_{k + 1}$")
        ax.plot(t_ms, U2[0][:, k], color=PALETTE[k], linestyle="--", linewidth=1.5,
                label=f"model 2: $u_{k + 1}$")
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("recovered latent")
    ax.set_title("Latents differ")
    ax.legend(fontsize=7)

    ax = axes[1]
    m1 = ds1.observed[ds1.mask("A", "B")].mean(axis=0)
    m2 = ds2.observed[ds2.mask("A", "B")].mean(axis=0)
    for k in range(3):
        ax.plot(t_ms, m1[:, k], color=PALETTE[k], linewidth=2.4, alpha=0.55, label=f"model 1: $S_{k + 1}$")
        ax.plot(t_ms, m2[:, k], color=PALETTE[k], linestyle="--", linewidth=1.4, label=f"model 2: $S_{k + 1}$")
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("E[S(t) | A→B]")
    ax.set_title("Observables do not")
    ax.legend(fontsize=6.5, ncols=2)

    ax = axes[2]
    labels = list(tests)
    stats = [tests[k]["median_statistic"] for k in labels]
    nulls = [tests[k]["median_null_q95"] for k in labels]
    idx = np.arange(len(labels))
    ax.barh(idx - 0.19, stats, height=0.34, color=PALETTE[0], label="observed statistic")
    ax.barh(idx + 0.19, nulls, height=0.34, color=MUTED, label="permutation null, 95th pct")
    ax.set_yticks(idx, [k.replace(" (", "\n(") for k in labels], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("median max$_t$ ‖mean difference‖ over replicates")
    ax.set_title("The test has power, and does not fire on the twin")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=7, loc="upper right")

    caption(
        fig,
        "Model 2 is model 1 in different latent coordinates. The recovered latents differ by "
        f"{gap.latent_relative_gap:.0%}; the observables agree to {per_transition_gap:.0e}; the "
        "recovered poles agree. The same permutation test separates a world that really is different.",
    )
    fig.tight_layout()
    save(fig, "identifiability", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
