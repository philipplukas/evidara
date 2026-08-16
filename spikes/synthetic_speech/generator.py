"""Dataset generation: phone sequences -> targets -> dynamics -> acoustics -> observations.

A *segment* is one transition q -> r sampled on the canonical time grid. A *sequence* is
a chain of segments (``A B C A ...``). Everything an experiment can legitimately see is
in ``Dataset.observed`` / ``Dataset.source`` / ``Dataset.speaker``; everything else on
``Dataset`` is ground truth and is only available to experiments explicitly marked
ORACLE (see README, "Oracle discipline").

Speaker variation is applied as a *read-out warp* on the canonical trajectory:

    u_speaker(t) = A_{r,q} u(t) + b_{r,q},      S = H_r Phi(u_speaker(t)).

With ``regime="group"`` the chart ``(A, b)`` is the same for every phone q; with
``regime="groupoid"`` it depends on q. Applying the warp at read-out rather than inside
the dynamics is what makes those two regimes differ in *exactly* one respect, which is
what experiment 07 needs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

import numpy as np

from acoustics import PolynomialAcousticMap, make_acoustic_map
from config import ArticulatoryConfig, DynamicsConfig, Phone, Transition, WorldConfig
from dynamics import LinearDynamics, acceleration, simulate_linear_batch, simulate_nonlinear
from noise import NoiseModel, snr_report

__all__ = ["SpeakerModel", "Dataset", "generate", "build_world_parts", "affine_twin_world"]


# --------------------------------------------------------------------------------------
# Speakers
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeakerModel:
    """Per-(speaker, phone) affine articulatory charts and per-speaker acoustic mixing.

    ``A[s, q]`` and ``b[s, q]`` are the chart for speaker ``s`` while producing phone
    ``q``. In the ``group`` regime they are constant in ``q``. In the ``groupoid``
    regime the per-phone deviations are constructed to be **zero-mean across phones**,
    so the groupoid world has the same speaker-average chart as the group world and the
    only difference is the phone-local part.
    """

    A: np.ndarray  # (n_speakers, n_phones, d, d)
    b: np.ndarray  # (n_speakers, n_phones, d)
    H: np.ndarray  # (n_speakers, d_s, d_s)
    regime: str

    @classmethod
    def from_config(cls, world: WorldConfig) -> SpeakerModel:
        cfg = world.speaker
        d, d_s = world.d_art, world.d_acoustic
        n_sp, n_ph = cfg.n_speakers, world.articulatory.n_phones
        rng = np.random.default_rng(cfg.seed)

        A = np.tile(np.eye(d), (n_sp, n_ph, 1, 1))
        b = np.zeros((n_sp, n_ph, d))
        H = np.tile(np.eye(d_s), (n_sp, 1, 1))

        if cfg.regime != "single":
            dA = rng.normal(0.0, cfg.delta_A, size=(n_sp, d, d))
            db = rng.normal(0.0, cfg.delta_b, size=(n_sp, d))
            A = np.tile(np.eye(d), (n_sp, n_ph, 1, 1)) + dA[:, None, :, :]
            b = np.tile(db[:, None, :], (1, n_ph, 1))
            if cfg.regime == "groupoid":
                pA = rng.normal(0.0, cfg.delta_phone, size=(n_sp, n_ph, d, d))
                pb = rng.normal(0.0, cfg.delta_phone, size=(n_sp, n_ph, d))
                pA -= pA.mean(axis=1, keepdims=True)  # zero-mean across phones
                pb -= pb.mean(axis=1, keepdims=True)
                A = A + pA
                b = b + pb
            if cfg.acoustic_transform:
                H = np.tile(np.eye(d_s), (n_sp, 1, 1)) + rng.normal(
                    0.0, cfg.delta_H, size=(n_sp, d_s, d_s)
                )

        # speaker 0 is always the canonical speaker -- it anchors cross-world comparisons
        A[0] = np.eye(d)
        b[0] = 0.0
        H[0] = np.eye(d_s)
        return cls(A=A, b=b, H=H, regime=cfg.regime)

    def warp(self, u: np.ndarray, speaker: np.ndarray, phone: np.ndarray) -> np.ndarray:
        """Apply the chart to (n, T, d) trajectories given per-segment speaker/phone ids."""
        A = self.A[speaker, phone]  # (n, d, d)
        b = self.b[speaker, phone]  # (n, d)
        return np.einsum("nij,ntj->nti", A, u, optimize=True) + b[:, None, :]

    def mix(self, s: np.ndarray, speaker: np.ndarray) -> np.ndarray:
        """Apply H_r to (n, T, d_s) acoustics."""
        if np.allclose(self.H, np.eye(self.H.shape[-1])):
            return s
        return np.einsum("nij,ntj->nti", self.H[speaker], s, optimize=True)


# --------------------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------------------


@dataclass
class Dataset:
    """One generated corpus. Segment-major: every per-segment array has leading axis n."""

    config: WorldConfig
    phi: PolynomialAcousticMap
    dyn: LinearDynamics
    speakers: SpeakerModel
    noise_model: NoiseModel

    t: np.ndarray  # (T,) seconds
    phone_sequences: np.ndarray  # (n_seq, L) phone indices
    sequence_speaker: np.ndarray  # (n_seq,)

    # --- observable ---------------------------------------------------------------
    observed: np.ndarray  # (n, T, d_s)   S_obs
    source: np.ndarray  # (n,)          q index  (the phone being produced)
    speaker: np.ndarray  # (n,)
    sequence_index: np.ndarray  # (n,)
    position: np.ndarray  # (n,) segment index within its sequence

    # --- ground truth -------------------------------------------------------------
    following: np.ndarray  # (n,)          r index
    transition: np.ndarray  # (n,)          index into config.transitions()
    alpha: np.ndarray  # (n,)          asymptotic alpha_{qr}
    theta: np.ndarray  # (n, T, d)     transition target trajectory
    clean: np.ndarray  # (n, T, d_s)   Phi(u_speaker)
    latent_u: np.ndarray | None  # (n, T, d) canonical articulation
    latent_du: np.ndarray | None
    latent_d2u: np.ndarray | None
    latent_u_speaker: np.ndarray | None  # (n, T, d) after the speaker chart

    meta: dict = field(default_factory=dict)

    # -- convenience -------------------------------------------------------------------

    @property
    def n_segments(self) -> int:
        return self.observed.shape[0]

    @property
    def n_frames(self) -> int:
        return self.observed.shape[1]

    @property
    def phones(self) -> tuple[Phone, ...]:
        return self.config.articulatory.phones

    @property
    def transitions(self) -> list[Transition]:
        return self.config.transitions()

    def phone_index(self, q: Phone) -> int:
        return self.phones.index(q)

    def transition_index(self, q: Phone, r: Phone) -> int:
        return self.transitions.index((q, r))

    def mask(self, q: Phone | None = None, r: Phone | None = None, speaker: int | None = None) -> np.ndarray:
        m = np.ones(self.n_segments, dtype=bool)
        if q is not None:
            m &= self.source == self.phone_index(q)
        if r is not None:
            m &= self.following == self.phone_index(r)
        if speaker is not None:
            m &= self.speaker == speaker
        return m

    def mean_observed(self, q: Phone, r: Phone, speaker: int | None = None) -> np.ndarray:
        """E[S_obs(t) | q -> r] -- the only estimator experiment 01 is allowed to use."""
        return self.observed[self.mask(q, r, speaker)].mean(axis=0)

    def sem_observed(self, q: Phone, r: Phone, speaker: int | None = None) -> np.ndarray:
        sel = self.observed[self.mask(q, r, speaker)]
        return sel.std(axis=0, ddof=1) / np.sqrt(sel.shape[0])

    def frames(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Flatten to frames: (X, phone_label, speaker, segment_id) for frame classifiers."""
        n, T, d = self.observed.shape
        X = self.observed.reshape(n * T, d)
        y = np.repeat(self.source, T)
        sp = np.repeat(self.speaker, T)
        seg = np.repeat(np.arange(n), T)
        return X, y, sp, seg

    def snr(self) -> dict[str, float]:
        return snr_report(self.clean, self.noise_model.sigma)


