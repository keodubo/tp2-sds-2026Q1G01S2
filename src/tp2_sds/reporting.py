from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import matplotlib
import numpy as np

from .analysis import DEFAULT_TRANSIENT_FRACTION, analyze_runs, compute_va_series, discover_run_directories
from .config import (
    DEFAULT_DT,
    DEFAULT_L,
    DEFAULT_OUTPUTS_ROOT,
    DEFAULT_R,
    DEFAULT_RHO,
    DEFAULT_V,
    RunSummary,
    SimulationConfig,
    build_run_directory,
    format_eta,
    make_simulation_config,
)
from .simulation import write_simulation_run

matplotlib.use("Agg")
from matplotlib import pyplot as plt

DEFAULT_CAMPAIGN_SCENARIOS = ("A", "B", "C")
DEFAULT_CAMPAIGN_ETAS = tuple(index * 0.5 for index in range(11))
DEFAULT_CAMPAIGN_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_CAMPAIGN_STEPS = 2000
RESULTS_DIRECTORY_NAME = "results"
DEMO_MANIFEST_NAME = "demo_manifest.csv"


@dataclass(frozen=True)
class CampaignSpec:
    scenarios: tuple[str, ...]
    etas: tuple[float, ...]
    seeds: tuple[int, ...]
    steps: int
    transient_fraction: float
    runs_root: Path


@dataclass(frozen=True)
class CampaignResult:
    created_runs: int
    skipped_runs: int
    analyzed_runs: int
    results_directory: Path


@dataclass(frozen=True)
class RunRecord:
    run_directory: Path
    trajectory_path: Path
    config: SimulationConfig
    summary: RunSummary


@dataclass(frozen=True)
class DemoSelection:
    scenario: str
    role: str
    record: RunRecord


@dataclass(frozen=True)
class AggregatedPoint:
    scenario: str
    eta: float
    va_mean: float
    va_std: float
    num_seeds: int


def default_campaign_spec(runs_root: Path = DEFAULT_OUTPUTS_ROOT) -> CampaignSpec:
    return CampaignSpec(
        scenarios=DEFAULT_CAMPAIGN_SCENARIOS,
        etas=DEFAULT_CAMPAIGN_ETAS,
        seeds=DEFAULT_CAMPAIGN_SEEDS,
        steps=DEFAULT_CAMPAIGN_STEPS,
        transient_fraction=DEFAULT_TRANSIENT_FRACTION,
        runs_root=runs_root,
    )


def run_campaign(
    spec: CampaignSpec,
    *,
    skip_existing: bool = False,
    L: float = DEFAULT_L,
    rho: float | None = DEFAULT_RHO,
    N: int | None = None,
    r: float = DEFAULT_R,
    v: float = DEFAULT_V,
    dt: float = DEFAULT_DT,
) -> CampaignResult:
    created_runs = 0
    skipped_runs = 0

    for scenario, eta, seed in product(spec.scenarios, spec.etas, spec.seeds):
        run_directory = build_run_directory(spec.runs_root, scenario, eta, seed)
        if skip_existing and _run_is_complete(run_directory):
            skipped_runs += 1
            continue

        config = make_simulation_config(
            scenario=scenario,
            eta=eta,
            steps=spec.steps,
            seed=seed,
            L=L,
            rho=rho,
            N=N,
            r=r,
            v=v,
            dt=dt,
        )
        write_simulation_run(config, spec.runs_root)
        created_runs += 1

    summaries = analyze_runs(
        spec.runs_root,
        scenario_filter=set(spec.scenarios),
        eta_filter={format_eta(eta) for eta in spec.etas},
        seed_filter=set(spec.seeds),
        transient_fraction=spec.transient_fraction,
    )
    results_directory = generate_results(
        spec.runs_root,
        scenario_filter=set(spec.scenarios),
        eta_filter={format_eta(eta) for eta in spec.etas},
        seed_filter=set(spec.seeds),
    )
    return CampaignResult(
        created_runs=created_runs,
        skipped_runs=skipped_runs,
        analyzed_runs=len(summaries),
        results_directory=results_directory,
    )


