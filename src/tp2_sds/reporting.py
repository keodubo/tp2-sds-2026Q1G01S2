from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import matplotlib
import numpy as np

from .analysis import DEFAULT_TRANSIENT_FRACTION, analyze_runs, compute_va_series, discover_run_directories, stationary_window
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
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.cm import get_cmap

LEADER_MAGENTA = "#CC00CC"


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
        axis.axvspan(times[0], cutoff_time, alpha=0.07, color=color)
        mid_transient = (times[0] + cutoff_time) / 2
        axis.text(mid_transient, 1.0, "transiente", ha="center", va="top", fontsize=8, color=color, alpha=0.7)
        mid_stationary = (cutoff_time + times[-1]) / 2
        axis.text(mid_stationary, 1.0, "estado estacionario", ha="center", va="top", fontsize=8, color=color, alpha=0.7)

    axis.set_xlabel(r"Tiempo (pasos)")
    axis.set_ylabel(r"Polarización $v_a$")
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
    axis.set_xlabel(r"Amplitud de ruido ($\eta$)")
    axis.set_ylabel(r"Polarización media ($v_a$)")
    axis.set_title(f"Escenario {scenario}")
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

    axis.set_xlabel(r"Amplitud de ruido ($\eta$)")
    axis.set_ylabel(r"Polarización media ($v_a$)")
    axis.set_title("Comparación entre escenarios")
    axis.set_ylim(-0.05, 1.05)
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
    steps: int = 2000,
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


def _run_is_complete(run_directory: Path) -> bool:
    return (run_directory / "run.json").exists() and (run_directory / "trajectory.extxyz").exists()


def animate_trajectory(
    trajectory_path: Path,
    output_path: Path,
    *,
    box_length: float = 10.0,
    frame_step: int = 10,
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
    title = axis.set_title(f"t = {frames[0]['time']:.0f}", color="white", fontsize=12)
    figure.patch.set_facecolor("black")

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
        title.set_text(f"t = {data['time']:.0f}")

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
    from collections import deque

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

    N_particles = int(frame.ids.shape[0])
    L = box_length

    figure = plt.figure(figsize=(12, 7), facecolor="white")
    gs = figure.add_gridspec(1, 2, width_ratios=[3, 1.3], wspace=0.3)
    ax_main = figure.add_subplot(gs[0, 0])
    ax_wheel = figure.add_subplot(gs[0, 1], projection="polar")

    figure.suptitle(
        "VISUALIZATION OF SELF-PROPELLED PARTICLE FLOCKING (VICSEK MODEL)",
        fontsize=13,
        fontweight="bold",
        y=0.97,
    )

    eta_str = f"{eta:.1f}" if eta is not None else "?"
    ax_main.set_title(
        f"Simulation Parameters: (N={N_particles}, L={L:.0f}, \u03b7={eta_str})",
        fontsize=10,
        pad=8,
    )

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
        lx = float(frame.positions[leader_mask, 0][0])
        ly = float(frame.positions[leader_mask, 1][0])
        ax_main.annotate(
            "Leader Agent\n(Fixed Unique Color)",
            xy=(lx, ly),
            xytext=(lx + L * 0.15, ly + L * 0.15),
            fontsize=8,
            fontweight="bold",
            ha="center",
            arrowprops=dict(arrowstyle="->", color="black", lw=1.5),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        )

    # --- Color wheel panel ---
    theta_wheel = np.linspace(0, TAU, 256)
    r_wheel = np.linspace(0, 1, 2)
    theta_grid, r_grid = np.meshgrid(theta_wheel, r_wheel)
    color_values = theta_grid / TAU
    ax_wheel.pcolormesh(theta_grid, r_grid, color_values, cmap="hsv", shading="auto")
    ax_wheel.set_yticks([])
    ax_wheel.set_xticks([0, np.pi / 2, np.pi, 3 * np.pi / 2])
    ax_wheel.set_xticklabels(["0 / 2\u03c0", "\u03c0/2", "\u03c0", "3\u03c0/2"], fontsize=8)

    n_arrows = 12
    for i in range(n_arrows):
        a = i * TAU / n_arrows
        c = hsv_cmap(a / TAU)
        ax_wheel.annotate(
            "",
            xy=(a, 0.85),
            xytext=(a, 0.45),
            arrowprops=dict(arrowstyle="->", color=c, lw=2),
        )

    ax_wheel.set_title(
        "Cyclicalization for\nDirection to Color\n(0 a 2\u03c0 radians)",
        fontsize=9,
        pad=12,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)
    return output_path.with_suffix(".png")


def _save_figure(figure: plt.Figure, base_path: Path) -> None:
    figure.tight_layout()
    figure.savefig(base_path.with_suffix(".png"), dpi=200)
    figure.savefig(base_path.with_suffix(".pdf"))
    plt.close(figure)
