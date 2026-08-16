"""The identifiability twin must be observationally exact, not merely close."""

from dataclasses import replace

import numpy as np

from acoustics import make_acoustic_map
from config import AcousticConfig, WorldConfig
from generator import affine_twin_world, generate


def _P_and_p(seed=5):
    rng = np.random.default_rng(seed)
    P = np.eye(2) + 0.35 * rng.normal(size=(2, 2))
    return P, rng.normal(scale=0.2, size=2)


def test_composed_map_satisfies_phi2_of_h_equals_phi1():
    P, p = _P_and_p()
    Pinv = np.linalg.inv(P)
    phi = make_acoustic_map(AcousticConfig(), 2)
    phi2 = phi.compose_with_affine(Pinv, -(Pinv @ p))
    u = np.random.default_rng(1).uniform(-1.5, 1.5, size=(500, 2))
    assert np.max(np.abs(phi2.Phi(u @ P.T + p) - phi.Phi(u))) < 1e-12


def test_composed_map_jacobian_stays_analytic():
    from acoustics import verify_jacobian

    P, p = _P_and_p()
    Pinv = np.linalg.inv(P)
    phi2 = make_acoustic_map(AcousticConfig(), 2).compose_with_affine(Pinv, -(Pinv @ p))
    pts = np.random.default_rng(2).uniform(-1.5, 1.5, size=(30, 2))
    assert verify_jacobian(phi2, pts)[0] < 1e-6


def test_twin_world_emits_identical_clean_acoustics():
    base = replace(WorldConfig(), sequence=replace(WorldConfig().sequence, n_sequences=60))
    P, p = _P_and_p()
    twin, phi2, h = affine_twin_world(base, P, p)
    a = generate(base, seed=3)
    b = generate(twin, seed=3, phi_override=phi2)
    assert np.max(np.abs(a.clean - b.clean)) < 1e-10
    assert np.max(np.abs(a.observed - b.observed)) < 1e-10  # same seed => same noise draw


def test_twin_latents_differ_and_are_related_by_h():
    base = replace(WorldConfig(), sequence=replace(WorldConfig().sequence, n_sequences=40))
    P, p = _P_and_p()
    twin, phi2, h = affine_twin_world(base, P, p)
    a = generate(base, seed=4)
    b = generate(twin, seed=4, phi_override=phi2)
    assert np.max(np.abs(a.latent_u - b.latent_u)) > 0.1  # genuinely different coordinates
    assert np.max(np.abs(h(a.latent_u) - b.latent_u)) < 1e-10  # ... but exactly h of each other


def test_twin_preserves_the_dynamical_spectrum_but_not_the_matrices():
    from analysis.identifiability import spectral_invariants

    base = WorldConfig()
    P, p = _P_and_p()
    twin, _, _ = affine_twin_world(base, P, p)
    e1 = spectral_invariants(-base.dynamics.K, -base.dynamics.C)
    e2 = spectral_invariants(
        -np.linalg.inv(twin.dynamics.M) @ twin.dynamics.K,
        -np.linalg.inv(twin.dynamics.M) @ twin.dynamics.C,
    )
    # The critically damped mode is a *defective* eigenvalue (a Jordan block at -25), so
    # its numerical conditioning under a change of basis is O(sqrt(eps)) ~ 1e-7, not
    # O(eps). That is a property of the ground truth, not of the estimator: it also caps
    # how precisely any method can ever pin that pole down.
    assert np.max(np.abs(np.sort_complex(e1) - np.sort_complex(e2))) < 1e-5
    assert np.max(np.abs(twin.dynamics.K - base.dynamics.K)) > 1.0


def test_twin_preserves_alpha_exactly():
    base = WorldConfig()
    P, p = _P_and_p()
    twin, _, h = affine_twin_world(base, P, p)
    for q, r in base.transitions():
        assert np.max(np.abs(twin.theta(q, r) - h(base.theta(q, r)))) < 1e-12
        assert abs(twin.anticipation.alpha(q, r) - base.anticipation.alpha(q, r)) < 1e-15
