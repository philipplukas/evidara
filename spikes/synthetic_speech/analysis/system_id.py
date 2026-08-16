"""Inverse problems: acoustics -> articulation -> dynamics (experiments 04 and 05).

Nothing here imports the generator. Where an estimator needs the acoustic map or its
Jacobian, the *caller* supplies it -- which is what makes the oracle boundary visible at
the call site rather than buried in a helper.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter

__all__ = [
    "smooth_and_differentiate",
    "invert_affine",
    "invert_nonlinear",
    "estimate_jacobian_by_probe",
    "estimate_tangent_blind",
    "SecondOrderFit",
    "fit_second_order_dynamics",
    "fit_first_order_dynamics",
]


# --------------------------------------------------------------------------------------
# Smoothing and numerical differentiation
# --------------------------------------------------------------------------------------


def smooth_and_differentiate(
    y: np.ndarray, dt: float, window: int = 41, polyorder: int = 4
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Savitzky-Golay smoothing plus its analytic first and second derivatives.

    A local polynomial of order ``polyorder`` is least-squares fitted in a sliding window
    of ``window`` samples and differentiated in closed form, so the derivative estimate
    never amplifies noise the way a raw finite difference does. Both knobs are reported
    by every experiment that uses this, because second derivatives of noisy data are the
    single most fragile step in the whole pipeline.

    ``y`` is (..., T, d); the time axis is -2.
    """
    if window % 2 == 0:
        window += 1
    window = min(window, y.shape[-2] - (1 - y.shape[-2] % 2))
    polyorder = min(polyorder, window - 1)
    kw = dict(window_length=window, polyorder=polyorder, axis=-2, mode="interp")
    y0 = savgol_filter(y, **kw)
    y1 = savgol_filter(y, deriv=1, delta=dt, **kw)
    y2 = savgol_filter(y, deriv=2, delta=dt, **kw)
    return y0, y1, y2


def trim_edges(arrays: list[np.ndarray], margin: int) -> list[np.ndarray]:
    """Drop ``margin`` frames from each end -- Savitzky-Golay is worst at the boundary."""
    return [a[..., margin:-margin, :] for a in arrays]


# --------------------------------------------------------------------------------------
# Acoustic inversion
# --------------------------------------------------------------------------------------


def invert_affine(S: np.ndarray, S0: np.ndarray, u0: np.ndarray, J: np.ndarray) -> np.ndarray:
    """u_hat = u0 + J^+ (S - S0): the local linear inverse of the acoustic map.

    ``J`` is supplied by the caller. Passing the analytic DPhi makes this the ORACLE
    inverse; passing an estimate makes it the blind one.
    """
    return u0 + (np.asarray(S, float) - S0) @ np.linalg.pinv(J).T


def invert_nonlinear(
    S: np.ndarray,
    phi: Callable[[np.ndarray], np.ndarray],
    u_init: np.ndarray,
    dphi: Callable[[np.ndarray], np.ndarray] | None = None,
) -> np.ndarray:
    """Frame-by-frame nonlinear least-squares inverse of ``phi``.

    Warm-started from the previous frame, which matters: the polynomial map is not
    globally injective, and a cold start can land in the wrong branch.
    """
    S = np.atleast_2d(np.asarray(S, float))
    out = np.empty((S.shape[0], np.size(u_init)))
    u = np.asarray(u_init, float).ravel().copy()
    for i, s in enumerate(S):
        res = least_squares(
            lambda uu, s=s: phi(uu) - s,
            u,
            jac=(lambda uu, s=s: dphi(uu)) if dphi is not None else "2-point",
            xtol=1e-12, ftol=1e-12, max_nfev=500,
        )
        u = res.x
        out[i] = u
    return out


# --------------------------------------------------------------------------------------
# Jacobian estimation
# --------------------------------------------------------------------------------------


@dataclass
class ProbeJacobian:
    jacobian: np.ndarray
    delta: float
    n_repeat: int


def estimate_jacobian_by_probe(
    observe: Callable[[np.ndarray, int], np.ndarray],
    u0: np.ndarray,
    delta: float,
    n_repeat: int = 1,
    central: bool = True,
) -> ProbeJacobian:
    """Estimate DPhi(u0) from *observations* at perturbed latent states.

    ``observe(u, n)`` must return ``n`` noisy observations of Phi(u). The latent state is
    chosen by the experimenter, which is why this is an ORACLE-INPUT probe (spec section
    18): it measures how well the acoustic Jacobian can be read off given controlled
    articulatory perturbations, and separates that from the harder blind problem.

    Central differences halve the O(delta) truncation bias; averaging ``n_repeat``
    observations shrinks the O(sigma / delta) noise term. Those two error sources move in
    opposite directions in ``delta``, which is exactly what experiment 05 sweeps.
    """
    u0 = np.asarray(u0, float)
    d = u0.size
    cols = []
    for j in range(d):
        step = np.zeros(d)
        step[j] = delta
        plus = observe(u0 + step, n_repeat).mean(axis=0)
        if central:
            minus = observe(u0 - step, n_repeat).mean(axis=0)
            cols.append((plus - minus) / (2 * delta))
        else:
            base = observe(u0, n_repeat).mean(axis=0)
            cols.append((plus - base) / delta)
    return ProbeJacobian(jacobian=np.stack(cols, axis=1), delta=delta, n_repeat=n_repeat)


