#!/usr/bin/env python3
"""
¿Las figuras que enlazan los documentos existen en docs/figuras y las regenera `publicar_figuras.sh`?

reports/ no se versiona (.gitignore); los documentos enlazan copias en docs/figuras/ que hace
`scripts/publicar_figuras.sh`. Este script revisa cada imagen enlazada desde README.md y docs/**/*.md
(markdown `![..](..)` y `<img src="..">`):

  - que el archivo exista (si no, en GitHub sale 404);
  - que `publicar_figuras.sh` la copie (si no, la copia se desincroniza al volver a correr el pipeline).

Uso:  python scripts/verificar_figuras.py            (sale con 1 si falta alguna)
      python scripts/verificar_figuras.py --max-mb 20 (además, falla si docs/figuras pesa más)
"""
import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FIG = RAIZ / "docs" / "figuras"
PUBLICAR = RAIZ / "scripts" / "publicar_figuras.sh"
_MD = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
_IMG = re.compile(r"<img[^>]+src=\"([^\"]+)\"")


def enlaces() -> list[tuple[Path, Path]]:
    """(documento, figura) para cada imagen local enlazada desde README.md y docs/."""
    docs = [RAIZ / "README.md", *sorted((RAIZ / "docs").rglob("*.md"))]
    out = []
    for d in docs:
        if not d.exists():
            continue
        txt = d.read_text(encoding="utf-8")
        for ref in _MD.findall(txt) + _IMG.findall(txt):
            if ref.startswith(("http://", "https://", "data:")):
                continue
            out.append((d, (d.parent / ref).resolve()))
    return out


def en_publicar(fig: Path, script: str | None = None) -> bool:
    """¿`publicar_figuras.sh` produce esta figura? (destino literal, o un nombre dentro de un `for f in ...` de su
    sección, o un comodín `red_*` / `partido_tipo_*`)."""
    script = PUBLICAR.read_text(encoding="utf-8") if script is None else script
    rel = fig.relative_to(FIG).as_posix()
    sec, nombre = rel.split("/", 1) if "/" in rel else ("", rel)
    base = nombre.removesuffix(".png")
    if re.search(rf"\s{re.escape(rel)}\s*$", script, re.M):
        return True
    for m in re.finditer(r"for f in (.+?);\s*do(.+?)done", script, re.S):
        nombres, cuerpo = m.group(1).replace("\\\n", " ").split(), m.group(2)
        if f"{sec}/$f.png" in cuerpo and base in nombres:
            return True
        if f"{sec}/$(basename" in cuerpo:
            patron = next((n for n in nombres if "*" in n), "")
            glob = patron.rsplit("/", 1)[-1]
            if glob and Path(nombre).match(glob):
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mb", type=float, default=None)
    a = ap.parse_args()
    malos = 0
    for doc, fig in enlaces():
        rel_doc = doc.relative_to(RAIZ)
        try:
            dentro = fig.is_relative_to(FIG)
        except AttributeError:
            dentro = str(fig).startswith(str(FIG))
        if not fig.exists():
            print(f"  FALTA      {rel_doc} → {fig.relative_to(RAIZ)}")
            malos += 1
        if dentro and not en_publicar(fig):
            print(f"  SIN ORIGEN {rel_doc} → {fig.relative_to(RAIZ)} (publicar_figuras.sh no la copia)")
            malos += 1
    mb = sum(f.stat().st_size for f in FIG.rglob("*") if f.is_file()) / 2 ** 20 if FIG.exists() else 0.0
    print(f"docs/figuras: {mb:.1f} MB; enlaces revisados: {len(enlaces())}; problemas: {malos}")
    if a.max_mb is not None and mb > a.max_mb:
        print(f"[PARA] docs/figuras pesa {mb:.1f} MB (> {a.max_mb:g} MB): revisar antes de commitear")
        return 2
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
