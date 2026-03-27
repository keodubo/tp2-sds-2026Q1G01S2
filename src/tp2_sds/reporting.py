from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import matplotlib
import numpy as np

from .analysis import DEFAULT_TRANSIENT_FRACTION, analyze_runs, compute_angular_correlation_series, compute_va_series, discover_run_directories, stationary_window
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
from .io_extxyz import iter_extxyz
from .simulation import LEADER_TYPE, TAU, simulate_trajectory, write_simulation_run

matplotlib.use("Agg")
from matplotlib import pyplot as plt, ticker
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.cm import get_cmap

LEADER_MAGENTA = "#CC00CC"
DISPLAY_ETA_TICKS = (0.0, 2.5, 5.0)
REPORT_STATIONARY_START = 600


def _break_periodic_trail(
    x: np.ndarray, y: np.ndarray, box_length: float
) -> tuple[np.ndarray, np.ndarray]:
    """Insert NaN at periodic-boundary jumps so the plotted line breaks."""
    x = x.astype(float).copy()
    y = y.astype(float).copy()
    half = box_length / 2.0
    dx = np.abs(np.diff(x))
    dy = np.abs(np.diff(y))
    breaks = np.where((dx > half) | (dy > half))[0] + 1
    if breaks.size:
        x = np.insert(x, breaks, np.nan)
        y = np.insert(y, breaks, np.nan)
    return x, y


def _format_eta_display(eta: float) -> str:
    return f"{eta:.1f}"


def _configure_eta_axis(axis: plt.Axes) -> None:
    axis.set_xlim(0.0, 5.0)
    axis.set_xticks(DISPLAY_ETA_TICKS)
    axis.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))

DEFAULT_CAMPAIGN_SCENARIOS = ("A", "B", "C")
DEFAULT_CAMPAIGN_ETAS = tuple(index * 0.5 for index in range(11))
DEFAULT_CAMPAIGN_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_CAMPAIGN_STEPS = 400
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
        _plot_va_timeseries(results_directory, scenario, records)
        _plot_eta_vs_va(results_directory, scenario, points)
    _plot_eta_vs_va_comparison(results_directory, aggregated_by_scenario)

    for selection in selections:
        if selection.scenario in ("B", "C"):
            eta_tag = format_eta(selection.record.config.eta)
            seed = selection.record.config.seed
            corr_name = f"angular_correlation_{selection.scenario}_{selection.role}_eta{eta_tag}_seed{seed}"
            plot_angular_correlation(
                selection.record.trajectory_path,
                results_directory / corr_name,
                scenario=selection.scenario,
                eta=selection.record.config.eta,
            )

    for selection in selections:
        eta_tag = format_eta(selection.record.config.eta)
        seed = selection.record.config.seed
        gif_name = f"animation_{selection.scenario}_{selection.role}_eta{eta_tag}_seed{seed}"
        animate_trajectory(selection.record.trajectory_path, results_directory / gif_name)

    for selection in selections:
        if selection.role == "low_noise":
            eta_tag = format_eta(selection.record.config.eta)
            seed = selection.record.config.seed
            viz_name = f"visualization_{selection.scenario}_eta{eta_tag}_seed{seed}"
            plot_visualization_figure(
                selection.record.trajectory_path,
                results_directory / viz_name,
                eta=selection.record.config.eta,
            )

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


