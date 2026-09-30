"""
Fase ofensiva (reto 5.1, G1): cómo sale, por dónde progresa, cómo llega y qué ocasión genera.

Cada métrica es una razón de sumas por equipo-partido (`m__n`, `m__d`), como el resto de
la capa de fútbol (03_FRAMEWORK §5), así que pasa por la misma maquinaria: foco contra
liga, percentil entre técnicos y fiabilidad. Definiciones exactas en 03_FRAMEWORK §7.

CARRILES (el "modelo de cinco carriles", con las líneas del área)
  banda      y < 18 o y > 62      (por fuera del área)
  interior   18 ≤ y < 30 o 50 < y ≤ 62   (entre el área chica y el área: "half-spaces")
  centro     30 ≤ y ≤ 50          (el ancho del área chica)

1. SALIDA
  perdidas_propio_tercio  pases fallados, controles fallados y balones perdidos con x < 40
  pase_bajo_presion       pases completos / pases hechos con un rival encima (bandera de StatsBomb)
  pase_largo              pases de juego de ≥ `largo_m` / pases de juego
2. PROGRESIÓN
  directness              Σ(x_fin − x) / Σ longitud, en pases completos y conducciones de juego:
                          1 = todo hacia el arco, 0 = todo en horizontal (Fernández-Navarro et al. 2016)
  velocidad_avance        Σ(x_max − x0) / Σ duración de las posesiones de juego que nacen en su
                          campo (m/s hacia el arco)
  prog_banda, prog_interior, prog_centro   reparto de las acciones progresivas por el carril
                          donde terminan
  prog_conduccion         fracción de las acciones progresivas que son conducciones
  cambios_orientacion     pases completos de juego con |Δy| ≥ `cambio_m` por partido
3. LLEGADA
  entrada_centro, entrada_filtrado, entrada_atras, entrada_conduccion, entrada_otro
                          reparto de las entradas al área por cómo entra (centro, pase filtrado,
                          pase atrás desde la línea de fondo, conducción, otro pase); necesita `extra`
  zona14                  pases completos y conducciones que terminan frente al área
                          (84 ≤ x < 102, 30 ≤ y ≤ 50) por partido
4. OCASIÓN
  remate_area, remate_cabeza, remate_primera   fracción de sus remates dentro del área, de cabeza,
                          de primera (esta última necesita `extra`)
  dist_remate             distancia media al arco de sus remates
  asist_centro, asist_filtrado, asist_atras, asist_pase, asist_sin
                          reparto de sus remates por la acción que los asistió (key pass de
                          StatsBomb); "sin" = remate sin pase previo (jugada individual, rechace)
  xg_juego_abierto        xG por partido fuera de jugadas a balón parado y penales
  remate_contra           remates por partido que nacen de un contraataque (play_pattern)
5. MOTIVOS DE PASE (Gyarmati, Kwak & Rodríguez 2014; Bekkers & Dabadghao 2019)
  Tres pases seguidos del mismo equipo, cada uno recibido por quien hace el siguiente,
  involucran hasta cuatro jugadores. Reetiquetando por orden de aparición quedan cinco
  dibujos: ABAB (ida y vuelta), ABAC (pared y salida), ABCA (triangulación que vuelve),
  ABCB y ABCD (el balón viaja a un cuarto jugador). motivo_XXXX = su fracción.
6. LAS FAMILIAS EN LA CANCHA
  Para cada familia del vocabulario: por dónde pasa el balón (visitas por zona, foco contra
  liga, ponderadas por la responsabilidad de cada secuencia) y el CAMINO TÍPICO: la ruta
  más probable desde la zona de inicio más frecuente hasta el remate,
      argmax_{camino} Π P(z_t → z_{t+1}) · P(z_T → remate),
  que es un camino más corto con pesos −log P (Dijkstra; los pesos son no negativos).
"""
from __future__ import annotations

import heapq

import numpy as np
import polars as pl

from .eventos import BALON_PARADO, en_area
from .futbol import _por_partido, _progresivo

