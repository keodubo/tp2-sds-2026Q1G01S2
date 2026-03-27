from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .reporting import DEMO_MANIFEST_NAME, RESULTS_DIRECTORY_NAME

GROUP_ID = "2026Q1G01S2"
DELIVERABLE_PREFIX = f"SdS_TP2_{GROUP_ID}"
REQUIRED_SCENARIOS = ("A", "B", "C")
REQUIRED_ROLES = ("low_noise", "high_noise")
REQUIRED_FIGURE_BASENAMES = (
    "va_timeseries_A",
    "va_timeseries_B",
    "va_timeseries_C",
    "eta_vs_va_A",
    "eta_vs_va_B",
    "eta_vs_va_C",
    "eta_vs_va_comparison",
)


@dataclass(frozen=True)
class PackageResult:
    out_dir: Path
    assets_dir: Path
    packaged_assets: int


def package_deliverables(
    runs_root: Path,
    out_dir: Path | None = None,
    extra_runs_roots: list[Path] | None = None,
) -> PackageResult:
    results_dir = runs_root / RESULTS_DIRECTORY_NAME
    aggregate_path = runs_root / "aggregate.csv"
    manifest_path = results_dir / DEMO_MANIFEST_NAME

    required_assets = _validate_required_inputs(runs_root, results_dir, aggregate_path, manifest_path)
    out_dir = out_dir if out_dir is not None else runs_root / "deliverables"
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    packaged_assets = 0
    for path in [aggregate_path, manifest_path, *required_assets]:
        shutil.copy2(path, assets_dir / path.name)
        packaged_assets += 1

    packaged_assets += _package_report_assets(assets_dir, results_dir)
    extra_densities = _package_extra_densities(assets_dir, extra_runs_roots or [])
    packaged_assets += extra_densities

    has_rho2 = (assets_dir / "eta_vs_va_comparison_rho2.png").exists()
    has_rho8 = (assets_dir / "eta_vs_va_comparison_rho8.png").exists()

    report_path = out_dir / f"{DELIVERABLE_PREFIX}_Informe.tex"
    if not report_path.exists():
        _write_report_template(
            report_path,
            has_rho2=has_rho2,
            has_rho8=has_rho8,
        )

    return PackageResult(out_dir=out_dir, assets_dir=assets_dir, packaged_assets=packaged_assets)


def _package_report_assets(assets_dir: Path, results_dir: Path) -> int:
    """Copy the additional assets referenced by the maintained report."""
    packaged = 0

    for scenario in REQUIRED_SCENARIOS:
        packaged += _copy_first_existing(
            [
                results_dir / f"visualization_{scenario}_low_noise_eta0.png",
                results_dir / f"visualization_{scenario}_eta0.png",
            ],
            assets_dir / f"snapshot_{scenario}.png",
        )
        packaged += _copy_first_existing(
            [
                results_dir / f"animation_{scenario}_low_noise_eta0.gif",
            ],
            assets_dir / f"animation_{scenario}_low_noise.gif",
        )

    packaged += _copy_first_existing(
        [results_dir / "va_timeseries_A.pdf"],
        assets_dir / "va_timeseries_A_rho4.pdf",
    )
    return packaged


def _package_extra_densities(assets_dir: Path, extra_roots: list[Path]) -> int:
    """Copy the extra-density assets referenced by the maintained report."""
    packaged = 0
    for root in extra_roots:
        rho_tag = _extract_rho_tag(root)
        if rho_tag is None:
            continue
        results_dir = root / RESULTS_DIRECTORY_NAME
        for suffix in (".png", ".pdf"):
            src = results_dir / f"eta_vs_va_comparison{suffix}"
            if src.exists():
                shutil.copy2(src, assets_dir / f"eta_vs_va_comparison_{rho_tag}{suffix}")
                packaged += 1
        manifest_src = results_dir / DEMO_MANIFEST_NAME
        if manifest_src.exists():
            shutil.copy2(manifest_src, assets_dir / f"demo_manifest_{rho_tag}.csv")
            packaged += 1
        timeseries_src = results_dir / "va_timeseries_A.pdf"
        if timeseries_src.exists():
            shutil.copy2(timeseries_src, assets_dir / f"va_timeseries_A_{rho_tag}.pdf")
            packaged += 1
    return packaged


def _extract_rho_tag(root: Path) -> str | None:
    """Extract rho tag from directory name like 'rho=2' → 'rho2'."""
    match = re.search(r"rho[=_](\d+)", root.name)
    if match:
        return f"rho{match.group(1)}"
    return None