def generate_results(
    runs_root: Path,
    *,
    scenario_filter: set[str] | None = None,
    eta_filter: set[str] | None = None,
    seed_filter: set[int] | None = None,
) -> Path:
    records = discover_run_records(
        runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
    )
    if not records:
        raise ValueError(f"No analyzed runs found under {runs_root}")

    results_directory = runs_root / RESULTS_DIRECTORY_NAME
    results_directory.mkdir(parents=True, exist_ok=True)

    aggregated_by_scenario = aggregate_records(records)
    selections = select_demo_runs(records)
    write_demo_manifest(results_directory / DEMO_MANIFEST_NAME, selections)

    for scenario, points in sorted(aggregated_by_scenario.items()):
        _plot_va_timeseries(results_directory, scenario, selections)
        _plot_eta_vs_va(results_directory, scenario, points)
    _plot_eta_vs_va_comparison(results_directory, aggregated_by_scenario)

    return results_directory


def discover_run_records(
    runs_root: Path,
    *,
    scenario_filter: set[str] | None = None,
    eta_filter: set[str] | None = None,
    seed_filter: set[int] | None = None,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    for run_directory in discover_run_directories(
        runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
    ):
        trajectory_path = run_directory / "trajectory.extxyz"
        summary_path = run_directory / "summary.json"
        config_path = run_directory / "run.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"Missing summary.json in {run_directory}")
        config = SimulationConfig.from_dict(json.loads(config_path.read_text(encoding="utf-8")))
        summary = RunSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        records.append(
            RunRecord(
                run_directory=run_directory,
                trajectory_path=trajectory_path,
                config=config,
                summary=summary,
            )
        )
    return records


def select_demo_runs(records: list[RunRecord]) -> list[DemoSelection]:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.config.scenario].append(record)

    selections: list[DemoSelection] = []
    for scenario in sorted(grouped):
        scenario_records = grouped[scenario]
        max_eta = max(record.config.eta for record in scenario_records)
        low_record = min(scenario_records, key=lambda record: (record.config.eta, record.config.seed))
        high_record = min(
            (record for record in scenario_records if np.isclose(record.config.eta, max_eta)),
            key=lambda record: record.config.seed,
        )
        selections.append(DemoSelection(scenario=scenario, role="low_noise", record=low_record))
        selections.append(DemoSelection(scenario=scenario, role="high_noise", record=high_record))
    return selections


def aggregate_records(records: list[RunRecord]) -> dict[str, list[AggregatedPoint]]:
    grouped_values: dict[tuple[str, float], list[float]] = defaultdict(list)
    for record in records:
        grouped_values[(record.summary.scenario, record.summary.eta)].append(record.summary.va_mean_stationary)

    aggregated: dict[str, list[AggregatedPoint]] = defaultdict(list)
    for (scenario, eta), values in sorted(grouped_values.items()):
        sample = np.asarray(values, dtype=float)
        aggregated[scenario].append(
            AggregatedPoint(
                scenario=scenario,
                eta=eta,
                va_mean=float(sample.mean()),
                va_std=float(sample.std(ddof=1)) if sample.size > 1 else 0.0,
                num_seeds=int(sample.size),
            )
        )
    return aggregated


def write_demo_manifest(path: Path, selections: list[DemoSelection]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["scenario", "role", "eta", "seed", "run_directory", "trajectory_path"],
        )
        writer.writeheader()
        for selection in sorted(selections, key=lambda item: (item.scenario, item.role)):
            writer.writerow(
                {
                    "scenario": selection.scenario,
                    "role": selection.role,
                    "eta": format_eta(selection.record.config.eta),
                    "seed": selection.record.config.seed,
                    "run_directory": str(selection.record.run_directory.resolve()),
                    "trajectory_path": str(selection.record.trajectory_path.resolve()),
                }
            )


