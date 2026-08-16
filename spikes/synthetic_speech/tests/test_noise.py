"""Noise must have exactly the covariance it claims -- experiments 02/03 read residuals."""

import numpy as np
import pytest

from config import DEFAULT_SIGMA_3, NoiseConfig
from noise import NoiseModel, build_covariance, is_positive_definite


@pytest.mark.parametrize("regime", ["white", "correlated", "strong"])
@pytest.mark.parametrize("d", [3, 5, 20])
def test_every_covariance_is_positive_definite(regime, d):
    assert is_positive_definite(build_covariance(regime, d))


def test_correlated_regime_at_d3_is_the_spec_matrix_up_to_normalisation():
    sigma = build_covariance("correlated", 3)
    assert np.allclose(sigma, DEFAULT_SIGMA_3)  # spec matrix already has trace/d = 1.1


def test_strong_regime_has_a_dominant_eigenvalue():
    ev = np.linalg.eigvalsh(build_covariance("strong", 3))
    assert ev[-1] / ev[0] > 50


def test_regimes_share_a_mean_variance_so_level_and_shape_are_independent_knobs():
    means = [np.trace(build_covariance(r, 3)) / 3 for r in ("white", "correlated", "strong")]
    assert np.allclose(means, means[0])


def test_empirical_covariance_matches_sigma():
    model = NoiseModel.from_config(NoiseConfig(regime="correlated", scale=1.0))
    eps = model.sample((4000, 50), np.random.default_rng(7))
    emp = np.cov(eps.reshape(-1, 3).T)
    assert np.max(np.abs(emp - model.sigma)) < 0.03


@pytest.mark.parametrize("rho", [0.0, 0.3, 0.7])
def test_ar1_lag_covariance_is_sigma_rho_to_the_lag(rho):
    model = NoiseModel.from_config(NoiseConfig(regime="correlated", scale=1.0, rho=rho))
    eps = model.sample((3000, 60), np.random.default_rng(11))
    for lag in (0, 1, 3):
        emp = model.empirical_lag_covariance(eps, lag)
        assert np.max(np.abs(emp - model.sigma * rho**lag)) < 0.05


def test_scale_multiplies_the_covariance_quadratically():
    a = NoiseModel.from_config(NoiseConfig(scale=1.0))
    b = NoiseModel.from_config(NoiseConfig(scale=0.5))
    assert np.allclose(b.sigma, 0.25 * a.sigma)


def test_sampling_is_deterministic_given_a_seed():
    model = NoiseModel.from_config(NoiseConfig(rho=0.5))
    a = model.sample((10, 20), np.random.default_rng(3))
    b = model.sample((10, 20), np.random.default_rng(3))
    assert np.array_equal(a, b)
