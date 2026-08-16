"""Transition contrasts and their temporal rank (experiments 01 and 02).

Everything here reads ``Dataset.observed`` only -- no latent variable is touched.

The central object is the contrast

    Delta S_{q; r1, r2}(t) = E[S(t) | q -> r1] - E[S(t) | q -> r2],

which is exactly zero under the no-anticipation control and, under anticipation, has a
ground-truth rank equal to the number of *distinct articulatory modes* excited (2 in the
base world) plus whatever the acoustic nonlinearity leaks into higher components.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from analysis.metrics import explained_variance_ratio

__all__ = [
    "Contrast",
    "contrast",
    "all_contrasts",
    "stack_contrasts",
    "RankSpectrum",
    "temporal_rank",
    "bootstrap_contrast_ci",
]


@dataclass(frozen=True)
class Contrast:
    """One ``q -> r1`` vs ``q -> r2`` acoustic contrast."""

    source: str
    r1: str
    r2: str
    delta: np.ndarray  # (T, d_s)
    sem: np.ndarray  # (T, d_s) standard error of the difference of means
    n1: int
    n2: int

    @property
    def label(self) -> str:
        return f"{self.source}->{self.r1} vs {self.source}->{self.r2}"

    def z(self) -> np.ndarray:
        """Pointwise z statistic of the contrast."""
        return self.delta / np.where(self.sem > 0, self.sem, np.inf)

    def peak_abs(self) -> float:
        return float(np.max(np.abs(self.delta)))


def contrast(ds, source: str, r1: str, r2: str, speaker: int | None = None, field: str = "observed") -> Contrast:
    """Mean-difference contrast between two transitions that share a source phone.

    ``field="clean"`` is ORACLE-only and exists so experiments can separate estimator
    error from observation noise; the default is the observable one.
    """
    arr = getattr(ds, field)
    a = arr[ds.mask(source, r1, speaker)]
    b = arr[ds.mask(source, r2, speaker)]
    if a.shape[0] < 2 or b.shape[0] < 2:
        raise ValueError(f"not enough segments for {source}->{r1} ({a.shape[0]}) / {source}->{r2} ({b.shape[0]})")
    sem = np.sqrt(a.var(axis=0, ddof=1) / a.shape[0] + b.var(axis=0, ddof=1) / b.shape[0])
    return Contrast(
        source=source, r1=r1, r2=r2,
        delta=a.mean(axis=0) - b.mean(axis=0), sem=sem, n1=a.shape[0], n2=b.shape[0],
    )


def all_contrasts(ds, speaker: int | None = None, field: str = "observed") -> list[Contrast]:
    """Every within-source pair of following phones, in a stable order."""
    out: list[Contrast] = []
    phones = ds.phones
    for q in phones:
        followers = [r for r in phones if (q, r) in ds.transitions]
        for r1, r2 in combinations(followers, 2):
            try:
                out.append(contrast(ds, q, r1, r2, speaker=speaker, field=field))
            except ValueError:
                continue
    return out


def stack_contrasts(contrasts: list[Contrast]) -> np.ndarray:
    """(T, P * d_s) design used for the *pooled* rank test.

    The per-contrast matrix of spec section 15 has at most ``d_s`` columns, so its rank
    is capped by the acoustic dimension rather than by the temporal structure. Pooling
    every contrast into one matrix removes that ceiling and asks the sharper question:
    does one low-dimensional temporal subspace serve *all* transitions?
    """
    return np.concatenate([c.delta for c in contrasts], axis=1)


@dataclass(frozen=True)
class RankSpectrum:
    """SVD summary of a temporal design matrix X (T x m)."""

    singular_values: np.ndarray
    U: np.ndarray  # (T, k) temporal components
    Vt: np.ndarray  # (k, m) loadings

    def ratio(self, k: int) -> float:
        return explained_variance_ratio(self.singular_values, k)

    def ratios(self, kmax: int = 5) -> dict[int, float]:
        kmax = min(kmax, self.singular_values.size)
        return {k: self.ratio(k) for k in range(1, kmax + 1)}

    def component(self, k: int) -> np.ndarray:
        """The k-th temporal component (1-indexed), sign-fixed to end positive."""
        v = self.U[:, k - 1]
        return v if v[np.argmax(np.abs(v))] >= 0 else -v


def temporal_rank(X: np.ndarray) -> RankSpectrum:
    """SVD of a (T, m) temporal design matrix. No centring: Delta S(0) = 0 by construction."""
    U, s, Vt = np.linalg.svd(np.asarray(X, float), full_matrices=False)
    return RankSpectrum(singular_values=s, U=U, Vt=Vt)


def bootstrap_contrast_ci(
    ds,
    source: str,
    r1: str,
    r2: str,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 0,
    speaker: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Percentile bootstrap over segments. Returns (point estimate, lower, upper).

    Resampling is over *segments*, which is the unit of independent replication here:
    frames within a segment share one latent trajectory and are not exchangeable.
    """
    rng = np.random.default_rng(seed)
    a = ds.observed[ds.mask(source, r1, speaker)]
    b = ds.observed[ds.mask(source, r2, speaker)]
    point = a.mean(axis=0) - b.mean(axis=0)
    boots = np.empty((n_boot, *point.shape))
    for i in range(n_boot):
        ia = rng.integers(0, a.shape[0], a.shape[0])
        ib = rng.integers(0, b.shape[0], b.shape[0])
        boots[i] = a[ia].mean(axis=0) - b[ib].mean(axis=0)
    lo = np.quantile(boots, alpha / 2, axis=0)
    hi = np.quantile(boots, 1 - alpha / 2, axis=0)
    return point, lo, hi


def simultaneous_band(
    ds,
    source: str,
    r1: str,
    r2: str,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 0,
    speaker: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Sup-t bootstrap band with *simultaneous* coverage over frames and dimensions.

    A pointwise 95% band on a (T x d) contrast is not a 95% statement about the contrast:
    with T = 201 and d = 3 it flags roughly one frame in seven under a true null. The
    sup-t band takes the bootstrap distribution of ``max_{t,j} |boot - point| / sem`` and
    uses its 95th percentile as a single critical value, so "the band excludes zero
    anywhere" is a 5%-level statement about the whole trajectory.

    Returns ``(point, lower, upper, critical_value)``.
    """
    rng = np.random.default_rng(seed)
    a = ds.observed[ds.mask(source, r1, speaker)]
    b = ds.observed[ds.mask(source, r2, speaker)]
    point = a.mean(axis=0) - b.mean(axis=0)
    sem = np.sqrt(a.var(axis=0, ddof=1) / a.shape[0] + b.var(axis=0, ddof=1) / b.shape[0])
    sem = np.where(sem > 0, sem, np.inf)
    sup = np.empty(n_boot)
    for i in range(n_boot):
        ia = rng.integers(0, a.shape[0], a.shape[0])
        ib = rng.integers(0, b.shape[0], b.shape[0])
        boot = a[ia].mean(axis=0) - b[ib].mean(axis=0)
        sup[i] = np.max(np.abs(boot - point) / sem)
    crit = float(np.quantile(sup, 1 - alpha))
    return point, point - crit * sem, point + crit * sem, crit
