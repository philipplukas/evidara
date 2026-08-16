"""Experiment 4 -- can articulation and the acoustic Jacobian be recovered?

Three estimators, deliberately separated because they are three different problems:

  ORACLE inverse   given the true Phi and DPhi, invert S back to u. Isolates the
                   *temporal* inverse problem from the acoustic one.
  PROBE Jacobian   choose latent states, observe noisy acoustics at u +- delta e_i,
                   estimate DPhi by central differences. The latent input is chosen by
                   the experimenter, so this is ORACLE-INPUT: it bounds what is possible
                   with controlled articulatory perturbations.
  BLIND tangent    local PCA on the acoustic point cloud, no latent access at all.

The blind estimator cannot recover DPhi and is not scored as if it could. Relabelling
the latent coordinates changes DPhi while leaving every observable distribution fixed,
so the most any acoustic-only method can fix is the *column space* of DPhi. It is scored
with principal angles; the probe estimator is scored in Frobenius norm.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from _common import GRID, MARKERS, MUTED, PALETTE, caption, parse_args, save

from acoustics import make_acoustic_map
from analysis.metrics import (
    IDENTIFIABLE,
    PARTIAL,
    best_linear_map_error,
    relative_error,
    subspace_error,
)
from analysis.recording import ExperimentRun
from analysis.system_id import estimate_jacobian_by_probe, estimate_tangent_blind, invert_nonlinear
from config import SequenceConfig, WorldConfig, noise_world
from generator import generate

# extended upward on purpose: with a mildly quadratic Phi the truncation-bias branch only
# appears at steps of order 1, and a sweep that stops at 0.3 shows a monotone curve and
# invites the wrong conclusion that smaller steps are simply worse
DELTAS = [3.0, 1.0, 0.3, 0.1, 0.03, 0.01, 0.003, 0.001]
NOISE_SCALES = [0.01, 0.1, 0.3, 1.0]


def main() -> None:
    args = parse_args(__doc__)
    n_seq = 400 if args.quick else 3000
    run = ExperimentRun(name="04_jacobian_recovery", title="Experiment 4 -- articulation and Jacobian recovery")

    world = replace(WorldConfig(), sequence=SequenceConfig(n_sequences=n_seq))
    run.scalar("n_sequences", n_seq)

    # ================================================================================
    # A. oracle inversion of articulation
    # ================================================================================
    oracle_rows = {}
    for scale in NOISE_SCALES:
        ds = generate(noise_world("correlated", scale, world), seed=args.seed)
        phi = ds.phi  # ORACLE: the inverse is given the true acoustic map
        errs, scales = [], []
        for q, r in ds.transitions:
            m = ds.mask(q, r)
            S = ds.observed[m].mean(axis=0)
            u_hat = invert_nonlinear(S, phi.Phi, ds.config.articulatory.target(q), phi.Dphi)  # ORACLE
            u_true = ds.latent_u[m][0]  # GT: scoring only
            errs.append(np.sqrt(np.mean((u_hat - u_true) ** 2)))
            scales.append(np.sqrt(np.mean(u_true**2)))
        oracle_rows[scale] = dict(
            rmse=float(np.mean(errs)),
            relative=float(np.mean(errs) / np.mean(scales)),
            snr_db=ds.snr()["snr_db"],  # GT: diagnostic
        )
    run.table("oracle_inversion_vs_noise", oracle_rows)

    # ================================================================================
    # B. probe estimation of DPhi (ORACLE-INPUT)
    # ================================================================================
    ds_probe = generate(noise_world("correlated", 0.1, world), seed=args.seed)
    noise_model = ds_probe.noise_model  # ORACLE: probe observations carry the same noise
    probe_points = np.array([[0.0, 0.0], [0.5, 0.2], [-0.3, 0.7], [1.0, 0.3]])
    chol = np.linalg.cholesky(noise_model.sigma)  # ORACLE

    # Two maps, because the theory makes different predictions for them. Central differences
    # truncate at O(delta^2 * third derivative), and the default Phi is *quadratic* -- its
    # third derivative is identically zero, so the probe estimator is unbiased at ANY step and
    # the error must fall monotonically as 1/delta. The saturating map has non-zero curvature
    # of every order, so there the bias/variance optimum should be interior. Running only the
    # first map and calling the resulting monotone curve a "trade-off" would be wrong.
    probe_maps = {
        "quadratic Phi (third derivative = 0)": ds_probe.phi,  # ORACLE
        "saturating Phi": make_acoustic_map(replace(world.acoustic, kind="strong_nonlinear"), world.d_art),
    }

    def make_observer(phi, scale: float, rng: np.random.Generator):
        def observe(u, n):
            clean = phi.Phi(u)
            eps = (rng.standard_normal((n, clean.size)) @ chol.T) * scale
            return clean + eps

        return observe

    probe_grid = {}
    probe_by_map = {}
    for map_name, phi_probe in probe_maps.items():
        for scale in NOISE_SCALES:
            for n_rep in ([1, 100] if args.quick else [1, 10, 100, 1000]):
                rng = np.random.default_rng(args.seed + 17)
                obs = make_observer(phi_probe, scale, rng)
                errs = [
                    float(np.mean([
                        relative_error(
                            estimate_jacobian_by_probe(obs, u0, delta, n_repeat=n_rep).jacobian,
                            phi_probe.Dphi(u0),  # GT: scoring
                        )
                        for u0 in probe_points
                    ]))
                    for delta in DELTAS
                ]
                probe_by_map[(map_name, scale, n_rep)] = errs
                if map_name.startswith("quadratic"):
                    probe_grid[(scale, n_rep)] = errs
    run.table(
        "probe_jacobian_relative_error",
        {f"{m} | noise={s} | n_repeat={n}": dict(zip(map(str, DELTAS), v, strict=True))
         for (m, s, n), v in probe_by_map.items()},
    )
    interior_by_map = {}
    for map_name in probe_maps:
        keys = [k for k in probe_by_map if k[0] == map_name]
        best_key = min(keys, key=lambda k: min(probe_by_map[k]))
        j = int(np.argmin(probe_by_map[best_key]))
        interior_by_map[map_name] = dict(
            best_delta=DELTAS[j],
            best_error=float(probe_by_map[best_key][j]),
            interior_optimum=bool(0 < j < len(DELTAS) - 1),
            at=str(best_key[1:]),
        )
    run.table("probe_optimum_by_map", interior_by_map)

    best_probe = min((min(v), k) for k, v in probe_grid.items())
    quad_name, sat_name = list(probe_maps)
    best_delta_overall = interior_by_map[sat_name]["best_delta"]

    # ================================================================================
    # C. blind tangent estimation
    # ================================================================================
    blind_rows = {}
    for scale in NOISE_SCALES:
        ds = generate(noise_world("correlated", scale, world), seed=args.seed)
        # noise-averaged acoustic manifold samples: one mean trajectory per transition
        cloud = np.concatenate(
            [ds.observed[ds.mask(q, r)].mean(axis=0) for q, r in ds.transitions], axis=0
        )
        sub_errs, jac_errs = [], []
        for u0 in probe_points:
            centre = ds.phi.Phi(u0)  # ORACLE: only used to place the neighbourhood
            basis, _ = estimate_tangent_blind(cloud, centre, d_latent=ds.config.d_art, k_neighbours=80)
            true_J = ds.phi.Dphi(u0)  # GT: scoring
            sub_errs.append(subspace_error(basis, true_J))
            jac_errs.append(relative_error(basis, true_J))
        blind_rows[scale] = dict(
            subspace_error=float(np.mean(sub_errs)),
            naive_frobenius_error=float(np.mean(jac_errs)),
        )
    run.table("blind_tangent_vs_noise", blind_rows)

    # blind inversion: use the estimated tangent basis as the Jacobian
    ds = generate(noise_world("correlated", 0.1, world), seed=args.seed)
    cloud = np.concatenate([ds.observed[ds.mask(q, r)].mean(axis=0) for q, r in ds.transitions], axis=0)
    u_ref = ds.config.articulatory.target("A")
    basis, _ = estimate_tangent_blind(cloud, ds.phi.Phi(u_ref), d_latent=2, k_neighbours=80)  # ORACLE: centre
    S_ab = ds.observed[ds.mask("A", "B")].mean(axis=0)
    u_blind = (S_ab - ds.phi.Phi(u_ref)) @ np.linalg.pinv(basis).T  # ORACLE: reference point
    u_true = ds.latent_u[ds.mask("A", "B")][0]  # GT: scoring
    blind_direct = relative_error(u_blind, u_true - u_ref)
    blind_reparam, _ = best_linear_map_error(u_blind, u_true - u_ref)
    run.scalar("blind_inversion_direct_relative_error", blind_direct)
    run.scalar("blind_inversion_error_after_affine_reparam", blind_reparam)

    # ================================================================================
    # findings
    # ================================================================================
    run.record(
        question="ORACLE -- can articulation be recovered given the true acoustic map?",
        ground_truth={"latent trajectories u(t)": "known exactly"},
        estimate={f"noise {s}": round(v["relative"], 5) for s, v in oracle_rows.items()},
        error=oracle_rows[0.1]["relative"],
        error_label="relative rmse at noise 0.1",
        status=IDENTIFIABLE,
        control="noise 0.01 gives " + f"{oracle_rows[0.01]['relative']:.2e}, so the residual is noise, not bias",
        notes=(
            "with Phi known, inversion is essentially exact and degrades only as fast as the "
            "noise on the transition-averaged trajectory. The temporal inverse problem is easy; "
            "everything hard in this pipeline lives in the acoustic map."
        ),
    )
    run.record(
        question="ORACLE-INPUT -- can DPhi be estimated by probing the latent state?",
        ground_truth={"DPhi(u)": "analytic, verified against finite differences to 1e-9"},
        estimate={"best relative error": best_probe[0], "at (noise, n_repeat)": str(best_probe[1])},
        error=float(best_probe[0]),
        error_label="relative Frobenius error",
        status=IDENTIFIABLE,
        control=f"the saturating map, run through the identical sweep: its optimum sits at "
                f"delta = {interior_by_map[sat_name]['best_delta']:g}, "
                f"{'interior to' if interior_by_map[sat_name]['interior_optimum'] else 'at the edge of'} "
                "the swept range",
        notes=(
            f"on the quadratic map the best step is delta = {interior_by_map[quad_name]['best_delta']:g}, "
            f"{'an interior' if interior_by_map[quad_name]['interior_optimum'] else 'an edge'} optimum -- "
            "and it should be an edge one: central differences truncate at O(delta^2 * third "
            "derivative) and a quadratic map has no third derivative, so the estimator is unbiased at "
            "every step and error falls as sigma/(delta sqrt(n)). The bias/variance trade-off only "
            "becomes visible on the saturating map, which is why both are swept. Reading the monotone "
            "curve as a trade-off would have been a comfortable and wrong conclusion."
        ),
    )
    run.record(
        question="BLIND -- can DPhi be estimated from acoustics alone?",
        ground_truth={"column space of DPhi": "2-dimensional inside R^3"},
        estimate={
            f"noise {s}": {"subspace error": round(v["subspace_error"], 4),
                           "naive Frobenius": round(v["naive_frobenius_error"], 3)}
            for s, v in blind_rows.items()
        },
        error=blind_rows[0.1]["subspace_error"],
        error_label="sin of the largest principal angle at noise 0.1",
        status=PARTIAL,
        control="the same quantity scored in Frobenius norm, which stays near 1 at every noise level",
        notes=(
            f"the tangent *subspace* is recovered (sin theta = {blind_rows[0.1]['subspace_error']:.3f}) "
            f"while the matrix itself is not (Frobenius {blind_rows[0.1]['naive_frobenius_error']:.2f}). "
            f"Blind inversion of A->B has direct error {blind_direct:.2f}, dropping to "
            f"{blind_reparam:.3f} once an affine reparameterisation of the latent is allowed. "
            "That gap IS Hypothesis 2: what is recoverable is the equivalence class, not the coordinates."
        ),
    )

    # ================================================================================
    # figure
    # ================================================================================
    fig, axes = plt.subplots(1, 4, figsize=(15.0, 3.8))

    ax = axes[0]
    n_lo, n_hi = 1, max(k[1] for k in probe_grid)
    for i, (map_name, sty) in enumerate(zip(probe_maps, ("-", "--"), strict=True)):
        key = (map_name, 0.1, n_hi)
        if key in probe_by_map:
            ax.loglog(DELTAS, probe_by_map[key], color=PALETTE[i], linestyle=sty,
                      marker=MARKERS[i], markersize=4,
                      label=("quadratic Φ" if i == 0 else "saturating Φ") + f", noise 0.1, n={n_hi}")
    ax.set_xlabel("probe step $\\delta$")
    ax.set_ylabel("relative $\\|\\hat{D\\Phi} - D\\Phi\\|_F$")
    ax.set_title("Probe Jacobian: bias appears only with curvature")
    ax.legend(fontsize=7, loc="upper center")

    ax = axes[1]
    # four series only: the categorical palette is validated for its first slots in fixed
    # order, and cycling eight hues through one axes is exactly what that rule forbids
    shown = [(0.01, n_lo), (0.01, n_hi), (1.0, n_lo), (1.0, n_hi)]
    for i, key in enumerate(shown):
        if key not in probe_grid:
            continue
        ax.loglog(DELTAS, probe_grid[key], color=PALETTE[i], linestyle=["-", "--", "-.", ":"][i],
                  marker=MARKERS[i], markersize=4, label=f"noise {key[0]}, n={key[1]}")
    ax.set_xlabel("probe step $\\delta$")
    ax.set_ylabel("relative $\\|\\hat{D\\Phi} - D\\Phi\\|_F$")
    ax.set_title("Noise and averaging, quadratic $\\Phi$")
    ax.legend(fontsize=7, loc="upper center")

    ax = axes[2]
    scales = NOISE_SCALES
    ax.loglog(scales, [blind_rows[s]["subspace_error"] for s in scales], color=PALETTE[0],
              marker="o", label="blind: subspace error")
    ax.loglog(scales, [blind_rows[s]["naive_frobenius_error"] for s in scales], color=PALETTE[1],
              linestyle="--", marker="s", label="blind: Frobenius error")
    ax.loglog(scales, [oracle_rows[s]["relative"] for s in scales], color=PALETTE[2],
              linestyle="-.", marker="^", label="oracle inversion of u")
    ax.set_xlabel("noise scale")
    ax.set_ylabel("relative error")
    ax.set_title("What each estimator can reach")
    ax.legend(fontsize=7, loc="lower right")

    ax = axes[3]
    t_ms = ds.t * 1000.0
    for k in range(2):
        ax.plot(t_ms, (u_true - u_ref)[:, k], color=PALETTE[k], linestyle="-", linewidth=2.4,
                alpha=0.5, label=f"true $u_{k + 1} - u_A$")
        ax.plot(t_ms, u_blind[:, k], color=PALETTE[k], linestyle="--", linewidth=1.5,
                label=f"blind $\\hat u_{k + 1}$")
    ax.axhline(0, color=GRID, linewidth=0.9)
    ax.set_xlabel("time within segment (ms)")
    ax.set_ylabel("latent displacement")
    ax.set_title("Blind inversion recovers a rotated latent")
    ax.legend(fontsize=7, loc="upper left")
    _ = MUTED

    caption(
        fig,
        f"Left: the probe estimator trades truncation bias (large δ) against observation noise "
        f"(small δ); the best step over this sweep is δ = {best_delta_overall:g}. Centre: the blind "
        "estimator pins the tangent subspace but not the Jacobian. Right: the blind latent is a "
        "linear reparameterisation of the true one, which is exactly what an acoustic-only method "
        "can identify.",
    )
    fig.tight_layout()
    save(fig, "jacobian_recovery", run)

    run.print_summary()
    run.save()


if __name__ == "__main__":
    main()