# --------------------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------------------


def build_world_parts(world: WorldConfig) -> tuple[PolynomialAcousticMap, LinearDynamics, SpeakerModel, NoiseModel]:
    """The four deterministic objects a world implies (no randomness consumed)."""
    phi = make_acoustic_map(world.acoustic, world.d_art)
    dyn = LinearDynamics.from_config(world.dynamics, world.grid.dt)
    speakers = SpeakerModel.from_config(world)
    noise_model = NoiseModel.from_config(world.noise)
    return phi, dyn, speakers, noise_model


def _sample_sequences(world: WorldConfig, rng: np.random.Generator) -> np.ndarray:
    cfg = world.sequence
    n_ph = world.articulatory.n_phones
    seqs = np.empty((cfg.n_sequences, cfg.sequence_length), dtype=np.int64)
    seqs[:, 0] = rng.integers(0, n_ph, size=cfg.n_sequences)
    for j in range(1, cfg.sequence_length):
        if cfg.allow_repeats:
            seqs[:, j] = rng.integers(0, n_ph, size=cfg.n_sequences)
        else:
            step = rng.integers(1, n_ph, size=cfg.n_sequences)
            seqs[:, j] = (seqs[:, j - 1] + step) % n_ph
    return seqs


def _theta_table(world: WorldConfig) -> np.ndarray:
    """(n_transitions, T, d) target trajectories, one per transition."""
    return np.stack([world.theta_profile(q, r) for q, r in world.transitions()])


