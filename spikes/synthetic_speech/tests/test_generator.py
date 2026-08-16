"""Generator invariants -- including the controls the experiments depend on."""

from dataclasses import replace

import numpy as np
import pytest

from config import (
    SequenceConfig,
    WorldConfig,
    condition_world,
    dimension_world,
    speaker_world,
)
from generator import generate


def _small(world: WorldConfig, n=200) -> WorldConfig:
    return replace(world, sequence=replace(world.sequence, n_sequences=n))


def test_generation_is_deterministic():
    w = _small(WorldConfig())
    a, b = generate(w), generate(w)
    assert np.array_equal(a.observed, b.observed)
    assert np.array_equal(a.source, b.source)


def test_shapes_and_segment_bookkeeping():
    w = _small(WorldConfig(), n=50)
    ds = generate(w)
    n_seg = 50 * (w.sequence.sequence_length - 1)
    assert ds.observed.shape == (n_seg, w.grid.n_frames, w.d_acoustic)
    assert ds.latent_u.shape == (n_seg, w.grid.n_frames, w.d_art)
    assert ds.source.shape == (n_seg,)
    # the segment's source phone is the sequence's phone at that position
    assert np.array_equal(ds.source, ds.phone_sequences[:, :-1].reshape(-1))
    assert np.array_equal(ds.following, ds.phone_sequences[:, 1:].reshape(-1))


def test_no_immediate_phone_repeats_by_default():
    ds = generate(_small(WorldConfig(), n=100))
    assert np.all(ds.source != ds.following)


def test_trajectory_starts_at_the_source_target_and_moves_towards_theta():
    """Starts exactly at u_q and covers >= 94% of the distance to theta within 200 ms.

    It does not fully arrive -- the slow pole has tau = 59 ms (see test_dynamics).
    """
    ds = generate(_small(WorldConfig(), n=30))
    targets = ds.config.articulatory.target_matrix()
    assert np.max(np.abs(ds.latent_u[:, 0, :] - targets[ds.source])) < 1e-12
    start_gap = np.abs(targets[ds.source] - ds.theta[:, -1, :])
    end_gap = np.abs(ds.latent_u[:, -1, :] - ds.theta[:, -1, :])
    covered = 1.0 - end_gap[start_gap > 1e-9] / start_gap[start_gap > 1e-9]
    assert covered.min() > 0.94


def test_observed_equals_clean_plus_noise_with_the_right_variance():
    w = _small(WorldConfig(), n=400)
    ds = generate(w)
    resid = (ds.observed - ds.clean).reshape(-1, w.d_acoustic)
    assert np.max(np.abs(np.cov(resid.T) - ds.noise_model.sigma)) < 0.05


# -- the controls the experiments rely on ----------------------------------------------


def test_no_anticipation_control_gives_exactly_zero_delta():
    """Condition I: theta_{qr} = u_q, so A->B and A->C are identical in the latent."""
    ds = generate(_small(condition_world("none"), n=200))
    ab = ds.latent_u[ds.mask("A", "B")].mean(0)
    ac = ds.latent_u[ds.mask("A", "C")].mean(0)
    assert np.max(np.abs(ab - ac)) < 1e-14


def test_shared_anticipation_still_gives_a_nonzero_delta():
    """Condition II separates 'anticipation exists' from 'anticipation is transition-specific'."""
    ds = generate(_small(condition_world("shared"), n=200))
    ab = ds.clean[ds.mask("A", "B")].mean(0)
    ac = ds.clean[ds.mask("A", "C")].mean(0)
    assert np.max(np.abs(ab - ac)) > 0.05


def test_transition_condition_uses_the_alpha_table():
    ds = generate(_small(WorldConfig(), n=60))
    ab = ds.alpha[ds.mask("A", "B")]
    ac = ds.alpha[ds.mask("A", "C")]
    assert np.allclose(ab, 0.35) and np.allclose(ac, 0.20)


def test_time_varying_anticipation_moves_the_target_over_time():
    ds = generate(_small(condition_world("time_varying"), n=20))
    th = ds.theta[ds.mask("A", "B")][0]
    assert np.max(np.abs(th[-1] - th[0])) > 0.05


# -- speakers ---------------------------------------------------------------------------


def test_group_and_groupoid_share_the_phone_averaged_chart():
    g = generate(_small(speaker_world("group", 8), n=50))
    gp = generate(_small(speaker_world("groupoid", 8), n=50))
    assert np.allclose(g.speakers.A.mean(axis=1), gp.speakers.A.mean(axis=1))
    assert np.allclose(g.speakers.b.mean(axis=1), gp.speakers.b.mean(axis=1))


def test_groupoid_chart_actually_depends_on_the_phone():
    gp = generate(_small(speaker_world("groupoid", 8), n=50))
    spread = np.max(np.abs(gp.speakers.A[1:] - gp.speakers.A[1:].mean(axis=1, keepdims=True)))
    assert spread > 0.05
    g = generate(_small(speaker_world("group", 8), n=50))
    assert np.max(np.abs(g.speakers.A - g.speakers.A.mean(axis=1, keepdims=True))) < 1e-14


def test_speaker_zero_is_canonical():
    ds = generate(_small(speaker_world("groupoid", 6), n=50))
    assert np.allclose(ds.speakers.A[0], np.eye(ds.config.d_art))
    assert np.allclose(ds.speakers.b[0], 0.0)


# -- alternative worlds -----------------------------------------------------------------


@pytest.mark.parametrize("d_art,d_acoustic", [(2, 3), (3, 5), (5, 10), (10, 20)])
def test_alternative_dimensionalities_generate(d_art, d_acoustic):
    ds = generate(_small(dimension_world(d_art, d_acoustic), n=20))
    assert ds.observed.shape[-1] == d_acoustic
    assert ds.latent_u.shape[-1] == d_art
    assert np.isfinite(ds.observed).all()


def test_continue_mode_carries_state_across_segments():
    w = _small(replace(WorldConfig(), sequence=SequenceConfig(n_sequences=20, initial_condition="continue")))
    ds = generate(w)
    order = np.lexsort((ds.position, ds.sequence_index))
    first, second = order[0], order[1]
    assert np.allclose(ds.latent_u[second, 0], ds.latent_u[first, -1], atol=1e-12)


def test_nonlinear_dynamics_diverge_from_the_linear_world():
    base = _small(WorldConfig(), n=30)
    nl = replace(base, dynamics=replace(base.dynamics, cubic_gain=3.0))
    a, b = generate(base), generate(nl)
    assert np.max(np.abs(a.latent_u - b.latent_u)) > 1e-3


def test_frames_view_is_consistent():
    ds = generate(_small(WorldConfig(), n=20))
    X, y, sp, seg = ds.frames()
    assert X.shape == (ds.n_segments * ds.n_frames, ds.config.d_acoustic)
    assert np.array_equal(y[:: ds.n_frames], ds.source)
    assert np.array_equal(sp[:: ds.n_frames], ds.speaker)
    assert np.array_equal(seg[:: ds.n_frames], np.arange(ds.n_segments))
