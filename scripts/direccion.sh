#!/usr/bin/env bash
# Experimento ADR-v2-37: estado zona × dirección de llegada (aumento de estado direccional).
# Reglas pre-registradas en docs/11_HIPOTESIS.md ANTES de correr esto con datos reales.
# NO toca el vocabulario oficial: todo va a data/processed/direccion/ y reports/direccion/.
# No necesita 360: usa las mismas transiciones que el vocabulario oficial (su control).
#
# Uso (raíz del repo, venv activo):   bash scripts/direccion.sh      |   KS="2 3 4 5 6" bash scripts/direccion.sh
# Para descartarlo sin rastro:        rm -rf data/processed/direccion reports/direccion reports/fase1/direccion_cv.*
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports/direccion
LOG="reports/direccion/corrida_$(date +%Y%m%d_%H%M).log"
KS_GRID="${KS:-2 3 4 5}"
k_max () {
python - "$@" <<'PY'
import sys, polars as pl
from dtcoach.config import Config
c = Config.load(sys.argv[1] if len(sys.argv) > 1 else None)
tag = f"{c['pitch']['nx']}x{c['pitch']['ny']}_{'p0' if c['mezcla'].get('paso_inicial', True) else 'atado'}"
p = c.ruta("reportes") / "mezcla" / f"curva_k_{tag}.csv"
if not p.exists():
    print(-1); sys.exit()
rep = pl.read_csv(p).filter(pl.col("reproducible"))["K"].to_list()
print(max(rep) if rep else 0)
PY
}
{
  echo "== $(date '+%F %T') · EXPERIMENTO DIRECCIÓN (ADR-v2-37) · K: $KS_GRID"
  echo "== 0. pruebas"; pytest -q
  echo "== 1. ¿la dirección de llegada mejora la predicción de la siguiente acción? (regla 1)"
  dtcoach direccion-cv
  eleccion=$(python - <<'PY'
import json
from dtcoach.config import Config
d = json.loads((Config.load().ruta("reportes") / "fase1" / "direccion_cv.json").read_text())
fila = [f for f in d["tabla"] if f["candidato"] == d["elegido"]][0]
print(d["elegido"] if (d["elegido"] != "base:1" and fila["mejora"]) else "no")
PY
)
  if [ "$eleccion" = "no" ]; then
    echo "   REGLA 1: la dirección no mejora la predicción. Fin del experimento; se queda la malla 5×4."; exit 0
  fi
  echo "   REGLA 1 cumplida: $eleccion"
  python - "$eleccion" <<'PY'
import re, sys
from pathlib import Path
p = Path("config/direccion.yaml"); s = p.read_text()
s = re.sub(r"(\n  metodo: )\S+", rf'\g<1>"{sys.argv[1]}"', s); p.write_text(s)
print(f"   config/direccion.yaml: metodo = {sys.argv[1]}")
PY
  echo "== 2. transiciones zona × dirección"
  dtcoach --config config/direccion.yaml direccion-aplicar
  echo "== 3. curva de K del experimento (control: la curva oficial de la malla 5×4)"
  dtcoach --config config/direccion.yaml curva-k --k $KS_GRID | grep -E "^K=|reproducibles"
  kc=$(k_max); kd=$(k_max config/direccion.yaml)
  echo "== REGLA 2: mayor K reproducible · control (oficial) $kc · dirección $kd"
  if [ "$kd" -ge 3 ] && [ "$kd" -ge "$kc" ]; then
    echo "   CUMPLIDA. Siguiente:"
    echo "   dtcoach --config config/direccion.yaml mezcla --K $kd && dtcoach --config config/direccion.yaml bondad --K 1 $kd"
    echo "   dtcoach --config config/direccion.yaml markov --K $kd"
    echo "   y mira reports/direccion/mezcla/tipos_K${kd}_*.png antes de nombrar nada."
  else
    echo "   NO cumplida: el vocabulario oficial sigue siendo 5×4, K = 3. La regla 1 queda como resultado de la fase 1."
  fi
  echo "== $(date '+%F %T') · listo"
} 2>&1 | tee "$LOG"
