#!/usr/bin/env bash
# Experimento ADR-v2-36: estado zona × nivel de presión (360 / Voronoi local).
# Reglas pre-registradas en docs/11_HIPOTESIS.md ANTES de correr esto con datos reales.
# NO toca el vocabulario oficial: todo va a data/processed/presion/ y reports/presion*/.
#
# Uso (raíz del repo, venv activo, config/default.yaml con la malla del vocabulario 5×4):
#   bash scripts/presion.sh
#   KS="2 3 4 5 6" bash scripts/presion.sh
# Para descartar el experimento sin dejar rastro:
#   rm -rf data/interim/rasgos_360.parquet data/processed/presion reports/presion reports/presion_base
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports/presion
LOG="reports/presion/corrida_$(date +%Y%m%d_%H%M).log"
KS_GRID="${KS:-2 3 4 5}"
k_max () {
python - "$1" <<'PY'
import sys, polars as pl
from dtcoach.config import Config
c = Config.load(sys.argv[1])
tag = f"{c['pitch']['nx']}x{c['pitch']['ny']}_{'p0' if c['mezcla'].get('paso_inicial', True) else 'atado'}"
t = pl.read_csv(c.ruta("reportes") / "mezcla" / f"curva_k_{tag}.csv")
rep = t.filter(pl.col("reproducible"))["K"].to_list()
print(max(rep) if rep else 0)
PY
}
{
  echo "== $(date '+%F %T') · EXPERIMENTO 360 (ADR-v2-36) · K: $KS_GRID"
  echo "== 0. pruebas"; pytest -q
  echo "== 1. rasgos de los freeze frames"
  if [ -f data/interim/rasgos_360.parquet ]; then echo "   ya existen (bórralos para recalcular)"; else dtcoach voronoi; fi
  echo "== 2. ¿la presión mejora la predicción de la siguiente acción? (regla 1)"
  dtcoach presion-cv
  eleccion=$(python - <<'PY'
import json
from dtcoach.config import Config
c = Config.load()
d = json.loads((c.ruta("reportes") / "fase1" / "presion_cv.json").read_text())
fila = [f for f in d["tabla"] if f["candidato"] == d["elegido"]][0]
print(d["elegido"] if (d["elegido"] != "base:1" and fila["mejora"]) else "no")
PY
)
  if [ "$eleccion" = "no" ]; then
    echo "   REGLA 1: la presión no mejora la predicción. Fin del experimento; se queda la malla 5×4."; exit 0
  fi
  echo "   REGLA 1 cumplida: $eleccion"
  python - "$eleccion" <<'PY'
import re, sys
from pathlib import Path
m, L = sys.argv[1].split(":")
p = Path("config/presion.yaml"); s = p.read_text()
s = re.sub(r"(\n  metodo: )\S+", rf"\g<1>{m}", s); s = re.sub(r"(\n  L: )\d+", rf"\g<1>{L}", s)
p.write_text(s); print(f"   config/presion.yaml: metodo = {m}, L = {L}")
PY
  echo "== 3. transiciones zona × nivel y su control (misma muestra, L = 1)"
  dtcoach --config config/presion.yaml presion-aplicar
  echo "== 4. curva de K del CONTROL (malla sola, partidos con 360)"
  dtcoach --config config/presion_base.yaml curva-k --k $KS_GRID | grep -E "^K=|reproducibles"
  echo "== 5. curva de K del EXPERIMENTO (zona × presión)"
  dtcoach --config config/presion.yaml curva-k --k $KS_GRID | grep -E "^K=|reproducibles"
  kb=$(k_max config/presion_base.yaml); kp=$(k_max config/presion.yaml)
  echo "== REGLA 2: mayor K reproducible · control $kb · experimento $kp"
  if [ "$kp" -ge 4 ] && [ "$kp" -gt "$kb" ]; then
    echo "   CUMPLIDA: la presión permite más tipos reproducibles. Siguiente:"
    echo "   dtcoach --config config/presion.yaml mezcla --K $kp && dtcoach --config config/presion.yaml markov --K $kp"
    echo "   y mira reports/presion/mezcla/tipos_K${kp}_*.png antes de nombrar nada."
  else
    echo "   NO cumplida: el vocabulario oficial sigue siendo 5×4, K = 3."
    echo "   La presión queda como resultado de la fase 1 (regla 1) y, si se quiere, como covariable de la fase 2."
  fi
  echo "== $(date '+%F %T') · listo"
} 2>&1 | tee "$LOG"
