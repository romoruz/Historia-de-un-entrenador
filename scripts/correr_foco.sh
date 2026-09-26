#!/usr/bin/env bash
# Réplica COMPLETA del análisis sobre otro técnico: fases 2, 3a, atlas, 3b y simulador.
# La fase 1 (vocabulario de la liga), las eras y el Elo NO se rehacen: son de toda la liga.
#
# Uso (desde la raíz del repo, con el venv activo):
#   bash scripts/correr_foco.sh "Guillermo Almada"          # clubes con ≥ 8 partidos
#   bash scripts/correr_foco.sh "Guillermo Almada" 15       # otro mínimo por club
set -euo pipefail
FOCO="${1:?uso: bash scripts/correr_foco.sh \"Nombre exacto del DT\" [min_partidos_por_club]}"
MIN="${2:-8}"
SLUG=$(python -c "import sys; print(sys.argv[1].lower().replace(' ', '_'))" "$FOCO")
LOG="reports/corrida_${SLUG}.log"
mkdir -p reports

# el nombre debe existir tal cual en las eras (error temprano y claro, no a los 10 minutos)
if ! grep -q "$FOCO" reports/cobertura_eras.csv; then
  echo "«$FOCO» no aparece en reports/cobertura_eras.csv. Nombres disponibles:"
  cut -d, -f2 reports/cobertura_eras.csv | sort -u | head -60
  exit 1
fi

{
  echo "== $(date '+%F %T') · réplica sobre «$FOCO» (clubes con ≥ $MIN partidos)"
  echo "== 0. pruebas";                 pytest -q
  echo "== 1. fase 2: H1–H8";           dtcoach fase2 --foco "$FOCO"
  echo "== 2. fase 3a: por club";       dtcoach fase3 --foco "$FOCO" --min-partidos "$MIN"
  echo "== 3. atlas (reutilizado)";     dtcoach atlas --foco "$FOCO"
  echo "== 4. fase 3b: decisiones";     dtcoach decisiones --foco "$FOCO"
  echo "== 5. simulador";               dtcoach simulador --foco "$FOCO"
  echo "== $(date '+%F %T') · listo. Salidas: reports/fase2/*${SLUG}* y reports/fase3/*${SLUG}*"
} 2>&1 | tee "$LOG"
