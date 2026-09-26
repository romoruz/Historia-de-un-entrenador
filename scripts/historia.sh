#!/usr/bin/env bash
# Capa de fútbol completa (fases A–F) para un técnico. Reglas de lectura pre-registradas en
# docs/11_HIPOTESIS.md ("Capa de fútbol"). Lo que es de toda la liga se calcula una vez y se reutiliza.
#
# Uso (raíz del repo, venv activo):
#   bash scripts/historia.sh "Andre Jardine"
#   bash scripts/historia.sh "Guillermo Almada"
#   REHACER=1 bash scripts/historia.sh "Andre Jardine"     # recalcula la tabla de la liga
# Requisitos: vocabulario oficial (mezcla_K3), fase 2/3 del foco (scripts/correr_foco.sh, para el BH global)
# y, para el 360, los frames en data/raw/statsbomb/frames.
set -euo pipefail
cd "$(dirname "$0")/.."
FOCO="${1:?uso: bash scripts/historia.sh \"Nombre exacto del DT\"}"
SLUG=$(python -c "import sys; print(sys.argv[1].lower().replace(' ', '_'))" "$FOCO")
mkdir -p "reports/historia/$SLUG"
LOG="reports/historia/$SLUG/corrida_$(date +%Y%m%d_%H%M).log"
{
  echo "== $(date '+%F %T') · capa de fútbol · «$FOCO»"
  echo "== 0. pruebas"; pytest -q
  if [ ! -f data/interim/rasgos_360.parquet ]; then echo "== 360: rasgos (Voronoi)"; dtcoach voronoi; fi
  if [ ! -f data/interim/bloque_360.parquet ]; then echo "== 360: bloque y marcaje"; dtcoach geometria; fi
  echo "== B. estilo de juego";      dtcoach futbol --foco "$FOCO" ${REHACER:+--rehacer}
  echo "== E. balón parado";         dtcoach balon-parado --foco "$FOCO"
  echo "== D. jugadores";            dtcoach jugadores --foco "$FOCO"
  echo "== C. identidad y tiempo";   dtcoach identidad --foco "$FOCO"
  echo "== F. simulador";            dtcoach simular --foco "$FOCO"
  echo "== A. blindaje";             dtcoach blindaje --foco "$FOCO"
  echo "== $(date '+%F %T') · listo. Salidas: reports/historia/$SLUG/"
} 2>&1 | tee "$LOG"