PATRONES_BP = ("From Corner", "From Free Kick", "From Throw In")
MOTIVOS = ("ABAB", "ABAC", "ABCA", "ABCB", "ABCD")

DEFINICIONES = {
    "perdidas_propio_tercio": {"nombre": "pérdidas en su propio tercio por partido", "formato": "{:.1f}"},
    "pase_bajo_presion": {"nombre": "pases completos bajo presión", "formato": "{:.3f}"},
    "pase_largo": {"nombre": "pases largos (≥ 30 m) de juego", "formato": "{:.3f}"},
    "directness": {"nombre": "verticalidad (avance hacia el arco / distancia recorrida)", "formato": "{:.3f}"},
    "velocidad_avance": {"nombre": "velocidad de avance de sus posesiones (m/s)", "formato": "{:.2f}"},
    "prog_banda": {"nombre": "progresiones que terminan por la banda", "formato": "{:.3f}"},
    "prog_interior": {"nombre": "progresiones que terminan por los carriles interiores", "formato": "{:.3f}"},
    "prog_centro": {"nombre": "progresiones que terminan por el centro", "formato": "{:.3f}"},
    "prog_conduccion": {"nombre": "progresiones con conducción (no pase)", "formato": "{:.3f}"},
    "cambios_orientacion": {"nombre": "cambios de orientación por partido", "formato": "{:.1f}"},
    "entrada_centro": {"nombre": "entradas al área con un centro", "formato": "{:.3f}"},
    "entrada_filtrado": {"nombre": "entradas al área con pase filtrado", "formato": "{:.3f}"},
    "entrada_atras": {"nombre": "entradas al área con pase atrás", "formato": "{:.3f}"},
    "entrada_conduccion": {"nombre": "entradas al área conduciendo", "formato": "{:.3f}"},
    "entrada_otro": {"nombre": "entradas al área con otro pase", "formato": "{:.3f}"},
    "zona14": {"nombre": "balones jugados frente al área (zona 14) por partido", "formato": "{:.1f}"},
    "remate_area": {"nombre": "remates desde dentro del área", "formato": "{:.3f}"},
    "remate_cabeza": {"nombre": "remates de cabeza", "formato": "{:.3f}"},
    "remate_primera": {"nombre": "remates de primera", "formato": "{:.3f}"},
    "dist_remate": {"nombre": "distancia media de remate (m)", "formato": "{:.1f}"},
    "asist_centro": {"nombre": "remates asistidos por un centro", "formato": "{:.3f}"},
    "asist_filtrado": {"nombre": "remates asistidos por un pase filtrado", "formato": "{:.3f}"},
    "asist_atras": {"nombre": "remates asistidos por un pase atrás", "formato": "{:.3f}"},
    "asist_pase": {"nombre": "remates asistidos por otro pase", "formato": "{:.3f}"},
    "asist_sin": {"nombre": "remates sin pase previo (individual o rechace)", "formato": "{:.3f}"},
    "xg_juego_abierto": {"nombre": "xG de juego abierto por partido", "formato": "{:.2f}"},
    "remate_contra": {"nombre": "remates de contraataque por partido", "formato": "{:.2f}"},
    **{f"motivo_{m}": {"nombre": f"motivo de pase {m}", "formato": "{:.3f}"} for m in MOTIVOS},
}

SALIDA = ["perdidas_propio_tercio", "pase_bajo_presion", "pase_largo"]
PROGRESION = ["directness", "velocidad_avance", "prog_banda", "prog_interior", "prog_centro", "prog_conduccion",
              "cambios_orientacion"]
LLEGADA = ["entrada_centro", "entrada_filtrado", "entrada_atras", "entrada_conduccion", "entrada_otro", "zona14"]
OCASION = ["remate_area", "remate_cabeza", "remate_primera", "dist_remate", "asist_centro", "asist_filtrado",
           "asist_atras", "asist_pase", "asist_sin", "xg_juego_abierto", "remate_contra"]
