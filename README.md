# TP2 SDS 2026Q1G01S2

Simulación de dinámica de partículas autopropulsadas (modelo de Vicsek) con tres escenarios:

- **A**: sin líder
- **B**: líder con dirección fija
- **C**: líder con trayectoria circular (R=5)

## Requisitos

- Python 3.12+

## Instalación

```bash
python3 -m pip install -e ".[dev]"
```

## Parámetros del enunciado

| Parámetro | Valor   | Descripción                         |
|-----------|---------|-------------------------------------|
| L         | 10      | Tamaño de la caja                   |
| ρ         | 4       | Densidad (→ N=400)                  |
| v         | 0.03    | Velocidad de las partículas         |
| r         | 1       | Radio de interacción                |
| dt        | 1       | Paso temporal                       |
| η         | 0.0–5.0 | Ruido (barrido en pasos de 0.5)     |
| seeds     | 1–5     | Realizaciones para promedio y error  |
| steps     | 2000    | Pasos de simulación                 |

## Generar los entregables

El script `generate_all.sh` ejecuta el pipeline completo: campañas de simulación para ρ=4 (obligatorio) y ρ=2, ρ=8 (opcionales), análisis, generación de figuras, y armado del bundle de entregables.

```bash
chmod +x generate_all.sh
./generate_all.sh
```

**Pasos del pipeline**:

1. **Campaña ρ=4** (obligatoria): simula A/B/C × 11 etas × 5 seeds = 165 corridas, analiza y genera figuras.
2. **Campaña ρ=2** (opcional): ídem con N=200.
3. **Campaña ρ=8** (opcional): ídem con N=800.
4. **Packaging**: valida resultados, copia assets, genera el template del informe y arma el ZIP de código.
5. **Aliases legacy**: copia visualizaciones y animaciones low-noise a `results/`.

**Variables de entorno para override**:

```bash
# Corrida rápida para test:
STEPS=50 SEEDS=1,2 ETAS=0.0,2.5,5.0 ./generate_all.sh

# Saltar densidades opcionales:
SKIP_OPTIONAL=1 ./generate_all.sh

# Forzar recálculo (no skip-existing):
FORCE_REBUILD=1 ./generate_all.sh
```

| Variable           | Default                           | Descripción                        |
|--------------------|-----------------------------------|------------------------------------|
| `STEPS`            | 2000                              | Pasos de simulación                |
| `SEEDS`            | 1,2,3,4,5                         | Seeds para promedios               |
| `ETAS`             | 0.0,0.5,...,5.0                   | Valores de η                       |
| `RUNS_BASE`        | outputs                           | Directorio base de corridas        |
| `DELIVERABLES_DIR` | deliverables                      | Directorio de salida del bundle    |
| `FORCE_REBUILD`    | 0                                 | Forzar recálculo                   |
| `SKIP_OPTIONAL`    | 0                                 | Saltar ρ=2 y ρ=8                   |

## Estructura de salidas

```
outputs/
  rho=4/                              ← campaña obligatoria
    scenario=A/eta=0.000000/seed=1/
      run.json
      trajectory.extxyz
    ...
    aggregate.csv                      ← promedios por (escenario, η)
    results/
      eta_vs_va_A.{png,pdf}           ← va vs η por escenario
      eta_vs_va_B.{png,pdf}
      eta_vs_va_C.{png,pdf}
      eta_vs_va_comparison.{png,pdf}   ← comparación de los 3 escenarios
      va_timeseries_A.{png,pdf}        ← evolución temporal de va
      va_timeseries_B.{png,pdf}
      va_timeseries_C.{png,pdf}
      visualization_*.{png,pdf}        ← figuras estáticas HSV
      animation_*.gif                  ← animaciones con flechas coloreadas
      demo_manifest.csv
  rho=2/                              ← campaña opcional
  rho=8/                              ← campaña opcional

deliverables/                          ← bundle de entrega
  assets/
    aggregate.csv
    demo_manifest.csv
    va_timeseries_{A,B,C}.{png,pdf}
    eta_vs_va_{A,B,C}.{png,pdf}
    eta_vs_va_comparison.{png,pdf}
    eta_vs_va_comparison_rho2.{png,pdf}  (si --extra-runs-roots)
    eta_vs_va_comparison_rho8.{png,pdf}  (si --extra-runs-roots)
  scenario_summary.csv
  ovito_demo_guide.md
  delivery_checklist.md
  SdS_TP2_2026Q1G01S2_Informe.tex
  SdS_TP2_2026Q1G01S2_Codigo.zip
```

La presentación se prepara manualmente y no forma parte de los archivos `.tex` generados por el pipeline.

## Comandos CLI

Todos los comandos se ejecutan con `tp2-sds`.

### campaign

Ejecuta batch de simulaciones + análisis + generación de figuras:

```bash
tp2-sds campaign --runs-root outputs/rho=4 --L 10 --rho 4 --steps 2000 \
  --seeds 1,2,3,4,5 --etas 0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0 \
  --skip-existing
```

### package

Valida resultados y arma bundle de entregables:

```bash
tp2-sds package --runs-root outputs/rho=4 --out-dir deliverables \
  --extra-runs-roots outputs/rho=2,outputs/rho=8
```

### simulate

Genera una corrida individual:

```bash
tp2-sds simulate --scenario A --eta 0.1 --seed 42 --steps 2000 --L 10 --rho 4
```

### batch

Producto cartesiano de corridas:

```bash
tp2-sds batch --scenarios A,B,C --etas 0.1,0.5,2.0 --seeds 1,2,3 --steps 2000 --skip-existing
```

### analyze

Analiza corridas existentes y genera `aggregate.csv`:

```bash
tp2-sds analyze --runs-root outputs/rho=4
```

### animate

Genera animación GIF desde una trayectoria:

```bash
tp2-sds animate outputs/rho=4/scenario=A/eta=0.100000/seed=1/trajectory.extxyz --output results/anim_A
```

### visualize

Genera figura estática HSV:

```bash
tp2-sds visualize --scenario B --eta 0.1 --N 400 --L 10 --steps 2000 --seed 42 --output results/viz_B
```

### sweep

Barrido va vs η para distintos N:

```bash
tp2-sds sweep --scenario A --N-values 40,100,400 --steps 2000 --seeds 1,2,3,4,5 --output results/va_vs_eta_by_N_A
```

### timeseries

Evolución temporal de va para múltiples η:

```bash
tp2-sds timeseries --scenario A --N 400 --etas 0.0,0.2,0.6,1.2,2.4,3.0,5.2 --steps 1000 --output results/va_timeseries
```

## Tests

```bash
pytest
```
