"""
Balón parado (reto 5.4): corners, tiros libres y laterales largos, ofensivo y defensivo.

LA JUGADA (03_FRAMEWORK §6)
---------------------------
Una jugada a balón parado es un SAQUE: un pase con `pass_type` Corner, Free Kick o
Throw-in, o un remate con `shot_type` Free Kick (tiro libre directo). Se clasifica por
dónde se ejecuta y a dónde va:
  corner           todos los corners
  tl_directo       tiro libre rematado directo al arco
  tl_centrado      tiro libre desde x ≥ `tl_min_x` cuyo destino cae en el área
  tl_otro          tiro libre desde x ≥ `tl_min_x` que no va al área (corto, a la banda)
  lateral_largo    saque de banda cuyo destino cae en el área rival
  lateral_zona     saque de banda desde x ≥ `lateral_min_x` que no va al área
Su desenlace se mide en una VENTANA de `ventana` s desde el saque, cortada en el
siguiente saque del partido: remates, xG y goles del equipo que saca. Así cuenta la
segunda jugada (el rechace que vuelve) sin depender de cómo StatsBomb corta posesiones.

RASGOS DEL SAQUE
----------------
  lado             banda desde la que se saca (y < 40: la de y = 0)
  tecnica          Inswinging (cerrado), Outswinging (abierto), Straight (recto); de `dtcoach extra`
  chica6           el destino cae en el área chica de verdad (6 yardas: x ≥ 114, 30 ≤ y ≤ 50);
                   la zona "area_chica" de abajo es solo su franja central, frente al arco
  zona             destino del balón en el marco del que saca, con u = (y − 40)·s, s = −1 si
                   el saque viene de y < 40 (u > 0 = del lado del saque):
                     corto        destino fuera del área
                     primer_palo  en el área, u > 4
                     segundo_palo en el área, u < −4
                     area_chica   |u| ≤ 4 y x ≥ 114 (la zona del portero)
                     penal        |u| ≤ 4 y x < 114
                   El destino de un pase interceptado es donde se cortó: una zona "corto" puede
                   ser un centro despejado en el primer palo (límite declarado).
  primer_contacto  el primer evento con balón tras el saque (sin recepciones ni duelos,
                   que StatsBomb registra también para quien pierde), en ≤ `contacto_s` s:
                   "ataque" si es del que saca, "defensa" si es del rival
  remate_directo   ese primer contacto es un remate
  intervienen      en las jugadas con remate: jugadores DISTINTOS del que saca que tocan el
                   balón después del saque y hasta el primer remate (incluido el que remata).
                   Lateral → remate = 1; lateral → peinada → remate = 2 (la "segunda jugada")
  pases_cadena     pases del que saca entre el saque y el primer remate (sin contar el saque)

TASAS COMO PROCESO DE POISSON CON EXPOSICIÓN
--------------------------------------------
    y ~ Poisson(n_jugadas · exp(β0 + β1 · foco));  exp(β1) = razón foco / liga
IRLS con varianza sandwich por partido (válida con sobredispersión, que se reporta).

RUTINAS Y LA "RECETA ARSENAL"
-----------------------------
Una rutina de corner = técnica × zona de destino. Para toda la liga: xG por corner y
tasa de remate de cada rutina, con IC por bootstrap de partidos, y qué rutinas usa el
foco. La receta que popularizó el Arsenal de Nicolas Jover (Shaw & Gopaladesikan 2020;
Power et al. 2018): corner cerrado al área chica o primer palo con atacantes encima
del portero (360: `at_portero` ≥ 1). No hay datos de la Premier: lo que se prueba es si
esa receta, jugada en la Liga MX, rinde más que el resto.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats

from .eventos import en_area

TIPOS = ("corner", "tl_directo", "tl_centrado", "tl_otro", "lateral_largo", "lateral_zona")
TIPOS_CENTRO = ("corner", "tl_centrado", "lateral_largo")          # balón al área: capa 1 del xDefense
ZONAS = ("corto", "primer_palo", "area_chica", "penal", "segundo_palo")
TECNICAS = ("Inswinging", "Outswinging", "Straight")
TOQUES = ("Pass", "Ball Receipt*", "Carry", "Shot", "Dribble", "Miscontrol", "Ball Recovery")
CONTACTO = ("Shot", "Clearance", "Interception", "Goal Keeper", "Block", "Pass", "Miscontrol",
            "Ball Recovery", "Carry", "Dribble", "Dispossessed")

NOMBRE = {"corner": "corner", "tl_directo": "tiro libre directo", "tl_centrado": "tiro libre al área",
          "tl_otro": "tiro libre en campo rival (no al área)", "lateral_largo": "lateral largo al área",
          "lateral_zona": "lateral en zona de peligro"}
PLURAL = {"corner": "corners", "tl_directo": "tiros libres directos", "tl_centrado": "tiros libres al área",
          "tl_otro": "tiros libres en campo rival (no al área)", "lateral_largo": "laterales largos al área",
          "lateral_zona": "laterales en zona de peligro"}
ZONA_NOMBRE = {"corto": "corto / fuera del área", "primer_palo": "primer palo", "area_chica": "área chica",
               "penal": "punto penal", "segundo_palo": "segundo palo"}

DEFINICIONES = {
    **{f"n_{t}": {"nombre": f"{PLURAL[t]} por partido", "formato": "{:.2f}"} for t in TIPOS},
    **{f"remate_{t}": {"nombre": f"{PLURAL[t]} con remate (≤ ventana)", "formato": "{:.3f}"} for t in TIPOS},
    **{f"xg_{t}": {"nombre": f"xG por {NOMBRE[t]}", "formato": "{:.3f}"} for t in TIPOS},
    "goles_bp": {"nombre": "goles a balón parado por partido", "formato": "{:.3f}"},
    "xg_bp": {"nombre": "xG a balón parado por partido", "formato": "{:.3f}"},
    "corner_cerrado": {"nombre": "corners cerrados (inswinging)", "formato": "{:.3f}"},
    "corner_abierto": {"nombre": "corners abiertos (outswinging)", "formato": "{:.3f}"},
    **{f"corner_{z}": {"nombre": f"corners al {ZONA_NOMBRE[z]}" if z != "corto" else "corners en corto",
                       "formato": "{:.3f}"} for z in ZONAS},
    "corner_primer_contacto": {"nombre": "corners con el primer contacto propio", "formato": "{:.3f}"},
    "corner_remate_directo": {"nombre": "corners rematados al primer contacto", "formato": "{:.3f}"},
    "at_area_corner": {"nombre": "atacantes en el área en sus corners (360)", "formato": "{:.2f}"},
    "at_chica_corner": {"nombre": "atacantes en el área chica en sus corners (360)", "formato": "{:.2f}"},
    "at_portero_corner": {"nombre": "atacantes encima del portero rival en sus corners (360)", "formato": "{:.2f}"},
    # defensa del balón parado (del equipo que DEFIENDE el saque)
    "de_area_corner": {"nombre": "defensores en el área en corners en contra (360)", "formato": "{:.2f}"},
    "de_chica_corner": {"nombre": "defensores en el área chica en corners en contra (360)", "formato": "{:.2f}"},
    "palo_cercano": {"nombre": "corners en contra con un defensor en el primer palo (360)", "formato": "{:.3f}"},
    "palo_lejano": {"nombre": "corners en contra con un defensor en el segundo palo (360)", "formato": "{:.3f}"},
    "al_hombre": {"nombre": "defensores del área marcando al hombre (≤ 2 m, 360)", "formato": "{:.3f}"},
    "dist_marca": {"nombre": "distancia media de marca en corners en contra (m, 360)", "formato": "{:.2f}"},
    "sobra": {"nombre": "defensores menos atacantes en la zona de remate (360)", "formato": "{:.2f}"},
    "altura_linea_tl": {"nombre": "altura de la línea en tiros libres en contra (m desde su arco, 360)",
                        "formato": "{:.1f}"},
    "en_linea_tl": {"nombre": "defensores formando la línea en tiros libres en contra (360)", "formato": "{:.2f}"},
    "fuera_juego_tl": {"nombre": "tiros libres en contra que terminan en fuera de lugar", "formato": "{:.3f}"},
    "primer_contacto_def": {"nombre": "centros a balón parado en contra con el primer contacto propio",
                            "formato": "{:.3f}"},
    "tl_peligro": {"nombre": "tiros libres a ≤ 30 m del arco por partido", "formato": "{:.2f}"},
    "lat_cuarto": {"nombre": "laterales en el último cuarto por partido", "formato": "{:.2f}"},
    "lat_cuarto_remate": {"nombre": "laterales del último cuarto con remate (≤ ventana)", "formato": "{:.3f}"},
    "lat_cuarto_xg": {"nombre": "xG por lateral del último cuarto", "formato": "{:.3f}"},
    "lat_cuarto_area": {"nombre": "laterales del último cuarto que caen en el área", "formato": "{:.3f}"},
    "lat_segunda": {"nombre": "laterales del último cuarto con remate tras ≥ 2 que intervienen", "formato": "{:.3f}"},
}

OFENSIVAS_BP = ([f"n_{t}" for t in TIPOS] + [f"remate_{t}" for t in TIPOS if t != "tl_directo"]
                + [f"xg_{t}" for t in TIPOS]
                + ["goles_bp", "xg_bp"])
RUTINA_BP = (["corner_cerrado", "corner_abierto"] + [f"corner_{z}" for z in ZONAS]
             + ["corner_primer_contacto", "corner_remate_directo", "at_area_corner", "at_chica_corner",
                "at_portero_corner"])
LATERAL_BP = ["lat_cuarto", "lat_cuarto_area", "lat_cuarto_remate", "lat_cuarto_xg", "lat_segunda"]
DEFENSIVAS_BP = ["de_area_corner", "de_chica_corner", "palo_cercano", "palo_lejano", "al_hombre", "dist_marca",
                 "sobra", "altura_linea_tl", "en_linea_tl", "fuera_juego_tl", "primer_contacto_def"]


# ----------------------------------------------------------------------
# Las jugadas
# ----------------------------------------------------------------------
def _saques(ev: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    pt, st = pl.col("pass_type"), pl.col("shot_type") if "shot_type" in ev.columns else pl.lit(None)
    es_pase = (pl.col("type") == "Pass") & pt.is_in(["Corner", "Free Kick", "Throw-in"]).fill_null(False)
    es_directo = (pl.col("type") == "Shot") & (st == "Free Kick").fill_null(False)
    s = ev.filter(es_pase | es_directo)
    al_area = en_area(pl.col("fin_x"), pl.col("fin_y")).fill_null(False)
    tipo = (pl.when(pl.col("type") == "Shot").then(pl.lit("tl_directo"))
            .when(pt == "Corner").then(pl.lit("corner"))
            .when((pt == "Free Kick") & (pl.col("x") >= cfg["tl_min_x"]) & al_area).then(pl.lit("tl_centrado"))
            .when((pt == "Free Kick") & (pl.col("x") >= cfg["tl_min_x"])).then(pl.lit("tl_otro"))
            .when((pt == "Throw-in") & al_area).then(pl.lit("lateral_largo"))
            .when((pt == "Throw-in") & (pl.col("x") >= cfg["lateral_min_x"])).then(pl.lit("lateral_zona"))
            .otherwise(pl.lit(None)))
    s = s.with_columns(tipo.alias("tipo")).filter(pl.col("tipo").is_not_null())
    sgn = pl.when(pl.col("y") < 40).then(-1.0).otherwise(1.0)
    u = (pl.col("fin_y") - 40.0) * sgn
    zona = (pl.when(~al_area).then(pl.lit("corto"))
            .when(u > 4).then(pl.lit("primer_palo"))
            .when(u < -4).then(pl.lit("segundo_palo"))
            .when(pl.col("fin_x") >= 114).then(pl.lit("area_chica"))
            .otherwise(pl.lit("penal")))
    tec = pl.col("pass_technique") if "pass_technique" in s.columns else pl.lit(None, dtype=pl.Utf8)
    return s.select(
        "match_id", "period", "index", "reloj", "team", "minute", pl.col("id").alias("id_saque"), "tipo",
        pl.col("x").alias("x_saque"), pl.col("y").alias("y_saque"),
        pl.col("fin_x").alias("x_contacto"), pl.col("fin_y").alias("y_contacto"),
        pl.when(pl.col("y") < 40).then(pl.lit("y0")).otherwise(pl.lit("y80")).alias("lado"),
        pl.when(pl.col("tipo") == "tl_directo").then(pl.lit(None)).otherwise(zona).alias("zona"),
        tec.alias("tecnica"), pl.col("pass_height").alias("altura") if "pass_height" in s.columns
        else pl.lit(None, dtype=pl.Utf8).alias("altura"),
        (((pl.col("fin_x") - pl.col("x")) ** 2 + (pl.col("fin_y") - pl.col("y")) ** 2).sqrt()).alias("largo"),
        (pl.col("pass_outcome") == "Pass Offside").fill_null(False).alias("fuera_de_lugar"),
        ((pl.col("fin_x") >= 114) & (pl.col("fin_y") >= 30) & (pl.col("fin_y") <= 50)).fill_null(False)
        .alias("chica6"),
        pl.when(pl.col("type") == "Shot").then(pl.col("shot_statsbomb_xg")).otherwise(None).alias("_xg_directo"))


def _clave(df: pl.DataFrame) -> pl.DataFrame:
    """Llave global ordenable para `join_asof` (partido, índice del evento)."""
    return df.with_columns((pl.col("match_id").cast(pl.Int64) * 1_000_000 + pl.col("index").cast(pl.Int64))
                           .alias("_k")).sort("_k")


def jugadas(ev: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    """Una fila por saque a balón parado con sus rasgos y su desenlace en la ventana."""
    w = float(cfg.get("ventana_bp", 15.0))
    wc = float(cfg.get("contacto_s", 5.0))
    s = _clave(_saques(ev, cfg))
    # la ventana se corta en CUALQUIER reanudación (también saques de meta y en campo propio)
    pt = pl.col("pass_type")
    st = pl.col("shot_type") if "shot_type" in ev.columns else pl.lit(None)
    reanuda = _clave(ev.filter(((pl.col("type") == "Pass") & pt.is_in(["Corner", "Free Kick", "Throw-in", "Goal Kick",
                                                                        "Kick Off"]).fill_null(False))
                               | ((pl.col("type") == "Shot") & (st == "Free Kick").fill_null(False)))
                     .select("match_id", "period", "index", pl.col("reloj").alias("reloj_saque"),
                             pl.col("id").alias("id_saque"), pl.col("team").alias("team_saque")))
    rem = _clave(ev.filter(pl.col("type") == "Shot")
                 .select("match_id", "period", "index", "reloj", pl.col("team").alias("team_remate"),
                         pl.col("shot_statsbomb_xg").fill_null(0.0).alias("xg_r"),
                         (pl.col("shot_outcome") == "Goal").fill_null(False).alias("gol_r"),
                         pl.col("x").alias("xr"), pl.col("y").alias("yr"), pl.col("id").alias("id_remate")))
    asig = rem.join_asof(reanuda.drop("match_id", "period", "index"), on="_k", strategy="backward") \
        .join(reanuda.select("id_saque", pl.col("match_id").alias("_m"), pl.col("period").alias("_p")),
              on="id_saque", how="left")
    asig = asig.filter(pl.col("id_saque").is_not_null() & (pl.col("_m") == pl.col("match_id"))
                       & (pl.col("_p") == pl.col("period")) & (pl.col("team_remate") == pl.col("team_saque"))
                       & (pl.col("reloj") - pl.col("reloj_saque") <= w))
    des = asig.group_by("id_saque").agg(
        pl.col("index").min().alias("_idx_rem1"), pl.len().alias("remates"), pl.col("xg_r").sum().alias("xg"), pl.col("gol_r").sum().alias("goles"),
        pl.col("xr").alias("x_remates"), pl.col("yr").alias("y_remates"), pl.col("id_remate").alias("ids_remate"))
    # primer contacto: primer evento con balón (sin recepciones ni duelos) tras el saque, en ≤ wc s
    con = _clave(ev.filter(pl.col("type").is_in(list(CONTACTO)))
                 .select("match_id", "period", "index", pl.col("reloj").alias("reloj_c"),
                         pl.col("team").alias("team_c"), pl.col("type").alias("tipo_c"), pl.col("id").alias("id_c"),
                         pl.col("match_id").alias("_mc"), pl.col("period").alias("_pc")))
    s = s.join_asof(con.drop("match_id", "period", "index"), on="_k", strategy="forward", allow_exact_matches=False)
    ok = (pl.col("id_c").is_not_null() & (pl.col("_mc") == pl.col("match_id")) & (pl.col("_pc") == pl.col("period"))
          & (pl.col("reloj_c") - pl.col("reloj") <= wc) & (pl.col("tipo") != "tl_directo"))
    s = s.with_columns(
        pl.when(ok & (pl.col("team_c") == pl.col("team"))).then(pl.lit("ataque"))
        .when(ok).then(pl.lit("defensa")).otherwise(pl.lit(None)).alias("primer_contacto"),
        (ok & (pl.col("team_c") == pl.col("team")) & (pl.col("tipo_c") == "Shot")).fill_null(False)
        .alias("remate_directo"))
    j = (s.drop("reloj_c", "team_c", "tipo_c", "id_c", "_mc", "_pc", "_k", "_xg_directo")
         .join(des, on="id_saque", how="left")
         .with_columns(pl.col("remates").fill_null(0), pl.col("xg").fill_null(0.0), pl.col("goles").fill_null(0)))
    # la cadena: quién toca el balón del que saca entre el saque y el primer remate
    toq = _clave(ev.filter(pl.col("type").is_in(list(TOQUES)) & pl.col("player_id").is_not_null())
                 .select("match_id", "period", "index", "team", "player_id", "type"))
    toq = toq.join_asof(reanuda.select("_k", "id_saque", "team_saque", pl.col("match_id").alias("_m"),
                                       pl.col("period").alias("_p"), pl.col("index").alias("_idx_s")),
                        on="_k", strategy="backward")
    toq = (toq.join(j.select("id_saque", "_idx_rem1"), on="id_saque", how="inner")
           .filter((pl.col("_m") == pl.col("match_id")) & (pl.col("_p") == pl.col("period"))
                   & (pl.col("team") == pl.col("team_saque")) & (pl.col("index") > pl.col("_idx_s"))
                   & (pl.col("index") <= pl.col("_idx_rem1"))))
    cad = toq.group_by("id_saque").agg(pl.col("player_id").n_unique().alias("intervienen"),
                                       (pl.col("type") == "Pass").sum().alias("pases_cadena"))
    j = (j.join(cad, on="id_saque", how="left")
         .with_columns(pl.when(pl.col("remates") > 0).then(pl.col("intervienen").fill_null(0)).alias("intervienen"),
                       pl.when(pl.col("remates") > 0).then(pl.col("pases_cadena").fill_null(0)).alias("pases_cadena"))
         .drop("_idx_rem1"))
    # el tiro libre directo ES el remate (la ventana lo incluye: el saque es el remate)
    return j.with_columns((pl.col("remate_directo") | (pl.col("tipo") == "tl_directo")).alias("remate_directo"))


def con_360(j: pl.DataFrame, saques360: pl.DataFrame | None) -> pl.DataFrame:
    if saques360 is None or saques360.height == 0:
        return j
    return j.join(saques360.rename({"id": "id_saque"}).drop("event_index", strict=False),
                  on=["match_id", "id_saque"], how="left")


# ----------------------------------------------------------------------
# Métricas equipo-partido (razón de sumas, como toda la capa de fútbol)
# ----------------------------------------------------------------------
def _agg(df: pl.DataFrame, nombre: str, n: pl.Expr, d: pl.Expr) -> pl.DataFrame:
    return df.group_by("match_id", "team").agg(n.cast(pl.Float64).alias(f"{nombre}__n"),
                                               d.cast(pl.Float64).alias(f"{nombre}__d"))


def lateral_cuarto(j: pl.DataFrame, x_min: float = 90.0) -> pl.DataFrame:
    """Laterales sacados en el último cuarto de la cancha rival (x ≥ `x_min`), vayan o no al área."""
    return j.filter(pl.col("tipo").is_in(["lateral_largo", "lateral_zona"]) & (pl.col("x_saque") >= x_min))


def _conteo(df: pl.DataFrame, tp: pl.DataFrame, nombre: str, n: pl.Expr) -> pl.DataFrame:
    """Conteo POR PARTIDO: el denominador es cada equipo-partido, también los que no tuvieron ninguna
    jugada de ese tipo (si no, `unir` los deja con d = 0 y el promedio solo cuenta los partidos con ≥ 1)."""
    a = df.group_by("match_id", "team").agg(n.cast(pl.Float64).alias(f"{nombre}__n"))
    return (tp.select("match_id", "team").unique().join(a, on=["match_id", "team"], how="left")
            .with_columns(pl.col(f"{nombre}__n").fill_null(0.0), pl.lit(1.0).alias(f"{nombre}__d")))


def metricas(j: pl.DataFrame, tp: pl.DataFrame, cobertura_min: float = 0.8,
             lateral_cuarto_x: float = 90.0) -> list[pl.DataFrame]:
    """`j`: `jugadas` (con `con_360` si hay 360). Ofensivas del que saca; defensivas del rival."""
    out = []
    rem = pl.col("remates") > 0
    for t in TIPOS:
        d = j.filter(pl.col("tipo") == t)
        out.append(_conteo(d, tp, f"n_{t}", pl.len()))
        out.append(d.group_by("match_id", "team").agg(
            rem.sum().cast(pl.Float64).alias(f"remate_{t}__n"), pl.len().cast(pl.Float64).alias(f"remate_{t}__d"),
            pl.col("xg").sum().alias(f"xg_{t}__n"), pl.len().cast(pl.Float64).alias(f"xg_{t}__d")))
    out += [_conteo(j, tp, "goles_bp", pl.col("goles").sum()), _conteo(j, tp, "xg_bp", pl.col("xg").sum())]
    c = j.filter(pl.col("tipo") == "corner")
    con_tec = pl.col("tecnica").is_in(list(TECNICAS))
    out += [_agg(c, "corner_cerrado", (pl.col("tecnica") == "Inswinging").sum(), con_tec.sum()),
            _agg(c, "corner_abierto", (pl.col("tecnica") == "Outswinging").sum(), con_tec.sum())]
    out += [_agg(c, f"corner_{z}", (pl.col("zona") == z).sum(), pl.len()) for z in ZONAS]
    out += [_agg(c, "corner_primer_contacto", (pl.col("primer_contacto") == "ataque").sum(),
                 pl.col("primer_contacto").is_not_null().sum()),
            _agg(c, "corner_remate_directo", pl.col("remate_directo").sum(), pl.len())]
    rival = tp.select("match_id", "team", "rival")
    # quien DEFIENDE el saque: el rival del que saca
    jd = j.join(rival, on=["match_id", "team"], how="inner").drop("team").rename({"rival": "team"})
    centros = jd.filter(pl.col("tipo").is_in(list(TIPOS_CENTRO)))
    out.append(_agg(centros, "primer_contacto_def", (pl.col("primer_contacto") == "defensa").sum(),
                    pl.col("primer_contacto").is_not_null().sum()))
    tl = jd.filter(pl.col("tipo").is_in(["tl_centrado", "tl_otro"]))
    out.append(_agg(tl, "fuera_juego_tl", pl.col("fuera_de_lugar").sum(), pl.len()))
    # tiros libres peligrosos (≤ 30 m del centro del arco): del que saca
    peligro = ((120.0 - pl.col("x_saque")) ** 2 + (40.0 - pl.col("y_saque")) ** 2).sqrt() <= 30.0
    tlp = j.filter(pl.col("tipo").is_in(["tl_directo", "tl_centrado", "tl_otro"]))
    out.append(_conteo(tlp, tp, "tl_peligro", peligro.sum()))
    # laterales en el último cuarto (x ≥ lateral_cuarto_x): del que saca
    la = lateral_cuarto(j, lateral_cuarto_x)
    out += [_conteo(la, tp, "lat_cuarto", pl.len()),
            _agg(la, "lat_cuarto_area", (pl.col("tipo") == "lateral_largo").sum(), pl.len()),
            _agg(la, "lat_cuarto_remate", rem.sum(), pl.len()),
            _agg(la, "lat_cuarto_xg", pl.col("xg").sum(), pl.len()),
            _agg(la, "lat_segunda", (rem & (pl.col("intervienen") >= 2)).fill_null(False).sum(), pl.len())]
    if "at_area" in j.columns:
        vis = c.filter(pl.col("cobertura_area") >= cobertura_min)
        out += [_agg(vis, "at_area_corner", pl.col("at_area").sum(), pl.len()),
                _agg(vis, "at_chica_corner", pl.col("at_chica").sum(), pl.len()),
                _agg(vis.filter(pl.col("gk_visible") == 1), "at_portero_corner", pl.col("at_portero").sum(), pl.len())]
        cd = jd.filter((pl.col("tipo") == "corner") & (pl.col("cobertura_area") >= cobertura_min))
        out += [_agg(cd, "de_area_corner", pl.col("de_area").sum(), pl.len()),
                _agg(cd, "de_chica_corner", pl.col("de_chica").sum(), pl.len()),
                _agg(cd, "palo_cercano", pl.col("palo_cercano").sum(), pl.len()),
                _agg(cd, "palo_lejano", pl.col("palo_lejano").sum(), pl.len()),
                _agg(cd, "al_hombre", pl.col("al_hombre").sum(), pl.col("de_area").sum())]
        cm = jd.filter(pl.col("tipo").is_in(["corner", "tl_centrado"]) & pl.col("dist_marca").is_not_nan())
        out += [_agg(cm, "dist_marca", pl.col("dist_marca").sum(), pl.len()),
                _agg(cm, "sobra", pl.col("sobra").sum(), pl.len())]
        ln = tl.filter(pl.col("altura_linea_tactica").is_not_null() & pl.col("altura_linea_tactica").is_not_nan())
        out += [_agg(ln, "altura_linea_tl", pl.col("altura_linea_tactica").sum(), pl.len()),
                _agg(ln, "en_linea_tl", pl.col("en_linea").sum(), pl.len())]
    return out


def ids_saques(ev: pl.DataFrame, cfg: dict) -> dict[int, set]:
    """Por partido, los ids de los saques a balón parado (para el frame 360 del saque)."""
    s = _saques(ev, cfg).filter(pl.col("tipo") != "lateral_zona")
    out: dict[int, set] = {}
    for m, i in s.select("match_id", "id_saque").iter_rows():
        out.setdefault(int(m), set()).add(i)
    return out


# ----------------------------------------------------------------------
# Poisson con exposición, IRLS y sandwich por partido
# ----------------------------------------------------------------------
def poisson_exposicion(y: np.ndarray, n: np.ndarray, X: np.ndarray, grupos: np.ndarray,
                       max_iter: int = 100) -> dict:
    y, n = np.asarray(y, float), np.asarray(n, float)
    keep = n > 0
    y, n, X, grupos = y[keep], n[keep], X[keep], np.asarray(grupos)[keep]
    b = np.zeros(X.shape[1])
    b[0] = np.log(max(y.sum(), 1e-9) / n.sum())
    for _ in range(max_iter):
        mu = n * np.exp(X @ b)
        H = X.T @ (X * mu[:, None])
        paso = np.linalg.solve(H + 1e-10 * np.eye(len(b)), X.T @ (y - mu))
        b = b + paso
        if np.abs(paso).max() < 1e-10:
            break
    mu = n * np.exp(X @ b)
    H = X.T @ (X * mu[:, None])
    U = X * (y - mu)[:, None]
    _, g = np.unique(grupos, return_inverse=True)
    S = np.zeros((g.max() + 1, X.shape[1]))
    np.add.at(S, g, U)
    G = S.shape[0]
    Hi = np.linalg.inv(H)
    V = Hi @ (S.T @ S) @ Hi * G / max(G - 1, 1)
    dispersion = float(((y - mu) ** 2 / np.maximum(mu, 1e-12)).sum() / max(len(y) - len(b), 1))
    return {"b": b, "V": V, "dispersion_pearson": dispersion, "n": len(y), "partidos": int(G)}


def _partidos_foco(s: pl.DataFrame, foco: str) -> list:
    return s.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique().to_list()


def razon_de_tasas(j: pl.DataFrame, tp: pl.DataFrame, foco: str, tipo: str, que: str = "remates",
                   lado: str = "propio") -> dict:
    """exp(β1): remates (o goles) por jugada del foco sobre los de la liga, con IC sandwich."""
    s = (j.filter(pl.col("tipo") == tipo).group_by("match_id", "team")
         .agg(pl.col(que).sum().alias("y"), pl.len().alias("n"))
         .join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"], how="left"))
    col = "coach" if lado == "propio" else "coach_rival"
    es_f = (s[col] == foco).fill_null(False)
    s = s.filter(es_f | ~pl.col("match_id").is_in(_partidos_foco(s, foco)))
    f = (s[col] == foco).fill_null(False).to_numpy().astype(float)
    y = s["y"].to_numpy()
    if f.sum() == 0 or f.sum() == len(f):
        return {"tipo": tipo, "que": que, "lado": lado, "nota": "sin jugadas del foco o de la liga"}
    if y[f == 1].sum() == 0 or y[f == 0].sum() == 0 or (tipo == "tl_directo" and que == "remates"):
        return {"tipo": tipo, "que": que, "lado": lado, "nota": "sin eventos en un grupo: la razón no se estima"}
    X = np.column_stack([np.ones(s.height), f])
    r = poisson_exposicion(s["y"].to_numpy(), s["n"].to_numpy(), X, s["match_id"].to_numpy())
    se = float(np.sqrt(r["V"][1, 1]))
    z = r["b"][1] / se if se > 0 else float("nan")
    return {"tipo": tipo, "que": que, "lado": lado, "tasa_liga": float(np.exp(r["b"][0])),
            "tasa_foco": float(np.exp(r["b"][0] + r["b"][1])), "razon": float(np.exp(r["b"][1])),
            "lo": float(np.exp(r["b"][1] - 1.96 * se)), "hi": float(np.exp(r["b"][1] + 1.96 * se)),
            "p": float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else float("nan"),
            "dispersion_pearson": r["dispersion_pearson"], "jugadas_foco": int(np.sum(s["n"].to_numpy()[f == 1])),
            "partidos_foco": int((f == 1).sum())}


# ----------------------------------------------------------------------
# Rutinas de corner y la receta Arsenal
# ----------------------------------------------------------------------
def _boot_tasa(mid: np.ndarray, y: np.ndarray, n_boot: int, rng) -> tuple[float, float]:
    """IC 95 % de una media por bootstrap de partidos (sumas por partido)."""
    u, g = np.unique(mid, return_inverse=True)
    sy, sn = np.bincount(g, weights=y, minlength=len(u)), np.bincount(g, minlength=len(u)).astype(float)
    b = []
    for _ in range(n_boot):
        i = rng.integers(0, len(u), len(u))
        b.append(sy[i].sum() / max(sn[i].sum(), 1))
    return float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))


def _boot_medias(mid: np.ndarray, y: np.ndarray, n_boot: int, rng) -> np.ndarray:
    """Distribución bootstrap (por partidos) de la media de `y`."""
    u, g = np.unique(mid, return_inverse=True)
    sy, sn = np.bincount(g, weights=y, minlength=len(u)), np.bincount(g, minlength=len(u)).astype(float)
    return np.array([sy[i].sum() / max(sn[i].sum(), 1) for i in (rng.integers(0, len(u), len(u))
                                                                  for _ in range(n_boot))])


def rutinas(j: pl.DataFrame, tp: pl.DataFrame, foco: str, n_boot: int = 500, seed: int = 0,
            min_corners: int = 150, margen: float = 0.01) -> dict:
    """xG por corner y remate por rutina (técnica × zona) en toda la liga, y el uso del foco."""
    c = j.filter(pl.col("tipo") == "corner").join(tp.select("match_id", "team", "coach", "coach_rival"),
                                                   on=["match_id", "team"], how="left")
    c = c.with_columns(pl.coalesce(pl.col("tecnica"), pl.lit("sin dato")).alias("tec"))
    rng = np.random.default_rng(seed)
    liga = c.filter(~pl.col("match_id").is_in(_partidos_foco(c, foco)))
    mios = c.filter(pl.col("coach") == foco)
    filas = []
    for (tec, zona), d in liga.group_by("tec", "zona"):
        if d.height < min_corners:
            continue
        mid = d["match_id"].to_numpy()
        b = _boot_medias(mid, d["xg"].to_numpy(), n_boot, rng)
        lo, hi = float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))
        resto = liga.filter(~((pl.col("tec") == tec) & (pl.col("zona") == zona)))["xg"].mean()
        # H0: esta rutina rinde lo mismo que el resto de los corners de la liga
        p_r = float(max(1 / n_boot, min(1.0, 2 * min((b <= resto).mean(), (b >= resto).mean()))))
        f = mios.filter((pl.col("tec") == tec) & (pl.col("zona") == zona))
        filas.append({"tecnica": tec, "zona": zona, "corners_liga": d.height,
                      "xg_por_corner": float(d["xg"].mean()), "lo": lo, "hi": hi, "xg_resto": float(resto), "p": p_r,
                      "remate": float((d["remates"] > 0).mean()),
                      "uso_liga": d.height / liga.height, "uso_foco": f.height / max(mios.height, 1),
                      "corners_foco": f.height, "xg_foco": float(f["xg"].mean()) if f.height else float("nan")})
    tab = sorted(filas, key=lambda r: -r["xg_por_corner"])
    # la receta Arsenal: cerrado al área chica o primer palo con atacantes encima del portero
    out = {"rutinas": tab, "corners_liga": liga.height, "corners_foco": mios.height}
    if "at_portero" in c.columns:
        receta = ((pl.col("tec") == "Inswinging") & pl.col("zona").is_in(["area_chica", "primer_palo"])
                  & (pl.col("at_portero") >= 1)).fill_null(False)
        a, b_ = liga.filter(receta), liga.filter(~receta & pl.col("at_portero").is_not_null())
        if a.height >= 30 and b_.height >= 30:
            dif = []
            ma, mb = a["match_id"].to_numpy(), b_["match_id"].to_numpy()
            ua, ub = np.unique(ma), np.unique(mb)
            xa, xb = a["xg"].to_numpy(), b_["xg"].to_numpy()
            ia = {m: np.flatnonzero(ma == m) for m in ua}
            ib = {m: np.flatnonzero(mb == m) for m in ub}
            for _ in range(n_boot):
                sa = np.concatenate([ia[m] for m in rng.choice(ua, len(ua))])
                sb = np.concatenate([ib[m] for m in rng.choice(ub, len(ub))])
                dif.append(xa[sa].mean() - xb[sb].mean())
            dif = np.array(dif)
            out["receta_arsenal"] = {
                "corners": a.height, "xg_receta": float(xa.mean()), "xg_resto": float(xb.mean()),
                "dif": float(xa.mean() - xb.mean()), "lo": float(np.quantile(dif, 0.025)),
                "hi": float(np.quantile(dif, 0.975)),
                "p": float(max(1 / n_boot, min(1, 2 * min((dif <= 0).mean(), (dif >= 0).mean())))),
                # equivalencia (TOST): ¿la diferencia cabe en ±margen? Se demuestra si p_tost < 0.05
                "margen": margen, "lo90": float(np.quantile(dif, 0.05)), "hi90": float(np.quantile(dif, 0.95)),
                "p_tost": float(max(1 / n_boot, max((dif >= margen).mean(), (dif <= -margen).mean()))),
                "uso_liga": a.height / liga.height,
                "uso_foco": float(mios.filter(receta).height / max(mios.height, 1))}
    return out


# ----------------------------------------------------------------------
# Zonas: densidad por jugada
# ----------------------------------------------------------------------
def densidad(x: np.ndarray, y: np.ndarray, n_jugadas: int, bw: float = 3.0, paso: float = 2.0,
             xmin: float = 60.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Kernel gaussiano en la mitad rival: remates por jugada y por m²."""
    gx = np.arange(xmin, 120 + 1e-9, paso)
    gy = np.arange(0, 80 + 1e-9, paso)
    X, Y = np.meshgrid(gx, gy)
    Z = np.zeros_like(X)
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    for a, b in zip(x[ok], y[ok]):
        Z += np.exp(-((X - a) ** 2 + (Y - b) ** 2) / (2 * bw * bw))
    Z /= 2 * np.pi * bw * bw * max(n_jugadas, 1)
    return gx, gy, Z


