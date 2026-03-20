#!/usr/bin/env bash
# =============================================================================
# generate_all.sh — Genera todas las simulaciones, visualizaciones y gráficos
#
# Uso:
#   chmod +x generate_all.sh
#   ./generate_all.sh
#
# Outputs:
#   results/viz_A.png, viz_B.png, viz_C.png                → figuras estáticas HSV
#   results/anim_A.gif, anim_B.gif, anim_C.gif             → animaciones GIF
#   results/va_vs_eta_by_N_A.png                           → va vs η distintos N
#   results/va_vs_eta_by_N_B.png
#   results/va_vs_eta_by_N_C.png
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

CLI="python3 -c 'from tp2_sds.cli import main; import sys; main(sys.argv[1:])'"
run_cli() { python3 -c "from tp2_sds.cli import main; import sys; main(sys.argv[1:])" "$@"; }

RESULTS=results
mkdir -p "$RESULTS"

# ─── Parámetros ──────────────────────────────────────────────────────────────
N=300
L=25
STEPS=2000
SEED=42
ETA_LOW=0.1       # ruido bajo  → estado ordenado (va ≈ 1)
ETA_HIGH=2.0      # ruido alto  → estado desordenado (va ≈ 0)

echo "=============================================="
echo " PASO 1: Simulaciones"
echo "=============================================="

for SCENARIO in A B C; do
    for ETA in $ETA_LOW $ETA_HIGH; do
        echo "→ Escenario $SCENARIO, η=$ETA ..."
        run_cli simulate \
            --scenario "$SCENARIO" --eta "$ETA" --seed "$SEED" \
            --steps "$STEPS" --N "$N" --L "$L" --force
    done
done

echo ""
echo "=============================================="
echo " PASO 2: Figuras estáticas HSV (visualize)"
echo "=============================================="

for SCENARIO in A B C; do
    TRAJ="outputs/scenario=${SCENARIO}/eta=0.100000/seed=${SEED}/trajectory.extxyz"
    echo "→ Visualización escenario $SCENARIO (η=$ETA_LOW) ..."
    run_cli visualize \
        --trajectory "$TRAJ" \
        --eta "$ETA_LOW" \
        --output "$RESULTS/viz_${SCENARIO}"
done

echo ""
echo "=============================================="
echo " PASO 2b: Animaciones GIF"
echo "=============================================="

for SCENARIO in A B C; do
    TRAJ="outputs/scenario=${SCENARIO}/eta=0.100000/seed=${SEED}/trajectory.extxyz"
    echo "→ Animación escenario $SCENARIO (η=$ETA_LOW) ..."
    run_cli animate "$TRAJ" \
        --output "$RESULTS/anim_${SCENARIO}"
done

echo ""
echo "=============================================="
echo " PASO 3: Gráficos va vs η para distintos N"
echo "=============================================="

SWEEP_N="40,100,400,4000"
SWEEP_ETAS="0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0"
SWEEP_SEEDS="1,2,3,4,5,6,7,8,9,10"

for SCENARIO in A B C; do
    echo "→ Sweep escenario $SCENARIO (N=$SWEEP_N, seeds=$SWEEP_SEEDS) ..."
    run_cli sweep \
        --scenario "$SCENARIO" \
        --N-values "$SWEEP_N" \
        --etas "$SWEEP_ETAS" \
        --steps "$STEPS" \
        --seeds "$SWEEP_SEEDS" \
        --output "$RESULTS/va_vs_eta_by_N_${SCENARIO}"
done

echo ""
echo "=============================================="
echo " LISTO"
echo "=============================================="
echo ""
echo "Archivos generados:"
echo ""
echo "  Figuras (PNG + PDF):"
ls "$RESULTS"/*.png 2>/dev/null | sed 's/^/    /'
echo ""
echo "  Animaciones (GIF):"
ls "$RESULTS"/*.gif 2>/dev/null | sed 's/^/    /'
echo ""
