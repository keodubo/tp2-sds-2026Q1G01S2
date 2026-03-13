from __future__ import annotations

import csv
from pathlib import Path

from tp2_sds.cli import main
from tp2_sds.reporting import discover_run_records, select_demo_runs


def test_select_demo_runs_prefers_min_max_eta_and_lowest_seed(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    assert (
        main(
            [
                "batch",
                "--scenarios",
                "A,B",
                "--etas",
                "0.5,1.5",
                "--seeds",
                "2,1",
                "--steps",
                "4",
                "--output-root",
                str(output_root),
                "--N",
                "12",
                "--rho",
                "0.12",
            ]
        )
        == 0
    )
    assert main(["analyze", "--runs-root", str(output_root)]) == 0

    records = discover_run_records(output_root)
    selections = {
        (selection.scenario, selection.role): (selection.record.config.eta, selection.record.config.seed)
        for selection in select_demo_runs(records)
    }

    assert selections[("A", "low_noise")] == (0.5, 1)
    assert selections[("A", "high_noise")] == (1.5, 1)
    assert selections[("B", "low_noise")] == (0.5, 1)
    assert selections[("B", "high_noise")] == (1.5, 1)


def test_plot_command_creates_expected_results_files(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    assert (
        main(
            [
                "batch",
                "--scenarios",
                "A,B,C",
                "--etas",
                "0.0,1.0",
                "--seeds",
                "1,2",
                "--steps",
                "5",
                "--output-root",
                str(output_root),
                "--N",
                "12",
                "--rho",
                "0.12",
            ]
        )
        == 0
    )
    assert main(["plot", "--runs-root", str(output_root), "--transient-fraction", "0.4"]) == 0

    results_directory = output_root / "results"
    expected_paths = [
        results_directory / "demo_manifest.csv",
        results_directory / "va_timeseries_A.png",
        results_directory / "va_timeseries_B.png",
        results_directory / "va_timeseries_C.png",
        results_directory / "eta_vs_va_A.pdf",
        results_directory / "eta_vs_va_B.pdf",
        results_directory / "eta_vs_va_C.pdf",
        results_directory / "eta_vs_va_comparison.png",
    ]
    for path in expected_paths:
        assert path.exists()

    with (results_directory / "demo_manifest.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 6
    assert {row["scenario"] for row in rows} == {"A", "B", "C"}
    assert {row["role"] for row in rows} == {"low_noise", "high_noise"}


def test_campaign_command_generates_runs_aggregate_and_figures(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    assert (
        main(
            [
                "campaign",
                "--runs-root",
                str(output_root),
                "--scenarios",
                "A,B,C",
                "--etas",
                "0.0,1.0",
                "--seeds",
                "1,2",
                "--steps",
                "5",
                "--N",
                "12",
                "--rho",
                "0.12",
            ]
        )
        == 0
    )

    assert len(list(output_root.rglob("trajectory.extxyz"))) == 12
    assert (output_root / "aggregate.csv").exists()
    assert (output_root / "results" / "demo_manifest.csv").exists()
    assert (output_root / "results" / "eta_vs_va_comparison.pdf").exists()
    assert (output_root / "results" / "va_timeseries_A.pdf").exists()
    assert (output_root / "results" / "va_timeseries_B.pdf").exists()
    assert (output_root / "results" / "va_timeseries_C.pdf").exists()
