#!/usr/bin/env bash
# Empaqueta el proyecto para revisión externa: código, pruebas, configuración,
# documentación, reportes y logs. NO incluye datos de StatsBomb (licenciados):
# data/raw, data/interim, data/processed, *.parquet, *.json.gz ni credenciales.
#
# Uso (desde cualquier lugar):
#   bash scripts/empaquetar_revision.sh                 # sin docs/proyecto_viejo
#   bash scripts/empaquetar_revision.sh --con-historial # incluye docs/proyecto_viejo
#
# Resultado: <raíz del repo>/dtcoach_revision_AAAAMMDD_HHMM.zip
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
HISTORIAL=0; [ "${1:-}" = "--con-historial" ] && HISTORIAL=1
NOMBRE="dtcoach_revision_$(date +%Y%m%d_%H%M)"

"$PY" - "$NOMBRE" "$HISTORIAL" <<'PY'
import hashlib, io, os, subprocess, sys, zipfile, datetime
from pathlib import Path

nombre, historial = sys.argv[1], sys.argv[2] == "1"
raiz = Path.cwd()
destino = raiz / f"{nombre}.zip"

INCLUIR = ["src", "tests", "scripts", "config", "docs", "reports", "data/referencia",
           "pyproject.toml", "Makefile", "README.md", "requirements-sb.txt", "uv.lock", ".gitignore"]
EXCLUIR_DIRS = {".venv", ".venv-sb", "__pycache__", ".pytest_cache", ".git", ".ruff_cache"}
EXCLUIR_SUFIJOS = (".parquet", ".json.gz", ".pyc", ".npz", ".zip", ".tmp")
EXCLUIR_NOMBRES = {".env", ".env.local", "credenciales.txt"}
MAX_MB = 25

def excluido(p: Path) -> str | None:
    rel = p.relative_to(raiz)
    partes = set(rel.parts)
    if partes & EXCLUIR_DIRS or any(x.endswith(".egg-info") or x.startswith(".kit_backup") for x in rel.parts):
        return "entorno/caché"
    if str(rel).startswith(("data/raw", "data/interim", "data/processed")):
        return "datos licenciados"
    if not historial and str(rel).startswith("docs/proyecto_viejo"):
        return "historial (usa --con-historial)"
    if p.name in EXCLUIR_NOMBRES or p.name.startswith(".env"):
        return "credenciales"
    if p.name.endswith(EXCLUIR_SUFIJOS):
        return "binario/datos"
    if p.stat().st_size > MAX_MB * 1024 * 1024:
        return f"> {MAX_MB} MB"
    return None

archivos, fuera = [], {}
for item in INCLUIR:
    base = raiz / item
    if not base.exists():
        continue
    for p in ([base] if base.is_file() else sorted(base.rglob("*"))):
        if p.is_file():
            motivo = excluido(p)
            if motivo:
                fuera[motivo] = fuera.get(motivo, 0) + 1
            else:
                archivos.append(p)

# Seguridad: ningún archivo de texto incluido puede traer una credencial ASIGNADA
# (línea que empieza con SB_PASSWORD=valor o export SB_USERNAME=valor).
import re
patron = re.compile(r"^\s*(?:export\s+)?SB_(?:PASSWORD|USERNAME)\s*=\s*['\"]?([^\s'\"#]+)")
for p in archivos:
    if p.suffix in {".py", ".sh", ".md", ".yaml", ".yml", ".toml", ".txt", ".csv", ".json", ".log", ".env"}:
        for linea in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = patron.match(linea)
            if m and not m.group(1).startswith("$") and m.group(1) not in ("...", "xxx", "tu_usuario", "tu_contraseña"):
                sys.exit(f"ABORTA: posible credencial en {p.relative_to(raiz)}: «{linea.strip()[:40]}…»")

def correr(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        return (r.stdout + r.stderr).strip()
    except Exception as e:  # se reporta, no se esconde
        return f"(no se pudo ejecutar {' '.join(cmd)}: {e})"

print(f"{len(archivos)} archivos a incluir · corriendo pruebas...", flush=True)
pytest_out = correr([sys.executable, "-m", "pytest", "-q"])
git = correr(["git", "log", "-1", "--format=%H %ad %s", "--date=iso"])
entorno = correr([sys.executable, "-m", "pip", "freeze"])
if "passed" not in pytest_out or "failed" in pytest_out or "error" in pytest_out.lower().split("passed")[-1]:
    print("AVISO: las pruebas no pasaron limpias; se empaqueta igual y queda registrado:\n" + pytest_out[-800:])

manifiesto = "\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raiz)}" for p in archivos) + "\n"
ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
resumen_fuera = "\n".join(f"- {m}: {n} archivos" for m, n in sorted(fuera.items())) or "- nada"

