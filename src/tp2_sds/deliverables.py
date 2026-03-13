from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

from .reporting import DEMO_MANIFEST_NAME, RESULTS_DIRECTORY_NAME

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


def package_deliverables(runs_root: Path, out_dir: Path | None = None) -> PackageResult:
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

    aggregate_rows = _read_csv_rows(aggregate_path)
    manifest_rows = _read_csv_rows(manifest_path)

    _write_scenario_summary(out_dir / "scenario_summary.csv", aggregate_rows, manifest_rows)
    _write_ovito_demo_guide(out_dir / "ovito_demo_guide.md", manifest_rows)
    _write_delivery_checklist(out_dir / "delivery_checklist.md")
    _write_presentation_template(out_dir / "presentation_template.tex")
    _write_report_template(out_dir / "report_template.tex")

    return PackageResult(out_dir=out_dir, assets_dir=assets_dir, packaged_assets=packaged_assets)


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


def _write_scenario_summary(
    path: Path,
    aggregate_rows: list[dict[str, str]],
    manifest_rows: list[dict[str, str]],
) -> None:
    rows_by_scenario: dict[str, list[dict[str, str]]] = {scenario: [] for scenario in REQUIRED_SCENARIOS}
    for row in aggregate_rows:
        if row["scenario"] in rows_by_scenario:
            rows_by_scenario[row["scenario"]].append(row)

    demo_by_key = {(row["scenario"], row["role"]): row for row in manifest_rows}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "eta_min",
                "eta_max",
                "num_eta",
                "min_num_seeds",
                "max_num_seeds",
                "low_noise_eta",
                "low_noise_seed",
                "high_noise_eta",
                "high_noise_seed",
            ],
        )
        writer.writeheader()
        for scenario in REQUIRED_SCENARIOS:
            rows = rows_by_scenario[scenario]
            etas = [float(row["eta"]) for row in rows]
            num_seeds = [int(row["num_seeds"]) for row in rows]
            low_demo = demo_by_key[(scenario, "low_noise")]
            high_demo = demo_by_key[(scenario, "high_noise")]
            writer.writerow(
                {
                    "scenario": scenario,
                    "eta_min": f"{min(etas):.6f}",
                    "eta_max": f"{max(etas):.6f}",
                    "num_eta": len(rows),
                    "min_num_seeds": min(num_seeds),
                    "max_num_seeds": max(num_seeds),
                    "low_noise_eta": low_demo["eta"],
                    "low_noise_seed": low_demo["seed"],
                    "high_noise_eta": high_demo["eta"],
                    "high_noise_seed": high_demo["seed"],
                }
            )


