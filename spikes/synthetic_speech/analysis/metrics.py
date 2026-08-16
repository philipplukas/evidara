"""Error, model-comparison and identifiability metrics shared by every experiment."""

from __future__ import annotations

import numpy as np

__all__ = [
    "rmse",
    "r2",
    "gaussian_nll",
    "aic",
    "bic",
    "frobenius_error",
    "relative_error",
    "principal_angles",
    "subspace_error",
    "procrustes_error",
    "best_linear_map_error",
    "explained_variance_ratio",
    "IDENTIFIABLE",
    "PARTIAL",
    "NON_IDENTIFIABLE",
    "identifiability_verdict",
]

IDENTIFIABLE = "IDENTIFIABLE"
PARTIAL = "PARTIALLY IDENTIFIABLE"
NON_IDENTIFIABLE = "NON-IDENTIFIABLE"


# --------------------------------------------------------------------------------------
# Point errors
# --------------------------------------------------------------------------------------


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def r2(y: np.ndarray, y_hat: np.ndarray) -> float:
    """Coefficient of determination against the mean of ``y`` (can be negative)."""
    y, y_hat = np.asarray(y, float), np.asarray(y_hat, float)
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def frobenius_error(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b), "fro"))


def relative_error(estimate: np.ndarray, truth: np.ndarray) -> float:
    """||est - truth|| / ||truth|| in the Frobenius norm."""
    truth = np.asarray(truth, float)
    denom = np.linalg.norm(truth)
    return float(np.linalg.norm(np.asarray(estimate, float) - truth) / denom) if denom > 0 else float("nan")


# --------------------------------------------------------------------------------------
# Likelihood and model comparison
# --------------------------------------------------------------------------------------


def gaussian_nll(residual: np.ndarray, sigma: np.ndarray | float) -> float:
    """Total negative log-likelihood of residuals of shape (n, d) under N(0, sigma)."""
    res = np.asarray(residual, float).reshape(-1, np.shape(residual)[-1])
    n, d = res.shape
    if np.isscalar(sigma):
        sigma = np.eye(d) * float(sigma)
    sigma = np.asarray(sigma, float)
    sign, logdet = np.linalg.slogdet(sigma)
    if sign <= 0:
        raise ValueError("sigma must be positive definite")
    sol = np.linalg.solve(sigma, res.T).T
    quad = float(np.einsum("ij,ij->", res, sol))
    return 0.5 * (n * d * np.log(2 * np.pi) + n * logdet + quad)


def gaussian_nll_mle(residual: np.ndarray) -> tuple[float, np.ndarray]:
    """NLL at the MLE covariance of the residuals, plus that covariance."""
    res = np.asarray(residual, float).reshape(-1, np.shape(residual)[-1])
    n, d = res.shape
    sigma = (res.T @ res) / n + 1e-12 * np.eye(d)
    _, logdet = np.linalg.slogdet(sigma)
    return 0.5 * n * (d * np.log(2 * np.pi) + logdet + d), sigma


def aic(nll: float, k_params: int) -> float:
    return 2.0 * nll + 2.0 * k_params


def bic(nll: float, k_params: int, n_obs: int) -> float:
    return 2.0 * nll + k_params * np.log(n_obs)


# --------------------------------------------------------------------------------------
# Equivalence-class errors (Hypothesis 2)
# --------------------------------------------------------------------------------------


def principal_angles(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Principal angles (radians) between the column spaces of A and B."""
    qa = np.linalg.qr(np.asarray(A, float))[0]
    qb = np.linalg.qr(np.asarray(B, float))[0]
    s = np.linalg.svd(qa.T @ qb, compute_uv=False)
    return np.arccos(np.clip(s, -1.0, 1.0))


def subspace_error(A: np.ndarray, B: np.ndarray) -> float:
    """sin of the largest principal angle: 0 = same subspace, 1 = orthogonal directions.

    This is the right error for anything recoverable only *up to* a change of latent
    coordinates -- a Jacobian estimated blindly, for example, fixes a subspace but not a
    basis for it.
    """
    ang = principal_angles(A, B)
    return float(np.sin(ang.max())) if ang.size else 0.0


def procrustes_error(X: np.ndarray, Y: np.ndarray) -> float:
    """Relative error of Y against X after the best orthogonal alignment of Y to X."""
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    Xc, Yc = X - X.mean(0), Y - Y.mean(0)
    u, s, vt = np.linalg.svd(Yc.T @ Xc)
    R = u @ vt
    scale = s.sum() / max(np.sum(Yc**2), 1e-300)
    return relative_error(scale * (Yc @ R), Xc)


def best_linear_map_error(X: np.ndarray, Y: np.ndarray) -> tuple[float, np.ndarray]:
    """Residual of Y after the best affine map from X, relative to ||Y - mean(Y)||.

    Answers "is Y a linear reparametrisation of X?" -- 0 means yes, exactly.
    """
    X, Y = np.asarray(X, float), np.asarray(Y, float)
    Xa = np.hstack([X, np.ones((X.shape[0], 1))])
    coef, *_ = np.linalg.lstsq(Xa, Y, rcond=None)
    resid = Y - Xa @ coef
    denom = np.linalg.norm(Y - Y.mean(0))
    return float(np.linalg.norm(resid) / denom) if denom > 0 else float("nan"), coef


def explained_variance_ratio(singular_values: np.ndarray, k: int) -> float:
    """R_k = sum_{i<=k} lambda_i^2 / sum_i lambda_i^2."""
    s2 = np.asarray(singular_values, float) ** 2
    return float(s2[:k].sum() / s2.sum()) if s2.sum() > 0 else float("nan")


# --------------------------------------------------------------------------------------
# Identifiability verdicts (spec section 25.5)
# --------------------------------------------------------------------------------------


def identifiability_verdict(
    direct_error: float,
    equivalence_error: float | None = None,
    tol: float = 0.05,
) -> str:
    """Classify a parameter given its direct error and its error modulo an equivalence.

    * direct error within ``tol``                        -> IDENTIFIABLE
    * only the equivalence-class error within ``tol``    -> PARTIALLY IDENTIFIABLE
    * neither                                            -> NON-IDENTIFIABLE
    """
    if np.isfinite(direct_error) and direct_error <= tol:
        return IDENTIFIABLE
    if equivalence_error is not None and np.isfinite(equivalence_error) and equivalence_error <= tol:
        return PARTIAL
    return NON_IDENTIFIABLE
