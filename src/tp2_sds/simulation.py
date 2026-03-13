from __future__ import annotations

import colorsys
import json
from pathlib import Path

import numpy as np

from .config import SimulationConfig, build_run_directory
from .io_extxyz import TrajectoryFrame, lattice_for_box, write_extxyz

NORMAL_TYPE = 1
LEADER_TYPE = 2
NORMAL_RADIUS = 0.25
LEADER_RADIUS = 0.35
NORMAL_COLOR = np.array([0.68, 0.68, 0.68], dtype=float)
LEADER_COLOR = np.array([0.92, 0.22, 0.14], dtype=float)
TAU = 2.0 * np.pi


def simulate_trajectory(config: SimulationConfig) -> list[TrajectoryFrame]:
    rng = np.random.default_rng(config.seed)
    positions_xy = rng.uniform(0.0, config.L, size=(config.N, 2))
    angles = rng.uniform(0.0, TAU, size=config.N)
    circular_phase = float(rng.uniform(0.0, 2.0 * np.pi))

    ids = np.arange(1, config.N + 1, dtype=int)
    types = np.full(config.N, NORMAL_TYPE, dtype=int)
    radii = np.full(config.N, NORMAL_RADIUS, dtype=float)
    colors = np.tile(NORMAL_COLOR, (config.N, 1))

    if config.scenario in {"B", "C"}:
        types[0] = LEADER_TYPE
        radii[0] = LEADER_RADIUS
        colors[0] = LEADER_COLOR

    frames: list[TrajectoryFrame] = []
    if config.scenario == "C":
        positions_xy[0] = _circular_position(config, circular_phase, step=0)
        angles[0] = _angle_from_vector(_circular_leader_velocity(config, circular_phase, step=0))
    if config.scenario == "B":
        angles[0] = float(config.leader_spec.theta0)

    for step in range(config.steps):
        if config.scenario == "B":
            angles[0] = float(config.leader_spec.theta0)
        if config.scenario == "B":
            positions_xy[0] = positions_xy[0] % config.L
        if config.scenario == "C":
            positions_xy[0] = _circular_position(config, circular_phase, step)
            angles[0] = _angle_from_vector(_circular_leader_velocity(config, circular_phase, step))

        velocities_xy = angles_to_velocities(angles, config.v)
        if config.scenario == "B":
            velocities_xy[0] = _fixed_leader_velocity(config)
        if config.scenario == "C":
            velocities_xy[0] = _circular_leader_velocity(config, circular_phase, step)

        positions = np.column_stack((positions_xy, np.zeros(config.N, dtype=float)))
        velocities = np.column_stack((velocities_xy, np.zeros(config.N, dtype=float)))
        vector_colors = _velocity_colors(velocities_xy)

        frames.append(
            TrajectoryFrame(
                ids=ids.copy(),
                types=types.copy(),
                positions=positions,
                velocities=velocities,
                radii=radii.copy(),
                colors=colors.copy(),
                vector_colors=vector_colors,
                time=step * config.dt,
                lattice=lattice_for_box(config.L),
            )
        )

        next_angles = compute_next_angles(
            positions_xy,
            angles,
            interaction_radius=config.r,
            box_length=config.L,
            eta=config.eta,
            rng=rng,
        )
        next_positions = positions_xy.copy()

        if config.scenario == "C":
            next_positions[1:] = (next_positions[1:] + velocities_xy[1:] * config.dt) % config.L
            next_positions[0] = _circular_position(config, circular_phase, step + 1)
            next_angles[0] = _angle_from_vector(_circular_leader_velocity(config, circular_phase, step + 1))
        else:
            next_positions = (next_positions + velocities_xy * config.dt) % config.L
            if config.scenario == "B":
                next_angles[0] = float(config.leader_spec.theta0)

        positions_xy = next_positions
        angles = _normalize_angles(next_angles)

    return frames


