"""Prueba INTEGRAL: una liga sintética en formato crudo de StatsBomb recorre el pipeline
completo, del JSON a cada sección de la historia. Lenta (~minutos): no corre por omisión.

    pytest -m lento tests/test_integral.py
"""
import json
from pathlib import Path

import pytest
import yaml
from liga_cruda import FOCO, generar

from dtcoach import cli
from dtcoach.config import DEFAULT

SECCIONES = ("identidad", "ofensiva", "defensa", "jugadores", "balon_parado", "simulacion", "blindaje")


def configurar(tmp: Path) -> Path:
    raw, it, pr, rep = tmp / "raw", tmp / "interim", tmp / "processed", tmp / "reports"
    c = {"hereda": str(DEFAULT),
         "rutas": {"raw_events": str(raw / "events"), "raw_matches": str(raw / "matches"),
                   "raw_frames": str(raw / "frames"), "eventos_parquet": str(it / "events"),
                   "eventos_extra": str(it / "eventos_extra.parquet"), "partidos": str(it / "partidos.parquet"),
                   "dt_partido": str(it / "dt.parquet"), "eras_dir": str(tmp / "eras"),
                   "exclusiones": str(tmp / "eras" / "absorbidos.csv"), "transiciones": str(pr / "trans.parquet"),
                   "mezcla_dir": str(pr / "mezcla"), "elo": str(pr / "elo.parquet"), "reportes": str(rep)},
         "foco": {"coach": FOCO},
         "mezcla": {"n_corto": 5, "max_iter": 150, "n_init": 2},
         "elo": {"burn_in": 10},
         "fase2": {"n_boot": 60, "n_sim": 60},
         "voronoi": {"rasgos": str(it / "rasgos_360.parquet"), "hilos": 1},
         "futbol": {"tabla": str(pr / "futbol" / "tabla.parquet"), "bloque": str(it / "bloque.parquet"),
                    "saques": str(it / "saques.parquet"), "n_boot": 60, "n_perm": 10, "sim_rep": 300,
                    "sim_validacion_rep": 100, "min_partidos_era": 10, "min_partidos_club": 5,
                    "min_acciones_jugador": 30, "xd_folds": 3},
         "proyeccion": {"n_pre": 7, "n_post": 7, "n_sim": 300}}
    p = tmp / "config.yaml"
    p.write_text(yaml.safe_dump(c, allow_unicode=True))
    return p


@pytest.mark.lento
def test_pipeline_completo(tmp_path):
    generar(tmp_path / "raw", tmp_path / "eras", temporadas=3, seed=0)
    c = str(configurar(tmp_path))
    pasos = [["aplanar", "--hilos", "2"], ["partidos"], ["fase0"], ["mezcla", "--K", "3"], ["elo"],
             ["fase2"], ["fase3", "--min-partidos", "5"], ["decisiones"], ["simulador"],
             ["voronoi", "--hilos", "1"], ["geometria", "--hilos", "1"], ["extra", "--hilos", "2"], ["tabla-liga"],
             ["identidad"], ["ofensiva"], ["defensa"], ["jugadores"], ["balon-parado"], ["simular"], ["blindaje"]]
    for p in pasos:
        print("==", p, flush=True)
        cli.main(["--config", c, *p])
    base = tmp_path / "reports" / "historia" / "guillermo_prueba"
    for s in SECCIONES:
        assert (base / s / f"{s.upper()}.md").exists(), s
        assert json.loads((base / s / f"{s}.json").read_text())
    figs = {p.name for p in base.rglob("*.png")}
    for f in ("curva_presion.png", "bloque_tipico.png", "esquema_bloque.png", "familias_cancha.png", "reparto.png",
              "rutinas_corner.png", "corner_defensivo.png", "linea_tiros_libres.png", "proyeccion.png",
              "efecto_cambios.png", "rival.png", "xd_prev_etapas.png"):
        assert f in figs, f
    bp = json.loads((base / "balon_parado" / "balon_parado.json").read_text())
    assert bp["modelos_xdefensa"]["capa1"]["centros"] > 100
    pr = json.loads((base / "simulacion" / "simulacion.json").read_text())["proyeccion"]
    assert pr["club"] == "Águilas"