def generate(
    world: WorldConfig, seed: int | None = None, phi_override: PolynomialAcousticMap | None = None
) -> Dataset:
    """Generate a corpus from a fully specified world. Deterministic given the seed.

    ``phi_override`` replaces the acoustic map implied by ``world.acoustic``; it exists
    for the identifiability twin, whose Phi is a composition rather than a member of the
    parameterised family.
    """
    rng = np.random.default_rng(world.seed if seed is None else seed)
    phi, dyn, speakers, noise_model = build_world_parts(world)
    if phi_override is not None:
        phi = phi_override
    grid = world.grid
    T, d = grid.n_frames, world.d_art
    dtype = np.dtype(world.sequence.dtype)

    seqs = _sample_sequences(world, rng)
    n_seq, L = seqs.shape
    n_seg_per = L - 1
    seq_speaker = rng.integers(0, world.speaker.n_speakers, size=n_seq)

    source = seqs[:, :-1].reshape(-1)
    following = seqs[:, 1:].reshape(-1)
    sequence_index = np.repeat(np.arange(n_seq), n_seg_per)
    position = np.tile(np.arange(n_seg_per), n_seq)
    speaker = seq_speaker[sequence_index]
    n = source.size

    trans_list = world.transitions()
    trans_lookup = {(world.articulatory.phones.index(q), world.articulatory.phones.index(r)): i
                    for i, (q, r) in enumerate(trans_list)}
    transition = np.array([trans_lookup[(int(a), int(b))] for a, b in zip(source, following, strict=True)])
    alpha = np.array([world.anticipation.alpha(*trans_list[i]) for i in transition])

    theta_tab = _theta_table(world)  # (n_trans, T, d)
    targets = world.articulatory.target_matrix()  # (n_phones, d)

    # ---- initial conditions ----------------------------------------------------------
    x0 = np.zeros((n, 2 * d))
    x0[:, :d] = targets[source]
    v_scale = world.dynamics.initial_velocity_scale
    if v_scale:
        prev = np.where(position > 0, np.roll(source, 1), source)
        prev[position == 0] = source[position == 0]
        x0[:, d:] = v_scale * (targets[source] - targets[prev]) / (grid.duration_ms / 1000.0)

    # ---- propagate -------------------------------------------------------------------
    theta = theta_tab[transition]  # (n, T, d)
    if world.sequence.initial_condition == "continue":
        x = _simulate_chained(world, dyn, x0, theta, sequence_index, position, n_seg_per)
    elif world.dynamics.is_nonlinear:
        x = simulate_nonlinear(dyn, x0, theta, world.dynamics.cubic_gain)
    else:
        x = _simulate_by_transition(dyn, x0, theta_tab, transition, x0_is_shared=not v_scale)

    u, du = x[:, :, :d], x[:, :, d:]
    d2u = acceleration(dyn, x, theta, world.dynamics.cubic_gain)

    # ---- speaker chart + acoustics ---------------------------------------------------
    u_sp = speakers.warp(u, speaker, source) if world.speaker.regime != "single" else u
    clean = speakers.mix(phi.Phi(u_sp), speaker)
    eps = noise_model.sample((n, T), rng)
    observed = clean + eps

    store = world.sequence.store_latents
    return Dataset(
        config=world,
        phi=phi,
        dyn=dyn,
        speakers=speakers,
        noise_model=noise_model,
        t=grid.t,
        phone_sequences=seqs,
        sequence_speaker=seq_speaker,
        observed=observed.astype(dtype),
        source=source,
        speaker=speaker,
        sequence_index=sequence_index,
        position=position,
        following=following,
        transition=transition,
        alpha=alpha,
        theta=theta.astype(dtype),
        clean=clean.astype(dtype),
        latent_u=u.astype(dtype) if store else None,
        latent_du=du.astype(dtype) if store else None,
        latent_d2u=d2u.astype(dtype) if store else None,
        latent_u_speaker=u_sp.astype(dtype) if store else None,
        meta={"seed": world.seed if seed is None else seed, "n_sequences": n_seq},
    )


