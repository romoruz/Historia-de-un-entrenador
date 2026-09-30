#!/usr/bin/env bash
# La historia completa de un técnico, sección por sección (reto 5.1–5.6 y 06). Reglas de lectura
# pre-registradas en docs/11_HIPOTESIS.md. Lo que es de toda la liga se calcula una vez y se reutiliza.
#
# Uso (raíz del repo, venv activo):
#   bash scripts/historia.sh "Guillermo Almada"
#   REHACER=1 bash scripts/historia.sh "Guillermo Almada"   # recalcula la tabla de toda la liga
# Requisitos: vocabulario (mezcla_K3), Elo y la fase 2/3 del foco (scripts/correr_foco.sh), y para el
# 360 los frames en data/raw/statsbomb/frames. Lo que falte de lo que se calcula una vez, se calcula aquí.
set -euo pipefail
cd "$(dirname "$0")/.."
# el entorno virtual: se activa solo si no lo está
if ! python -c "import dtcoach" 2>/dev/null; then
  if [ -f .venv/bin/activate ]; then source .venv/bin/activate
  else echo "falta el entorno: python3.12 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'" >&2; exit 1; fi
fi
FOCO="${1:?uso: bash scripts/historia.sh \"Nombre exacto del DT\"}"
SLUG=$(python -c "import sys; print(sys.argv[1].lower().replace(' ', '_'))" "$FOCO")
mkdir -p "reports/historia/$SLUG"
LOG="reports/historia/$SLUG/corrida_$(date +%Y%m%d_%H%M).log"
# ¿hace falta rehacer la geometría 360? (versiones anteriores no guardaban el ancho visible ni el frame del saque)
GEOM=$(python - <<'PY'
from dtcoach.config import Config
import polars as pl
c = Config.load(); f = c["futbol"]
from dtcoach.cli_historia import _ruta
b, s = _ruta(c, f["bloque"]), _ruta(c, f["saques"])
ok = b.exists() and s.exists() and "ancho_visible" in pl.read_parquet_schema(b)
print("ok" if ok else "rehacer")
PY
)
{
  echo "== $(date '+%F %T') · la historia de «$FOCO»"
  echo "== 0. pruebas"; pytest -q
  if [ ! -f data/interim/eventos_extra.parquet ]; then echo "== campos extra del JSON (una vez)"; dtcoach extra; fi
  if [ ! -f data/interim/rasgos_360.parquet ]; then echo "== 360: rasgos por evento (una vez)"; dtcoach voronoi; fi
  if [ "$GEOM" = "rehacer" ]; then echo "== 360: bloque y frame del saque (una vez)"; dtcoach geometria; fi
  echo "== tabla de la liga";            dtcoach tabla-liga ${REHACER:+--rehacer}
  echo "== 1. identidad y contexto";     dtcoach identidad --foco "$FOCO"
  echo "== 2. fase ofensiva";            dtcoach ofensiva --foco "$FOCO"
  echo "== 3. fase defensiva";           dtcoach defensa --foco "$FOCO"
  echo "== 4. jugadores y banca";        dtcoach jugadores --foco "$FOCO"
  echo "== 5. balón parado";             dtcoach balon-parado --foco "$FOCO"
  echo "== 6. simulación y proyección";  dtcoach simular --foco "$FOCO"
  echo "== 7. blindaje";                 dtcoach blindaje --foco "$FOCO"
  echo "== $(date '+%F %T') · listo. Salidas: reports/historia/$SLUG/<sección>/"
} 2>&1 | tee "$LOG"
