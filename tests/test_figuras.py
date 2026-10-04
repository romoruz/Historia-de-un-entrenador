"""Las figuras que enlazan los documentos tienen origen en publicar_figuras.sh (si no, la copia en docs/figuras se
desincroniza de reports/ al volver a correr el pipeline)."""
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verificar_figuras", RAIZ / "scripts" / "verificar_figuras.py")
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)


def test_cada_figura_enlazada_tiene_origen():
    sin_origen = [str(f.relative_to(RAIZ)) for _, f in vf.enlaces()
                  if str(f).startswith(str(vf.FIG)) and not vf.en_publicar(f)]
    assert not sin_origen, sin_origen


def test_en_publicar_distingue():
    s = ('copiar a/x.png identidad/contexto.png\n'
         'for f in percentiles reparto; do copiar $H/ofensiva/$f.png ofensiva/$f.png; done\n'
         'for f in $H/jugadores/red_*.png; do [ -f "$f" ] && copiar "$f" "jugadores/$(basename "$f")"; done\n')
    si = ["identidad/contexto.png", "ofensiva/reparto.png", "jugadores/red_pachuca.png"]
    no = ["identidad/rival.png", "ofensiva/valor_zona.png", "defensa/reparto.png", "jugadores/decisiones.png"]
    assert all(vf.en_publicar(vf.FIG / r, s) for r in si)
    assert not any(vf.en_publicar(vf.FIG / r, s) for r in no)
