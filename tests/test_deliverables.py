from __future__ import annotations

import csv
from pathlib import Path

from tp2_sds.cli import main


def test_package_command_creates_deliverables_bundle(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    deliverables_root = tmp_path / "deliverables"

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
    assert main(["package", "--runs-root", str(output_root), "--out-dir", str(deliverables_root)]) == 0

    assets_dir = deliverables_root / "assets"
    assert assets_dir.exists()

    expected_asset_paths = [
        assets_dir / "aggregate.csv",
        assets_dir / "demo_manifest.csv",
        assets_dir / "va_timeseries_A.pdf",
        assets_dir / "va_timeseries_B.png",
        assets_dir / "va_timeseries_C.pdf",
        assets_dir / "eta_vs_va_A.png",
        assets_dir / "eta_vs_va_B.pdf",
        assets_dir / "eta_vs_va_C.png",
        assets_dir / "eta_vs_va_comparison.pdf",
    ]
    for path in expected_asset_paths:
        assert path.exists()

    expected_output_paths = [
        deliverables_root / "scenario_summary.csv",
        deliverables_root / "ovito_demo_guide.md",
        deliverables_root / "delivery_checklist.md",
        deliverables_root / "presentation_template.tex",
        deliverables_root / "report_template.tex",
    ]
    for path in expected_output_paths:
        assert path.exists()

    with (deliverables_root / "scenario_summary.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3
    assert {row["scenario"] for row in rows} == {"A", "B", "C"}
    assert {row["low_noise_eta"] for row in rows} == {"0.000000"}
    assert {row["high_noise_eta"] for row in rows} == {"1.000000"}

    checklist_text = (deliverables_root / "delivery_checklist.md").read_text(encoding="utf-8")
    presentation_text = (deliverables_root / "presentation_template.tex").read_text(encoding="utf-8")
    report_text = (deliverables_root / "report_template.tex").read_text(encoding="utf-8")

    assert "rho=2" in checklist_text
    assert "\\setbeamertemplate{footline}[frame number]" in presentation_text
    assert "Opcional: densidades extra" in report_text


def test_package_command_fails_when_required_scenarios_are_missing(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "outputs"

    assert (
        main(
            [
                "campaign",
                "--runs-root",
                str(output_root),
                "--scenarios",
                "A,B",
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

    assert main(["package", "--runs-root", str(output_root)]) == 1
    assert "Missing required scenarios in aggregate.csv: C" in capsys.readouterr().err
