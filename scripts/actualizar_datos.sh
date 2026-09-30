#!/usr/bin/env bash
# Suma los partidos NUEVOS de la temporada (descargados de StatsBomb) a todo el análisis.
#
# Uso (raíz del repo):
#   read -rs SB_USERNAME; export SB_USERNAME        # no se ve lo que tecleas
#   read -rs SB_PASSWORD; export SB_PASSWORD
#   bash scripts/actualizar_datos.sh "Guillermo Almada"
#   SOLO_EQUIPO="América" bash scripts/actualizar_datos.sh "Guillermo Almada"   # solo ese club (menos completo)
#
# Qué hace, en orden:
#   1. baja la lista de partidos, los eventos y las alineaciones nuevas (actualizar_temporada.py) y su 360
#   2. alarga las eras vigentes si el técnico del API es el mismo (extender_eras.py); un cambio de técnico
#      se detiene y se agrega a mano
#   3. rehace lo de toda la liga: aplanar, partidos, secuencias, Elo. El VOCABULARIO (las tres familias) NO se
#      reajusta: la mezcla guardada se aplica a las secuencias nuevas, así las familias significan lo mismo
#   4. rehace las fases del foco, la historia completa (con extra, 360 y tabla de la liga) y la demostración
#   5. publica las figuras
set -euo pipefail
cd "$(dirname "$0")/.."
FOCO="${1:?uso: bash scripts/actualizar_datos.sh \"Nombre exacto del DT\"}"
if ! python -c "import dtcoach" 2>/dev/null; then source .venv/bin/activate; fi
LOG="reports/actualizacion_$(date +%Y%m%d_%H%M).log"
mkdir -p reports
{
  echo "== $(date '+%F %T') · actualización con los partidos nuevos"
  if [ -n "${SB_USERNAME:-}" ] && [ -n "${SB_PASSWORD:-}" ]; then
    echo "== 1. descarga: partidos, eventos y alineaciones"
    .venv-sb/bin/python scripts/descargar/actualizar_temporada.py ${SOLO_EQUIPO:+--equipo "$SOLO_EQUIPO"}
    echo "== 1b. descarga: 360 de los partidos nuevos"
    .venv-sb/bin/python scripts/descargar/descargar_360.py || echo "[aviso] hubo 360 fallidos: vuelve a correr la descarga"
  else
    echo "[aviso] sin SB_USERNAME/SB_PASSWORD: no se descarga nada; se reprocesa lo que haya en data/raw"
  fi
  echo "== 2. eras: técnicos de los partidos nuevos"
  python scripts/descargar/extender_eras.py --aplicar
  git --no-pager diff --stat -- data/referencia || true
  echo "== 3. la liga: aplanar, partidos, secuencias, Elo (el vocabulario NO se reajusta)"
  dtcoach aplanar
  dtcoach partidos
  dtcoach fase0
  dtcoach elo
  echo "== 4. el foco: fases 2 y 3, y la historia completa"
  bash scripts/correr_foco.sh "$FOCO" 7
  ACTUALIZAR=1 bash scripts/historia.sh "$FOCO"
  echo "== 5. figuras"
  bash scripts/publicar_figuras.sh "$FOCO"
  echo "== $(date '+%F %T') · listo. Revisa reports/historia/<foco>/demostracion/DEMOSTRACION.md"
} 2>&1 | tee "$LOG"
