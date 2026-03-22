from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import RunSummary, SimulationConfig, format_eta
from .io_extxyz import iter_extxyz
from .simulation import LEADER_TYPE

DEFAULT_TRANSIENT_FRACTION = 0.3


def analyze_run(
    run_directory: Path,
    *,
    transient_fraction: float = DEFAULT_TRANSIENT_FRACTION,
) -> RunSummary:
    config = _load_simulation_config(run_directory / "run.json")
    va_series = list(compute_va_series(run_directory / "trajectory.extxyz", config.v))
    if not va_series:
        raise ValueError(f"No frames found in {run_directory / 'trajectory.extxyz'}")
    t_start, t_end = stationary_window(len(va_series), transient_fraction=transient_fraction)
    stationary_values = [value for _, value in va_series[t_start : t_end + 1]]
    summary = RunSummary(
        scenario=config.scenario,
        eta=config.eta,
        seed=config.seed,
        t_start=t_start,
        t_end=t_end,
        va_mean_stationary=float(np.mean(stationary_values)),
    )
    (run_directory / "summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def analyze_runs(
    runs_root: Path,
    *,
    scenario_filter: set[str] | None = None,
    eta_filter: set[str] | None = None,
    seed_filter: set[int] | None = None,
    transient_fraction: float = DEFAULT_TRANSIENT_FRACTION,
) -> list[RunSummary]:
    summaries: list[RunSummary] = []
    for run_directory in discover_run_directories(
        runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
    ):
        summaries.append(analyze_run(run_directory, transient_fraction=transient_fraction))
    aggregate_path = runs_root / "aggregate.csv"
    write_aggregate_csv(aggregate_path, summaries)
    return summaries


def compute_va_series(trajectory_path: Path, speed: float) -> list[tuple[float, float]]:
    values: list[tuple[float, float]] = []
    for frame in iter_extxyz(trajectory_path):
        collective_velocity = np.linalg.norm(frame.velocities[:, :2].sum(axis=0))
        particle_count = frame.velocities.shape[0]
        values.append((frame.time, float(collective_velocity / (particle_count * speed))))
    return values


def compute_angular_correlation_series(
    trajectory_path: Path,
) -> list[tuple[float, float, float, float]]:
    """Compute collective angle and leader-swarm angular correlation.

    Returns list of (time, theta_S, theta_L, C) tuples.
    Only meaningful for trajectories with a leader particle (scenarios B/C).
    Returns empty list if no leader is found.
    """
    values: list[tuple[float, float, float, float]] = []
    for frame in iter_extxyz(trajectory_path):
        leader_mask = frame.types == LEADER_TYPE
        if not np.any(leader_mask):
            return []
        swarm_mask = ~leader_mask
        swarm_vx = frame.velocities[swarm_mask, 0]
        swarm_vy = frame.velocities[swarm_mask, 1]
        swarm_angles = np.arctan2(swarm_vy, swarm_vx)
        theta_s = float(np.arctan2(np.mean(np.sin(swarm_angles)), np.mean(np.cos(swarm_angles))))
        leader_vx = frame.velocities[leader_mask, 0][0]
        leader_vy = frame.velocities[leader_mask, 1][0]
        theta_l = float(np.arctan2(leader_vy, leader_vx))
        c = float(np.cos(theta_l - theta_s))
        values.append((frame.time, theta_s, theta_l, c))
    return values


def stationary_window(num_frames: int, transient_fraction: float = DEFAULT_TRANSIENT_FRACTION) -> tuple[int, int]:
    if num_frames <= 0:
        raise ValueError("num_frames must be positive")
    if not 0.0 <= transient_fraction <= 1.0:
        raise ValueError("transient_fraction must be between 0 and 1")
    t_end = num_frames - 1
    if num_frames == 1:
        return 0, 0
    raw_start = int(np.floor(num_frames * transient_fraction))
    t_start = min(t_end, max(1, raw_start))
    return t_start, t_end


def discover_run_directories(
    runs_root: Path,
    *,
    scenario_filter: set[str] | None = None,
    eta_filter: set[str] | None = None,
    seed_filter: set[int] | None = None,
) -> list[Path]:
    discovered: list[tuple[str, float, int, Path]] = []
    for run_json_path in runs_root.rglob("run.json"):
        run_directory = run_json_path.parent
        trajectory_path = run_directory / "trajectory.extxyz"
        if not trajectory_path.exists():
            continue
        config = _load_simulation_config(run_json_path)
        if scenario_filter and config.scenario not in scenario_filter:
            continue
        if eta_filter and format_eta(config.eta) not in eta_filter:
            continue
        if seed_filter and config.seed not in seed_filter:
            continue
        discovered.append((config.scenario, config.eta, config.seed, run_directory))
    discovered.sort(key=lambda item: (item[0], item[1], item[2]))
    return [run_directory for _, _, _, run_directory in discovered]


def write_aggregate_csv(path: Path, summaries: list[RunSummary]) -> None:
    grouped: dict[tuple[str, float], list[float]] = defaultdict(list)
    for summary in summaries:
        grouped[(summary.scenario, summary.eta)].append(summary.va_mean_stationary)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scenario", "eta", "va_mean", "va_std", "num_seeds"],
        )
        writer.writeheader()
        for scenario, eta in sorted(grouped):
            values = np.asarray(grouped[(scenario, eta)], dtype=float)
            std = float(values.std(ddof=1)) if values.size > 1 else 0.0
            writer.writerow(
                {
                    "scenario": scenario,
                    "eta": format_eta(eta),
                    "va_mean": f"{float(values.mean()):.8f}",
                    "va_std": f"{std:.8f}",
                    "num_seeds": int(values.size),
                }
            )


def _load_simulation_config(path: Path) -> SimulationConfig:
    return SimulationConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