def _plot_va_timeseries(results_directory: Path, scenario: str, selections: list[DemoSelection]) -> None:
    scenario_selections = [selection for selection in selections if selection.scenario == scenario]
    if not scenario_selections:
        return

    plotted: dict[Path, tuple[RunRecord, list[str]]] = {}
    for selection in scenario_selections:
        key = selection.record.run_directory
        if key not in plotted:
            plotted[key] = (selection.record, [selection.role])
        else:
            plotted[key][1].append(selection.role)

    figure, axis = plt.subplots(figsize=(7, 4))
    color_cycle = iter(plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0", "C1", "C2"]))

    for run_directory in sorted(plotted):
        record, roles = plotted[run_directory]
        color = next(color_cycle, None) or "C0"
        series = compute_va_series(record.trajectory_path, record.config.v)
        times = np.asarray([time for time, _ in series], dtype=float)
        values = np.asarray([value for _, value in series], dtype=float)
        role_label = "/".join(sorted(roles))
        axis.plot(
            times,
            values,
            label=f"{role_label} (eta={format_eta(record.config.eta)}, seed={record.config.seed})",
            color=color,
            linewidth=1.4,
        )
        cutoff_time = times[record.summary.t_start]
        axis.axvline(cutoff_time, color=color, linestyle="--", linewidth=1.0, alpha=0.5)

    axis.set_title(f"Scenario {scenario}: polarization over time")
    axis.set_xlabel("Time (steps)")
    axis.set_ylabel("Polarization va")
    axis.set_ylim(-0.05, 1.05)
    axis.legend()
    _save_figure(figure, results_directory / f"va_timeseries_{scenario}")


def _plot_eta_vs_va(results_directory: Path, scenario: str, points: list[AggregatedPoint]) -> None:
    sorted_points = sorted(points, key=lambda point: point.eta)
    etas = np.asarray([point.eta for point in sorted_points], dtype=float)
    means = np.asarray([point.va_mean for point in sorted_points], dtype=float)
    stds = np.asarray([point.va_std for point in sorted_points], dtype=float)

    figure, axis = plt.subplots(figsize=(6.5, 4))
    axis.plot(etas, means, color="C0", linewidth=0.9, alpha=0.7)
    axis.errorbar(etas, means, yerr=stds, fmt="o", color="C0", markersize=4, capsize=3)
    axis.set_title(f"Scenario {scenario}: mean polarization vs noise")
    axis.set_xlabel("Noise amplitude eta")
    axis.set_ylabel("Mean polarization va")
    axis.set_ylim(-0.05, 1.05)
    _save_figure(figure, results_directory / f"eta_vs_va_{scenario}")


def _plot_eta_vs_va_comparison(
    results_directory: Path,
    aggregated_by_scenario: dict[str, list[AggregatedPoint]],
) -> None:
    markers = {"A": "o", "B": "s", "C": "^"}
    figure, axis = plt.subplots(figsize=(6.5, 4))

    for scenario in sorted(aggregated_by_scenario):
        points = sorted(aggregated_by_scenario[scenario], key=lambda point: point.eta)
        etas = np.asarray([point.eta for point in points], dtype=float)
        means = np.asarray([point.va_mean for point in points], dtype=float)
        stds = np.asarray([point.va_std for point in points], dtype=float)
        axis.plot(etas, means, linewidth=0.9, alpha=0.7)
        axis.errorbar(
            etas,
            means,
            yerr=stds,
            fmt=markers.get(scenario, "o"),
            markersize=4,
            capsize=3,
            label=f"Scenario {scenario}",
        )

    axis.set_title("Mean polarization vs noise")
    axis.set_xlabel("Noise amplitude eta")
    axis.set_ylabel("Mean polarization va")
    axis.set_ylim(-0.05, 1.05)
    axis.legend()
    _save_figure(figure, results_directory / "eta_vs_va_comparison")


def _run_is_complete(run_directory: Path) -> bool:
    return (run_directory / "run.json").exists() and (run_directory / "trajectory.extxyz").exists()


def _save_figure(figure: plt.Figure, base_path: Path) -> None:
    figure.tight_layout()
    figure.savefig(base_path.with_suffix(".png"), dpi=200)
    figure.savefig(base_path.with_suffix(".pdf"))
    plt.close(figure)
