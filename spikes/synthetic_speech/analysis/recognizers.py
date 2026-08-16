"""Three recognisers for segment-level transition classification (experiment 8).

The task is: given an observed segment S(0..T), name the transition (q, r) that produced
it. Six classes in the base world.

  FrameIndependent  p(c | S_t) from a logistic regression on single frames, averaged over
                    t. No temporal information whatsoever.
  GRU               a small recurrent network over the frame sequence. Generic temporal
                    capacity, no structural assumptions.
  Structured        estimates the generative parameters (phone targets, dynamics, alpha)
                    and *synthesises* a template for each class, then scores by Gaussian
                    likelihood. Can construct a class it has never seen.

The structured model is given the acoustic map Phi -- that is the "acoustic geometry"
layer of the framework being tested, not an estimate it is expected to produce. Every
experiment that uses it says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import expm
from sklearn.linear_model import LogisticRegression

from analysis.system_id import fit_trajectory_second_order, invert_nonlinear

__all__ = ["FrameIndependent", "GRURecogniser", "StructuredRecogniser", "torch_available"]


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------------------
# Baseline A -- frame independent
# --------------------------------------------------------------------------------------


@dataclass
class FrameIndependent:
    """p(c | S_t) averaged over frames. The temporal axis is discarded by construction."""

    C: float = 1.0
    max_iter: int = 400
    model: LogisticRegression | None = None
    classes_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> FrameIndependent:
        n, T, d = X.shape
        self.model = LogisticRegression(C=self.C, max_iter=self.max_iter)
        self.model.fit(X.reshape(n * T, d), np.repeat(y, T))
        self.classes_ = self.model.classes_
        return self

    def log_proba(self, X: np.ndarray) -> np.ndarray:
        n, T, d = X.shape
        lp = self.model.predict_log_proba(X.reshape(n * T, d)).reshape(n, T, -1)
        return lp.mean(axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.classes_[np.argmax(self.log_proba(X), axis=1)]


# --------------------------------------------------------------------------------------
# Baseline B -- generic temporal
# --------------------------------------------------------------------------------------


@dataclass
class GRURecogniser:
    """A small GRU over the frame sequence. Generic temporal model, no structure."""

    n_classes: int
    hidden: int = 48
    epochs: int = 40
    lr: float = 3e-3
    batch: int = 64
    seed: int = 0
    subsample: int = 4
    _net: object = field(default=None, repr=False)
    _mu: np.ndarray | None = None
    _sd: np.ndarray | None = None

    def _build(self, d_in: int):
        import torch
        from torch import nn

        torch.manual_seed(self.seed)

        class Net(nn.Module):
            def __init__(self, d_in, hidden, n_classes):
                super().__init__()
                self.gru = nn.GRU(d_in, hidden, batch_first=True)
                self.head = nn.Linear(hidden, n_classes)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.head(out[:, -1])

        return Net(d_in, self.hidden, self.n_classes)

    def fit(self, X: np.ndarray, y: np.ndarray) -> GRURecogniser:
        import torch
        from torch import nn

        Xs = X[:, :: self.subsample]
        self._mu, self._sd = Xs.mean((0, 1)), Xs.std((0, 1)) + 1e-8
        xb = torch.tensor((Xs - self._mu) / self._sd, dtype=torch.float32)
        yb = torch.tensor(y, dtype=torch.long)
        self._net = self._build(X.shape[-1])
        opt = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        loss_fn = nn.CrossEntropyLoss()
        g = torch.Generator().manual_seed(self.seed)
        n = xb.shape[0]
        for _ in range(self.epochs):
            perm = torch.randperm(n, generator=g)
            for i in range(0, n, self.batch):
                idx = perm[i : i + self.batch]
                opt.zero_grad()
                loss_fn(self._net(xb[idx]), yb[idx]).backward()
                opt.step()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        import torch

        Xs = (X[:, :: self.subsample] - self._mu) / self._sd
        with torch.no_grad():
            logits = self._net(torch.tensor(Xs, dtype=torch.float32))
        return logits.argmax(dim=1).numpy()


# --------------------------------------------------------------------------------------
# The structured recogniser
# --------------------------------------------------------------------------------------


def _zoh(A, B, dt):
    n, m = A.shape[0], B.shape[1]
    blk = np.zeros((n + m, n + m))
    blk[:n, :n], blk[:n, n:] = A, B
    E = expm(blk * dt)
    return E[:n, :n], E[:n, n:]


@dataclass
class StructuredRecogniser:
    r"""Generative classifier built from the assumed factorisation.

    q, r -> theta_{qr} -> second-order dynamics -> u(t) -> Phi -> S(t) + N(0, Sigma)

    Fitting estimates the phone targets, one shared pair (A_u, A_v), and one alpha per
    seen transition. Scoring synthesises the class template and takes a Gaussian
    likelihood. Because the template is *constructed* rather than memorised, a transition
    absent from training still gets a template -- built from its two phones' targets and
    the alpha prior. That is the whole point of the structure, and the reason the
    unseen-transition test is meaningful rather than a trick.
    """

    phi: object  # the acoustic map; ORACLE input, see the module docstring
    transitions: list[tuple[int, int]]
    dt: float
    n_frames: int
    randomise_dynamics: bool = False
    ignore_anticipation: bool = False
    seed: int = 0

    targets_: np.ndarray | None = None
    A_u_: np.ndarray | None = None
    A_v_: np.ndarray | None = None
    alpha_: dict | None = None
    alpha_prior_: float = 0.25
    sigma_: np.ndarray | None = None
    templates_: np.ndarray | None = None

    # -- fitting ------------------------------------------------------------------------

    def fit(self, X: np.ndarray, y: np.ndarray, d_art: int) -> StructuredRecogniser:
        seen = sorted(set(int(v) for v in y))
        means = {c: X[y == c].mean(axis=0) for c in seen}

        # 1. invert the class means into the latent, warm-started from the first frame
        latents = {}
        for c, S in means.items():
            u0 = self._cold_start(S[0], d_art)
            latents[c] = invert_nonlinear(S, self.phi.Phi, u0, self.phi.Dphi)

        # 2. phone targets: where a segment with source q *starts*
        n_phones = 1 + max(max(q, r) for q, r in self.transitions)
        targets = np.zeros((n_phones, d_art))
        for q in range(n_phones):
            starts = [latents[c][0] for c in seen if self.transitions[c][0] == q]
            if starts:
                targets[q] = np.mean(starts, axis=0)
        self.targets_ = targets

        # 3. one shared second-order system, fitted to all seen class trajectories at once
        U = np.stack([latents[c] for c in seen])
        U0 = np.stack([targets[self.transitions[c][0]] for c in seen])
        fit = fit_trajectory_second_order(U, self.dt, U0)
        if self.randomise_dynamics:
            rng = np.random.default_rng(self.seed)
            # a random *stable* second-order system on the same timescale: the ablation has
            # to keep the model class and change only the dynamics, or it tests nothing
            w = rng.uniform(8.0, 80.0, size=d_art)
            z = rng.uniform(0.4, 2.5, size=d_art)
            self.A_u_ = -np.diag(w**2)
            self.A_v_ = -np.diag(2 * z * w)
        else:
            self.A_u_, self.A_v_ = fit.A_u, fit.A_v

        # 4. alpha per seen transition, from theta = (1 - alpha) u_q + alpha u_r
        alpha = {}
        for i, c in enumerate(seen):
            q, r = self.transitions[c]
            diff = targets[r] - targets[q]
            denom = float(diff @ diff)
            alpha[c] = float((fit.targets[i] - targets[q]) @ diff / denom) if denom > 1e-12 else 0.0
        if self.ignore_anticipation:
            # second ablation: keep the dynamics and the phone targets, drop anticipation.
            # theta_{qr} collapses to u_q, so every class sharing a source phone becomes
            # the same template and only the source is recoverable.
            alpha = dict.fromkeys(alpha, 0.0)
            self.alpha_prior_ = 0.0
        else:
            self.alpha_prior_ = float(np.mean(list(alpha.values()))) if alpha else 0.25
        self.alpha_ = alpha

        # 5. templates for EVERY class, seen or not, plus the residual covariance
        self.templates_ = np.stack([self._template(c) for c in range(len(self.transitions))])
        resid = np.concatenate([X[y == c] - self.templates_[c] for c in seen])
        flat = resid.reshape(-1, resid.shape[-1])
        self.sigma_ = (flat.T @ flat) / flat.shape[0] + 1e-9 * np.eye(flat.shape[-1])
        return self

    def _cold_start(self, s0: np.ndarray, d_art: int) -> np.ndarray:
        """Least-squares latent for the first frame, used only to seed the inversion."""
        return np.linalg.pinv(self.phi.Dphi(np.zeros(d_art))) @ (s0 - self.phi.Phi(np.zeros(d_art)))

    def _template(self, c: int) -> np.ndarray:
        q, r = self.transitions[c]
        a = self.alpha_.get(c, self.alpha_prior_)
        theta = (1.0 - a) * self.targets_[q] + a * self.targets_[r]
        d = self.targets_.shape[1]
        A = np.zeros((2 * d, 2 * d))
        A[:d, d:] = np.eye(d)
        A[d:, :d], A[d:, d:] = self.A_u_, self.A_v_
        B = np.zeros((2 * d, d))
        B[d:, :] = -self.A_u_
        Ad, Bd = _zoh(A, B, self.dt)
        x = np.concatenate([self.targets_[q], np.zeros(d)])
        traj = np.empty((self.n_frames, d))
        traj[0] = x[:d]
        for k in range(self.n_frames - 1):
            x = Ad @ x + Bd @ theta
            traj[k + 1] = x[:d]
        return self.phi.Phi(traj)

    # -- scoring ------------------------------------------------------------------------

    def log_likelihoods(self, X: np.ndarray) -> np.ndarray:
        prec = np.linalg.inv(self.sigma_)
        out = np.empty((X.shape[0], self.templates_.shape[0]))
        for c in range(self.templates_.shape[0]):
            r = X - self.templates_[c]
            out[:, c] = -0.5 * np.einsum("ntd,de,nte->n", r, prec, r, optimize=True)
        return out

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.log_likelihoods(X), axis=1)