def _plot_va_timeseries(
    results_directory: Path,
    scenario: str,
    records: list[RunRecord],
    etas_to_plot: tuple[float, ...] = (0.0, 2.5, 5.0),
) -> None:
    scenario_records = [r for r in records if r.config.scenario == scenario]
    if not scenario_records:
        return

    # Group records by eta
    by_eta: dict[float, list[RunRecord]] = defaultdict(list)
    for record in scenario_records:
        by_eta[record.config.eta].append(record)

    figure, axis = plt.subplots(figsize=(7, 4))
    colors = ["C0", "C1", "C2", "C3", "C4"]
    stationary_marker_drawn = False

    for idx, eta in enumerate(etas_to_plot):
        # Find closest available eta
        closest_eta = min(by_eta.keys(), key=lambda e: abs(e - eta))
        if abs(closest_eta - eta) > 0.01:
            continue
        eta_records = by_eta[closest_eta]
        color = colors[idx % len(colors)]

        # Compute va series for all seeds
        all_values: list[np.ndarray] = []
        times: np.ndarray | None = None
        for record in sorted(eta_records, key=lambda r: r.config.seed):
            series = compute_va_series(record.trajectory_path, record.config.v)
            t = np.asarray([time for time, _ in series], dtype=float)
            v = np.asarray([value for _, value in series], dtype=float)
            if times is None:
                times = t
            all_values.append(v)

        if times is None or not all_values:
            continue

        matrix = np.stack(all_values)  # (n_seeds, n_timesteps)
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0, ddof=1) if matrix.shape[0] > 1 else np.zeros_like(mean)

        axis.plot(times, mean, color=color, linewidth=1.4, label=rf"$\eta={_format_eta_display(closest_eta)}$")
        axis.fill_between(times, mean - std, mean + std, color=color, alpha=0.2)

        if not stationary_marker_drawn:
            cutoff_time = float(REPORT_STATIONARY_START)
            if cutoff_time < times[0] or cutoff_time > times[-1]:
                t_start = min(max(eta_records[0].summary.t_start, 0), len(times) - 1)
                cutoff_time = float(times[t_start])
            axis.axvline(cutoff_time, color="0.45", linestyle="--", linewidth=1.1, alpha=0.9)
            stationary_marker_drawn = True

    axis.set_xlabel(r"Tiempo (pasos)")
    axis.set_ylabel(r"Polarización $v_a$")
    axis.set_ylim(-0.05, 1.05)
    axis.set_xlim(left=0.0)
    axis.set_xticks([0.0, float(REPORT_STATIONARY_START), 1200.0, 1800.0])
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
    axis.set_xlabel(r"Amplitud de ruido ($\eta$)")
    axis.set_ylabel(r"Polarización media ($v_a$)")
    axis.set_ylim(-0.05, 1.05)
    _configure_eta_axis(axis)
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
            label=f"Escenario {scenario}",
        )

    axis.set_xlabel(r"Amplitud de ruido ($\eta$)")
    axis.set_ylabel(r"Polarización media ($v_a$)")
    axis.set_ylim(-0.05, 1.05)
    _configure_eta_axis(axis)
    axis.legend()
    _save_figure(figure, results_directory / "eta_vs_va_comparison")


def compute_va_mean_inline(
    config: SimulationConfig,
    transient_fraction: float = DEFAULT_TRANSIENT_FRACTION,
) -> float:
    """Run a simulation in memory and return stationary va_mean without writing to disk."""
    frames = simulate_trajectory(config)
    n_frames = len(frames)
    t_start, t_end = stationary_window(n_frames, transient_fraction)
    va_values = []
    for frame in frames[t_start: t_end + 1]:
        collective = np.linalg.norm(frame.velocities[:, :2].sum(axis=0))
        n_particles = frame.velocities.shape[0]
        va_values.append(collective / (n_particles * config.v))
    return float(np.mean(va_values))


