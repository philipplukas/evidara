"""The nonlinear acoustic map Phi: R^{d_art} -> R^{d_acoustic}, with analytic Jacobian.

The default map is exactly the spec's:

    Phi(u) = ( u1 + 0.15 u1 u2,
               2 u2 + 0.10 u1^2,
               u1 - u2 + 0.08 u1 u2 )

represented as ``W u + u^T Q u`` with symmetric ``Q``, which generalises cleanly to any
(d_art, d_acoustic) and keeps the Jacobian closed-form:

    DPhi(u)_{ij} = W_{ij} + 2 sum_k Q_{ijk} u_k.

``verify_jacobian`` (and the mandatory test in ``tests/test_acoustics.py``) checks this
against central finite differences.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import AcousticConfig

__all__ = [
    "PolynomialAcousticMap",
    "make_acoustic_map",
    "finite_difference_jacobian",
    "verify_jacobian",
]


@dataclass(frozen=True)
class PolynomialAcousticMap:
    r"""Phi(u) = saturate(W u + u^T Q u) with Q symmetric in its last two indices.

    ``saturation`` is ``None`` for the polynomial maps. When set to ``s``, the output is
    ``s * tanh(p / s)``, which is smooth, invertible on the working range and strongly
    nonlinear -- used for the "wrong acoustic map" stress test.
    """

    W: np.ndarray  # (d_s, d_u)
    Q: np.ndarray  # (d_s, d_u, d_u), symmetric in the last two axes
    saturation: float | None = None
    bias: np.ndarray | None = None  # (d_s,), non-zero only for composed maps

    def __post_init__(self) -> None:
        if self.bias is None:
            object.__setattr__(self, "bias", np.zeros(self.W.shape[0]))
        if self.Q.shape[1:] != (self.W.shape[1], self.W.shape[1]):
            raise ValueError(f"Q shape {self.Q.shape} inconsistent with W shape {self.W.shape}")
        if not np.allclose(self.Q, np.swapaxes(self.Q, 1, 2)):
            raise ValueError("Q must be symmetric in its last two axes")

    @property
    def d_art(self) -> int:
        return self.W.shape[1]

    @property
    def d_acoustic(self) -> int:
        return self.W.shape[0]

    # -- forward -----------------------------------------------------------------------

    def _poly(self, u: np.ndarray) -> np.ndarray:
        lin = u @ self.W.T
        quad = np.einsum("ijk,...j,...k->...i", self.Q, u, u, optimize=True)
        return self.bias + lin + quad

    def compose_with_affine(self, A: np.ndarray, c: np.ndarray) -> PolynomialAcousticMap:
        r"""Return ``v -> Phi(A v + c)``, still inside the polynomial family.

        Used to build the identifiability twin: with ``h(u) = P u + p`` and
        ``A = P^-1``, ``c = -P^-1 p``, the composed map satisfies ``Phi_2 . h = Phi``
        exactly, so the two worlds emit the *same* acoustics from different latents.
        """
        A, c = np.asarray(A, float), np.asarray(c, float)
        Qc = np.einsum("ijk,k->ij", self.Q, c, optimize=True)
        W2 = self.W @ A + 2.0 * (Qc @ A)
        Q2 = np.einsum("ja,ijk,kb->iab", A, self.Q, A, optimize=True)
        Q2 = 0.5 * (Q2 + np.swapaxes(Q2, 1, 2))
        bias2 = self.bias + self.W @ c + np.einsum("ijk,j,k->i", self.Q, c, c, optimize=True)
        return PolynomialAcousticMap(W=W2, Q=Q2, saturation=self.saturation, bias=bias2)

    def Phi(self, u: np.ndarray) -> np.ndarray:
        """Acoustic observation for latent ``u`` of shape (..., d_art)."""
        p = self._poly(np.asarray(u, dtype=float))
        if self.saturation is None:
            return p
        return self.saturation * np.tanh(p / self.saturation)

    __call__ = Phi

    # -- Jacobian ----------------------------------------------------------------------

    def Dphi(self, u: np.ndarray) -> np.ndarray:
        """Analytic Jacobian of shape (..., d_acoustic, d_art)."""
        u = np.asarray(u, dtype=float)
        jac = self.W + 2.0 * np.einsum("ijk,...k->...ij", self.Q, u, optimize=True)
        if self.saturation is None:
            return jac
        p = self._poly(u)
        sech2 = 1.0 / np.cosh(p / self.saturation) ** 2
        return sech2[..., :, None] * jac

    def linearise(self, u0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(Phi(u0), DPhi(u0)) -- the local affine model used by the oracle inverse."""
        return self.Phi(u0), self.Dphi(u0)