def _write_ovito_demo_guide(path: Path, manifest_rows: list[dict[str, str]]) -> None:
    lines = [
        "# OVITO demo guide",
        "",
        "Use the trajectories listed below for the live demos.",
        "",
        "Recommended OVITO settings:",
        "- Open the trajectory file from the path in the table.",
        "- Keep particle colors from the `Color` property.",
        "- Enable vectors using the `Velocity` property.",
        "- Keep the leader visually distinct by using the stored particle type and radius.",
        "- Use the low-noise and high-noise runs to illustrate ordering and disorder.",
        "",
        "| Scenario | Role | Eta | Seed | Trajectory |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in sorted(manifest_rows, key=lambda item: (item["scenario"], item["role"])):
        lines.append(
            f"| {row['scenario']} | {row['role']} | {row['eta']} | {row['seed']} | `{row['trajectory_path']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_delivery_checklist(path: Path) -> None:
    lines = [
        "# Delivery checklist",
        "",
        "- Verify that the presentation PDF includes fixed screenshots plus an explicit video/demo link.",
        "- Verify that the report is self-contained and uses the same section order as the presentation.",
        "- Replace the placeholder group identifiers in final filenames: `SdS_TP2_2026Q1GXXCSS_Presentacion.pdf`, `SdS_TP2_2026Q1GXXCSS_Codigo.zip`, `SdS_TP2_2026Q1GXXCSS_Informe.pdf`.",
        "- Confirm that scenarios A, B, and C are all discussed and compared in the final material.",
        "- Confirm that `eta_vs_va_comparison` appears in both the presentation and the report.",
        "- If optional densities are included, add one comparative figure for `rho=2` and one for `rho=8`, plus at most two demos per extra density.",
        "- Use `ovito_demo_guide.md` and `assets/demo_manifest.csv` to prepare the live demo order.",
        "- Keep only the final source code in the code zip; do not include outputs or generated media.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_presentation_template(path: Path) -> None:
    template = r"""\documentclass{beamer}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\setbeamertemplate{footline}[frame number]
\title{Simulacion de Sistemas - TP2}
\author{Grupo XX - Comision SS}
\date{}

\AtBeginSection[]{
\begin{frame}
\centering
\Large\insertsection
\end{frame}
}

\begin{document}

\frame{\titlepage}

\section{Introduccion}
\begin{frame}{Sistema y modelo}
Resumen tecnico del modelo de Vicsek, parametros principales y objetivo del estudio.
\end{frame}

\section{Implementacion}
\begin{frame}{Arquitectura}
Describir el motor de simulacion, el formato de salida y el pipeline de analisis.
\end{frame}

\section{Simulaciones}
\begin{frame}{Configuracion}
Detallar rango de ruido, cantidad de seeds, steps y criterio de estado estacionario.
\end{frame}

\section{Resultados}
\begin{frame}{Escenario A}
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_A.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_A.pdf}

\vspace{0.5em}
\small Demo link: \texttt{REEMPLAZAR\_POR\_LINK}
\end{frame}

\begin{frame}{Escenario B}
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_B.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_B.pdf}

\vspace{0.5em}
\small Demo link: \texttt{REEMPLAZAR\_POR\_LINK}
\end{frame}

\begin{frame}{Escenario C}
\includegraphics[width=0.48\textwidth]{assets/va_timeseries_C.pdf}
\includegraphics[width=0.48\textwidth]{assets/eta_vs_va_C.pdf}

\vspace{0.5em}
\small Demo link: \texttt{REEMPLAZAR\_POR\_LINK}
\end{frame}

\begin{frame}{Comparacion final}
\includegraphics[width=0.8\textwidth]{assets/eta_vs_va_comparison.pdf}
\end{frame}

\begin{frame}{Opcionales: otras densidades}
\begin{itemize}
\item Si se incluyen los opcionales, insertar una figura comparativa para \texttt{rho=2}.
\item Insertar hasta dos fotogramas o links de demo para \texttt{rho=2}.
\item Repetir lo mismo para \texttt{rho=8}.
\end{itemize}
\end{frame}

\section{Conclusiones}
\begin{frame}{Conclusiones}
\begin{itemize}
\item Concluir solo a partir de los resultados mostrados.
\item Resumir diferencias entre A, B y C.
\item Indicar el criterio usado para el estado estacionario.
\end{itemize}
\end{frame}

\end{document}
"""
    path.write_text(template + "\n", encoding="utf-8")


def _write_report_template(path: Path) -> None:
    template = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{booktabs}

\title{Simulacion de Sistemas - TP2}
\author{Grupo XX - Comision SS}
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

\subsection{Opcional: densidades extra}
Si se incluyen los casos opcionales, agregar una subseccion para \texttt{rho=2} y otra para \texttt{rho=8}. Cada una debe mostrar una figura comparativa entre escenarios y, como maximo, dos capturas fijas de demos representativas.

\section{Conclusiones}
Concluir solo a partir de las figuras y resultados incluidos arriba.

\section*{Referencias}
Agregar aqui la referencia al articulo de Vicsek y cualquier otra fuente citada en el texto.

\end{document}
"""
    path.write_text(template + "\n", encoding="utf-8")