def plot_va_vs_eta_by_N(
    output_path: Path,
    *,
    scenario: str = "A",
    N_values: tuple[int, ...] = (40, 100, 400, 4000),
    etas: tuple[float, ...] | None = None,
    steps: int = 400,
    seed: int = 1,
    seeds: tuple[int, ...] | None = None,
    L: float | None = None,
) -> Path:
    """Generate va vs η plot for different N values (replicates Vicsek 1995 Fig. 1a).

    When *seeds* is provided, each (N, η) point is averaged over all seeds
    and plotted with error bars (± 1 std).  The legacy *seed* parameter is
    used only when *seeds* is ``None`` (single-seed mode, backwards compat).
    """
    if etas is None:
        etas = tuple(i * 0.25 for i in range(21))  # 0.0 to 5.0 step 0.25

    if seeds is None:
        seeds = (seed,)

    markers = ["o", "s", "^", "D", "v", "P", "*", "X"]
    figure, axis = plt.subplots(figsize=(7, 5))

    for idx, N in enumerate(sorted(N_values)):
        # Compute L from N to keep density constant (rho = N / L^2)
        if L is not None:
            box_L = L
        else:
            box_L = np.sqrt(N / DEFAULT_RHO)
        means = []
        stds = []
        for eta in etas:
            va_values = []
            for s in seeds:
                config = make_simulation_config(
                    scenario=scenario,
                    eta=eta,
                    steps=steps,
                    seed=s,
                    L=box_L,
                    rho=None,
                    N=N,
                )
                va_values.append(compute_va_mean_inline(config))
            sample = np.asarray(va_values, dtype=float)
            va_mean = float(sample.mean())
            va_std = float(sample.std(ddof=1)) if sample.size > 1 else 0.0
            means.append(va_mean)
            stds.append(va_std)
            print(f"  N={N}, η={eta:.2f} → va={va_mean:.4f} ± {va_std:.4f} ({len(seeds)} seeds)")

        marker = markers[idx % len(markers)]
        axis.errorbar(
            etas, means, yerr=stds,
            fmt=marker, markersize=4, linewidth=1.0, capsize=3,
            label=f"N={N}",
        )

    axis.set_xlabel(r"$\eta$", fontsize=12)
    axis.set_ylabel(r"$v_a$", fontsize=12)
    axis.set_title(f"Escenario {scenario}: $v_a$ vs $\\eta$ para distintos N")
    axis.set_ylim(-0.05, 1.05)
    axis.set_xlim(left=0)
    axis.legend()
    axis.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_figure(figure, output_path)
    return output_path.with_suffix(".png")


def plot_va_timeseries_by_eta(
    output_path: Path,
    *,
    scenario: str = "A",
    N: int = 300,
    etas: tuple[float, ...] = (0.0, 0.2, 0.6, 1.2, 2.4, 3.0, 5.2),
    steps: int = 400,
    seed: int = 1,
    L: float | None = None,
) -> Path:
    """Generate polarisation vs time plot for different eta values."""
    if L is None:
        box_L = np.sqrt(N / DEFAULT_RHO)
    else:
        box_L = L

    figure, axis = plt.subplots(figsize=(10, 6))

    for eta in sorted(etas):
        config = make_simulation_config(
            scenario=scenario,
            eta=eta,
            steps=steps,
            seed=seed,
            L=box_L,
            rho=None,
            N=N,
        )
        frames = simulate_trajectory(config)
        times = []
        va_values = []
        for frame in frames:
            collective = np.linalg.norm(frame.velocities[:, :2].sum(axis=0))
            n_particles = frame.velocities.shape[0]
            va = collective / (n_particles * config.v)
            times.append(frame.time)
            va_values.append(va)
        axis.plot(times, va_values, linewidth=0.8, label=f"η = {eta}")
        print(f"  η={eta:.1f} done ({steps} steps)")

    axis.set_xlabel("Tiempo (s)", fontsize=12)
    axis.set_ylabel("Polarización", fontsize=12)
    axis.set_title(f"Escenario {scenario}: Polarización vs tiempo (N={N})")
    axis.set_ylim(-0.05, 1.05)
    axis.set_xlim(left=0)
    axis.legend(loc="center right")
    axis.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_figure(figure, output_path)
    return output_path.with_suffix(".png")


def _run_is_complete(run_directory: Path) -> bool:
    return (run_directory / "run.json").exists() and (run_directory / "trajectory.extxyz").exists()