# --------------------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------------------


def _canonical_W_Q() -> tuple[np.ndarray, np.ndarray]:
    """The spec's 3-dimensional map over a 2-dimensional articulatory space."""
    W = np.array([[1.0, 0.0], [0.0, 2.0], [1.0, -1.0]])
    Q = np.zeros((3, 2, 2))
    Q[0, 0, 1] = Q[0, 1, 0] = 0.075  # 0.15 u1 u2
    Q[1, 0, 0] = 0.10  # 0.10 u1^2
    Q[2, 0, 1] = Q[2, 1, 0] = 0.04  # 0.08 u1 u2
    return W, Q


def make_acoustic_map(cfg: AcousticConfig, d_art: int) -> PolynomialAcousticMap:
    """Build the acoustic map for a world.

    The canonical 3x2 block is preserved wherever it fits, so that higher-dimensional
    worlds are strict extensions of the base world rather than unrelated systems.
    Additional rows/columns are drawn deterministically from ``cfg.seed``.
    """
    d_s = cfg.d_acoustic
    rng = np.random.default_rng(cfg.seed)

    W = np.zeros((d_s, d_art))
    Q = np.zeros((d_s, d_art, d_art))
    Wc, Qc = _canonical_W_Q()
    rs, cs = min(d_s, 3), min(d_art, 2)
    W[:rs, :cs] = Wc[:rs, :cs]
    Q[:rs, :cs, :cs] = Qc[:rs, :cs, :cs]

    if d_s > 3 or d_art > 2:
        extra_W = rng.normal(0.0, 0.8, size=(d_s, d_art))
        extra_Q = rng.normal(0.0, 0.06, size=(d_s, d_art, d_art))
        extra_Q = 0.5 * (extra_Q + np.swapaxes(extra_Q, 1, 2))
        mask = np.ones((d_s, d_art), dtype=bool)
        mask[:rs, :cs] = False
        W = np.where(mask, extra_W, W)
        qmask = np.ones((d_s, d_art, d_art), dtype=bool)
        qmask[:rs, :cs, :cs] = False
        Q = np.where(qmask, extra_Q, Q)

    if cfg.kind == "linear":
        Q = np.zeros_like(Q)
        saturation = None
    elif cfg.kind == "strong_nonlinear":
        Q = Q * (6.0 * cfg.nonlinearity_scale)
        saturation = 1.5
    else:
        Q = Q * cfg.nonlinearity_scale
        saturation = None

    return PolynomialAcousticMap(W=W, Q=Q, saturation=saturation)


# --------------------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------------------


def finite_difference_jacobian(fn, u: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Central-difference Jacobian of ``fn`` at a single point ``u``."""
    u = np.asarray(u, dtype=float)
    base = np.atleast_1d(fn(u))
    jac = np.empty((base.shape[-1], u.shape[-1]))
    for j in range(u.shape[-1]):
        step = np.zeros_like(u)
        step[j] = eps
        jac[:, j] = (fn(u + step) - fn(u - step)) / (2.0 * eps)
    return jac


def verify_jacobian(
    phi: PolynomialAcousticMap, points: np.ndarray, eps: float = 1e-6
) -> tuple[float, np.ndarray]:
    """Max absolute analytic-vs-finite-difference Jacobian error over ``points``.

    This check is mandatory (spec section 7) -- every experiment that touches DPhi
    calls it, and ``tests/test_acoustics.py`` asserts it stays below 1e-7.
    """
    points = np.atleast_2d(points)
    errs = np.empty(points.shape[0])
    for i, u in enumerate(points):
        errs[i] = np.max(np.abs(phi.Dphi(u) - finite_difference_jacobian(phi.Phi, u, eps)))
    return float(errs.max()), errs
