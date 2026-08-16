"""Jacobian verification is mandatory (spec section 7)."""

import numpy as np
import pytest

from acoustics import finite_difference_jacobian, make_acoustic_map, verify_jacobian
from config import AcousticConfig


def _spec_phi(u):
    u1, u2 = u[..., 0], u[..., 1]
    return np.stack([u1 + 0.15 * u1 * u2, 2 * u2 + 0.10 * u1**2, u1 - u2 + 0.08 * u1 * u2], axis=-1)


def test_default_map_reproduces_the_spec_formula_exactly():
    phi = make_acoustic_map(AcousticConfig(), d_art=2)
    rng = np.random.default_rng(0)
    u = rng.uniform(-1.5, 1.5, size=(200, 2))
    assert np.max(np.abs(phi.Phi(u) - _spec_phi(u))) < 1e-14


def test_analytic_jacobian_matches_finite_differences():
    phi = make_acoustic_map(AcousticConfig(), d_art=2)
    rng = np.random.default_rng(1)
    pts = rng.uniform(-1.5, 1.5, size=(50, 2))
    max_err, _ = verify_jacobian(phi, pts)
    assert max_err < 1e-7, f"analytic Jacobian disagrees with finite differences: {max_err:g}"


@pytest.mark.parametrize("d_art", [2, 3, 5, 10])
@pytest.mark.parametrize("d_acoustic", [3, 5, 20])
def test_jacobian_matches_at_every_supported_dimensionality(d_art, d_acoustic):
    phi = make_acoustic_map(AcousticConfig(d_acoustic=d_acoustic), d_art=d_art)
    rng = np.random.default_rng(2)
    pts = rng.uniform(-1.2, 1.2, size=(10, d_art))
    max_err, _ = verify_jacobian(phi, pts)
    assert max_err < 1e-6


@pytest.mark.parametrize("kind", ["polynomial", "linear", "strong_nonlinear"])
def test_jacobian_matches_for_every_map_kind(kind):
    phi = make_acoustic_map(AcousticConfig(kind=kind), d_art=2)
    rng = np.random.default_rng(3)
    pts = rng.uniform(-1.2, 1.2, size=(30, 2))
    max_err, _ = verify_jacobian(phi, pts)
    assert max_err < 1e-6


def test_linear_map_has_constant_jacobian():
    phi = make_acoustic_map(AcousticConfig(kind="linear"), d_art=2)
    rng = np.random.default_rng(4)
    pts = rng.uniform(-2, 2, size=(20, 2))
    jacs = phi.Dphi(pts)
    assert np.max(np.abs(jacs - jacs[0])) < 1e-14


def test_strong_nonlinear_map_is_meaningfully_more_curved():
    poly = make_acoustic_map(AcousticConfig(kind="polynomial"), d_art=2)
    strong = make_acoustic_map(AcousticConfig(kind="strong_nonlinear"), d_art=2)
    rng = np.random.default_rng(9)
    pts = rng.uniform(-1.0, 1.0, size=(200, 2))
    spread_poly = np.max(np.abs(poly.Dphi(pts) - poly.Dphi(pts).mean(0)))
    spread_strong = np.max(np.abs(strong.Dphi(pts) - strong.Dphi(pts).mean(0)))
    assert spread_strong > 3 * spread_poly


def test_finite_difference_helper_is_itself_correct_on_a_known_function():
    def f(u):
        return np.array([u[0] ** 2, np.sin(u[1])])

    u = np.array([0.3, 0.7])
    jac = finite_difference_jacobian(f, u)
    assert np.allclose(jac, np.array([[0.6, 0.0], [0.0, np.cos(0.7)]]), atol=1e-7)
