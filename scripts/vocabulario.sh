#!/usr/bin/env bash
# Enmienda de la fase 1 v3 (ADR-v2-35, registrada en docs/11_HIPOTESIS.md ANTES de correr esto):
# la malla del VOCABULARIO es la más fina cuyo mayor K reproducible es >= 3.
# Se prueba de la más fina a la más gruesa y se detiene en la primera que cumpla.
# Si ninguna llega a K >= 3: la más fina con algún K reproducible, con ese K. Si ninguna: se detiene.
#
# Uso (raíz del repo, venv activo):
#   bash scripts/vocabulario.sh
#   MALLAS="8x5 6x4 5x4" KS="2 3 4 5" bash scripts/vocabulario.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports/fase1
LOG="reports/fase1/corrida_vocabulario_$(date +%Y%m%d_%H%M).log"
MALLAS="${MALLAS:-8x5 6x4 5x4}"
KS_GRID="${KS:-2 3 4 5}"

poner_malla () {
python - "$1" <<'PY'
import re, sys
from dtcoach.config import Config
nx, ny = (int(x) for x in sys.argv[1].split("x"))
p = Config.load().archivo
p.write_text(re.sub(r"pitch:\s*\{nx:\s*\d+,\s*ny:\s*\d+", f"pitch: {{nx: {nx}, ny: {ny}", p.read_text()))
print(f"   malla en config: {nx}x{ny}")
PY
}

k_max () {
python - <<'PY'
import polars as pl
from dtcoach.config import Config
c = Config.load()
tag = f"{c['pitch']['nx']}x{c['pitch']['ny']}_{'p0' if c['mezcla'].get('paso_inicial', True) else 'atado'}"
t = pl.read_csv(c.ruta("reportes") / "mezcla" / f"curva_k_{tag}.csv")
rep = t.filter(pl.col("reproducible"))["K"].to_list()
print(max(rep) if rep else 0)
PY
}

{
  echo "== $(date '+%F %T') · VOCABULARIO (enmienda ADR-v2-35) · mallas: $MALLAS · K: $KS_GRID"
  echo "== 0. pruebas"; pytest -q
  elegida=""; K=0; respaldo=""; KR=0
  for M in $MALLAS; do
    echo "== malla $M"
    poner_malla "$M"
    dtcoach fase0 | grep -E "transiciones\"|secuencias\"|estados_transitorios|coordinate" || true
    dtcoach curva-k --k $KS_GRID | grep -E "^K=|reproducibles"
    k=$(k_max)
    echo "   $M: mayor K reproducible = $k"
    if [ "$k" -ge 3 ]; then elegida="$M"; K="$k"; break; fi
    if [ -z "$respaldo" ] && [ "$k" -ge 2 ]; then respaldo="$M"; KR="$k"; fi
  done
  if [ -z "$elegida" ]; then
    if [ -n "$respaldo" ]; then
      elegida="$respaldo"; K="$KR"
      echo "   ninguna malla llegó a K >= 3; regla de respaldo: $elegida con K = $K"
    else
      echo "   NINGUNA malla tiene un K reproducible. Se detiene (no se elige sin regla)."; exit 3
    fi
  fi
  echo "== vocabulario elegido: malla $elegida, K = $K"
  poner_malla "$elegida"
  dtcoach fase0 | grep -E "estados_transitorios" || true
  echo "== mezcla final";                   dtcoach mezcla --K "$K"
  echo "== reproducibilidad";              dtcoach reproducibilidad --K "$K"
  echo "== bondad de la duración";         dtcoach bondad --K 1 "$K"
  echo "== propiedades de la cadena";      dtcoach markov --K "$K"
  python - "$K" <<'PY'
import re, sys
from dtcoach.config import Config
cfg = Config.load(); K = int(sys.argv[1]); p = cfg.archivo; s = p.read_text()
viejo = int(re.search(r"\nfase2:\n  K: (\d+)", s).group(1))
s = re.sub(r"(\nfase2:\n  K: )\d+", rf"\g<1>{K}", s)
fam_actual = re.search(r"\n  familias: \[([^\]]*)\]", s).group(1).split(",")
if K != viejo or len(fam_actual) != K:
    fam = ", ".join(f"Tipo {k + 1}" for k in range(K))
    s = re.sub(r"(\n  familias: )\[[^\]]*\]", rf"\1[{fam}]", s)
    print(f"config: fase2.K = {K}; familias → [{fam}]: NÓMBRALAS tras ver las figuras")
else:
    print(f"config: fase2.K = {K} (sin cambio de nombres)")
p.write_text(s)
PY
  echo "== $(date '+%F %T') · listo"
  echo "Siguiente: mira reports/mezcla/tipos_K${K}_*.png y reports/fase1/MARKOV_${elegida}.md; nombra las familias;"
  echo "  dtcoach atlas --rehacer · bash scripts/correr_foco.sh \"Andre Jardine\" 30 · bash scripts/correr_foco.sh \"Guillermo Almada\" 7"
} 2>&1 | tee "$LOG"
