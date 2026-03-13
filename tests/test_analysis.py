from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from tp2_sds.analysis import analyze_run, stationary_window, write_aggregate_csv
from tp2_sds.config import RunSummary, make_simulation_config
from tp2_sds.io_extxyz import TrajectoryFrame, lattice_for_box, write_extxyz


def test_stationary_window_discards_initial_fraction_but_keeps_last_frame() -> None:
    assert stationary_window(1) == (0, 0)
    assert stationary_window(2) == (1, 1)
    assert stationary_window(10) == (3, 9)


def test_write_aggregate_csv_uses_sample_standard_deviation(tmp_path: Path) -> None:
    path = tmp_path / "aggregate.csv"
    summaries = [
        RunSummary(scenario="A", eta=0.1, seed=1, t_start=3, t_end=9, va_mean_stationary=1.0),
        RunSummary(scenario="A", eta=0.1, seed=2, t_start=3, t_end=9, va_mean_stationary=3.0),
    ]

    write_aggregate_csv(path, summaries)

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["scenario"] == "A"
    assert rows[0]["eta"] == "0.100000"
    assert np.isclose(float(rows[0]["va_mean"]), 2.0)
    assert np.isclose(float(rows[0]["va_std"]), np.sqrt(2.0))


def test_analyze_run_respects_transient_fraction(tmp_path: Path) -> None:
    run_directory = tmp_path / "scenario=A" / "eta=0.100000" / "seed=1"
    run_directory.mkdir(parents=True)
    config = make_simulation_config(
        scenario="A",
        eta=0.1,
        steps=5,
        seed=1,
        L=2.0,
        N=2,
        rho=0.5,
        v=1.0,
    )
    (run_directory / "run.json").write_text(json.dumps(config.to_dict()), encoding="utf-8")

    velocities = [
        np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]], dtype=float),
        np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]], dtype=float),
        np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
        np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
        np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float),
    ]
    frames = [
        TrajectoryFrame(
            ids=np.array([1, 2], dtype=int),
            types=np.array([1, 1], dtype=int),
            positions=np.zeros((2, 3), dtype=float),
            velocities=velocity_frame,
            radii=np.full(2, 0.25, dtype=float),
            colors=np.tile(np.array([0.5, 0.5, 0.5], dtype=float), (2, 1)),
            vector_colors=np.tile(np.array([1.0, 0.0, 0.0], dtype=float), (2, 1)),
            time=float(index),
            lattice=lattice_for_box(2.0),
        )
        for index, velocity_frame in enumerate(velocities)
    ]
    write_extxyz(run_directory / "trajectory.extxyz", frames)

    summary = analyze_run(run_directory, transient_fraction=0.4)

    assert summary.t_start == 2
    assert summary.t_end == 4
    assert np.isclose(summary.va_mean_stationary, 1.0)