def estimate_tangent_blind(
    cloud: np.ndarray, centre: np.ndarray, d_latent: int, k_neighbours: int = 60
) -> tuple[np.ndarray, np.ndarray]:
    """Local PCA tangent estimate at ``centre`` from an acoustic point cloud.

    Returns ``(basis, singular_values)`` where ``basis`` is (d_s, d_latent).

    This is the blind counterpart of the probe estimator, and it recovers something
    strictly weaker: the *column space* of DPhi, not DPhi itself. No acoustic-only
    method can do better -- relabelling the latent coordinates changes DPhi but leaves
    every observable distribution untouched (Hypothesis 2). Experiment 04 therefore
    scores the blind estimate with a subspace metric and the probe estimate with a
    Frobenius metric, and says so.
    """
    cloud = np.asarray(cloud, float)
    dist = np.linalg.norm(cloud - centre, axis=1)
    idx = np.argsort(dist)[: min(k_neighbours, cloud.shape[0])]
    local = cloud[idx]
    local = local - local.mean(axis=0)
    _, s, vt = np.linalg.svd(local, full_matrices=False)
    return vt[:d_latent].T, s


# --------------------------------------------------------------------------------------
# Dynamics identification
# --------------------------------------------------------------------------------------


@dataclass
class SecondOrderFit:
    r"""u'' = A_u u + A_v u' + c_g, with one intercept per group g."""

    A_u: np.ndarray
    A_v: np.ndarray
    intercepts: np.ndarray  # (n_groups, d)
    r2: float
    residual_rmse: float
    n_obs: int

    def implied_targets(self) -> np.ndarray:
        r"""theta_g = -A_u^{-1} c_g.

        The intercept absorbs -A_u theta_g, so identifying the dynamics also identifies
        the transition targets -- without ever being told what they are.
        """
        return -(self.intercepts @ np.linalg.inv(self.A_u).T)

    def predict(self, u: np.ndarray, du: np.ndarray, group: np.ndarray) -> np.ndarray:
        return u @ self.A_u.T + du @ self.A_v.T + self.intercepts[group]


def fit_second_order_dynamics(
    u: np.ndarray, du: np.ndarray, d2u: np.ndarray, group: np.ndarray | None = None
) -> SecondOrderFit:
    r"""Least-squares identification of the acceleration law.

    The true law is u'' = -M^-1 K (u - theta) - M^-1 C u', i.e. an intercept that depends
    on the transition. Fitting a *single* intercept across transitions would bias A_u; a
    per-group intercept both removes that bias and recovers theta as a by-product.
    """
    u, du, d2u = (np.asarray(a, float).reshape(-1, np.shape(a)[-1]) for a in (u, du, d2u))
    n, d = u.shape
    if group is None:
        group = np.zeros(n, dtype=int)
    group = np.asarray(group).reshape(-1)
    n_groups = int(group.max()) + 1

    dummies = np.zeros((n, n_groups))
    dummies[np.arange(n), group] = 1.0
    X = np.hstack([u, du, dummies])
    coef, *_ = np.linalg.lstsq(X, d2u, rcond=None)

    A_u, A_v = coef[:d].T, coef[d : 2 * d].T
    intercepts = coef[2 * d :]
    pred = X @ coef
    ss_res = float(np.sum((d2u - pred) ** 2))
    ss_tot = float(np.sum((d2u - d2u.mean(0)) ** 2))
    return SecondOrderFit(
        A_u=A_u, A_v=A_v, intercepts=intercepts,
        r2=1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        residual_rmse=float(np.sqrt(ss_res / d2u.size)),
        n_obs=n,
    )


@dataclass
class DiscreteFit:
    """Discrete-time state map ``x_{k+1} = A_d x_k + c_g`` and its continuous image."""

    A_d: np.ndarray
    A_c: np.ndarray
    intercepts: np.ndarray
    r2: float
    d: int

    @property
    def A_u(self) -> np.ndarray:
        return self.A_c[self.d :, : self.d]

    @property
    def A_v(self) -> np.ndarray:
        return self.A_c[self.d :, self.d :]

    def poles(self) -> np.ndarray:
        ev = np.linalg.eigvals(self.A_c)
        return ev[np.lexsort((ev.imag, ev.real))]