def write_simulation_run(config: SimulationConfig, output_root: Path, force: bool = False) -> Path:
    run_directory = build_run_directory(output_root, config.scenario, config.eta, config.seed)
    trajectory_path = run_directory / "trajectory.extxyz"
    metadata_path = run_directory / "run.json"
    summary_path = run_directory / "summary.json"

    if not force and any(path.exists() for path in (trajectory_path, metadata_path, summary_path)):
        raise FileExistsError(f"Run already exists at {run_directory}. Use --force to overwrite.")

    run_directory.mkdir(parents=True, exist_ok=True)
    frames = simulate_trajectory(config)
    write_extxyz(trajectory_path, frames)
    metadata_path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    if force and summary_path.exists():
        summary_path.unlink()
    return run_directory


def compute_next_angles(
    positions_xy: np.ndarray,
    angles: np.ndarray,
    *,
    interaction_radius: float,
    box_length: float,
    eta: float,
    rng: np.random.Generator,
) -> np.ndarray:
    neighbors = neighbor_mask(positions_xy, interaction_radius=interaction_radius, box_length=box_length)
    mean_angles = mean_neighbor_angles(angles, neighbors)
    if np.isclose(eta, 0.0):
        noise = np.zeros_like(mean_angles)
    else:
        noise = rng.uniform(-eta / 2.0, eta / 2.0, size=angles.shape[0])
    return _normalize_angles(mean_angles + noise)


def neighbor_mask(
    positions_xy: np.ndarray,
    *,
    interaction_radius: float,
    box_length: float,
) -> np.ndarray:
    deltas = minimum_image_displacements(positions_xy, box_length=box_length)
    distances_sq = np.sum(deltas * deltas, axis=2)
    mask = distances_sq <= (interaction_radius * interaction_radius)
    np.fill_diagonal(mask, True)
    return mask


def minimum_image_displacements(positions_xy: np.ndarray, *, box_length: float) -> np.ndarray:
    displacements = positions_xy[np.newaxis, :, :] - positions_xy[:, np.newaxis, :]
    displacements -= box_length * np.rint(displacements / box_length)
    return displacements


def mean_neighbor_angles(angles: np.ndarray, neighbors: np.ndarray) -> np.ndarray:
    sum_cos = neighbors @ np.cos(angles)
    sum_sin = neighbors @ np.sin(angles)
    return np.arctan2(sum_sin, sum_cos)


def angles_to_velocities(angles: np.ndarray, speed: float) -> np.ndarray:
    return speed * np.column_stack((np.cos(angles), np.sin(angles)))


def _fixed_leader_velocity(config: SimulationConfig) -> np.ndarray:
    theta0 = float(config.leader_spec.theta0)
    return np.array([np.cos(theta0), np.sin(theta0)]) * config.v


def _circular_position(config: SimulationConfig, phase0: float, step: int) -> np.ndarray:
    phase = phase0 + float(config.leader_spec.omega) * step
    center = np.array([float(config.leader_spec.center_x), float(config.leader_spec.center_y)])
    offset = float(config.leader_spec.radius) * np.array([np.cos(phase), np.sin(phase)])
    return center + offset


def _circular_leader_velocity(config: SimulationConfig, phase0: float, step: int) -> np.ndarray:
    phase = phase0 + float(config.leader_spec.omega) * step
    tangent = np.array([-np.sin(phase), np.cos(phase)])
    return tangent * config.v


def _angle_from_vector(vector_xy: np.ndarray) -> float:
    return float(np.arctan2(vector_xy[1], vector_xy[0]))


def _normalize_angles(angles: np.ndarray) -> np.ndarray:
    return (angles + np.pi) % TAU - np.pi


def _velocity_colors(velocities_xy: np.ndarray) -> np.ndarray:
    angles = np.arctan2(velocities_xy[:, 1], velocities_xy[:, 0])
    colors = np.empty((velocities_xy.shape[0], 3), dtype=float)
    for index, angle in enumerate(angles):
        hue = (angle % TAU) / TAU
        colors[index] = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return colors
