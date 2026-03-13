# TP2 SDS 2026Q1G01S2

Base Python para el TP2 con:

- paquete instalable en `src/tp2_sds`
- CLI `tp2-sds` con `simulate`, `batch`, `analyze`, `campaign` y `plot`
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

Generar un batch:

```bash
tp2-sds batch --scenarios A,B,C --etas 0.1,0.5 --seeds 1,2,3 --steps 120
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

## Convención de salidas

Cada corrida se escribe en:

```text
outputs/scenario=<A|B|C>/eta=<%.6f>/seed=<int>/
```

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
