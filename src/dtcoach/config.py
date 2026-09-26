"""Cargador del YAML de configuración. ÚNICO lugar con suposición de layout."""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DEFAULT = RAIZ / "config" / "default.yaml"


class Config(dict):
    archivo: Path = DEFAULT

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        p = Path(path) if path else DEFAULT
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        # `hereda: default.yaml` (relativo al archivo): el hijo solo declara lo que cambia.
        # Así un experimento (config/presion.yaml) no duplica parámetros que luego divergen.
        padre = d.pop("hereda", None)
        if padre:
            base = cls.load(p.parent / padre)
            d = _fusionar(dict(base), d)
        c = cls(d)
        c.archivo = p.resolve()          # el archivo REAL cargado (lo editan --aplicar)
        return c

    def ruta(self, clave: str) -> Path:
        """Ruta de `rutas.<clave>` resuelta contra la raíz del repo."""
        r = Path(self["rutas"][clave])
        return r if r.is_absolute() else RAIZ / r


def _fusionar(base: dict, hijo: dict) -> dict:
    """Fusión profunda: los diccionarios se mezclan, todo lo demás lo reemplaza el hijo."""
    out = dict(base)
    for k, v in hijo.items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out
