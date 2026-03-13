# Runbook de ejecucion final TP2

Este runbook fija el flujo recomendado para cerrar el TP con la implementacion actual.

## 1. Verificacion de codigo

Ejecutar la suite antes de lanzar campañas largas:

```bash
pytest -q
```

## 2. Campaña obligatoria `rho=4`

Root dedicado:

```bash
RUNS_ROOT="outputs/rho=4.000000"
```

Barrido grueso:

```bash
tp2-sds campaign \
  --runs-root "$RUNS_ROOT" \
  --scenarios A,B,C \
  --etas 0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0 \
  --seeds 1,2,3,4,5 \
  --steps 2000 \
  --rho 4
```

Empaquetado inicial:

```bash
tp2-sds package --runs-root "$RUNS_ROOT"
```

## 3. Validacion del estacionario

Revisar en `results/va_timeseries_A.pdf`, `results/va_timeseries_B.pdf` y `results/va_timeseries_C.pdf` que la linea vertical `t_start` quede antes del tramo visualmente estacionario en las curvas `low_noise` y `high_noise`.

Si el corte del 30 por ciento no es satisfactorio, elegir un unico valor global de `--transient-fraction` para toda la densidad `rho=4` y regenerar figuras y bundle:

```bash
tp2-sds plot --runs-root "$RUNS_ROOT" --transient-fraction 0.4
tp2-sds package --runs-root "$RUNS_ROOT"
```

## 4. Refinamiento de `eta` para `rho=4`

Tomar `results/eta_vs_va_comparison.pdf` y definir una banda fina comun para `A`, `B` y `C` usando esta regla:

- `eta_fine_min`: primer `eta` grueso donde cualquier escenario cae a `va_mean <= 0.7`
- `eta_fine_max`: ultimo `eta` grueso donde cualquier escenario todavia tiene `va_mean >= 0.3`
- expandir un paso grueso a cada lado y recortar a `[0, 5]`

Ejemplo de campaña refinada:

```bash
tp2-sds campaign \
  --runs-root "$RUNS_ROOT" \
  --scenarios A,B,C \
  --etas 1.4,1.5,1.6,1.7,1.8,1.9,2.0,2.1,2.2,2.3,2.4 \
  --seeds 1,2,3,4,5 \
  --steps 2000 \
  --rho 4 \
  --skip-existing
```

Luego regenerar:

```bash
tp2-sds plot --runs-root "$RUNS_ROOT"
tp2-sds package --runs-root "$RUNS_ROOT"
```

## 5. Campañas opcionales `rho=2` y `rho=8`

Usar un root distinto por densidad y un barrido mas liviano:

```bash
tp2-sds campaign \
  --runs-root outputs/rho=2.000000 \
  --scenarios A,B,C \
  --etas 0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0 \
  --seeds 1,2,3 \
  --steps 2000 \
  --rho 2

tp2-sds package --runs-root outputs/rho=2.000000

tp2-sds campaign \
  --runs-root outputs/rho=8.000000 \
  --scenarios A,B,C \
  --etas 0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0 \
  --seeds 1,2,3 \
  --steps 2000 \
  --rho 8

tp2-sds package --runs-root outputs/rho=8.000000
```

## 6. Validacion visual en OVITO

Para `rho=4`, abrir las seis corridas listadas en `deliverables/assets/demo_manifest.csv` y verificar:

- importacion sin remapeos manuales
- flechas usando `Velocity`
- coloracion consistente con la direccion
- lider distinguible por tipo, color y radio

Para `rho=2` y `rho=8`, elegir solo dos demos por densidad para la presentacion:

- demo ordenada: corrida con mayor `va_mean_stationary`
- demo desordenada: corrida con menor `va_mean_stationary`

Las capturas fijas de la presentacion deben tomarse en un tiempo `t >= t_start`.

## 7. Entregables

Por cada root, `tp2-sds package` deja:

- `deliverables/assets/`
- `deliverables/scenario_summary.csv`
- `deliverables/ovito_demo_guide.md`
- `deliverables/delivery_checklist.md`
- `deliverables/presentation_template.tex`
- `deliverables/report_template.tex`

Entrega final:

- `SdS_TP2_2026Q1GXXCSS_Presentacion.pdf`
- `SdS_TP2_2026Q1GXXCSS_Codigo.zip`
- `SdS_TP2_2026Q1GXXCSS_Informe.pdf`

El zip de codigo debe contener solo la version final del codigo fuente, sin `outputs`, sin `docs`, sin `tests` y sin media generada.