MOTIVO = [f"motivo_{m}" for m in MOTIVOS]
BLOQUES = {"salida": SALIDA, "progresion": PROGRESION, "llegada": LLEGADA, "ocasion": OCASION, "motivos": MOTIVO}
REQUIERE_EXTRA = {"entrada_centro", "entrada_filtrado", "entrada_atras", "entrada_otro", "remate_primera",
                  "asist_centro", "asist_filtrado", "asist_atras", "asist_pase", "asist_sin"}


def carril(y: pl.Expr) -> pl.Expr:
    return (pl.when((y < 18) | (y > 62)).then(pl.lit("banda"))
            .when((y < 30) | (y > 50)).then(pl.lit("interior")).otherwise(pl.lit("centro")))


def metricas(ev: pl.DataFrame, pos: pl.DataFrame, cfg: dict, con_extra: bool = True) -> list[pl.DataFrame]:
    """Todas las métricas ofensivas nuevas, una tabla por métrica (equipo-partido)."""
    x, y, fx, fy = pl.col("x"), pl.col("y"), pl.col("fin_x"), pl.col("fin_y")
    t = pl.col("type")
    pase = t == "Pass"
    de_juego = ~pl.col("pass_type").is_in(list(BALON_PARADO)).fill_null(False)
    completo = pase & pl.col("pass_outcome").is_null()
    cond = t == "Carry"
    largo = ((fx - x) ** 2 + (fy - y) ** 2).sqrt()
    avanza = (completo & de_juego) | cond
    out = []
    # 1. salida
    perdida = ((pase & de_juego & pl.col("pass_outcome").is_not_null()) | t.is_in(["Miscontrol", "Dispossessed"]))
    out.append(_por_partido(ev, "perdidas_propio_tercio", (perdida & (x < 40)).sum()))
    bp = pase & de_juego & pl.col("under_pressure")
    out.append(_por_partido(ev, "pase_bajo_presion", (bp & pl.col("pass_outcome").is_null()).sum(), bp.sum()))
    out.append(_por_partido(ev, "pase_largo", (pase & de_juego & (largo >= cfg.get("largo_m", 30.0))).sum(),
                            (pase & de_juego).sum()))
    # 2. progresión
    mov = ev.filter(avanza & (largo > 0))
    out.append(_por_partido(mov, "directness", (pl.col("fin_x") - pl.col("x")).sum(),
                            (((pl.col("fin_x") - pl.col("x")) ** 2 + (pl.col("fin_y") - pl.col("y")) ** 2).sqrt()).sum()))
    abiertas = pos.filter(pl.col("patron").is_in(["Regular Play", "From Counter", "From Keeper", "From Goal Kick"])
                          & (pl.col("x0") < 60) & (pl.col("fin") > pl.col("inicio")) & pl.col("x_max").is_not_null())
    out.append(_por_partido(abiertas, "velocidad_avance", (pl.col("x_max") - pl.col("x0")).clip(0, None).sum(),
                            (pl.col("fin") - pl.col("inicio")).sum()))
    prog = ev.filter(((completo & de_juego) | cond) & _progresivo(x, y, fx, fy, cfg)).with_columns(carril(fy).alias("_c"))
    for c in ("banda", "interior", "centro"):
        out.append(_por_partido(prog, f"prog_{c}", (pl.col("_c") == c).sum(), pl.len()))
    out.append(_por_partido(prog, "prog_conduccion", (pl.col("type") == "Carry").sum(), pl.len()))
    out.append(_por_partido(ev, "cambios_orientacion",
                            (completo & de_juego & ((fy - y).abs() >= cfg.get("cambio_m", 35.0))).sum()))
    # 3. llegada
    entra = ev.filter(avanza & ~en_area(x, y) & en_area(fx, fy))
    if con_extra:
        tipo = (pl.when(pl.col("type") == "Carry").then(pl.lit("conduccion"))
                .when(pl.col("pass_cut_back")).then(pl.lit("atras"))
                .when(pl.col("pass_through_ball")).then(pl.lit("filtrado"))
                .when(pl.col("pass_cross")).then(pl.lit("centro")).otherwise(pl.lit("otro")))
        entra = entra.with_columns(tipo.alias("_t"))
        for c in ("centro", "filtrado", "atras", "conduccion", "otro"):
            out.append(_por_partido(entra, f"entrada_{c}", (pl.col("_t") == c).sum(), pl.len()))
    else:
        out.append(_por_partido(entra, "entrada_conduccion", (pl.col("type") == "Carry").sum(), pl.len()))
    out.append(_por_partido(ev, "zona14", (avanza & (fx >= 84) & (fx < 102) & (fy >= 30) & (fy <= 50)).sum()))
    # 4. ocasión
    st = pl.col("shot_type") if "shot_type" in ev.columns else pl.lit(None)
    rem = ev.filter((t == "Shot") & (st != "Penalty").fill_null(True))
    out.append(_por_partido(rem, "remate_area", en_area(x, y).sum(), pl.len()))
    out.append(_por_partido(rem, "remate_cabeza", (pl.col("shot_body_part") == "Head").fill_null(False).sum(), pl.len()))
    out.append(_por_partido(rem, "dist_remate", ((120 - x) ** 2 + (40 - y) ** 2).sqrt().sum(), pl.len()))
    abierto = ~pl.col("play_pattern").is_in(list(PATRONES_BP)).fill_null(False) & \
        ~st.is_in(["Free Kick", "Penalty", "Corner"]).fill_null(False)
    out.append(_por_partido(ev.filter(t == "Shot"), "xg_juego_abierto",
                            (pl.col("shot_statsbomb_xg").fill_null(0.0) * abierto.cast(pl.Float64)).sum()))
    out.append(_por_partido(ev, "remate_contra", ((t == "Shot") & (pl.col("play_pattern") == "From Counter")).sum()))
    if con_extra:
        out.append(_por_partido(rem, "remate_primera", pl.col("shot_first_time").fill_null(False).sum(), pl.len()))
        kp = ev.filter(pase).select(pl.col("id").alias("shot_key_pass_id"), pl.col("pass_cross").alias("_x"),
                                    pl.col("pass_through_ball").alias("_f"), pl.col("pass_cut_back").alias("_a"))
        r = rem.join(kp, on="shot_key_pass_id", how="left")
        asist = (pl.when(pl.col("shot_key_pass_id").is_null()).then(pl.lit("sin"))
                 .when(pl.col("_a")).then(pl.lit("atras")).when(pl.col("_f")).then(pl.lit("filtrado"))
                 .when(pl.col("_x")).then(pl.lit("centro")).otherwise(pl.lit("pase")))
        r = r.with_columns(asist.alias("_as"))
        for c in ("centro", "filtrado", "atras", "pase", "sin"):
            out.append(_por_partido(r, f"asist_{c}", (pl.col("_as") == c).sum(), pl.len()))
    # 5. motivos
    out.append(motivos(ev))
    return out