def affine_twin_world(
    world: WorldConfig, P: np.ndarray, p: np.ndarray
) -> tuple[WorldConfig, PolynomialAcousticMap, Callable[[np.ndarray], np.ndarray]]:
    r"""Build the second model of the identifiability pair (spec section 20).

    With the latent change of coordinates ``h(u) = P u + p``:

        targets:   u_q^{(2)} = h(u_q)          => theta^{(2)}_{qr} = h(theta_{qr})
                                                  (alpha is preserved -- h is affine and
                                                   theta is a convex combination)
        dynamics:  M2, C2, K2 = P M P^-1, P C P^-1, P K P^-1   =>  F2 = h . F1 . h^-1
        acoustics: Phi2 = Phi . h^-1                            =>  Phi2 . h = Phi1

    Both models therefore emit **bit-identical clean acoustics** from latent states that
    differ by ``h``. Returns ``(twin_world, Phi2, h)``.
    """
    P, p = np.asarray(P, float), np.asarray(p, float)
    Pinv = np.linalg.inv(P)

    def h(u: np.ndarray) -> np.ndarray:
        return np.asarray(u, float) @ P.T + p

    art = world.articulatory
    twin_targets = {q: h(art.target(q)) for q in art.phones}
    twin_art = ArticulatoryConfig(d_art=art.d_art, phones=art.phones, targets=twin_targets)
    dyn = world.dynamics
    twin_dyn = DynamicsConfig(
        d_art=dyn.d_art,
        M=P @ dyn.M @ Pinv,
        C=P @ dyn.C @ Pinv,
        K=P @ dyn.K @ Pinv,
        cubic_gain=dyn.cubic_gain,
        initial_velocity_scale=dyn.initial_velocity_scale,
    )
    twin_world = replace(world, articulatory=twin_art, dynamics=twin_dyn)
    phi_base = make_acoustic_map(world.acoustic, world.d_art)
    phi_twin = phi_base.compose_with_affine(Pinv, -(Pinv @ p))
    return twin_world, phi_twin, h


def _simulate_by_transition(
    dyn: LinearDynamics,
    x0: np.ndarray,
    theta_tab: np.ndarray,
    transition: np.ndarray,
    x0_is_shared: bool,
) -> np.ndarray:
    """Reset-mode fast path: in the linear world every segment of a given transition has
    an identical canonical trajectory, so we propagate once per transition (6 solves,
    not n)."""
    if not x0_is_shared:
        return simulate_linear_batch(dyn, x0, theta_tab[transition])
    d = dyn.d_art
    n_trans = theta_tab.shape[0]
    starts = np.zeros((n_trans, 2 * d))
    for i in range(n_trans):
        first = int(np.argmax(transition == i)) if np.any(transition == i) else 0
        starts[i] = x0[first]
    canon = simulate_linear_batch(dyn, starts, theta_tab)  # (n_trans, T, 2d)
    return canon[transition]


def _simulate_chained(
    world: WorldConfig,
    dyn: LinearDynamics,
    x0: np.ndarray,
    theta: np.ndarray,
    sequence_index: np.ndarray,
    position: np.ndarray,
    n_seg_per: int,
) -> np.ndarray:
    """``continue`` mode: the state carries over from the previous segment."""
    n, T, _ = theta.shape
    x = np.empty((n, T, x0.shape[1]))
    order = np.lexsort((position, sequence_index))
    state = None
    nonlinear = world.dynamics.is_nonlinear
    gain = world.dynamics.cubic_gain
    for start in range(0, n, n_seg_per):
        idx = order[start : start + n_seg_per]
        state = x0[idx[0]]
        for j in idx:
            xs = (
                simulate_nonlinear(dyn, state[None, :], theta[j][None, :, :], gain)
                if nonlinear
                else simulate_linear_batch(dyn, state[None, :], theta[j][None, :, :])
            )
            x[j] = xs[0]
            state = xs[0, -1]
    return x