def mapas(j: pl.DataFrame, tp: pl.DataFrame, foco: str, tipo: str, lado: str = "propio") -> dict:
    s = j.filter(pl.col("tipo") == tipo).join(tp.select("match_id", "team", "coach", "coach_rival"),
                                              on=["match_id", "team"], how="left")
    col = "coach" if lado == "propio" else "coach_rival"
    f = s.filter(pl.col(col) == foco)
    lg = s.filter(~pl.col("match_id").is_in(_partidos_foco(s, foco)))
    out = {}
    for nombre, d in (("foco", f), ("liga", lg)):
        xs = np.concatenate([np.asarray(v, float) for v in d["x_remates"].drop_nulls().to_list()] or [np.array([])])
        ys = np.concatenate([np.asarray(v, float) for v in d["y_remates"].drop_nulls().to_list()] or [np.array([])])
        gx, gy, Zr = densidad(xs, ys, d.height)
        _, _, Zc = densidad(d["x_contacto"].to_numpy(), d["y_contacto"].to_numpy(), d.height)
        out[nombre] = {"remates": Zr, "contacto": Zc, "jugadas": d.height, "n_remates": len(xs)}
    out["gx"], out["gy"] = gx, gy
    return out


def perfil_defensivo(j: pl.DataFrame, tp: pl.DataFrame, foco: str, cobertura_min: float = 0.8) -> dict | None:
    """Organización media en los corners en contra (360): cuántos defienden cada zona.
    Para el dibujo del corner defensivo (foco contra liga)."""
    if "de_area" not in j.columns:
        return None
    jd = (j.filter((pl.col("tipo") == "corner") & (pl.col("cobertura_area") >= cobertura_min))
          .join(tp.select("match_id", "team", "rival", "coach", "coach_rival"), on=["match_id", "team"]))
    f = jd.filter(pl.col("coach_rival") == foco)
    lg = jd.filter(~pl.col("match_id").is_in(_partidos_foco(jd, foco)))
    cols = ["de_area", "de_chica", "palo_cercano", "palo_lejano", "al_hombre", "zonales", "at_area", "at_chica",
            "at_portero"]
    return {n: {c: float(d[c].mean()) for c in cols} | {"corners": d.height} for n, d in (("foco", f), ("liga", lg))
            if d.height}


