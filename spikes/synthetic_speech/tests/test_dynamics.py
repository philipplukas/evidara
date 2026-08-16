"""The propagator must be exact: numerical error has to sit far below every measured effect."""

import numpy as np
import pytest

from config import DynamicsConfig, TimeGrid, WorldConfig
from dynamics import (
    LinearDynamics,
    error_decay,
    ground_truth_kernels,
    modal_report,
    simulate_linear_batch,
    state_space,
)


def test_equilibrium_is_target_with_zero_velocity():
    cfg = DynamicsConfig()
    A, B = state_space(cfg.M, cfg.C, cfg.K)
    theta = np.array([0.37, -0.11])
    x_star = np.concatenate([theta, np.zeros(2)])
    assert np.allclose(A @ x_star + B @ theta, 0.0, atol=1e-14)


def test_default_modes_are_overdamped_and_critically_damped():
    rep = modal_report(DynamicsConfig())
    assert np.allclose(rep.omega_n, [30.0, 25.0])
    assert np.allclose(rep.zeta, [7.0 / 6.0, 1.0])
    assert rep.regime == ("overdamped", "critically damped")


def test_zoh_matches_closed_form_modal_solution():
    """Exactness check: the discrete propagator against the analytic second-order solution."""
    cfg = DynamicsConfig()
    grid = TimeGrid(dt_ms=1.0, duration_ms=250.0)
    dyn = LinearDynamics.from_config(cfg, grid.dt)
    rep = modal_report(cfg)

    u0 = np.array([0.0, 0.0])
    theta = np.array([0.43, -0.19])
    x0 = np.concatenate([u0, np.zeros(2)])
    theta_seq = np.tile(theta, (grid.n_frames, 1))
    x = simulate_linear_batch(dyn, x0[None, :], theta_seq)[0]

    t = grid.t
    expected = np.stack(
        [theta[i] + (u0[i] - theta[i]) * error_decay(rep.omega_n[i], rep.zeta[i], t) for i in range(2)],
        axis=1,
    )
    assert np.max(np.abs(x[:, :2] - expected)) < 1e-12


def test_velocity_matches_numerical_derivative_of_closed_form():
    cfg = DynamicsConfig()
    grid = TimeGrid(dt_ms=0.1, duration_ms=200.0)
    dyn = LinearDynamics.from_config(cfg, grid.dt)
    theta = np.array([0.4, 0.25])
    x0 = np.zeros(4)
    x = simulate_linear_batch(dyn, x0[None, :], np.tile(theta, (grid.n_frames, 1)))[0]
    fd = np.gradient(x[:, :2], grid.dt, axis=0)
    # np.gradient truncates at O(dt^2 * third derivative); at dt = 0.1 ms that bound is
    # ~2e-5 here, so this confirms the state velocity really is du/dt and not a free
    # variable that merely happens to look like it
    assert np.max(np.abs(fd[2:-2] - x[2:-2, 2:])) < 1e-4


def test_A_u_and_A_v_are_minus_Minv_K_and_C():
    cfg = DynamicsConfig()
    dyn = LinearDynamics.from_config(cfg, 0.001)
    assert np.allclose(dyn.A_u, -np.linalg.inv(cfg.M) @ cfg.K)
    assert np.allclose(dyn.A_v, -np.linalg.inv(cfg.M) @ cfg.C)


def test_ground_truth_kernels_rise_monotonically_but_do_not_fully_settle():
    """The slow pole of mode 0 is -16.97 rad/s (tau = 59 ms), so K(200 ms) = 0.951.

    The kernel is therefore still informative across the whole segment. Any inference
    that assumes a settled trajectory is wrong in this world, deliberately.
    """
    grid = TimeGrid()
    kern = ground_truth_kernels(DynamicsConfig(), grid.t)
    assert np.allclose(kern[0], 0.0)
    assert np.all(kern[-1] > 0.94) and np.all(kern[-1] < 0.98)
    assert np.all(np.diff(kern, axis=0) >= -1e-12)  # monotone for zeta >= 1


def test_delta_between_two_transitions_is_exactly_the_kernel_basis():
    """Ground truth for experiments 02/03: Delta u(t) = diag(K_i(t)) (theta_1 - theta_2)."""
    world = WorldConfig()
    grid = world.grid
    dyn = LinearDynamics.from_config(world.dynamics, grid.dt)
    u_a = world.articulatory.target("A")
    x0 = np.concatenate([u_a, np.zeros(2)])
    th_ab, th_ac = world.theta("A", "B"), world.theta("A", "C")
    x_ab = simulate_linear_batch(dyn, x0[None, :], np.tile(th_ab, (grid.n_frames, 1)))[0]
    x_ac = simulate_linear_batch(dyn, x0[None, :], np.tile(th_ac, (grid.n_frames, 1)))[0]
    delta = x_ab[:, :2] - x_ac[:, :2]
    kern = ground_truth_kernels(world.dynamics, grid.t)
    expected = kern * (th_ab - th_ac)[None, :]
    assert np.max(np.abs(delta - expected)) < 1e-12


@pytest.mark.parametrize("zeta", [0.4, 1.0, 1.6])
def test_error_decay_starts_at_one_with_zero_slope(zeta):
    """g(0) = 1 and g'(0) = 0, so the departure from 1 must be second order in t."""
    omega = 25.0
    assert abs(error_decay(omega, zeta, np.array([0.0]))[0] - 1.0) < 1e-12
    slopes = []
    for dt in (1e-4, 1e-5):
        g = error_decay(omega, zeta, np.array([0.0, dt]))
        slopes.append(abs(g[1] - g[0]) / dt)
    # a first-order term would hold the difference quotient constant; it must fall ~10x
    assert slopes[1] < 0.2 * slopes[0]
