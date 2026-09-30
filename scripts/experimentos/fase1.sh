#!/usr/bin/env bash
# FASE 1 v3 completa, desde los eventos ya aplanados (ADR-v2-29 a 33).
# Las tres decisiones (malla, paso inicial, K) se toman con reglas PRE-REGISTRADAS
# en docs/11_HIPOTESIS.md §"Fase 1 v3". Nada se decide a ojo.
#
# Uso (raíz del repo, venv activo):
#   bash scripts/fase1.sh                 # K candidatos 2..6
#   KS="2 3 4 5 6 7 8" bash scripts/fase1.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p reports/fase1
LOG="reports/fase1/corrida_fase1_v3_$(date +%Y%m%d_%H%M).log"
KS_GRID="${KS:-2 3 4 5 6}"

leer_k () {
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
  echo "== $(date '+%F %T') · FASE 1 v3"
  echo "== 0. pruebas";                                   pytest -q
  echo "== 1. calibración del mallado (regla 1-EE pareada, se escribe en config)"
  dtcoach mallado --aplicar
  echo "== 2. transiciones y secuencias con la malla elegida"
  dtcoach fase0
  echo "== 3. ¿paso inicial propio? (K = 3 provisional; t > 2 y KS menor)"
  dtcoach comparar-paso --K 3 --aplicar
  echo "== 4. curva de K con la malla y variante elegidas (regla: el MAYOR K reproducible)"
  dtcoach curva-k --k $KS_GRID
  K=$(leer_k)
  if [ "$K" = "0" ]; then
    echo "   NINGÚN K cumple la regla pre-registrada. El script se DETIENE: elegir K sin regla"
    echo "   sería una decisión post hoc. Revisa la curva de K y registra una enmienda con fecha"
    echo "   en docs/11_HIPOTESIS.md antes de continuar (ver ADR-v2-35)."
    exit 3
  fi
  echo "   K elegido: $K"
  echo "== 5. mezcla final";                              dtcoach mezcla --K "$K"
  echo "== 6. reproducibilidad del K final";              dtcoach reproducibilidad --K "$K"
  echo "== 7. bondad de la duración (K = 1 contra K final)"; dtcoach bondad --K 1 "$K"
  echo "== 8. propiedades de la cadena, primer paso y memoria"; dtcoach markov --K "$K"
  python - "$K" <<'PY'
import re, sys
from dtcoach.config import Config
cfg = Config.load()
K = int(sys.argv[1]); p = cfg.archivo; s = p.read_text()
viejo = int(re.search(r"\nfase2:\n  K: (\d+)", s).group(1))
s = re.sub(r"(\nfase2:\n  K: )\d+", rf"\g<1>{K}", s)
if K != viejo:
    fam = ", ".join(f"Tipo {k + 1}" for k in range(K))
    s = re.sub(r"(\n  familias: )\[[^\]]*\]", rf"\1[{fam}]", s)
p.write_text(s)
print(f"config: fase2.K = {K}" + ("" if K == viejo else f" (antes {viejo}); familias → [{fam}]: NÓMBRALAS tras ver las figuras"))
atlas = cfg.ruta("reportes") / "fase3" / "atlas.csv"
if atlas.exists():
    import datetime
    atlas.rename(atlas.with_name(f"atlas_vocabulario_anterior_{datetime.date.today():%Y%m%d}.csv"))
    print("   atlas anterior archivado: el vocabulario cambió y el atlas debe rehacerse")
PY
  echo "== $(date '+%F %T') · FASE 1 v3 lista"
  echo "Siguiente:"
  echo "  1. mira reports/mezcla/tipos_K${K}_*.png y reports/fase1/{mallado,yaglom}.png; nombra las familias en config"
  echo "  2. dtcoach elo  (no cambia)  ·  dtcoach atlas --rehacer"
  echo "  3. bash scripts/correr_foco.sh \"Andre Jardine\" 30  ·  bash scripts/correr_foco.sh \"Guillermo Almada\" 7"
} 2>&1 | tee "$LOG"