def _validate_required_inputs(
    runs_root: Path,
    results_dir: Path,
    aggregate_path: Path,
    manifest_path: Path,
) -> list[Path]:
    if not runs_root.exists():
        raise FileNotFoundError(f"Runs root does not exist: {runs_root}")
    if not aggregate_path.exists():
        raise FileNotFoundError(f"Missing aggregate.csv at {aggregate_path}")
    if not results_dir.exists():
        raise FileNotFoundError(f"Missing results directory at {results_dir}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing demo manifest at {manifest_path}")

    aggregate_rows = _read_csv_rows(aggregate_path)
    manifest_rows = _read_csv_rows(manifest_path)

    scenarios_in_aggregate = {row["scenario"] for row in aggregate_rows}
    missing_scenarios = [scenario for scenario in REQUIRED_SCENARIOS if scenario not in scenarios_in_aggregate]
    if missing_scenarios:
        raise ValueError(f"Missing required scenarios in aggregate.csv: {', '.join(missing_scenarios)}")

    roles_by_scenario = {
        scenario: {row["role"] for row in manifest_rows if row["scenario"] == scenario}
        for scenario in REQUIRED_SCENARIOS
    }
    for scenario, roles in roles_by_scenario.items():
        missing_roles = [role for role in REQUIRED_ROLES if role not in roles]
        if missing_roles:
            raise ValueError(f"Missing demo selections for scenario {scenario}: {', '.join(missing_roles)}")

    missing_paths: list[str] = []
    for row in manifest_rows:
        if row["scenario"] not in REQUIRED_SCENARIOS:
            continue
        trajectory_path = Path(row["trajectory_path"])
        run_directory = Path(row["run_directory"])
        if not trajectory_path.exists():
            missing_paths.append(str(trajectory_path))
        if not run_directory.exists():
            missing_paths.append(str(run_directory))
    if missing_paths:
        raise FileNotFoundError(f"Manifest references missing paths: {', '.join(missing_paths)}")

    figure_paths: list[Path] = []
    for basename in REQUIRED_FIGURE_BASENAMES:
        for suffix in (".png", ".pdf"):
            figure_path = results_dir / f"{basename}{suffix}"
            if not figure_path.exists():
                raise FileNotFoundError(f"Missing required figure at {figure_path}")
            figure_paths.append(figure_path)

    return figure_paths


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _copy_first_existing(candidates: list[Path], destination: Path) -> int:
    for candidate in candidates:
        if candidate.exists():
            shutil.copy2(candidate, destination)
            return 1
    return 0



def _write_report_template(path: Path, *, has_rho2: bool = False, has_rho8: bool = False) -> None:
    optional_sections = ""
    if has_rho2 or has_rho8:
        parts = [r"\subsection{Densidades extra (opcional)}"]
        if has_rho2:
            parts.append(r"""
\begin{figure}[h]
\centering
\includegraphics[width=0.75\textwidth]{assets/eta_vs_va_comparison_rho2.pdf}
\caption{Comparacion entre escenarios para $\rho = 2$.}
\end{figure}
Incluir como maximo dos capturas fijas de demos representativas para $\rho = 2$ (bajo y alto ruido).""")
        if has_rho8:
            parts.append(r"""
\begin{figure}[h]
\centering
\includegraphics[width=0.75\textwidth]{assets/eta_vs_va_comparison_rho8.pdf}
\caption{Comparacion entre escenarios para $\rho = 8$.}
\end{figure}
Incluir como maximo dos capturas fijas de demos representativas para $\rho = 8$ (bajo y alto ruido).""")
        optional_sections = "\n".join(parts)
    else:
        optional_sections = r"""\subsection{Opcional: densidades extra}
Si se incluyen los casos opcionales, agregar una subseccion para \texttt{rho=2} y otra para \texttt{rho=8}. Cada una debe mostrar una figura comparativa entre escenarios y, como maximo, dos capturas fijas de demos representativas."""

    template = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}

\title{Simulacion de Sistemas - TP2}
\author{Grupo 01 - Comisi\'{o}n S2}
\date{}

\begin{document}
\maketitle

\section{Introduccion}
Describir el sistema real y el modelo matematico general.

\section{Modelo}
Presentar la regla de actualizacion del modelo de Vicsek y la definicion del observable $va$.

\section{Implementacion}
Describir arquitectura del simulador, salida OVITO-ready y pipeline de analisis.

\section{Simulaciones}
Detallar parametros fijos, rango de $\eta$, cantidad de seeds, cantidad de pasos y criterio de estado estacionario.

\section{Resultados}
\subsection{Escenario A}
\begin{figure}[h]
\centering
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_A.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_A.pdf}
\caption{Series temporales y curva ruido vs polarizacion para el escenario A.}
\end{figure}

\subsection{Escenario B}
\begin{figure}[h]
\centering
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_B.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_B.pdf}
\caption{Series temporales y curva ruido vs polarizacion para el escenario B.}
\end{figure}

\subsection{Escenario C}
\begin{figure}[h]
\centering
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_C.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_C.pdf}
\caption{Series temporales y curva ruido vs polarizacion para el escenario C.}
\end{figure}

\subsection{Comparacion}
\begin{figure}[h]
\centering
\includegraphics[width=0.75\textwidth]{assets/eta_vs_va_comparison.pdf}
\caption{Comparacion final entre los tres escenarios obligatorios.}
\end{figure}

""" + optional_sections + r"""

\section{Conclusiones}
Concluir solo a partir de las figuras y resultados incluidos arriba.

\section*{Referencias}
Agregar aqui la referencia al articulo de Vicsek y cualquier otra fuente citada en el texto.

\end{document}
"""
    path.write_text(template + "\n", encoding="utf-8")