# ----------------------------------------------------------------------
# Motivos de pase
# ----------------------------------------------------------------------
def etiqueta_motivo(jugadores: list) -> str:
    """[a, b, c, d] → ABAB, ABAC, ... reetiquetando por orden de aparición."""
    m, out = {}, []
    for p in jugadores:
        if p not in m:
            m[p] = "ABCD"[len(m)]
        out.append(m[p])
    return "".join(out)


def motivos(ev: pl.DataFrame) -> pl.DataFrame:
    """Conteo de motivos de 3 pases por equipo-partido (razón: fracción de cada motivo)."""
    p = (ev.filter((pl.col("type") == "Pass") & pl.col("pass_outcome").is_null()
                   & pl.col("pass_recipient_id").is_not_null() & (pl.col("team") == pl.col("possession_team")))
         .select("match_id", "team", "possession", "index", "player_id", "pass_recipient_id")
         .sort("match_id", "index"))
    cuenta: dict = {}
    prev_key, cadena = None, []
    for mid, team, poss, _, a, b in p.iter_rows():
        key = (mid, team, poss)
        if key != prev_key or not cadena or cadena[-1] != a:
            cadena = [a]
        cadena.append(b)
        prev_key = key
        if len(cadena) >= 4:
            et = etiqueta_motivo(cadena[-4:])
            d = cuenta.setdefault((mid, team), dict.fromkeys(MOTIVOS, 0))
            if et in d:
                d[et] += 1
    filas = []
    for (mid, team), d in cuenta.items():
        tot = float(sum(d.values()))
        filas.append({"match_id": mid, "team": team, **{f"motivo_{m}__n": float(d[m]) for m in MOTIVOS},
                      **{f"motivo_{m}__d": tot for m in MOTIVOS}})
    esquema = {"match_id": pl.Int64, "team": pl.Utf8, **{f"motivo_{m}__n": pl.Float64 for m in MOTIVOS},
               **{f"motivo_{m}__d": pl.Float64 for m in MOTIVOS}}
    return pl.DataFrame(filas, schema=esquema)