# ----------------------------------------------------------------------
# Resúmenes por grupo: el foco atacando, el foco defendiendo y la liga
# ----------------------------------------------------------------------
GRUPOS = ("foco_ataque", "foco_defensa", "liga")


def grupos(d: pl.DataFrame, tp: pl.DataFrame, foco: str) -> dict[str, pl.DataFrame]:
    """Las jugadas `d` (una fila por saque, `team` = el que saca) partidas en: las que saca el foco,
    las que le sacan al foco y las de la liga (partidos sin el foco)."""
    d = d.join(tp.select("match_id", "team", "coach", "coach_rival"), on=["match_id", "team"], how="left")
    pf = _partidos_foco(d, foco)
    return {"foco_ataque": d.filter(pl.col("coach") == foco), "foco_defensa": d.filter(pl.col("coach_rival") == foco),
            "liga": d.filter(~pl.col("match_id").is_in(pf))}


def razon_boot(d: pl.DataFrame, num: pl.Expr, den: pl.Expr, n_boot: int = 500, rng=None) -> dict:
    """Σnum/Σden con IC 95 % por bootstrap de partidos."""
    rng = rng if rng is not None else np.random.default_rng(0)
    if d.height == 0:
        return {"valor": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    a = d.group_by("match_id").agg(num.cast(pl.Float64).alias("n"), den.cast(pl.Float64).alias("d"))
    n, dd = a["n"].to_numpy(), a["d"].to_numpy()
    v = n.sum() / dd.sum() if dd.sum() > 0 else float("nan")
    b = []
    for _ in range(n_boot):
        i = rng.integers(0, len(n), len(n))
        if dd[i].sum() > 0:
            b.append(n[i].sum() / dd[i].sum())
    lo, hi = (np.quantile(b, [0.025, 0.975]) if b else (np.nan, np.nan))
    return {"valor": float(v), "lo": float(lo), "hi": float(hi), "n": int(dd.sum())}


def _por_partido(d: pl.DataFrame, tp: pl.DataFrame, grupo: str, foco: str) -> float:
    """Jugadas por partido del grupo (el denominador son los partidos del grupo)."""
    if grupo == "liga":
        m = tp.filter(~pl.col("match_id").is_in(
            tp.filter((pl.col("coach") == foco) | (pl.col("coach_rival") == foco))["match_id"].unique().to_list()))
        partidos = m.height                     # equipo-partido: cada equipo saca en su partido
    else:
        partidos = tp.filter(pl.col("coach") == foco).height
    return d.height / max(partidos, 1)


def resumen_laterales(j: pl.DataFrame, tp: pl.DataFrame, foco: str, x_min: float = 90.0, x_octavo: float = 105.0,
                      n_boot: int = 500, seed: int = 0) -> dict:
    """Laterales en el último cuarto (x ≥ x_min) y en el último octavo (x ≥ x_octavo): cuántos, a dónde
    caen, cuántos acaban en remate y gol, y con cuántos que intervienen (la segunda jugada)."""
    rng = np.random.default_rng(seed)
    la = lateral_cuarto(j, x_min)
    rem = pl.col("remates") > 0
    out = {"x_min": x_min, "x_octavo": x_octavo}
    for tramo, d0 in (("cuarto", la), ("octavo", la.filter(pl.col("x_saque") >= x_octavo))):
        G = grupos(d0, tp, foco)
        out[tramo] = {}
        for g, d in G.items():
            r = {"laterales": d.height, "por_partido": _por_partido(d, tp, g, foco),
                 "al_area": razon_boot(d, (pl.col("tipo") == "lateral_largo").sum(), pl.len(), n_boot, rng),
                 "area_chica": razon_boot(d, pl.col("chica6").sum(), pl.len(), n_boot, rng),
                 "primer_contacto": razon_boot(d, (pl.col("primer_contacto") == "ataque").sum(),
                                               pl.col("primer_contacto").is_not_null().sum(), n_boot, rng),
                 "remate": razon_boot(d, rem.sum(), pl.len(), n_boot, rng),
                 "gol": razon_boot(d, (pl.col("goles") > 0).sum(), pl.len(), n_boot, rng),
                 "xg": razon_boot(d, pl.col("xg").sum(), pl.len(), n_boot, rng),
                 "segunda": razon_boot(d, (rem & (pl.col("intervienen") >= 2)).fill_null(False).sum(), pl.len(),
                                       n_boot, rng)}
            cr = d.filter(rem)
            iv = cr["intervienen"].fill_null(0).to_numpy()
            r["intervienen"] = {"1": int((iv <= 1).sum()), "2": int((iv == 2).sum()), "3+": int((iv >= 3).sum())}
            # el caso que pide el reto: cae en el área chica y termina en remate con ≥ 2 que intervienen
            ch = d.filter(pl.col("chica6"))
            r["chica_segunda"] = {"laterales": ch.height, "de_todos": d.height,
                                  "remate": int(ch.filter(rem).height),
                                  "remate_2mas": int(ch.filter(rem & (pl.col("intervienen") >= 2)).height),
                                  "goles": int(ch["goles"].sum()) if ch.height else 0}
            out[tramo][g] = r
        # prueba exacta de Fisher: de todos los laterales del tramo, ¿cae en el área chica y acaba en remate con
        # ≥ 2 que intervienen más seguido que en la liga?
        L = out[tramo].get("liga", {}).get("chica_segunda")
        for g in ("foco_ataque", "foco_defensa"):
            F = out[tramo].get(g, {}).get("chica_segunda")
            if F and L and F["de_todos"] and L["de_todos"]:
                tabla = [[F["remate_2mas"], F["de_todos"] - F["remate_2mas"]],
                         [L["remate_2mas"], L["de_todos"] - L["remate_2mas"]]]
                F["p_fisher"] = float(stats.fisher_exact(tabla)[1])
    return out


def resumen_tiros_libres(j: pl.DataFrame, directos: pl.DataFrame | None, tp: pl.DataFrame, foco: str,
                         n_boot: int = 500, seed: int = 0) -> dict:
    """Tiros libres en campo rival: cuántos y dónde (≤ 30 m), cómo se juegan (directo, al área, corto) y,
    en los directos, distancia, xG, gol, cuánto arco deja la barrera (goal_open) y cuántos la forman.
    `directos`: remates de tiro libre directo con sus rasgos (de la capa 2: id, goal_open, barrera, ...)."""
    rng = np.random.default_rng(seed)
    tl = j.filter(pl.col("tipo").is_in(["tl_directo", "tl_centrado", "tl_otro"]))
    dist = ((120.0 - pl.col("x_saque")) ** 2 + (40.0 - pl.col("y_saque")) ** 2).sqrt()
    tl = tl.with_columns(dist.alias("dist_arco"))
    if directos is not None and directos.height:
        tl = tl.join(directos.rename({"id": "id_saque"}), on=["match_id", "id_saque"], how="left")
    rem = pl.col("remates") > 0
    out = {}
    for g, d in grupos(tl, tp, foco).items():
        pel = d.filter(pl.col("dist_arco") <= 30.0)
        di = d.filter(pl.col("tipo") == "tl_directo")
        r = {"tiros_libres": d.height, "por_partido": _por_partido(d, tp, g, foco),
             "peligrosos_por_partido": _por_partido(pel, tp, g, foco),
             "reparto_peligrosos": {t: (pel.filter(pl.col("tipo") == t).height / max(pel.height, 1))
                                    for t in ("tl_directo", "tl_centrado", "tl_otro")},
             "directo": {"n": di.height,
                         "dist": razon_boot(di, pl.col("dist_arco").sum(), pl.len(), n_boot, rng),
                         "xg": razon_boot(di, pl.col("xg").sum(), pl.len(), n_boot, rng),
                         "gol": razon_boot(di, (pl.col("goles") > 0).sum(), pl.len(), n_boot, rng)},
             "al_area": {t: {"remate": razon_boot(d.filter(pl.col("tipo") == t), rem.sum(), pl.len(), n_boot, rng),
                             "xg": razon_boot(d.filter(pl.col("tipo") == t), pl.col("xg").sum(), pl.len(), n_boot,
                                              rng)}
                         for t in ("tl_centrado", "tl_otro")}}
        if "goal_open" in d.columns:
            dv = di.filter(pl.col("goal_open").is_not_null() & pl.col("goal_open").is_not_nan())
            r["directo"] |= {"goal_open": razon_boot(dv, pl.col("goal_open").sum(), pl.len(), n_boot, rng),
                             "barrera": razon_boot(dv, pl.col("barrera").sum(), pl.len(), n_boot, rng),
                             "con_foto": dv.height}
        out[g] = r
    return out
