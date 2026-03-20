# TP2 SDS 2026Q1G01S2

Simulación de dinámica de partículas autopropulsadas (modelo de Vicsek) con tres escenarios:

- **A**: sin líder
- **B**: líder con dirección fija
- **C**: líder con dirección variable

## Requisitos

- Python 3.12+

## Instalación

```bash
python3 -m pip install -e ".[dev]"
```

## Estructura de salidas

```
outputs/                          ← trayectorias de simulación
  scenario=A/eta=0.100000/seed=42/
    run.json                      ← configuración de la corrida
    trajectory.extxyz             ← trayectoria multi-frame

results/                          ← figuras y animaciones generadas
  viz_A.png, viz_B.png, viz_C.png
  anim_A.gif, anim_B.gif, anim_C.gif
  va_vs_eta_by_N_A.png, ...
```

## Uso: comandos individuales

Todos los comandos se ejecutan con `tp2-sds` (si se instaló el paquete) o con `PYTHONPATH=src python3 -m tp2_sds.cli`.

### Simular una corrida

```bash
tp2-sds simulate --scenario A --eta 0.1 --seed 42 --steps 2000 --N 300 --L 25
```

Parámetros principales:

| Parámetro     | Descripción                          | Default |
|---------------|--------------------------------------|---------|
| `--scenario`  | Escenario: A, B o C                  | —       |
| `--eta`       | Nivel de ruido                       | —       |
| `--seed`      | Semilla para reproducibilidad        | —       |
| `--steps`     | Cantidad de pasos de simulación      | —       |
| `--N`         | Cantidad de partículas               | —       |
| `--L`         | Tamaño de la caja                    | 10.0    |
| `--force`     | Sobreescribir corrida existente      | false   |

La trayectoria se guarda en `outputs/scenario=<X>/eta=<Y>/seed=<Z>/trajectory.extxyz`.

### Generar una animación GIF

A partir de una trayectoria ya simulada:

```bash
tp2-sds animate outputs/scenario=A/eta=0.100000/seed=42/trajectory.extxyz --output results/anim_A
```

Opciones: `--frame-step` (default 10), `--fps` (default 20), `--arrow-scale` (default 2.0), `--dpi` (default 150).

### Generar una figura estática (HSV)

```bash
tp2-sds visualize --trajectory outputs/scenario=A/eta=0.100000/seed=42/trajectory.extxyz --eta 0.1 --output results/viz_A
```

También puede simular y visualizar en un solo paso (sin trayectoria previa):

```bash
tp2-sds visualize --scenario B --eta 0.1 --N 300 --L 25 --steps 2000 --seed 42 --output results/viz_B
```

### Generar gráfico va vs eta (sweep)

Barrido de alineación para distintos N:

```bash
tp2-sds sweep --scenario A --N-values 40,100,400,4000 --etas 0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0 --steps 2000 --seeds 1,2,3,4,5 --output results/va_vs_eta_by_N_A
```

### Batch de simulaciones

```bash
tp2-sds batch --scenarios A,B,C --etas 0.1,0.5,2.0 --seeds 1,2,3 --steps 2000
```

## Generar todo de una vez

El script `generate_all.sh` ejecuta todas las simulaciones, visualizaciones, animaciones y sweeps:

```bash
chmod +x generate_all.sh
./generate_all.sh
```

Este script realiza los siguientes pasos:

1. **Simulaciones**: corre los escenarios A, B y C con eta bajo (0.1) y alto (2.0), N=300, L=25, 2000 pasos.
2. **Figuras estáticas**: genera `results/viz_A.png`, `viz_B.png`, `viz_C.png` a partir de las trayectorias con eta bajo.
3. **Animaciones GIF**: genera `results/anim_A.gif`, `anim_B.gif`, `anim_C.gif`.
4. **Sweeps va vs eta**: genera gráficos de alineación vs ruido para N = 40, 100, 400 y 4000 con 10 seeds, para cada escenario.

Los resultados quedan en la carpeta `results/`.

## Tests

```bash
pytest
```
