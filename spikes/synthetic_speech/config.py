"""Ground-truth configuration for the synthetic speech world.

Every number in this module is a *known* generative parameter. Inference code must
never import ground truth from here except through an explicitly ``oracle_``-prefixed
path (see the methodological rule in README.md §"Oracle discipline").

The world is:

    q -> theta_{qr} -> F (second-order dynamics) -> u(t) -> Phi -> S(t) + eps, eps ~ N(0, Sigma)

This module only *declares* the parameters. ``dynamics``, ``acoustics``, ``noise`` and
``generator`` turn them into trajectories.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np

Phone = str
Transition = tuple[Phone, Phone]

# --------------------------------------------------------------------------------------
# Canonical constants (spec sections 2, 3, 4, 7, 9)
# --------------------------------------------------------------------------------------

DEFAULT_PHONES: tuple[Phone, ...] = ("A", "B", "C")

#: Abstract articulatory coordinates. NOT tongue/jaw -- see README.
DEFAULT_TARGETS_2D: dict[Phone, tuple[float, ...]] = {
    "A": (0.0, 0.0),
    "B": (1.0, 0.3),
    "C": (-0.4, 1.0),
}

#: Transition-dependent anticipation coefficients (Condition III).
DEFAULT_ALPHA: dict[Transition, float] = {
    ("A", "B"): 0.35,
    ("A", "C"): 0.20,
    ("B", "A"): 0.25,
    ("B", "C"): 0.30,
    ("C", "A"): 0.20,
    ("C", "B"): 0.25,
}

#: Literal spec covariance for d_acoustic = 3.
DEFAULT_SIGMA_3 = np.array(
    [
        [1.0, 0.7, 0.3],
        [0.7, 1.5, 0.6],
        [0.3, 0.6, 0.8],
    ]
)

AnticipationCondition = Literal["none", "shared", "transition", "time_varying"]
NoiseRegime = Literal["white", "correlated", "strong"]
SpeakerRegime = Literal["single", "group", "groupoid"]
AcousticKind = Literal["polynomial", "linear", "strong_nonlinear"]
InitialConditionMode = Literal["reset", "continue"]


def _frozen(a: np.ndarray) -> np.ndarray:
    """Return a read-only copy so ground truth cannot be mutated by inference code."""
    out = np.array(a, dtype=float)
    out.setflags(write=False)
    return out


# --------------------------------------------------------------------------------------
# Articulatory space
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArticulatoryConfig:
    """Latent articulatory space: phones and their canonical targets u_q in R^{d_art}."""

    d_art: int = 2
    phones: tuple[Phone, ...] = DEFAULT_PHONES
    targets: dict[Phone, np.ndarray] = field(default_factory=dict)
    target_seed: int = 20260812

    def __post_init__(self) -> None:
        if not self.targets:
            object.__setattr__(self, "targets", _default_targets(self.phones, self.d_art, self.target_seed))
        for q in self.phones:
            if q not in self.targets:
                raise ValueError(f"no target for phone {q!r}")
            if self.targets[q].shape != (self.d_art,):
                raise ValueError(f"target for {q!r} has shape {self.targets[q].shape}, expected ({self.d_art},)")

    @property
    def n_phones(self) -> int:
        return len(self.phones)

    def target(self, q: Phone) -> np.ndarray:
        return self.targets[q]

    def target_matrix(self) -> np.ndarray:
        """(n_phones, d_art) stack of targets, ordered as ``self.phones``."""
        return np.stack([self.targets[q] for q in self.phones])


def _default_targets(phones: tuple[Phone, ...], d_art: int, seed: int) -> dict[Phone, np.ndarray]:
    """Canonical 2-D targets for A/B/C, deterministically extended to other shapes.

    The first two coordinates of A, B, C always match ``DEFAULT_TARGETS_2D`` so that
    higher-dimensional worlds remain comparable to the base world.
    """
    rng = np.random.default_rng(seed)
    out: dict[Phone, np.ndarray] = {}
    for i, q in enumerate(phones):
        vec = np.zeros(d_art)
        base = DEFAULT_TARGETS_2D.get(q)
        n_base = 0
        if base is not None:
            n_base = min(d_art, len(base))
            vec[:n_base] = base[:n_base]
        if n_base < d_art:
            # deterministic, well-separated filler coordinates
            vec[n_base:] = rng.uniform(-0.6, 1.0, size=d_art - n_base)
            if base is None:
                vec[:n_base] = rng.uniform(-0.6, 1.0, size=n_base)
        out[q] = _frozen(vec)
        _ = i
    return out


# --------------------------------------------------------------------------------------
# Anticipation (transition-dependent targets)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnticipationConfig:
    r"""theta_{qr} = (1 - alpha_{qr}) u_q + alpha_{qr} u_r.

    Conditions (spec section 3):
      * ``none``         -- alpha = 0 (no anticipation; the control)
      * ``shared``       -- alpha_{qr} = alpha for every transition
      * ``transition``   -- alpha_{qr} from the table (the hypothesis)
      * ``time_varying`` -- alpha_{qr}(t), a smooth sigmoid ramp up to alpha_{qr}
    """

    condition: AnticipationCondition = "transition"
    alpha_table: dict[Transition, float] = field(default_factory=lambda: dict(DEFAULT_ALPHA))
    shared_alpha: float = 0.30
    #: sigmoid ramp centre and width as a fraction of segment duration (``time_varying``)
    ramp_centre: float = 0.5
    ramp_width: float = 0.15
    default_alpha: float = 0.25

    def alpha(self, q: Phone, r: Phone) -> float:
        """Asymptotic anticipation coefficient for q -> r."""
        if self.condition == "none":
            return 0.0
        if self.condition == "shared":
            return self.shared_alpha
        return float(self.alpha_table.get((q, r), self.default_alpha))

    def alpha_profile(self, q: Phone, r: Phone, t_frac: np.ndarray) -> np.ndarray:
        """alpha_{qr}(t) on a normalised time grid ``t_frac`` in [0, 1]."""
        a = self.alpha(q, r)
        t_frac = np.asarray(t_frac, dtype=float)
        if self.condition != "time_varying":
            return np.full(t_frac.shape, a)
        z = (t_frac - self.ramp_centre) / self.ramp_width
        ramp = 1.0 / (1.0 + np.exp(-z))
        z1 = (1.0 - self.ramp_centre) / self.ramp_width
        return a * ramp / (1.0 / (1.0 + np.exp(-z1)))

    def is_time_varying(self) -> bool:
        return self.condition == "time_varying"


# --------------------------------------------------------------------------------------
# Articulatory dynamics
# --------------------------------------------------------------------------------------


def default_C(d_art: int) -> np.ndarray:
    """Damping. Modes 1 and 2 reproduce the spec exactly (overdamped, critically damped)."""
    base = [70.0, 50.0]
    vals = [base[i] if i < len(base) else 40.0 + 8.0 * i for i in range(d_art)]
    return np.diag(vals)


def default_K(d_art: int) -> np.ndarray:
    """Stiffness. Modes 1 and 2 reproduce the spec exactly."""
    base = [900.0, 625.0]
    vals = [base[i] if i < len(base) else 400.0 + 60.0 * i for i in range(d_art)]
    return np.diag(vals)


@dataclass(frozen=True)
class DynamicsConfig:
    r"""M u'' + C u' + K (u - theta) = 0, optionally with a cubic stiffness term.

    With the defaults (M = I, C = diag(70, 50), K = diag(900, 625)) mode 1 is
    *overdamped* (zeta = 7/6) and mode 2 is *critically damped* (zeta = 1). That is a
    deliberate ground truth: the two modes belong to different kernel families, so a
    rank-1 exponential kernel model cannot be exactly right (see experiment 03).
    """

    d_art: int = 2
    M: np.ndarray | None = None
    C: np.ndarray | None = None
    K: np.ndarray | None = None
    #: nonlinear (cubic) stiffness gain -- 0.0 keeps the system exactly linear
    cubic_gain: float = 0.0
    initial_velocity_scale: float = 0.0

    def __post_init__(self) -> None:
        d = self.d_art
        object.__setattr__(self, "M", _frozen(np.eye(d) if self.M is None else self.M))
        object.__setattr__(self, "C", _frozen(default_C(d) if self.C is None else self.C))
        object.__setattr__(self, "K", _frozen(default_K(d) if self.K is None else self.K))
        for name in ("M", "C", "K"):
            mat = getattr(self, name)
            if mat.shape != (d, d):
                raise ValueError(f"{name} has shape {mat.shape}, expected ({d}, {d})")

    @property
    def is_nonlinear(self) -> bool:
        return self.cubic_gain != 0.0


# --------------------------------------------------------------------------------------
# Time grid
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeGrid:
    """Canonical sampling grid for one transition segment."""

    dt_ms: float = 1.0
    duration_ms: float = 200.0

    @property
    def dt(self) -> float:
        """Step in seconds (the dynamics constants are in SI-like units)."""
        return self.dt_ms / 1000.0

    @property
    def n_frames(self) -> int:
        return int(round(self.duration_ms / self.dt_ms)) + 1

    @property
    def t(self) -> np.ndarray:
        """Time vector in seconds, length ``n_frames``, starting at 0."""
        return np.arange(self.n_frames) * self.dt

    @property
    def t_ms(self) -> np.ndarray:
        return np.arange(self.n_frames) * self.dt_ms

    @property
    def t_frac(self) -> np.ndarray:
        return self.t_ms / self.duration_ms


# --------------------------------------------------------------------------------------
# Acoustic map
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AcousticConfig:
    """Configuration of the nonlinear acoustic map Phi: R^{d_art} -> R^{d_acoustic}."""

    d_acoustic: int = 3
    kind: AcousticKind = "polynomial"
    seed: int = 4242
    #: multiplies every quadratic coefficient; 0.0 makes ``polynomial`` exactly linear
    nonlinearity_scale: float = 1.0


# --------------------------------------------------------------------------------------
# Observation noise
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class NoiseConfig:
    """Observation noise: eps_t ~ N(0, scale^2 * Sigma_regime), AR(1) across time.

    ``scale = 1.0`` reproduces the literal spec covariance, which is a *very* low SNR
    regime (noise std ~ 1 against an acoustic signal of magnitude ~ 1). Experiments
    that need a usable per-frame SNR set a smaller scale explicitly and report the
    measured SNR alongside every result.
    """

    regime: NoiseRegime = "correlated"
    scale: float = 1.0
    #: AR(1) coefficient: Cov(eps_t, eps_{t+k}) = Sigma rho^{|k|}
    rho: float = 0.0
    d_acoustic: int = 3
    seed: int = 90210


# --------------------------------------------------------------------------------------
# Speakers
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeakerConfig:
    r"""Speaker variation g_r(u) = A_r u + b_r, applied as a read-out warp.

    ``regime``:
      * ``single``   -- one speaker, g = identity
      * ``group``    -- g_{r,q} = g_r for every phone q (a group action)
      * ``groupoid`` -- g_{r,q} depends on the phone q (phone-local charts)

    The warp is applied to the *canonical* trajectory rather than to the dynamics, so
    the two regimes differ in exactly one way: whether the chart depends on q. This
    keeps the group/groupoid comparison free of any confound (see experiment 07).
    """

    n_speakers: int = 1
    regime: SpeakerRegime = "single"
    #: magnitude of A_r = I + delta_A_r
    delta_A: float = 0.12
    #: magnitude of the offset b_r
    delta_b: float = 0.08
    #: extra per-phone perturbation used only when ``regime == "groupoid"``
    delta_phone: float = 0.12
    #: apply a speaker-specific acoustic transform S_r = H_r Phi(u)
    acoustic_transform: bool = False
    delta_H: float = 0.08
    seed: int = 777


# --------------------------------------------------------------------------------------
# Sequences
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SequenceConfig:
    """How phone sequences are drawn and how segments are initialised."""

    n_sequences: int = 1000
    #: number of phones per sequence; segments per sequence is this minus one
    sequence_length: int = 6
    #: ``reset``: every segment starts at u(0) = u_q with zero velocity (spec section 5).
    #: ``continue``: the state carries over from the previous segment.
    initial_condition: InitialConditionMode = "reset"
    allow_repeats: bool = False
    seed: int = 12345
    #: store latent u / du / d2u (ground truth). Turn off for large scaling runs.
    store_latents: bool = True
    dtype: str = "float64"


# --------------------------------------------------------------------------------------
# The world
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WorldConfig:
    """The complete generative mechanism. Everything downstream derives from this."""

    articulatory: ArticulatoryConfig = field(default_factory=ArticulatoryConfig)
    anticipation: AnticipationConfig = field(default_factory=AnticipationConfig)
    dynamics: DynamicsConfig = field(default_factory=DynamicsConfig)
    grid: TimeGrid = field(default_factory=TimeGrid)
    acoustic: AcousticConfig = field(default_factory=AcousticConfig)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    sequence: SequenceConfig = field(default_factory=SequenceConfig)
    seed: int = 0

    def __post_init__(self) -> None:
        d = self.articulatory.d_art
        if self.dynamics.d_art != d:
            object.__setattr__(self, "dynamics", replace(self.dynamics, d_art=d))
        if self.noise.d_acoustic != self.acoustic.d_acoustic:
            object.__setattr__(self, "noise", replace(self.noise, d_acoustic=self.acoustic.d_acoustic))

    @property
    def d_art(self) -> int:
        return self.articulatory.d_art

    @property
    def d_acoustic(self) -> int:
        return self.acoustic.d_acoustic

    def transitions(self) -> list[Transition]:
        """All transitions the world can emit, in a stable order."""
        ph = self.articulatory.phones
        return [(q, r) for q in ph for r in ph if self.sequence.allow_repeats or q != r]

    def theta(self, q: Phone, r: Phone) -> np.ndarray:
        """Asymptotic transition target theta_{qr} (ground truth)."""
        a = self.anticipation.alpha(q, r)
        return (1.0 - a) * self.articulatory.target(q) + a * self.articulatory.target(r)

    def theta_profile(self, q: Phone, r: Phone) -> np.ndarray:
        """(T, d_art) target trajectory; constant unless anticipation is time-varying."""
        a = self.anticipation.alpha_profile(q, r, self.grid.t_frac)[:, None]
        return (1.0 - a) * self.articulatory.target(q) + a * self.articulatory.target(r)


# --------------------------------------------------------------------------------------
# Named experimental conditions
# --------------------------------------------------------------------------------------


def world(**overrides) -> WorldConfig:
    """Build a ``WorldConfig``, overriding top-level fields by keyword."""
    return WorldConfig(**overrides)


def condition_world(condition: AnticipationCondition, base: WorldConfig | None = None) -> WorldConfig:
    """Spec section 3, Conditions I-IV."""
    base = base or WorldConfig()
    return replace(base, anticipation=replace(base.anticipation, condition=condition))


def noise_world(regime: NoiseRegime, scale: float, base: WorldConfig | None = None, rho: float = 0.0) -> WorldConfig:
    base = base or WorldConfig()
    return replace(base, noise=replace(base.noise, regime=regime, scale=scale, rho=rho))


def speaker_world(
    regime: SpeakerRegime,
    n_speakers: int,
    base: WorldConfig | None = None,
    **speaker_overrides,
) -> WorldConfig:
    base = base or WorldConfig()
    return replace(
        base,
        speaker=replace(base.speaker, regime=regime, n_speakers=n_speakers, **speaker_overrides),
    )


def dimension_world(d_art: int, d_acoustic: int, base: WorldConfig | None = None) -> WorldConfig:
    """Rebuild a world at a different latent/acoustic dimensionality (spec sections 2, 8)."""
    base = base or WorldConfig()
    art = ArticulatoryConfig(d_art=d_art, phones=base.articulatory.phones, target_seed=base.articulatory.target_seed)
    return replace(
        base,
        articulatory=art,
        dynamics=DynamicsConfig(d_art=d_art, cubic_gain=base.dynamics.cubic_gain),
        acoustic=replace(base.acoustic, d_acoustic=d_acoustic),
        noise=replace(base.noise, d_acoustic=d_acoustic),
    )