def animate_trajectory(
    trajectory_path: Path,
    output_path: Path,
    *,
    box_length: float = 10.0,
    frame_step: int = 1,
    fps: int = 20,
    arrow_scale: float = 2.0,
    dpi: int = 150,
) -> Path:
    from .simulation import _hsv_to_rgb

    frames: list[dict] = []
    for i, frame in enumerate(iter_extxyz(trajectory_path)):
        if i % frame_step != 0:
            continue
        L = frame.lattice[0]
        if L > 0:
            box_length = L
        leader_mask = frame.types == LEADER_TYPE
        normal_mask = ~leader_mask
        angles = np.arctan2(frame.velocities[:, 1], frame.velocities[:, 0])
        hue = (angles % TAU) / TAU
        colors = _hsv_to_rgb(hue)
        frames.append({
            "x": frame.positions[:, 0].copy(),
            "y": frame.positions[:, 1].copy(),
            "u": np.cos(angles),
            "v": np.sin(angles),
            "colors": colors,
            "leader": leader_mask,
            "normal": normal_mask,
            "time": frame.time,
        })
    if not frames:
        raise ValueError(f"No frames found in {trajectory_path}")

    figure, axis = plt.subplots(figsize=(6, 6))
    axis.set_facecolor("black")
    axis.set_aspect("equal")
    axis.set_xlim(0, box_length)
    axis.set_ylim(0, box_length)
    axis.set_xticks([])
    axis.set_yticks([])
    figure.patch.set_facecolor("black")
    figure.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.98)

    f0 = frames[0]
    nm = f0["normal"]
    lm = f0["leader"]
    quiver_normal = axis.quiver(
        f0["x"][nm], f0["y"][nm], f0["u"][nm], f0["v"][nm],
        color=f0["colors"][nm],
        angles="xy", scale_units="xy", scale=arrow_scale,
        width=0.004, headwidth=3, headlength=4,
    )
    quiver_leader = None
    has_leader = lm.any()
    leader_trail_line = None
    leader_trail_x: list[float] = []
    leader_trail_y: list[float] = []
    if has_leader:
        quiver_leader = axis.quiver(
            f0["x"][lm], f0["y"][lm], f0["u"][lm], f0["v"][lm],
            color=LEADER_MAGENTA, edgecolor="white", linewidth=1.0,
            angles="xy", scale_units="xy", scale=arrow_scale * 0.7,
            width=0.010, headwidth=3, headlength=4, zorder=10,
        )
        (leader_trail_line,) = axis.plot(
            [], [], linestyle="--", color=LEADER_MAGENTA, alpha=0.6,
            linewidth=1.2, zorder=5,
        )
        leader_trail_x.append(float(f0["x"][lm][0]))
        leader_trail_y.append(float(f0["y"][lm][0]))

    def _update(frame_index: int):
        data = frames[frame_index]
        nm = data["normal"]
        lm = data["leader"]
        quiver_normal.set_offsets(np.column_stack((data["x"][nm], data["y"][nm])))
        quiver_normal.set_UVC(data["u"][nm], data["v"][nm])
        quiver_normal.set_color(data["colors"][nm])
        if quiver_leader is not None and lm.any():
            quiver_leader.set_offsets(np.column_stack((data["x"][lm], data["y"][lm])))
            quiver_leader.set_UVC(data["u"][lm], data["v"][lm])
            leader_trail_x.append(float(data["x"][lm][0]))
            leader_trail_y.append(float(data["y"][lm][0]))
            tx, ty = _break_periodic_trail(
                np.array(leader_trail_x), np.array(leader_trail_y), box_length,
            )
            leader_trail_line.set_data(tx, ty)

    animation = FuncAnimation(figure, _update, frames=len(frames), interval=1000 // fps, blit=False)
    gif_path = output_path.with_suffix(".gif")
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    animation.save(str(gif_path), writer=PillowWriter(fps=fps), dpi=dpi)
    plt.close(figure)
    return gif_path


def plot_visualization_figure(
    trajectory_path: Path,
    output_path: Path,
    *,
    frame_index: int = -1,
    eta: float | None = None,
    dpi: int = 200,
) -> Path:
    # Collect leader trail positions while iterating to the target frame.
    leader_trail_x: list[float] = []
    leader_trail_y: list[float] = []
    if frame_index == -1:
        for f in iter_extxyz(trajectory_path):
            lm = f.types == LEADER_TYPE
            if lm.any():
                leader_trail_x.append(float(f.positions[lm, 0][0]))
                leader_trail_y.append(float(f.positions[lm, 1][0]))
            frame = f  # keep last
    else:
        for i, f in enumerate(iter_extxyz(trajectory_path)):
            lm = f.types == LEADER_TYPE
            if lm.any():
                leader_trail_x.append(float(f.positions[lm, 0][0]))
                leader_trail_y.append(float(f.positions[lm, 1][0]))
            if i == frame_index:
                frame = f
                break
        else:
            raise ValueError(f"Frame index {frame_index} not found in {trajectory_path}")

    box_length = frame.lattice[0]
    leader_mask = frame.types == LEADER_TYPE
    normal_mask = ~leader_mask
    angles = np.arctan2(frame.velocities[:, 1], frame.velocities[:, 0])
    hsv_cmap = get_cmap("hsv")
    colors = hsv_cmap((angles % TAU) / TAU)

    L = box_length

    figure, ax_main = plt.subplots(figsize=(6.8, 6.8), facecolor="white")
    figure.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.98)

    # --- Main panel ---
    ax_main.set_facecolor("white")
    ax_main.set_aspect("equal")
    ax_main.set_xlim(0, L)
    ax_main.set_ylim(0, L)
    ax_main.set_xticks([])
    ax_main.set_yticks([])
    for spine in ax_main.spines.values():
        spine.set_linewidth(2)
        spine.set_color("black")

    u = np.cos(angles)
    v_arr = np.sin(angles)

    if normal_mask.any():
        ax_main.quiver(
            frame.positions[normal_mask, 0],
            frame.positions[normal_mask, 1],
            u[normal_mask],
            v_arr[normal_mask],
            color=colors[normal_mask],
            angles="xy",
            scale_units="xy",
            scale=2.5,
            width=0.005,
            headwidth=3,
            headlength=4,
        )

    if leader_mask.any():
        ax_main.quiver(
            frame.positions[leader_mask, 0],
            frame.positions[leader_mask, 1],
            u[leader_mask],
            v_arr[leader_mask],
            color=LEADER_MAGENTA,
            edgecolor="black",
            linewidth=1.0,
            angles="xy",
            scale_units="xy",
            scale=2.5 * 0.55,
            width=0.012,
            headwidth=3,
            headlength=4,
            zorder=10,
        )
        if len(leader_trail_x) > 1:
            tx, ty = _break_periodic_trail(
                np.array(leader_trail_x), np.array(leader_trail_y), L,
            )
            ax_main.plot(
                tx, ty, linestyle=":", color=LEADER_MAGENTA,
                alpha=0.5, linewidth=1.5, zorder=5,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path.with_suffix(".png"), dpi=dpi, bbox_inches="tight", pad_inches=0.02)
    figure.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.02)
    plt.close(figure)
    return output_path.with_suffix(".png")


