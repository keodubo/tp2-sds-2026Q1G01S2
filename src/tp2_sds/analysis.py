from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import RunSummary, SimulationConfig, format_eta
from .io_extxyz import iter_extxyz


def analyze_run(run_directory: Path) -> RunSummary:
    config = _load_simulation_config(run_directory / "run.json")
    va_series = list(compute_va_series(run_directory / "trajectory.extxyz", config.v))
    if not va_series:
        raise ValueError(f"No frames found in {run_directory / 'trajectory.extxyz'}")
    summary = RunSummary(
        scenario=config.scenario,
        eta=config.eta,
        seed=config.seed,
        t_start=0,
        t_end=len(va_series) - 1,
        va_mean_stationary=float(np.mean([value for _, value in va_series])),
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
) -> list[RunSummary]:
    summaries: list[RunSummary] = []
    for run_directory in discover_run_directories(
        runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
    ):
        summaries.append(analyze_run(run_directory))
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
            writer.writerow(
                {
                    "scenario": scenario,
                    "eta": format_eta(eta),
                    "va_mean": f"{float(values.mean()):.8f}",
                    "va_std": f"{float(values.std(ddof=0)):.8f}",
                    "num_seeds": int(values.size),
                }
            )


def _load_simulation_config(path: Path) -> SimulationConfig:
    return SimulationConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