leeme = f"""# Paquete de revisión — dtcoach (Hackathon ISAC 2026)

Generado: {ahora} · commit: {git or 'sin git'}

## Qué contiene
- `src/dtcoach/`: el paquete (vocabulario de la liga, fases 2–3, decisiones, simulador).
- `tests/`: pruebas con datos **sintéticos**; corren sin datos de StatsBomb.
- `scripts/`, `config/`, `docs/` (roadmap, framework, decisiones ADR, hipótesis pre-registradas, resultados, informe comparativo).
- `reports/`: todas las salidas ya calculadas (tablas `.md`, `.json`, `.csv`, figuras `.png`, logs).
- `data/referencia/`: eras de técnicos verificadas contra el API (sin eventos).
- `REVISION/`: salida de pytest al empaquetar, entorno (`pip freeze`) y `MANIFIESTO.sha256`.

## Qué NO contiene (y por qué)
Datos de StatsBomb (licenciados, uso exclusivo del reto) ni credenciales. Excluido:
{resumen_fuera}

## Verificación rápida (sin datos)
```bash
unzip {nombre}.zip -d {nombre} && cd {nombre}
bash VERIFICAR.sh        # integridad (sha256) + instala + corre las pruebas
```

## Reproducir el análisis completo (con datos y credenciales propias)
```bash
# 1. descargar eventos y partidos de Liga MX a data/raw/statsbomb/{{events,matches}}
dtcoach aplanar && dtcoach partidos && dtcoach fase0
dtcoach mezcla --K 3 && dtcoach reproducibilidad --K 3 && dtcoach bondad --K 1 3
dtcoach elo
bash scripts/correr_foco.sh "Guillermo Almada" 7
bash scripts/correr_foco.sh "Guillermo Almada" 7
```

## Orden de lectura sugerido
1. `docs/INFORME_METODO_Y_COMPARACION.md` — método, resultados y comparación entre proyectos.
2. `docs/11_HIPOTESIS.md` — hipótesis pre-registradas y enmiendas (con fecha).
3. `docs/10_RESULTADOS.md` — resultados con etiqueta de evidencia (🟢🟡⚪🔴).
4. `docs/06_DECISIONES.md` — decisiones de diseño (ADR-v2-01 a 28).
5. `docs/03_FRAMEWORK.md` y `docs/01_ARQUITECTURA.md`.

## Indicación para la IA que revise este paquete
Verifica cada afirmación contra el código y los reportes incluidos antes de aceptarla.
Prioriza: (1) validez de la unidad de análisis y de la inferencia (clusters, FDR,
reproducibilidad de la mezcla), (2) coherencia entre `docs/` y `reports/`,
(3) supuestos declarados en `docs/03_FRAMEWORK.md`. Señala contradicciones con
archivo y línea.
"""

verificar = """#!/usr/bin/env bash
# Verifica integridad, instala en un entorno aislado y corre las pruebas (no requiere datos).
set -euo pipefail
cd "$(dirname "$0")"
echo "== integridad (sha256)"
if command -v sha256sum >/dev/null; then sha256sum -c --quiet REVISION/MANIFIESTO.sha256
else shasum -a 256 -c --quiet REVISION/MANIFIESTO.sha256; fi
echo "   OK"
echo "== entorno"
if command -v uv >/dev/null; then
  uv venv --python 3.12 .venv >/dev/null && uv pip install --python .venv/bin/python -e ".[dev]" >/dev/null
else
  python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
fi
echo "== pruebas"
.venv/bin/python -m pytest -q
echo
echo "Código verificado. El análisis completo requiere datos de StatsBomb (ver LEEME_REVISION.md)."
"""

with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in archivos:
        z.write(p, f"{nombre}/{p.relative_to(raiz)}")
    z.writestr(f"{nombre}/LEEME_REVISION.md", leeme)
    zi = zipfile.ZipInfo(f"{nombre}/VERIFICAR.sh", date_time=datetime.datetime.now().timetuple()[:6])
    zi.external_attr = 0o755 << 16
    z.writestr(zi, verificar)
    z.writestr(f"{nombre}/REVISION/MANIFIESTO.sha256", manifiesto)
    z.writestr(f"{nombre}/REVISION/pytest.txt", pytest_out + "\n")
    z.writestr(f"{nombre}/REVISION/entorno.txt", entorno + "\n")
    z.writestr(f"{nombre}/REVISION/commit.txt", (git or "sin git") + "\n")

with zipfile.ZipFile(destino) as z:
    malo = z.testzip()
    n = len(z.namelist())
if malo:
    sys.exit(f"ABORTA: el zip está corrupto en {malo}")
print(f"\nListo: {destino}")
print(f"  {n} entradas · {destino.stat().st_size / 1e6:.1f} MB · integridad del zip OK")
print(f"  pruebas al empaquetar: {pytest_out.splitlines()[-1] if pytest_out else 'sin salida'}")
print("  excluido:\n" + resumen_fuera)
PY
