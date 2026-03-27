#!/usr/bin/env bash
# =============================================================================
# generate_all.sh — Pipeline completo de entrega del TP2
#
# Genera campañas para ρ=4 (obligatorio) y ρ=2, ρ=8 (opcionales),
# luego actualiza el bundle de entregables en deliverables/.
#
# Parámetros alineados al enunciado: L=10, ρ=4, v=0.03, r=1, dt=1.
#
# Variables de entorno para override:
#   STEPS=2000          Pasos de simulación
#   SEEDS=1,2,3,4,5     Seeds para promedios
#   ETAS=0.0,0.5,...     Valores de η
#   RUNS_BASE=outputs    Directorio base de corridas
#   DELIVERABLES_DIR=deliverables  Directorio de salida del bundle
#   FORCE_REBUILD=1      Forzar recálculo (no skip-existing)
#   SKIP_OPTIONAL=1      Saltar densidades opcionales ρ=2 y ρ=8
#
# Si ya existe un informe manual en DELIVERABLES_DIR, el packaging preserva ese
# .tex y sólo actualiza los assets/copias auxiliares.
#
# Uso:
#   chmod +x generate_all.sh
#   ./generate_all.sh
#
#   # Corrida rápida para test:
#   STEPS=50 SEEDS=1,2 ETAS=0.0,2.5,5.0 ./generate_all.sh
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

run_cli() { tp2-sds "$@"; }

# ─── Parámetros ──────────────────────────────────────────────────────────────
L=10
STEPS="${STEPS:-2000}"
SEEDS="${SEEDS:-1,2,3,4,5}"
ETAS="${ETAS:-0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0}"
RUNS_BASE="${RUNS_BASE:-outputs}"
DELIVERABLES_DIR="${DELIVERABLES_DIR:-deliverables}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
SKIP_OPTIONAL="${SKIP_OPTIONAL:-0}"

SKIP_FLAG=""
if [ "$FORCE_REBUILD" != "1" ]; then
    SKIP_FLAG="--skip-existing"
fi


# =============================================================================
echo "=============================================="
echo " PASO 1: Campaña obligatoria ρ=4"
echo "=============================================="
RHO4_ROOT="${RUNS_BASE}/rho=4"
run_cli campaign \
    --runs-root "$RHO4_ROOT" \
    --steps "$STEPS" \
    --seeds "$SEEDS" \
    --etas "$ETAS" \
    --L "$L" --rho 4 \
    $SKIP_FLAG

# =============================================================================
if [ "$SKIP_OPTIONAL" != "1" ]; then
    echo ""
    echo "=============================================="
    echo " PASO 2: Campaña opcional ρ=2"
    echo "=============================================="
    RHO2_ROOT="${RUNS_BASE}/rho=2"
    run_cli campaign \
        --runs-root "$RHO2_ROOT" \
        --steps "$STEPS" \
        --seeds "$SEEDS" \
        --etas "$ETAS" \
        --L "$L" --rho 2 \
        $SKIP_FLAG

    echo ""
    echo "=============================================="
    echo " PASO 3: Campaña opcional ρ=8"
    echo "=============================================="
    RHO8_ROOT="${RUNS_BASE}/rho=8"
    run_cli campaign \
        --runs-root "$RHO8_ROOT" \
        --steps "$STEPS" \
        --seeds "$SEEDS" \
        --etas "$ETAS" \
        --L "$L" --rho 8 \
        $SKIP_FLAG
fi

# =============================================================================
echo ""
echo "=============================================="
echo " PASO 4: Packaging de entregables"
echo "=============================================="

EXTRA_ROOTS_FLAG=""
if [ "$SKIP_OPTIONAL" != "1" ]; then
    EXTRA_ROOTS_FLAG="--extra-runs-roots ${RUNS_BASE}/rho=2,${RUNS_BASE}/rho=8"
fi

run_cli package \
    --runs-root "$RHO4_ROOT" \
    --out-dir "$DELIVERABLES_DIR" \
    $EXTRA_ROOTS_FLAG

# =============================================================================
echo ""
echo "=============================================="
echo " LISTO"
echo "=============================================="
echo ""
echo "  Entregables en: ${DELIVERABLES_DIR}/"
ls "$DELIVERABLES_DIR"/ 2>/dev/null | sed 's/^/    /'
echo ""
echo "  Assets:"
ls "$DELIVERABLES_DIR"/assets/ 2>/dev/null | sed 's/^/    /'
echo ""
