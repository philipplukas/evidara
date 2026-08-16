"""Temporal kernel families and their fits (experiment 03).

Deliberately *not* importing the generator's ``error_decay``: the second-order response
below is re-derived here as a **hypothesis** an estimator is entitled to entertain, so
that ``analysis/`` never imports the ground-truth modules at all
(``tests/test_oracle_discipline.py`` enforces that mechanically).

The families are ordered by how much they assume, not by how well anyone expects them
to do. Which one wins is the experiment's output, not its input.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import make_smoothing_spline
from scipy.optimize import least_squares

from analysis.metrics import aic, bic, r2, rmse

__all__ = ["KernelFamily", "KernelFit", "FAMILIES", "fit_kernel", "compare_families", "fit_modal_model"]


# --------------------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------------------


def _second_order_rise(t: np.ndarray, omega: float, zeta: float) -> np.ndarray:
    """1 - g(t) for a unit second-order system, valid in all three damping regimes."""
    t = np.asarray(t, float)
    wt = omega * t
    if abs(zeta - 1.0) < 1e-9:
        g = (1.0 + wt) * np.exp(-wt)
    elif zeta < 1.0:
        wd = omega * np.sqrt(max(1.0 - zeta**2, 1e-12))
        g = np.exp(-zeta * wt) * (np.cos(wd * t) + (zeta * omega / wd) * np.sin(wd * t))
    else:
        wd = omega * np.sqrt(zeta**2 - 1.0)
        # cosh/sinh overflow for large arguments; use the two-real-pole form instead
        p1, p2 = -zeta * omega + wd, -zeta * omega - wd
        g = (p2 * np.exp(p1 * t) - p1 * np.exp(p2 * t)) / (p2 - p1)
    return 1.0 - g


@dataclass(frozen=True)
class KernelFamily:
    """A parametric rise kernel K(t; params), with K(0) = 0 by construction."""

    name: str
    n_params: int
    fn: Callable[[np.ndarray, np.ndarray], np.ndarray]
    lower: np.ndarray
    upper: np.ndarray
    init: Callable[[np.ndarray, np.ndarray], list[np.ndarray]]
    assumption: str = ""

    def starts(self, t: np.ndarray, y: np.ndarray) -> list[np.ndarray]:
        return self.init(t, y)


def _amp(y: np.ndarray) -> float:
    return float(y[-1]) if abs(y[-1]) > 1e-12 else float(np.sign(np.sum(y)) or 1.0)


def _tau_guess(t: np.ndarray) -> float:
    return max(float(t[-1]) / 4.0, 1e-4)


def _f_exp(t, p):
    a, tau = p
    return a * (1.0 - np.exp(-t / max(tau, 1e-9)))


def _f_double_exp(t, p):
    a, c, t1, t2 = p
    return a * (1.0 - c * np.exp(-t / max(t1, 1e-9)) - (1.0 - c) * np.exp(-t / max(t2, 1e-9)))


def _f_crit(t, p):
    a, w = p
    return a * _second_order_rise(t, max(w, 1e-6), 1.0)


def _f_under(t, p):
    a, w, z = p
    return a * _second_order_rise(t, max(w, 1e-6), float(np.clip(z, 1e-3, 0.999)))


def _f_second_order(t, p):
    a, w, z = p
    return a * _second_order_rise(t, max(w, 1e-6), max(float(z), 1e-3))


FAMILIES: tuple[KernelFamily, ...] = (
    KernelFamily(
        name="exponential", n_params=2, fn=_f_exp,
        lower=np.array([-np.inf, 1e-5]), upper=np.array([np.inf, np.inf]),
        init=lambda t, y: [np.array([_amp(y), _tau_guess(t)]), np.array([_amp(y), _tau_guess(t) / 4])],
        assumption="one real pole; zero initial slope is impossible",
    ),
    KernelFamily(
        name="double_exponential", n_params=4, fn=_f_double_exp,
        # c must be allowed OUTSIDE [0, 1]: the zero-initial-slope solution needs
        # c / tau1 + (1 - c) / tau2 = 0, i.e. c > 1 with a negative second weight. Bounding
        # c to [0, 1] silently excludes every second-order response and makes this family
        # collapse onto the single exponential.
        lower=np.array([-np.inf, -20.0, 1e-5, 1e-5]), upper=np.array([np.inf, 20.0, np.inf, np.inf]),
        init=lambda t, y: [
            np.array([_amp(y), 0.5, _tau_guess(t), _tau_guess(t) / 5]),
            np.array([_amp(y), -1.0, _tau_guess(t) * 2, _tau_guess(t) / 10]),
            np.array([_amp(y), 1.6, _tau_guess(t), _tau_guess(t) / 3]),
            np.array([_amp(y), 3.0, _tau_guess(t) / 2, _tau_guess(t) / 6]),
        ],
        assumption="two real poles (this is the overdamped second-order response)",
    ),
    KernelFamily(
        name="critically_damped", n_params=2, fn=_f_crit,
        lower=np.array([-np.inf, 1e-3]), upper=np.array([np.inf, np.inf]),
        init=lambda t, y: [np.array([_amp(y), 2.0 / _tau_guess(t)]), np.array([_amp(y), 8.0 / _tau_guess(t)])],
        assumption="zeta exactly 1",
    ),
    KernelFamily(
        name="underdamped", n_params=3, fn=_f_under,
        lower=np.array([-np.inf, 1e-3, 1e-3]), upper=np.array([np.inf, np.inf, 0.999]),
        init=lambda t, y: [
            np.array([_amp(y), 2.0 / _tau_guess(t), 0.7]),
            np.array([_amp(y), 6.0 / _tau_guess(t), 0.3]),
        ],
        assumption="zeta < 1 (oscillatory)",
    ),
    KernelFamily(
        name="second_order_free", n_params=3, fn=_f_second_order,
        lower=np.array([-np.inf, 1e-3, 1e-3]), upper=np.array([np.inf, np.inf, 20.0]),
        init=lambda t, y: [
            np.array([_amp(y), 2.0 / _tau_guess(t), 1.0]),
            np.array([_amp(y), 5.0 / _tau_guess(t), 1.5]),
            np.array([_amp(y), 1.0 / _tau_guess(t), 0.6]),
        ],
        assumption="second order, damping free (nests the three above)",
    ),
)


# --------------------------------------------------------------------------------------
# Fitting
# --------------------------------------------------------------------------------------


@dataclass
class KernelFit:
    family: str
    params: np.ndarray
    n_params: int
    predict: Callable[[np.ndarray], np.ndarray] = field(repr=False)
    train_rmse: float = float("nan")
    train_r2: float = float("nan")
    aic: float = float("nan")
    bic: float = float("nan")
    test_rmse: float = float("nan")
    test_r2: float = float("nan")
    test_nll: float = float("nan")
    extrapolation_rmse: float = float("nan")

    def to_row(self) -> dict:
        return {
            "family": self.family,
            "k": self.n_params,
            "train_rmse": self.train_rmse,
            "train_r2": self.train_r2,
            "AIC": self.aic,
            "BIC": self.bic,
            "test_rmse": self.test_rmse,
            "test_r2": self.test_r2,
            "test_nll": self.test_nll,
            "extrap_rmse": self.extrapolation_rmse,
        }


def fit_kernel(family: KernelFamily, t: np.ndarray, y: np.ndarray) -> KernelFit:
    """Multi-start bounded least squares. Returns the best of the family's starting points."""
    t, y = np.asarray(t, float), np.asarray(y, float)
    best, best_cost = None, np.inf
    for p0 in family.starts(t, y):
        p0 = np.clip(p0, family.lower + 1e-9, family.upper - 1e-9)
        try:
            res = least_squares(
                lambda p: family.fn(t, p) - y, p0, bounds=(family.lower, family.upper),
                max_nfev=20000, xtol=1e-14, ftol=1e-14, gtol=1e-14,
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        if res.cost < best_cost:
            best, best_cost = res.x, res.cost
    if best is None:
        raise RuntimeError(f"kernel family {family.name} failed to fit")
    params = best
    return KernelFit(
        family=family.name,
        params=params,
        n_params=family.n_params,
        predict=lambda tt, p=params, f=family.fn: f(np.asarray(tt, float), p),
    )


def fit_spline(t: np.ndarray, y: np.ndarray, lam: float | None = 1e-10) -> KernelFit:
    """Nonparametric smoothing-spline baseline.

    ``lam`` is deliberately tiny: the point of this baseline is a model flexible enough
    to track the training window closely and structurally incapable of extrapolating,
    so it isolates "does the parametric family carry information beyond interpolation?".
    With GCV-chosen smoothing it under-fits here and stops being that reference.

    No AIC/BIC is reported for it. Its parameter count is not the number of B-spline
    coefficients but the trace of the penalised smoother, and reporting the former would
    misrepresent the comparison in whichever direction happened to be convenient.
    """
    t, y = np.asarray(t, float), np.asarray(y, float)
    spl = make_smoothing_spline(t, y, lam=lam)
    return KernelFit(
        family="spline",
        params=np.array([float(len(spl.c))]),
        n_params=int(len(spl.c)),
        predict=lambda tt, s=spl: s(np.asarray(tt, float)),
        train_rmse=rmse(y, spl(t)),
        train_r2=r2(y, spl(t)),
    )


def compare_families(
    t_train: np.ndarray,
    y_train: np.ndarray,
    t_test: np.ndarray,
    y_test: np.ndarray,
    t_extrap: np.ndarray | None = None,
    y_extrap: np.ndarray | None = None,
    include_spline: bool = True,
) -> list[KernelFit]:
    """Fit every family on ``(t_train, y_train)`` and score it out of sample.

    Two kinds of held-out data are used, and they answer different questions:
      * ``t_test``/``y_test`` -- the *same* time grid measured on independent segments:
        tests statistical stability.
      * ``t_extrap``/``y_extrap`` -- a *later* part of the time window never fitted:
        tests whether the functional form is right. A wrong family can look fine on the
        first and fail badly on the second.
    """
    fits: list[KernelFit] = []
    for fam in FAMILIES:
        fit = fit_kernel(fam, t_train, y_train)
        pred = fit.predict(t_train)
        fit.train_rmse = rmse(y_train, pred)
        fit.train_r2 = r2(y_train, pred)
        n = y_train.size
        sse = float(np.sum((y_train - pred) ** 2))
        sigma2 = max(sse / n, 1e-300)
        nll = 0.5 * n * (np.log(2 * np.pi * sigma2) + 1.0)
        fit.aic = aic(nll, fam.n_params + 1)
        fit.bic = bic(nll, fam.n_params + 1, n)
        fits.append(fit)
    if include_spline:
        fits.append(fit_spline(t_train, y_train))

    for fit in fits:
        pt = fit.predict(t_test)
        fit.test_rmse = rmse(y_test, pt)
        fit.test_r2 = r2(y_test, pt)
        m = y_test.size
        s2 = max(float(np.mean((y_test - pt) ** 2)), 1e-300)
        fit.test_nll = 0.5 * m * (np.log(2 * np.pi * s2) + 1.0)
        if t_extrap is not None and y_extrap is not None:
            fit.extrapolation_rmse = rmse(y_extrap, fit.predict(t_extrap))
    return fits


# --------------------------------------------------------------------------------------
# Multi-mode (rank > 1) model
# --------------------------------------------------------------------------------------


@dataclass
class ModalFit:
    """A K-mode separable model Delta S(t) = sum_k K(t; w_k, z_k) v_k^T."""

    omega: np.ndarray
    zeta: np.ndarray
    loadings: np.ndarray  # (K, m)
    residual_rmse: float
    n_modes: int

    def predict(self, t: np.ndarray) -> np.ndarray:
        basis = np.stack([_second_order_rise(t, w, z) for w, z in zip(self.omega, self.zeta, strict=True)], axis=1)
        return basis @ self.loadings


def fit_modal_model(t: np.ndarray, Y: np.ndarray, n_modes: int, seed: int = 0) -> ModalFit:
    """Variable-projection fit of ``n_modes`` second-order kernels to a (T, m) contrast set.

    For fixed poles the loadings are linear, so only 2 * n_modes numbers are searched.
    This is the estimator that can recover the *generating* poles rather than an
    orthogonalised mixture of them -- SVD components are orthogonal, and the true modes
    are not, so no singular vector equals a physical mode.
    """
    t, Y = np.asarray(t, float), np.asarray(Y, float)
    rng = np.random.default_rng(seed)

    def basis(p):
        w, z = np.exp(p[:n_modes]), np.exp(p[n_modes:])
        return np.stack([_second_order_rise(t, wi, zi) for wi, zi in zip(w, z, strict=True)], axis=1)

    def resid(p):
        B = basis(p)
        coef, *_ = np.linalg.lstsq(B, Y, rcond=None)
        return (B @ coef - Y).ravel()

    scale = 4.0 / max(float(t[-1]), 1e-9)
    best, best_cost = None, np.inf
    for _ in range(8):
        w0 = np.log(scale * rng.uniform(0.4, 3.0, size=n_modes))
        z0 = np.log(rng.uniform(0.5, 2.0, size=n_modes))
        try:
            res = least_squares(resid, np.concatenate([w0, z0]), max_nfev=8000, xtol=1e-13, ftol=1e-13)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if res.cost < best_cost:
            best, best_cost = res.x, res.cost
    if best is None:
        raise RuntimeError("modal fit failed")

    B = basis(best)
    coef, *_ = np.linalg.lstsq(B, Y, rcond=None)
    order = np.argsort(-np.exp(best[:n_modes]))
    return ModalFit(
        omega=np.exp(best[:n_modes])[order],
        zeta=np.exp(best[n_modes:])[order],
        loadings=coef[order],
        residual_rmse=rmse(Y, B @ coef),
        n_modes=n_modes,
    )