def plot_angular_correlation(
    trajectory_path: Path,
    output_path: Path,
    *,
    scenario: str = "",
    eta: float = 0.0,
) -> Path | None:
    """Plot collective angle theta_S, leader angle theta_L, and correlation C(t).

    Returns the output PNG path, or None if the trajectory has no leader.
    """
    series = compute_angular_correlation_series(trajectory_path)
    if not series:
        return None

    times = np.asarray([t for t, _, _, _ in series], dtype=float)
    theta_s = np.asarray([ts for _, ts, _, _ in series], dtype=float)
    theta_l = np.asarray([tl for _, _, tl, _ in series], dtype=float)
    correlation = np.asarray([c for _, _, _, c in series], dtype=float)

    figure, (ax_angles, ax_corr) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    ax_angles.plot(times, theta_l, linewidth=1.0, label=r"$\theta_L$ (líder)", color=LEADER_MAGENTA)
    ax_angles.plot(times, theta_s, linewidth=1.0, label=r"$\theta_S$ (colectivo)", color="C0")
    ax_angles.set_ylabel(r"Ángulo (rad)")
    ax_angles.set_ylim(-np.pi - 0.3, np.pi + 0.3)
    ax_angles.axhline(np.pi, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)
    ax_angles.axhline(-np.pi, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)
    ax_angles.legend(loc="upper right")
    ax_corr.plot(times, correlation, linewidth=1.0, color="C2")
    ax_corr.set_xlabel(r"Tiempo (pasos)")
    ax_corr.set_ylabel(r"$C(t) = \cos(\theta_L - \theta_S)$")
    ax_corr.set_ylim(-1.1, 1.1)
    ax_corr.axhline(1.0, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)
    ax_corr.axhline(0.0, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)
    ax_corr.axhline(-1.0, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_figure(figure, output_path)
    return output_path.with_suffix(".png")


def _save_figure(figure: plt.Figure, base_path: Path) -> None:
    figure.tight_layout()
    figure.savefig(base_path.with_suffix(".png"), dpi=200)
    figure.savefig(base_path.with_suffix(".pdf"))
    plt.close(figure)