def fit_discrete_state_space(
    u: np.ndarray, du: np.ndarray, dt: float, group: np.ndarray | None = None
) -> DiscreteFit:
    r"""Identify the dynamics from the *one-step map* instead of from accelerations.

    Regressing ``x_{k+1}`` on ``x_k`` uses one numerical derivative (for velocity) where
    the acceleration law needs two, and each extra derivative multiplies the noise by
    roughly ``1/dt``. The continuous generator is then ``A_c = log(A_d) / dt``, which is
    exact for a zero-order-hold system -- the same discretisation the generator uses.

    ``u`` and ``du`` are (n_groups, T, d) trajectories on a uniform grid.
    """
    from scipy.linalg import logm

    u, du = np.asarray(u, float), np.asarray(du, float)
    if u.ndim == 2:
        u, du = u[None], du[None]
    n_groups, T, d = u.shape
    if group is None:
        group = np.arange(n_groups)
    group = np.asarray(group).reshape(-1)
    n_g = int(group.max()) + 1

    x = np.concatenate([u, du], axis=-1)
    X0 = x[:, :-1].reshape(-1, 2 * d)
    X1 = x[:, 1:].reshape(-1, 2 * d)
    g = np.repeat(group, T - 1)
    dummies = np.zeros((X0.shape[0], n_g))
    dummies[np.arange(X0.shape[0]), g] = 1.0
    design = np.hstack([X0, dummies])
    coef, *_ = np.linalg.lstsq(design, X1, rcond=None)
    A_d = coef[: 2 * d].T
    pred = design @ coef
    ss_res = float(np.sum((X1 - pred) ** 2))
    ss_tot = float(np.sum((X1 - X1.mean(0)) ** 2))
    A_c = np.real(logm(A_d)) / dt
    return DiscreteFit(
        A_d=A_d, A_c=A_c, intercepts=coef[2 * d :],
        r2=1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"), d=d,
    )


def fit_ar2_poles(u: np.ndarray, dt: float, group: np.ndarray | None = None) -> np.ndarray:
    r"""Continuous-time poles from a matrix AR(2) fit -- **no differentiation at all**.

    Eliminating the velocity from the zero-order-hold recursion gives exactly

        u_{k+2} = F1 u_{k+1} + F2 u_k + c_g,

    whose companion matrix is similar to the discrete state matrix and therefore shares
    its eigenvalues. So the poles of the articulatory dynamics are estimable from
    positions alone. The state matrix itself is not: the companion form lives in the
    basis ``(u_{k+1}, u_k)``, and no amount of data fixes the change of basis to
    ``(u, u')``. That is Hypothesis 2 appearing as a concrete, checkable statement.
    """
    u = np.asarray(u, float)
    if u.ndim == 2:
        u = u[None]
    n_groups, T, d = u.shape
    if group is None:
        group = np.arange(n_groups)
    group = np.asarray(group).reshape(-1)
    n_g = int(group.max()) + 1

    Y = u[:, 2:].reshape(-1, d)
    X = np.hstack([u[:, 1:-1].reshape(-1, d), u[:, :-2].reshape(-1, d)])
    g = np.repeat(group, T - 2)
    dummies = np.zeros((X.shape[0], n_g))
    dummies[np.arange(X.shape[0]), g] = 1.0
    coef, *_ = np.linalg.lstsq(np.hstack([X, dummies]), Y, rcond=None)
    F1, F2 = coef[:d].T, coef[d : 2 * d].T
    comp = np.zeros((2 * d, 2 * d))
    comp[:d, :d] = F1
    comp[:d, d:] = F2
    comp[d:, :d] = np.eye(d)
    lam = np.linalg.eigvals(comp)
    poles = np.log(lam.astype(complex)) / dt
    return poles[np.lexsort((poles.imag, poles.real))]


@dataclass
class TrajectoryFit:
    r"""Second-order dynamics fitted to trajectories directly, without differentiating."""

    A_u: np.ndarray
    A_v: np.ndarray
    targets: np.ndarray  # (n_groups, d)
    v0: np.ndarray  # (d,) shared initial velocity
    residual_rmse: float
    n_params: int

    def poles(self) -> np.ndarray:
        d = self.A_u.shape[0]
        A = np.zeros((2 * d, 2 * d))
        A[:d, d:] = np.eye(d)
        A[d:, :d] = self.A_u
        A[d:, d:] = self.A_v
        ev = np.linalg.eigvals(A)
        return ev[np.lexsort((ev.imag, ev.real))]


