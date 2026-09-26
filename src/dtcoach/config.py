"""Cargador del YAML de configuración. ÚNICO lugar con suposición de layout."""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DEFAULT = RAIZ / "config" / "default.yaml"


class Config(dict):
    archivo: Path = DEFAULT

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        p = Path(path) if path else DEFAULT
        with open(p, encoding="utf-8") as f:
            c = cls(yaml.safe_load(f))
        c.archivo = p.resolve()          # el archivo REAL cargado (lo editan --aplicar)
        return c

    def ruta(self, clave: str) -> Path:
        """Ruta de `rutas.<clave>` resuelta contra la raíz del repo."""
        r = Path(self["rutas"][clave])
        return r if r.is_absolute() else RAIZ / r
