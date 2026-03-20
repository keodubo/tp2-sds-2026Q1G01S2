# TP2 SDS 2026Q1G01S2

Base Python para el TP2 con:

- paquete instalable en `src/tp2_sds`
- CLI `tp2-sds` con `simulate`, `batch`, `analyze`, `campaign`, `plot` y `package`
- trayectorias multi-frame `extended XYZ` listas para OVITO
- analisis reproducible sobre el mismo archivo de trayectoria
- figuras reproducibles PNG/PDF y manifest para demos en OVITO

## Requisitos

- Python 3.12+

## Instalación

```bash
python3 -m pip install -e ".[dev]"
```

## Uso rápido

Generar una corrida:

```bash
tp2-sds simulate --scenario A --eta 0.150000 --seed 7 --steps 100
```

Generar una animación GIF a partir de una trayectoria:

```bash
tp2-sds animate outputs/scenario=A/eta=0.150000/seed=7/trajectory.extxyz --output ./animacion_A
```

O si prefieres no usar el comando instalado, puedes ejecutar el módulo de Python directamente (ej. para otra prueba manual):

```bash
PYTHONPATH=src python3 -m tp2_sds.cli simulate --scenario B --eta 0.1 --seed 42 --steps 500 --N 100 --L 10.0 --output-root /tmp/tp2_sim_output
PYTHONPATH=src python3 -m tp2_sds.cli animate /tmp/tp2_sim_output/scenario=B/eta=0.100000/seed=42/trajectory.extxyz --output ./mi_animacion_B
```

Abrir una trayectoria directamente en OVITO (macOS):

```bash
open -a Ovito outputs/scenario=A/eta=0.150000/seed=7/trajectory.extxyz
```

Generar un batch:

```bash
tp2-sds batch --scenarios A,B,C --etas 0.1,0.5 --seeds 1,2,3 --steps 120
```

Generar un barrido (sweep) rápido para el gráfico de alineación ($V_a$) vs ruido ($\eta$):

```bash
tp2-sds sweep --scenario A --N-values 40,100,400 --output ./grafico_va_vs_eta
```

Analizar corridas existentes:

```bash
tp2-sds analyze --runs-root outputs
```

Ejecutar una campana completa y generar figuras:

```bash
tp2-sds campaign --runs-root outputs
```

Regenerar figuras y manifest sin re-simular:

```bash
tp2-sds plot --runs-root outputs
```

Preparar el bundle de entregables y templates:

```bash
tp2-sds package --runs-root outputs
```

## Runbook de ejecución final

Para el cierre del TP conviene separar campañas por densidad usando roots distintos:

- `outputs/rho=4.000000` para el caso obligatorio
- `outputs/rho=2.000000` para el opcional de baja densidad
- `outputs/rho=8.000000` para el opcional de alta densidad

El runbook completo con comandos y criterio de refinamiento está en [docs/Runbook_Ejecucion_Final_TP2.md](docs/Runbook_Ejecucion_Final_TP2.md).

## Convención de salidas

Cada corrida se escribe en:

```text
outputs/scenario=<A|B|C>/eta=<%.6f>/seed=<int>/
```

Si se estudian varias densidades, cada una debe usar un `runs-root` distinto para evitar sobreescribir corridas con el mismo `scenario`, `eta` y `seed`.

Artefactos por corrida:

- `run.json`: configuración serializada
- `trajectory.extxyz`: trayectoria OVITO-ready
- `summary.json`: resumen de análisis

Artefacto agregado:

- `aggregate.csv`: promedio y desvío estándar por `scenario` y `eta`

Artefactos de resultados:

- `results/demo_manifest.csv`: corridas representativas para abrir en OVITO
- `results/va_timeseries_<scenario>.png/.pdf`
- `results/eta_vs_va_<scenario>.png/.pdf`
- `results/eta_vs_va_comparison.png/.pdf`

Artefactos de cierre:

- `deliverables/assets/`: copia de figuras, `aggregate.csv` y `demo_manifest.csv`
- `deliverables/scenario_summary.csv`
- `deliverables/ovito_demo_guide.md`
- `deliverables/delivery_checklist.md`
- `deliverables/presentation_template.tex`
- `deliverables/report_template.tex`