def _zoh(A: np.ndarray, B: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    from scipy.linalg import expm

    n, m = A.shape[0], B.shape[1]
    blk = np.zeros((n + m, n + m))
    blk[:n, :n], blk[:n, n:] = A, B
    E = expm(blk * dt)
    return E[:n, :n], E[:n, n:]


def fit_trajectory_second_order(
    u_traj: np.ndarray, dt: float, u_start: np.ndarray, max_nfev: int = 4000
) -> TrajectoryFit:
    r"""Fit ``u'' = A_u (u - theta_g) + A_v u'`` to trajectories by simulation, not by
    differentiation.

    ``u_traj`` is (n_groups, T, d) and ``u_start`` is (n_groups, d).

    Numerical differentiation is the fragile step in the whole pipeline: each derivative
    multiplies observation noise by ~1/dt, and the resulting errors-in-variables bias
    *attenuates* the regression coefficients rather than merely scattering them. Fitting
    the forward model instead trades a linear least-squares problem for a nonlinear one
    and avoids that entirely -- the free parameters here are only 2 d^2 + n_groups * d.
    """
    u_traj = np.asarray(u_traj, float)
    n_g, T, d = u_traj.shape
    u_start = np.asarray(u_start, float).reshape(n_g, d)

    def unpack(p):
        A_u = p[: d * d].reshape(d, d)
        A_v = p[d * d : 2 * d * d].reshape(d, d)
        theta = p[2 * d * d : 2 * d * d + n_g * d].reshape(n_g, d)
        v0 = p[2 * d * d + n_g * d :]
        return A_u, A_v, theta, v0

    def simulate(p):
        A_u, A_v, theta, v0 = unpack(p)
        A = np.zeros((2 * d, 2 * d))
        A[:d, d:] = np.eye(d)
        A[d:, :d] = A_u
        A[d:, d:] = A_v
        B = np.zeros((2 * d, d))
        B[d:, :] = -A_u
        Ad, Bd = _zoh(A, B, dt)
        x = np.concatenate([u_start, np.tile(v0, (n_g, 1))], axis=1)
        out = np.empty((n_g, T, d))
        out[:, 0] = x[:, :d]
        for k in range(T - 1):
            x = x @ Ad.T + theta @ Bd.T
            out[:, k + 1] = x[:, :d]
        return out

    # initialise from a crude, well-conditioned guess: settled value as the target and a
    # decay rate read off the time to 63% of the excursion
    theta0 = u_traj[:, -1, :]
    span = np.abs(theta0 - u_start).max(axis=0)
    scale = 4.0 / max(T * dt, 1e-9)
    A_u0 = -np.eye(d) * scale**2
    A_v0 = -np.eye(d) * 2.0 * scale
    p0 = np.concatenate([A_u0.ravel(), A_v0.ravel(), theta0.ravel(), np.zeros(d)])
    # x_scale="jac" is not a nicety here: the parameters span three orders of magnitude
    # (A_u entries ~ -900 against targets ~ 0.5), and an unscaled trust region spends most
    # of its budget crawling along the stiff directions. At d_art = 5 that is the
    # difference between seconds and many minutes.
    res = least_squares(
        lambda p: (simulate(p) - u_traj).ravel(), p0,
        max_nfev=max_nfev, xtol=1e-13, ftol=1e-13, x_scale="jac",
    )
    A_u, A_v, theta, v0 = unpack(res.x)
    _ = span
    return TrajectoryFit(
        A_u=A_u, A_v=A_v, targets=theta, v0=v0,
        residual_rmse=float(np.sqrt(np.mean((simulate(res.x) - u_traj) ** 2))),
        n_params=int(res.x.size),
    )


def fit_first_order_dynamics(u: np.ndarray, du: np.ndarray, group: np.ndarray | None = None):
    """u' = A u + c_g -- the deliberately mis-specified first-order alternative."""
    u, du = (np.asarray(a, float).reshape(-1, np.shape(a)[-1]) for a in (u, du))
    n, d = u.shape
    if group is None:
        group = np.zeros(n, dtype=int)
    group = np.asarray(group).reshape(-1)
    n_groups = int(group.max()) + 1
    dummies = np.zeros((n, n_groups))
    dummies[np.arange(n), group] = 1.0
    X = np.hstack([u, dummies])
    coef, *_ = np.linalg.lstsq(X, du, rcond=None)
    pred = X @ coef
    ss_res = float(np.sum((du - pred) ** 2))
    ss_tot = float(np.sum((du - du.mean(0)) ** 2))
    return coef[:d].T, coef[d:], 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
