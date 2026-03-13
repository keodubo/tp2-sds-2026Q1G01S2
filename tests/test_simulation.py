from __future__ import annotations

from pathlib import Path

import numpy as np

from tp2_sds.analysis import analyze_run
from tp2_sds.config import make_simulation_config
from tp2_sds.simulation import (
    compute_next_angles,
    mean_neighbor_angles,
    minimum_image_displacements,
    neighbor_mask,
    simulate_trajectory,
    write_simulation_run,
)


def test_minimum_image_and_periodic_neighbors_detect_across_boundary() -> None:
    positions = np.array(
        [
            [0.1, 0.1],
            [9.8, 0.2],
            [5.0, 5.0],
        ],
        dtype=float,
    )

    deltas = minimum_image_displacements(positions, box_length=10.0)
    neighbors = neighbor_mask(positions, interaction_radius=0.5, box_length=10.0)

    np.testing.assert_allclose(deltas[0, 1], np.array([-0.3, 0.1]), atol=1e-12)
    assert neighbors[0, 0]
    assert neighbors[0, 1]
    assert neighbors[1, 0]
    assert not neighbors[0, 2]


def test_mean_neighbor_angles_wraps_across_branch_cut() -> None:
    angles = np.array([np.pi - 0.1, -np.pi + 0.1], dtype=float)
    neighbors = np.ones((2, 2), dtype=bool)

    means = mean_neighbor_angles(angles, neighbors)

    np.testing.assert_allclose(np.cos(means), np.array([-1.0, -1.0]), atol=1e-12)
    np.testing.assert_allclose(np.sin(means), np.array([0.0, 0.0]), atol=1e-12)


def test_compute_next_angles_eta_zero_aligns_to_neighbor_average() -> None:
    positions = np.array(
        [
            [1.0, 1.0],
            [1.2, 1.0],
            [1.1, 1.2],
        ],
        dtype=float,
    )
    angles = np.array([0.0, np.pi / 2.0, np.pi], dtype=float)

    next_angles = compute_next_angles(
        positions,
        angles,
        interaction_radius=1.0,
        box_length=10.0,
        eta=0.0,
        rng=np.random.default_rng(123),
    )

    np.testing.assert_allclose(next_angles, np.full(3, np.pi / 2.0), atol=1e-12)


def test_simulate_trajectory_preserves_speed_and_box_invariants_for_standard_case() -> None:
    config = make_simulation_config(
        scenario="A",
        eta=0.6,
        steps=8,
        seed=5,
        L=4.0,
        N=16,
        rho=1.0,
    )

    frames = simulate_trajectory(config)

    assert len(frames) == config.steps
    for frame in frames:
        assert frame.ids.shape[0] == config.N
        np.testing.assert_allclose(
            np.linalg.norm(frame.velocities[:, :2], axis=1),
            np.full(config.N, config.v),
            atol=1e-10,
        )
        assert np.all(frame.positions[:, :2] >= 0.0)
        assert np.all(frame.positions[:, :2] < config.L)


def test_fixed_leader_keeps_constant_direction() -> None:
    config = make_simulation_config(
        scenario="B",
        eta=1.8,
        steps=6,
        seed=9,
        L=4.0,
        N=16,
        rho=1.0,
    )

    frames = simulate_trajectory(config)
    leader_angles = np.array([np.arctan2(frame.velocities[0, 1], frame.velocities[0, 0]) for frame in frames])

    np.testing.assert_allclose(leader_angles, np.full(config.steps, leader_angles[0]), atol=1e-12)
    assert all(int(frame.types[0]) == 2 for frame in frames)


def test_circular_leader_stays_on_circle_and_keeps_speed() -> None:
    config = make_simulation_config(
        scenario="C",
        eta=0.5,
        steps=6,
        seed=4,
        L=10.0,
        N=16,
        rho=0.16,
    )

    frames = simulate_trajectory(config)
    center = np.array([float(config.leader_spec.center_x), float(config.leader_spec.center_y)])
    radius = float(config.leader_spec.radius)

    for frame in frames:
        leader_position = frame.positions[0, :2]
        leader_speed = np.linalg.norm(frame.velocities[0, :2])
        assert np.isclose(np.linalg.norm(leader_position - center), radius, atol=1e-10)
        assert np.isclose(leader_speed, config.v, atol=1e-12)


def test_low_noise_run_is_more_ordered_than_high_noise_run(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    low_noise_config = make_simulation_config(
        scenario="A",
        eta=0.0,
        steps=100,
        seed=11,
        L=3.0,
        N=36,
        rho=4.0,
    )
    high_noise_config = make_simulation_config(
        scenario="A",
        eta=5.0,
        steps=100,
        seed=11,
        L=3.0,
        N=36,
        rho=4.0,
    )

    low_run = write_simulation_run(low_noise_config, output_root)
    high_run = write_simulation_run(high_noise_config, output_root)

    low_summary = analyze_run(low_run)
    high_summary = analyze_run(high_run)

    assert low_summary.va_mean_stationary > high_summary.va_mean_stationary
