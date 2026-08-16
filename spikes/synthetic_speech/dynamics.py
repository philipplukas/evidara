"""Articulatory dynamics: M u'' + C u' + K (u - theta) = 0.

Everything here is propagated with a **matrix exponential** (exact zero-order-hold
discretisation), not Euler integration. That matters: the effects we measure later
(anticipation differences of order 1e-1, Jacobian errors of order 1e-3) must not be
contaminated by integrator error. ``tests/test_dynamics.py`` pins the discretisation
against the closed-form modal solution to ~1e-12.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm

from config import DynamicsConfig

__all__ = [
    "LinearDynamics",
    "ModalReport",
    "state_space",
    "zoh_discretize",
    "modal_report",
    "error_decay",
    "simulate_linear",
    "simulate_nonlinear",
    "acceleration",
]


# --------------------------------------------------------------------------------------
# State-space form
# --------------------------------------------------------------------------------------


def state_space(M: np.ndarray, C: np.ndarray, K: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r"""First-order form of M u'' + C u' + K(u - theta) = 0.

    With x = [u; u'],

        x' = A x + B theta,
        A = [[0, I], [-M^-1 K, -M^-1 C]],
        B = [[0], [M^-1 K]].

    The forced equilibrium is x* = [theta; 0] exactly (A x* + B theta = 0).
    """
    d = M.shape[0]
    Minv = np.linalg.inv(M)
    A = np.zeros((2 * d, 2 * d))
    A[:d, d:] = np.eye(d)
    A[d:, :d] = -Minv @ K
    A[d:, d:] = -Minv @ C
    B = np.zeros((2 * d, d))
    B[d:, :] = Minv @ K
    return A, B


def zoh_discretize(A: np.ndarray, B: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact zero-order-hold discretisation via the block matrix exponential.

    expm([[A, B], [0, 0]] dt) = [[A_d, B_d], [0, I]], so ``x_{k+1} = A_d x_k + B_d theta_k``
    is exact whenever theta is constant across the step -- which it is for constant
    targets and for the sampled time-varying targets of Condition IV.
    """
    n, m = A.shape[0], B.shape[1]
    blk = np.zeros((n + m, n + m))
    blk[:n, :n] = A
    blk[:n, n:] = B
    E = expm(blk * dt)
    return E[:n, :n], E[:n, n:]


@dataclass(frozen=True)
class LinearDynamics:
    """Cached exact propagator for one ``DynamicsConfig`` on one time step."""

    A: np.ndarray
    B: np.ndarray
    Ad: np.ndarray
    Bd: np.ndarray
    dt: float
    d_art: int
    Minv_K: np.ndarray
    Minv_C: np.ndarray

    @classmethod
    def from_config(cls, cfg: DynamicsConfig, dt: float) -> LinearDynamics:
        A, B = state_space(cfg.M, cfg.C, cfg.K)
        Ad, Bd = zoh_discretize(A, B, dt)
        Minv = np.linalg.inv(cfg.M)
        return cls(
            A=A, B=B, Ad=Ad, Bd=Bd, dt=dt, d_art=cfg.M.shape[0],
            Minv_K=Minv @ cfg.K, Minv_C=Minv @ cfg.C,
        )

    @property
    def A_u(self) -> np.ndarray:
        """Ground-truth position coefficient of the acceleration law: -M^-1 K."""
        return -self.Minv_K

    @property
    def A_v(self) -> np.ndarray:
        """Ground-truth velocity coefficient of the acceleration law: -M^-1 C."""
        return -self.Minv_C


# --------------------------------------------------------------------------------------
# Modal analysis (ground-truth temporal kernels)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModalReport:
    """Per-mode natural frequency, damping ratio and regime for a diagonal system."""

    omega_n: np.ndarray
    zeta: np.ndarray
    regime: tuple[str, ...]

    def describe(self) -> str:
        return "; ".join(
            f"mode {i}: omega_n={w:.3f} rad/s, zeta={z:.4f} ({r})"
            for i, (w, z, r) in enumerate(zip(self.omega_n, self.zeta, self.regime, strict=True))
        )


def _is_diagonal(a: np.ndarray, tol: float = 1e-12) -> bool:
    return bool(np.all(np.abs(a - np.diag(np.diag(a))) <= tol))


def modal_report(cfg: DynamicsConfig) -> ModalReport:
    """Natural frequencies and damping ratios. Requires diagonal M, C, K.

    With the defaults this returns ``zeta = (7/6, 1)`` -- mode 1 overdamped, mode 2
    exactly critically damped. Two different kernel families in one world, by design.
    """
    if not all(_is_diagonal(m) for m in (cfg.M, cfg.C, cfg.K)):
        raise ValueError("modal_report requires simultaneously diagonal M, C, K")
    m, c, k = np.diag(cfg.M), np.diag(cfg.C), np.diag(cfg.K)
    omega_n = np.sqrt(k / m)
    zeta = c / (2.0 * np.sqrt(k * m))
    regime = tuple(
        "underdamped" if z < 1 - 1e-12 else ("critically damped" if abs(z - 1) <= 1e-12 else "overdamped")
        for z in zeta
    )
    return ModalReport(omega_n=omega_n, zeta=zeta, regime=regime)


def error_decay(omega_n: float, zeta: float, t: np.ndarray) -> np.ndarray:
    r"""Closed-form decay g(t) of the target error for a single second-order mode.

    For u(0) = u_0, u'(0) = 0 and a constant target theta,

        u(t) = theta + (u_0 - theta) g(t),

    so the *rise* kernel is K(t) = 1 - g(t). The three regimes:

      * zeta < 1:  g = e^{-zeta w t} (cos(w_d t) + zeta w / w_d sin(w_d t)),  w_d = w sqrt(1 - zeta^2)
      * zeta = 1:  g = (1 + w t) e^{-w t}
      * zeta > 1:  g = e^{-zeta w t} (cosh(w_d t) + zeta w / w_d sinh(w_d t)), w_d = w sqrt(zeta^2 - 1)

    Note that the overdamped case is exactly a *two-real-pole* (double exponential)
    response and the critically damped case is not: no single family covers both.
    """
    t = np.asarray(t, dtype=float)
    if abs(zeta - 1.0) <= 1e-12:
        return (1.0 + omega_n * t) * np.exp(-omega_n * t)
    if zeta < 1.0:
        wd = omega_n * np.sqrt(1.0 - zeta**2)
        return np.exp(-zeta * omega_n * t) * (np.cos(wd * t) + (zeta * omega_n / wd) * np.sin(wd * t))
    wd = omega_n * np.sqrt(zeta**2 - 1.0)
    return np.exp(-zeta * omega_n * t) * (np.cosh(wd * t) + (zeta * omega_n / wd) * np.sinh(wd * t))


def ground_truth_kernels(cfg: DynamicsConfig, t: np.ndarray) -> np.ndarray:
    """(T, d_art) rise kernels K_i(t) = 1 - g_i(t), one per articulatory mode.

    These are the exact temporal kernels that generate ``Delta u`` between two
    transitions sharing a source phone, and hence the ground truth for experiment 03.
    """
    rep = modal_report(cfg)
    return np.stack([1.0 - error_decay(w, z, t) for w, z in zip(rep.omega_n, rep.zeta, strict=True)], axis=1)


# --------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------


def simulate_linear(dyn: LinearDynamics, x0: np.ndarray, theta_seq: np.ndarray) -> np.ndarray:
    """Propagate a single segment exactly. Returns ``x`` of shape (T, 2 d_art).

    ``theta_seq`` is (T, d_art); the step from frame k to k+1 holds ``theta_seq[k]``.
    """
    T = theta_seq.shape[0]
    x = np.empty((T, dyn.Ad.shape[0]))
    x[0] = x0
    for k in range(T - 1):
        x[k + 1] = dyn.Ad @ x[k] + dyn.Bd @ theta_seq[k]
    return x


def simulate_linear_batch(dyn: LinearDynamics, x0: np.ndarray, theta_seq: np.ndarray) -> np.ndarray:
    """Vectorised ``simulate_linear`` over a batch.

    ``x0`` is (N, 2d), ``theta_seq`` is (N, T, d) or (T, d). Returns (N, T, 2d).
    """
    x0 = np.atleast_2d(x0)
    N = x0.shape[0]
    if theta_seq.ndim == 2:
        theta_seq = np.broadcast_to(theta_seq, (N, *theta_seq.shape))
    T = theta_seq.shape[1]
    out = np.empty((N, T, dyn.Ad.shape[0]))
    out[:, 0] = x0
    AdT, BdT = dyn.Ad.T, dyn.Bd.T
    for k in range(T - 1):
        out[:, k + 1] = out[:, k] @ AdT + theta_seq[:, k] @ BdT
    return out


def _nonlinear_rhs(x: np.ndarray, theta: np.ndarray, dyn: LinearDynamics, gain: float) -> np.ndarray:
    """x' for M u'' + C u' + K(u - theta) + gain * K (u - theta)^3 = 0."""
    d = dyn.d_art
    u, v = x[..., :d], x[..., d:]
    e = u - theta
    acc = -(e + gain * e**3) @ dyn.Minv_K.T - v @ dyn.Minv_C.T
    return np.concatenate([v, acc], axis=-1)


def simulate_nonlinear(
    dyn: LinearDynamics, x0: np.ndarray, theta_seq: np.ndarray, gain: float
) -> np.ndarray:
    """RK4 propagation of the cubic-stiffness variant (assumption stress test).

    Used only where the *generator* is deliberately non-linear; the linear path stays
    exact. With dt = 1 ms against omega_n ~ 30 rad/s this is ~200 steps per natural
    period, so RK4 error is far below every effect measured here.
    """
    x0 = np.atleast_2d(x0)
    N = x0.shape[0]
    if theta_seq.ndim == 2:
        theta_seq = np.broadcast_to(theta_seq, (N, *theta_seq.shape))
    T = theta_seq.shape[1]
    h = dyn.dt
    out = np.empty((N, T, 2 * dyn.d_art))
    out[:, 0] = x0
    for k in range(T - 1):
        th = theta_seq[:, k]
        x = out[:, k]
        k1 = _nonlinear_rhs(x, th, dyn, gain)
        k2 = _nonlinear_rhs(x + 0.5 * h * k1, th, dyn, gain)
        k3 = _nonlinear_rhs(x + 0.5 * h * k2, th, dyn, gain)
        k4 = _nonlinear_rhs(x + h * k3, th, dyn, gain)
        out[:, k + 1] = x + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return out


def acceleration(dyn: LinearDynamics, x: np.ndarray, theta_seq: np.ndarray, gain: float = 0.0) -> np.ndarray:
    """Ground-truth acceleration u'' implied by the state and the target."""
    d = dyn.d_art
    u, v = x[..., :d], x[..., d:]
    e = u - theta_seq
    if gain:
        e = e + gain * e**3
    return -(e @ dyn.Minv_K.T) - (v @ dyn.Minv_C.T)
