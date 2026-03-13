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


def simulate_trajectory(config: SimulationConfig) -> list[TrajectoryFrame]:
    rng = np.random.default_rng(config.seed)
    positions_xy = rng.uniform(0.0, config.L, size=(config.N, 2))
    phase_offsets = rng.uniform(0.0, 2.0 * np.pi, size=config.N)
    global_phase = float(rng.uniform(0.0, 2.0 * np.pi))
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
    movable_start = 1 if config.scenario == "C" else 0

    for step in range(config.steps):
        velocities_xy = _synthetic_velocities(config, rng, phase_offsets, global_phase, step)
        if config.scenario == "B":
            velocities_xy[0] = _fixed_leader_velocity(config)
        if config.scenario == "C":
            positions_xy[0] = _circular_position(config, circular_phase, step)
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

        positions_xy[movable_start:] = (positions_xy[movable_start:] + velocities_xy[movable_start:] * config.dt) % config.L

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


def _synthetic_velocities(
    config: SimulationConfig,
    rng: np.random.Generator,
    phase_offsets: np.ndarray,
    global_phase: float,
    step: int,
) -> np.ndarray:
    mix = np.clip(config.eta / np.pi, 0.0, 1.0)
    alignment_angle = global_phase + 0.045 * step
    alignment_vector = np.array([np.cos(alignment_angle), np.sin(alignment_angle)])
    noise_angles = rng.uniform(0.0, 2.0 * np.pi, size=config.N)
    noise_vectors = np.column_stack((np.cos(noise_angles), np.sin(noise_angles)))
    bias_angles = phase_offsets + 0.08 * step
    bias_vectors = 0.12 * np.column_stack((np.cos(bias_angles), np.sin(bias_angles)))

    combined = ((1.0 - mix) * alignment_vector) + (mix * noise_vectors) + bias_vectors
    norms = np.linalg.norm(combined, axis=1, keepdims=True)
    return config.v * combined / norms


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


def _velocity_colors(velocities_xy: np.ndarray) -> np.ndarray:
    angles = np.arctan2(velocities_xy[:, 1], velocities_xy[:, 0])
    colors = np.empty((velocities_xy.shape[0], 3), dtype=float)
    for index, angle in enumerate(angles):
        hue = (angle % (2.0 * np.pi)) / (2.0 * np.pi)
        colors[index] = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return colors
