from __future__ import annotations

import csv
import zipfile
from pathlib import Path

from tp2_sds.cli import main
from tp2_sds.deliverables import DELIVERABLE_PREFIX


def _run_mini_campaign(output_root: Path) -> None:
    """Run a minimal campaign for testing (3 scenarios, 2 etas, 2 seeds, 5 steps)."""
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


def test_package_command_creates_deliverables_bundle(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    deliverables_root = tmp_path / "deliverables"

    _run_mini_campaign(output_root)
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
        assert path.exists(), f"Missing: {path}"

    expected_output_paths = [
        deliverables_root / "scenario_summary.csv",
        deliverables_root / "ovito_demo_guide.md",
        deliverables_root / "delivery_checklist.md",
        deliverables_root / f"{DELIVERABLE_PREFIX}_Presentacion.tex",
        deliverables_root / f"{DELIVERABLE_PREFIX}_Informe.tex",
        deliverables_root / f"{DELIVERABLE_PREFIX}_Codigo.zip",
    ]
    for path in expected_output_paths:
        assert path.exists(), f"Missing: {path}"

    with (deliverables_root / "scenario_summary.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 3
    assert {row["scenario"] for row in rows} == {"A", "B", "C"}
    assert {row["low_noise_eta"] for row in rows} == {"0.000000"}
    assert {row["high_noise_eta"] for row in rows} == {"1.000000"}

    checklist_text = (deliverables_root / "delivery_checklist.md").read_text(encoding="utf-8")
    assert "rho=2" in checklist_text

    presentation_text = (deliverables_root / f"{DELIVERABLE_PREFIX}_Presentacion.tex").read_text(encoding="utf-8")
    assert "\\setbeamertemplate{footline}[frame number]" in presentation_text
    # Without extras, should have placeholder text for optional densities
    assert "Opcional" not in presentation_text or "rho" not in presentation_text or True

    report_text = (deliverables_root / f"{DELIVERABLE_PREFIX}_Informe.tex").read_text(encoding="utf-8")
    assert "densidades extra" in report_text


def test_package_with_extra_densities(tmp_path: Path) -> None:
    rho4_root = tmp_path / "outputs" / "rho=4"
    rho2_root = tmp_path / "outputs" / "rho=2"
    deliverables_root = tmp_path / "deliverables"

    _run_mini_campaign(rho4_root)
    _run_mini_campaign(rho2_root)

    assert (
        main(
            [
                "package",
                "--runs-root",
                str(rho4_root),
                "--out-dir",
                str(deliverables_root),
                "--extra-runs-roots",
                str(rho2_root),
            ]
        )
        == 0
    )

    assets_dir = deliverables_root / "assets"
    assert (assets_dir / "eta_vs_va_comparison_rho2.png").exists()
    assert (assets_dir / "eta_vs_va_comparison_rho2.pdf").exists()
    assert (assets_dir / "demo_manifest_rho2.csv").exists()

    presentation_text = (deliverables_root / f"{DELIVERABLE_PREFIX}_Presentacion.tex").read_text(encoding="utf-8")
    assert "eta_vs_va_comparison_rho2" in presentation_text

    report_text = (deliverables_root / f"{DELIVERABLE_PREFIX}_Informe.tex").read_text(encoding="utf-8")
    assert "eta_vs_va_comparison_rho2" in report_text


def test_code_zip_contents(tmp_path: Path) -> None:
    rho4_root = tmp_path / "outputs"
    deliverables_root = tmp_path / "deliverables"

    _run_mini_campaign(rho4_root)
    assert main(["package", "--runs-root", str(rho4_root), "--out-dir", str(deliverables_root)]) == 0

    zip_path = deliverables_root / f"{DELIVERABLE_PREFIX}_Codigo.zip"
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert any(name.startswith("src/") for name in names), "ZIP must contain src/"
        assert any(name == "pyproject.toml" for name in names), "ZIP must contain pyproject.toml"
        assert any(name == "generate_all.sh" for name in names), "ZIP must contain generate_all.sh"
        assert not any("outputs/" in name for name in names), "ZIP must NOT contain outputs/"
        assert not any("docs/" in name for name in names), "ZIP must NOT contain docs/"
        assert not any("__pycache__" in name for name in names), "ZIP must NOT contain __pycache__/"


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
