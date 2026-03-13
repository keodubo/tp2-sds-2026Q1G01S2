from __future__ import annotations

import csv
import json
from pathlib import Path

from tp2_sds.cli import main
from tp2_sds.config import build_run_directory


def test_simulate_is_reproducible_and_force_controls_overwrite(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "outputs"
    args = [
        "simulate",
        "--scenario",
        "A",
        "--eta",
        "0.200000",
        "--seed",
        "42",
        "--steps",
        "4",
        "--output-root",
        str(output_root),
        "--N",
        "12",
        "--rho",
        "0.12",
    ]

    assert main(args) == 0
    run_directory = build_run_directory(output_root, "A", 0.2, 42)
    first_contents = (run_directory / "trajectory.extxyz").read_text(encoding="utf-8")

    assert main(args) == 1
    assert "Use --force to overwrite" in capsys.readouterr().err

    assert main([*args, "--force"]) == 0
    second_contents = (run_directory / "trajectory.extxyz").read_text(encoding="utf-8")

    assert first_contents == second_contents
    assert json.loads((run_directory / "run.json").read_text(encoding="utf-8"))["seed"] == 42


def test_batch_and_analyze_generate_expected_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    assert (
        main(
            [
                "batch",
                "--scenarios",
                "A,B",
                "--etas",
                "0.1,1.4",
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

    trajectories = sorted(output_root.rglob("trajectory.extxyz"))
    assert len(trajectories) == 8

    assert main(["analyze", "--runs-root", str(output_root)]) == 0

    summary_paths = sorted(output_root.rglob("summary.json"))
    assert len(summary_paths) == 8

    summary_payload = json.loads(summary_paths[0].read_text(encoding="utf-8"))
    assert set(summary_payload) == {"scenario", "eta", "seed", "t_start", "t_end", "va_mean_stationary"}

    with (output_root / "aggregate.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4
    assert {row["scenario"] for row in rows} == {"A", "B"}
    assert {row["eta"] for row in rows} == {"0.100000", "1.400000"}
