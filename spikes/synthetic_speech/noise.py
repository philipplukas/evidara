"""Correlated observation noise: S_obs(t) = Phi(u(t)) + eps(t).

Spatial covariance regimes (spec section 9) and an optional AR(1) temporal correlation
(spec section 10) with the exact property

    Cov(eps_t, eps_{t+k}) = Sigma rho^{|k|}.

Positive-definiteness of every Sigma is verified on construction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import DEFAULT_SIGMA_3, NoiseConfig, NoiseRegime

__all__ = ["NoiseModel", "build_covariance", "is_positive_definite", "snr_report"]


def is_positive_definite(sigma: np.ndarray, tol: float = 0.0) -> bool:
    if not np.allclose(sigma, sigma.T):
        return False
    return bool(np.min(np.linalg.eigvalsh(sigma)) > tol)


def build_covariance(regime: NoiseRegime, d: int, seed: int = 90210) -> np.ndarray:
    """Unit-scale covariance for a regime, at any acoustic dimensionality.

    * ``white``      -- identity
    * ``correlated`` -- the literal spec matrix at d = 3; a Toeplitz-correlated matrix
      with heterogeneous variances otherwise
    * ``strong``     -- one dominant eigenvalue (condition number ~ 1e2)

    All three are normalised to the same mean variance (trace / d = 1.1) so that noise
    *regime* and noise *level* are independent knobs.
    """
    if regime == "white":
        sigma = np.eye(d)
    elif regime == "correlated":
        if d == 3:
            sigma = DEFAULT_SIGMA_3.copy()
        else:
            rng = np.random.default_rng(seed)
            sd = np.sqrt(rng.uniform(0.7, 1.6, size=d))
            idx = np.arange(d)
            corr = 0.65 ** np.abs(idx[:, None] - idx[None, :])
            sigma = corr * np.outer(sd, sd)
    elif regime == "strong":
        rng = np.random.default_rng(seed + 1)
        v = rng.normal(size=d)
        v /= np.linalg.norm(v)
        sigma = 10.0 * np.outer(v, v) + 0.1 * np.eye(d)
    else:  # pragma: no cover - guarded by Literal typing
        raise ValueError(f"unknown noise regime {regime!r}")

    sigma = 0.5 * (sigma + sigma.T)
    if not is_positive_definite(sigma):
        raise ValueError(f"covariance for regime {regime!r} is not positive definite")
    target_mean_var = 1.1  # matches the spec matrix: trace(Sigma_3)/3 = 1.1
    sigma *= target_mean_var / (np.trace(sigma) / d)
    return sigma


@dataclass(frozen=True)
class NoiseModel:
    """Sampler for eps with spatial covariance ``sigma`` and AR(1) coefficient ``rho``."""

    sigma: np.ndarray
    rho: float
    chol: np.ndarray

    @classmethod
    def from_config(cls, cfg: NoiseConfig) -> NoiseModel:
        sigma = build_covariance(cfg.regime, cfg.d_acoustic, cfg.seed) * (cfg.scale**2)
        if not is_positive_definite(sigma):
            raise ValueError("scaled covariance is not positive definite")
        if not -1.0 < cfg.rho < 1.0:
            raise ValueError(f"rho must lie in (-1, 1), got {cfg.rho}")
        return cls(sigma=sigma, rho=float(cfg.rho), chol=np.linalg.cholesky(sigma))

    @property
    def d(self) -> int:
        return self.sigma.shape[0]

    def sample(self, shape: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
        """Draw eps of shape ``(*shape, T, d)`` where ``shape[-1]`` is the frame count.

        ``shape`` must end with the number of frames T; the returned array has an extra
        trailing axis of size d.
        """
        *lead, T = shape
        z = rng.standard_normal((*lead, T, self.d))
        eps = z @ self.chol.T
        if self.rho == 0.0:
            return eps
        out = np.empty_like(eps)
        out[..., 0, :] = eps[..., 0, :]
        s = np.sqrt(1.0 - self.rho**2)
        for k in range(1, T):
            out[..., k, :] = self.rho * out[..., k - 1, :] + s * eps[..., k, :]
        return out

    def empirical_lag_covariance(self, eps: np.ndarray, lag: int) -> np.ndarray:
        """Cov(eps_t, eps_{t+lag}) estimated from samples of shape (..., T, d)."""
        flat = eps.reshape(-1, eps.shape[-2], eps.shape[-1])
        a = flat[:, : flat.shape[1] - lag, :].reshape(-1, self.d)
        b = flat[:, lag:, :].reshape(-1, self.d)
        return (a - a.mean(0)).T @ (b - b.mean(0)) / (a.shape[0] - 1)


def snr_report(clean: np.ndarray, sigma: np.ndarray) -> dict[str, float]:
    """Signal-to-noise summary for a clean acoustic array of shape (..., T, d).

    Every experiment prints this: a "result" at an unstated SNR is not interpretable.
    """
    flat = clean.reshape(-1, clean.shape[-1])
    sig_var = flat.var(axis=0)
    noise_var = np.diag(sigma)
    per_dim = sig_var / noise_var
    return {
        "signal_var_mean": float(sig_var.mean()),
        "noise_var_mean": float(noise_var.mean()),
        "snr_mean": float(per_dim.mean()),
        "snr_db": float(10.0 * np.log10(max(per_dim.mean(), 1e-300))),
        "snr_min_dim": float(per_dim.min()),
    }