# ----------------------------------------------------------------------
# Las familias en la cancha
# ----------------------------------------------------------------------
def camino_tipico(P: np.ndarray, inicio: int, nt: int, destinos: tuple[int, ...]) -> dict:
    """Camino de máxima probabilidad desde `inicio` hasta un estado absorbente de `destinos`
    (Dijkstra con pesos −log P). Devuelve los estados transitorios visitados y su probabilidad."""
    fin = np.asarray(P)[:, list(destinos)].sum(axis=1)
    dist = np.full(nt, np.inf)
    padre = np.full(nt, -1)
    dist[inicio] = 0.0
    h = [(0.0, inicio)]
    hecho = np.zeros(nt, bool)
    while h:
        d, i = heapq.heappop(h)
        if hecho[i]:
            continue
        hecho[i] = True
        for j in range(nt):
            p = P[i, j]
            if p <= 0 or hecho[j]:
                continue
            nd = d - np.log(p)
            if nd < dist[j]:
                dist[j], padre[j] = nd, i
                heapq.heappush(h, (nd, j))
    total = dist - np.log(np.maximum(fin, 1e-300))
    k = int(np.argmin(total))
    camino = [k]
    while padre[camino[-1]] >= 0:
        camino.append(int(padre[camino[-1]]))
    return {"estados": camino[::-1], "prob": float(np.exp(-total[k]))}


def familias_en_cancha(d, r: np.ndarray, es_foco: np.ndarray, es_liga: np.ndarray, P_liga: np.ndarray,
                       mu_liga: np.ndarray, lam: float = 50.0) -> list[dict]:
    """Por familia: visitas por zona (foco y liga), zona de inicio y camino típico de cada uno.
    `d`: DatosPosesion; `r`: responsabilidades (n_sec, K); `P_liga`: (K, nt, ns) de la mezcla."""
    from .estimate import shrink
    nt, ns = d.n_transient, d.n_states
    n_z = nt // d.n_phases
    destinos = (nt, nt + 1)                          # GOL y REMATE sin gol
    S1 = d.S1 if d.S0 is not None else d.S
    out = []
    for k in range(r.shape[1]):
        fam = {}
        for nombre, m in (("foco", es_foco), ("liga", es_liga)):
            w = r[m, k]
            C = np.asarray(S1[m].T @ w).reshape(nt, ns)
            vis = C.sum(axis=1)
            ini = np.bincount(d.inicio[m], weights=w, minlength=nt)
            Pk = shrink(C, P_liga[k], lam) if nombre == "foco" else P_liga[k]
            s0 = int(np.argmax(ini)) if ini.sum() > 0 else int(np.argmax(mu_liga[k]))
            cam = camino_tipico(Pk, s0, nt, destinos)
            fam[nombre] = {"visitas": (vis / max(vis.sum(), 1e-12)).reshape(n_z, d.n_phases).sum(1).tolist(),
                           "inicio": (ini / max(ini.sum(), 1e-12)).reshape(n_z, d.n_phases).sum(1).tolist(),
                           "camino": [s // d.n_phases for s in cam["estados"]], "prob_camino": cam["prob"],
                           "secuencias": float(w.sum())}
        out.append(fam)
    return out


def zona_a_xy(z: int, nx: int, ny: int) -> tuple[float, float]:
    ix, iy = divmod(int(z), ny)
    return (ix + 0.5) * 120.0 / nx, (iy + 0.5) * 80.0 / ny

