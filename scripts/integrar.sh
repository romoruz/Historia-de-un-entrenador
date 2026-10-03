#!/usr/bin/env bash
# Integración de exp/mejoras-6 con los datos reales (docs/experimentos/INTEGRACION.md; ADR-v2-69 a 72).
# Un paso por llamada: corre uno, revisa su salida y PARA antes del siguiente.
#
# Uso (raíz del repo, en exp/mejoras-6):
#   bash scripts/integrar.sh paso2     # balón parado con el orden fijo, con el código del paso 2 (cuatro absorbentes)
#   bash scripts/integrar.sh paso4     # quinto absorbente: fase0, mezcla, compuertas, fase 2/3 e historia
#
# Los pasos 1 y 3 son solo documentos (ya están en la rama). Cada paso escribe su log en reports/integracion/.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! python -c "import dtcoach" 2>/dev/null; then source .venv/bin/activate; fi
PASO="${1:?uso: bash scripts/integrar.sh paso2|paso4}"
FOCO="Guillermo Almada"
D=reports/historia/guillermo_almada
RAMA=exp/mejoras-6
mkdir -p reports/integracion
LOG="reports/integracion/${PASO}_$(date +%Y%m%d_%H%M).log"

# Tus cambios locales sin commit (p. ej. config/direccion.yaml) se respetan: solo se para si tocan un archivo que el
# checkout del paso 2 tendría que cambiar.
sin_choque() {
  local cambiados choque
  cambiados=$(git diff --name-only "$1" "$RAMA")
  choque=$(git diff --name-only HEAD | grep -Fx -f <(printf '%s\n' "$cambiados") || true)
  if [ -n "$choque" ]; then
    echo "[PARA] tienes cambios sin commit en archivos que el checkout del paso 2 cambiaría:" >&2
    echo "$choque" >&2; exit 1
  fi
}

case "$PASO" in
paso2)
  [ "$(git branch --show-current)" = "$RAMA" ] || { echo "[PARA] no estás en $RAMA" >&2; exit 1; }
  C2=$(git log "$RAMA" --format=%h --grep="Integración, paso 2" -1)
  [ -n "$C2" ] || { echo "[PARA] no encuentro el commit del paso 2 en $RAMA" >&2; exit 1; }
  sin_choque "$C2"
  [ -f "$D/demostracion/demostracion.csv" ] || { echo "[PARA] falta $D/demostracion/demostracion.csv (la publicada)" >&2; exit 1; }
  {
    echo "== $(date '+%F %T') · paso 2 con el código de $C2 (cuatro absorbentes, mezcla publicada)"
    if [ -e "$D/demostracion_antes_paso2" ]; then
      echo "   ya existe $D/demostracion_antes_paso2: se conserva (es la publicada de la primera vez)"
    else
      cp -a "$D/demostracion" "$D/demostracion_antes_paso2"
      cp -a "$D/balon_parado" "$D/balon_parado_antes_paso2"
    fi
    git checkout -q "$C2"
    trap 'git checkout -q "$RAMA"' EXIT
    echo "== pruebas (171)";            pytest -q
    echo "== balón parado";             dtcoach balon-parado --foco "$FOCO"
    echo "== demostración";             dtcoach demostracion --foco "$FOCO"
    git checkout -q "$RAMA"; trap - EXIT
    echo "== comparación (código de $RAMA)"
    python scripts/experimentos/comparar_demostracion.py "$D/demostracion_antes_paso2/demostracion.csv" \
      "$D/demostracion/demostracion.csv" --titulo "Paso 2: balón parado con el orden fijo (ADR-v2-61, 70)"
    echo "== $(date '+%F %T') · listo. Revisa $D/demostracion/COMPARAR.md: solo debe moverse balon_parado."
  } 2>&1 | tee "$LOG"
  ;;
paso4)
  [ "$(git branch --show-current)" = "$RAMA" ] || { echo "[PARA] no estás en $RAMA" >&2; exit 1; }
  python - <<'PY'
from dtcoach.grid import ABSORBING
assert "INTERRUPCION_FAVOR" in ABSORBING, "el código no es el del paso 4"
PY
  {
    echo "== $(date '+%F %T') · paso 4: quinto absorbente (variante ii)"
    echo "== 0. archivar lo de cuatro absorbentes (no se borra nada)"
    A=data/processed/archivo_4abs; R=reports/archivo_4abs
    if [ -e "$A/transitions.parquet" ]; then
      echo "   ya existe $A: se conserva (es el de cuatro absorbentes de la primera vez)"
    else
      mkdir -p "$A" "$R"
      cp -a data/processed/transitions.parquet "$A/"
      cp -a data/processed/mezcla "$A/"
      for x in mezcla fase2 fase3 historia; do [ -e "reports/$x" ] && cp -a "reports/$x" "$R/"; done
    fi
    echo "== 1. pruebas (174)";         pytest -q
    echo "== 2. fase 0";                dtcoach fase0
    echo "== 3. vocabulario";           dtcoach mezcla --K 3
    echo "== 4. COMPUERTA: xG por secuencia idéntico y cinco contra cuatro sobre los mismos datos"
    python scripts/experimentos/verificar_absorbente5.py --antes "$A/transitions.parquet" \
      --publicada "$A/mezcla/mezcla_K3.npz"
    echo "== 5. COMPUERTA: criterio del §4 con 467,327 secuencias"
    dtcoach reproducibilidad --K 3 --semillas 1 2 3
    dtcoach bondad --K 3
    python - <<'PY'
import json, sys
r = json.load(open("reports/mezcla/reproducibilidad_K3.json"))
b = [x for x in json.load(open("reports/mezcla/bondad_largo.json")) if x["K"] == 3 and x.get("paso_inicial", True)][0]
ok = r["reproducible"] and b["KS"] <= 0.0051 and abs(b["E_T_modelo"] - b["E_T_empirico"]) <= 0.02
print(f"acuerdo suave {r['acuerdo_suave_minimo']:.4f} · rango de J {r['rango_J_por_secuencia']:.2e} por secuencia · "
      f"π mín {r['pi_minimo']:.3f} · KS {b['KS']:.4f} · E[T] {b['E_T_modelo']:.3f} contra {b['E_T_empirico']:.3f}")
if not ok:
    sys.exit("[PARA] el vocabulario con cinco absorbentes no cumple el criterio del §4")
print("criterio del §4: cumple")
PY
    echo "== 6. fase 2 y 3";            bash scripts/correr_foco.sh "$FOCO"
    echo "== 7. la historia";           bash scripts/historia.sh "$FOCO"
    echo "== 8. demostración: cinco contra cuatro absorbentes"
    python scripts/experimentos/comparar_demostracion.py "$R/historia/guillermo_almada/demostracion/demostracion.csv" \
      "$D/demostracion/demostracion.csv" --titulo "Paso 4: cinco contra cuatro absorbentes (ADR-v2-72)"
    echo "== $(date '+%F %T') · listo. Mándame: reports/experimentos/absorbente5_integrado/VERIFICAR.md, la línea del"
    echo "   criterio de arriba, $D/demostracion/COMPARAR.md y $D/demostracion/DEMOSTRACION.md"
  } 2>&1 | tee "$LOG"
  ;;
*) echo "uso: bash scripts/integrar.sh paso2|paso4" >&2; exit 1 ;;
esac
