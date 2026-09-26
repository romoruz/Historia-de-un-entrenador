#!/usr/bin/env python3
"""
explorar_datos_sb.py — Inventario completo de lo que trae tu descarga de StatsBomb.

Recorre recursivamente una carpeta con archivos .json o .json.gz del API
(matches, events, lineups, 360) y responde, SIN suponer nada del esquema:

  1. Qué campos existen (ruta aplanada, p. ej. "pass.end_location[0]"),
     en qué tipos de evento aparecen, con qué frecuencia, rangos y valores.
  2. Cómo cambia cada campo y cada tipo de evento POR TORNEO
     (deriva del proveedor: el proyecto viejo la descubrió tarde).
  3. Cobertura de 360: fracción de eventos con freeze frame, jugadores
     visibles, área visible.
  4. Alineaciones: posiciones, motivos de entrada/salida, tarjetas.
  5. Formaciones (Starting XI / Tactical Shift) por equipo y torneo.
  6. Entrenadores por equipo y torneo (desde `managers` de matches).
  7. Controles de calidad: coordenadas fuera de cancha, periodos,
     autogoles, posesiones, índices.

Solo usa la biblioteca estándar: corre en .venv o en .venv-sb.

Uso típico:
    python explorar_datos_sb.py --raiz data/raw_api --salida reports/inventario
    python explorar_datos_sb.py --raiz data/raw_api --muestra 200      # rápido
    python explorar_datos_sb.py --raiz data/raw_api --equipo "América" # sección del club

La clasificación de archivos es por CONTENIDO, no por nombre de carpeta:
si tus carpetas se llaman distinto, funciona igual.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
MAX_DISTINTOS = 60            # tope de valores distintos que se guardan por campo
LISTA_CORTA = 3               # listas numéricas de hasta este largo se expanden (x, y, z)
CANCHA_X, CANCHA_Y = 120.0, 80.0
UMBRAL_DERIVA = 0.05          # cambio absoluto de tasa entre torneos que se reporta


# --------------------------------------------------------------------------
# Utilidades de lectura
# --------------------------------------------------------------------------
def abrir(ruta: str):
    return gzip.open(ruta, "rt", encoding="utf-8") if ruta.endswith(".gz") \
        else open(ruta, "r", encoding="utf-8")


def cargar(ruta: str):
    with abrir(ruta) as f:
        return json.load(f)


def olfatear(ruta: str) -> str:
    """Clasifica un archivo leyendo solo su inicio."""
    try:
        with abrir(ruta) as f:
            cabeza = f.read(6000)
    except (OSError, EOFError, UnicodeDecodeError):
        return "ilegible"
    if '"event_uuid"' in cabeza and ('"freeze_frame"' in cabeza or '"visible_area"' in cabeza):
        return "frames360"
    if '"lineup"' in cabeza and '"team_name"' in cabeza:
        return "lineups"
    if '"home_team"' in cabeza and '"match_id"' in cabeza:
        return "matches"
    if '"possession"' in cabeza and '"type"' in cabeza and '"period"' in cabeza:
        return "events"
    if '"competition_id"' in cabeza and '"season_id"' in cabeza:
        return "competitions"
    return "desconocido"


def match_id_de_ruta(ruta: str):
    numeros = re.findall(r"\d{4,}", os.path.basename(ruta))
    return int(max(numeros, key=len)) if numeros else None


def torneo_de_fecha(fecha: str | None) -> str:
    """Jul–dic = Apertura, ene–jun = Clausura. Lección del proyecto viejo:
    `competition_stage` es inconsistente entre temporadas; la fecha no."""
    if not fecha:
        return "SIN_FECHA"
    try:
        a, m = int(fecha[:4]), int(fecha[5:7])
    except ValueError:
        return "SIN_FECHA"
    return f"A{a}" if m >= 7 else f"C{a}"


def orden_torneo(t: str):
    """Orden cronológico real (no alfabético): C2023 < A2023 < C2024."""
    m = re.match(r"([AC])(\d{4})", t)
    if not m:
        return (9999, 9)
    return (int(m.group(2)), 0 if m.group(1) == "C" else 1)


# --------------------------------------------------------------------------
# Aplanado genérico de un evento
# --------------------------------------------------------------------------
def tipo_valor(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    return "dict"


def aplanar(obj, prefijo="", salida=None):
    """Devuelve lista de (ruta, valor_hoja). Reglas:
    - dict {id, name}: se guarda ruta.name (y ruta.id como int).
    - lista corta de números: se expande en ruta[0], ruta[1], ...
    - lista de dicts: se recorre con ruta[] (freeze_frame, lineup de tácticas).
    - otra lista: se guarda su largo en ruta#len.
    """
    if salida is None:
        salida = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ruta = f"{prefijo}.{k}" if prefijo else k
            if isinstance(v, dict):
                aplanar(v, ruta, salida)
            elif isinstance(v, list):
                if v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) \
                        and len(v) <= LISTA_CORTA:
                    for i, x in enumerate(v):
                        salida.append((f"{ruta}[{i}]", x))
                elif v and all(isinstance(x, dict) for x in v):
                    salida.append((f"{ruta}#len", len(v)))
                    for x in v:
                        aplanar(x, f"{ruta}[]", salida)
                else:
                    salida.append((f"{ruta}#len", len(v)))
            else:
                salida.append((ruta, v))
    return salida


class StatCampo:
    """Acumulador por ruta de campo."""
    __slots__ = ("n", "tipos", "por_tipo_evento", "nmin", "nmax", "suma", "suma2",
                 "nnum", "valores", "saturado")

    def __init__(self):
        self.n = 0
        self.tipos = Counter()
        self.por_tipo_evento = Counter()
        self.nmin = math.inf
        self.nmax = -math.inf
        self.suma = 0.0
        self.suma2 = 0.0
        self.nnum = 0
        self.valores = Counter()
        self.saturado = False

    def agregar(self, v, tipo_evento):
        self.n += 1
        t = tipo_valor(v)
        self.tipos[t] += 1
        self.por_tipo_evento[tipo_evento] += 1
        if t in ("int", "float"):
            fv = float(v)
            if math.isfinite(fv):
                self.nnum += 1
                self.suma += fv
                self.suma2 += fv * fv
                self.nmin = min(self.nmin, fv)
                self.nmax = max(self.nmax, fv)
            # enteros de baja cardinalidad también se cuentan (periodos, ids de posición)
            if t == "int":
                self._valor(v)
        elif t in ("str", "bool", "null"):
            self._valor(v)

    def _valor(self, v):
        if v in self.valores:
            self.valores[v] += 1
        elif len(self.valores) < MAX_DISTINTOS:
            self.valores[v] += 1
        else:
            self.saturado = True

    def fusionar(self, o: "StatCampo"):
        self.n += o.n
        self.tipos.update(o.tipos)
        self.por_tipo_evento.update(o.por_tipo_evento)
        self.nmin = min(self.nmin, o.nmin)
        self.nmax = max(self.nmax, o.nmax)
        self.suma += o.suma
        self.suma2 += o.suma2
        self.nnum += o.nnum
        self.saturado = self.saturado or o.saturado
        for v, c in o.valores.items():
            if v in self.valores or len(self.valores) < MAX_DISTINTOS:
                self.valores[v] += c
            else:
                self.saturado = True


# --------------------------------------------------------------------------
# Procesamiento de un partido (corre en un proceso hijo)
# --------------------------------------------------------------------------
def procesar_eventos(ruta: str, match_id: int, equipo_local: str | None):
    eventos = cargar(ruta)
    campos: dict[str, StatCampo] = {}
    tipo_campo = Counter()           # (tipo_evento, ruta) -> eventos con ese campo
    n_tipo = Counter()               # tipo_evento -> eventos
    calidad = Counter()
    formaciones = Counter()          # (equipo, evento, formación)
    ids = set()
    periodos = Counter()
    min_max_periodo = defaultdict(int)
    num_por_tipo = defaultdict(lambda: [0.0, 0])   # (tipo, ruta) -> [suma, n] para deriva numérica
    posesiones = set()
    ultimo_indice = 0

    for e in eventos:
        te = (e.get("type") or {}).get("name", "SIN_TIPO")
        n_tipo[te] += 1

        # --- calidad ---
        eid = e.get("id")
        if eid in ids:
            calidad["id_duplicado"] += 1
        ids.add(eid)
        idx = e.get("index")
        if isinstance(idx, int):
            if idx != ultimo_indice + 1:
                calidad["index_no_consecutivo"] += 1
            ultimo_indice = idx
        p = e.get("period")
        periodos[p] += 1
        if isinstance(e.get("minute"), int):
            min_max_periodo[p] = max(min_max_periodo[p], e["minute"])
        if "possession" in e:
            posesiones.add(e["possession"])
        loc = e.get("location")
        if isinstance(loc, list) and len(loc) >= 2:
            x, y = loc[0], loc[1]
            if not (0 <= x <= CANCHA_X and 0 <= y <= CANCHA_Y):
                calidad["location_fuera_de_cancha"] += 1
        elif te not in ("Starting XI", "Half Start", "Half End", "Substitution",
                        "Tactical Shift", "Player Off", "Player On", "Injury Stoppage",
                        "Referee Ball-Drop", "Bad Behaviour", "Own Goal For"):
            calidad[f"sin_location::{te}"] += 1
        if te in ("Own Goal For", "Own Goal Against"):
            calidad[f"evento::{te}"] += 1
        if te == "Shot" and ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
            calidad["goles_por_remate"] += 1
        if te in ("Starting XI", "Tactical Shift"):
            form = (e.get("tactics") or {}).get("formation")
            formaciones[((e.get("team") or {}).get("name"), te, form)] += 1

        # --- campos ---
        vistos = set()
        for ruta_c, v in aplanar(e):
            sc = campos.get(ruta_c)
            if sc is None:
                sc = campos[ruta_c] = StatCampo()
            sc.agregar(v, te)
            if ruta_c not in vistos:
                vistos.add(ruta_c)
                tipo_campo[(te, ruta_c)] += 1
            if isinstance(v, (int, float)) and not isinstance(v, bool) and "[]" not in ruta_c \
                    and not ruta_c.endswith(".id") and ruta_c not in ("index", "possession"):
                acc = num_por_tipo[(te, ruta_c)]
                acc[0] += float(v)
                acc[1] += 1

    return {
        "match_id": match_id,
        "n_eventos": len(eventos),
        "n_posesiones": len(posesiones),
        "campos": campos,
        "tipo_campo": tipo_campo,
        "n_tipo": n_tipo,
        "calidad": calidad,
        "formaciones": formaciones,
        "periodos": periodos,
        "min_max_periodo": dict(min_max_periodo),
        "num_por_tipo": dict(num_por_tipo),
        "ids": None,  # no se devuelven: pesan
    }, {e.get("id") for e in eventos}


def area_poligono(pts):
    """Fórmula del cordón (shoelace). `visible_area` viene como x1,y1,x2,y2,..."""
    if not pts or len(pts) < 6:
        return 0.0
    xs, ys = pts[0::2], pts[1::2]
    s = 0.0
    for i in range(len(xs)):
        j = (i + 1) % len(xs)
        s += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(s) / 2.0


def procesar_360(ruta: str, match_id: int):
    frames = cargar(ruta)
    r = Counter()
    r["frames"] = len(frames)
    uuids = set()
    for fr in frames:
        uuids.add(fr.get("event_uuid"))
        ff = fr.get("freeze_frame") or []
        r["jugadores"] += len(ff)
        r["companeros"] += sum(1 for p in ff if p.get("teammate"))
        r["rivales"] += sum(1 for p in ff if not p.get("teammate"))
        r["con_actor"] += int(any(p.get("actor") for p in ff))
        r["con_portero"] += int(any(p.get("keeper") for p in ff))
        va = fr.get("visible_area")
        if va:
            r["area_visible_suma"] += area_poligono(va)
            r["con_area"] += 1
        claves = set(fr.keys())
        for k in claves:
            r[f"clave::{k}"] += 1
        for p in ff[:1]:
            for k in p.keys():
                r[f"clave_jugador::{k}"] += 1
    return {"match_id": match_id, "stats": r}, uuids


def procesar_lineups(ruta: str, match_id: int):
    data = cargar(ruta)
    r = Counter()
    posiciones = Counter()
    motivos = Counter()
    tarjetas = Counter()
    claves_jugador = Counter()
    for eq in data:
        jugadores = eq.get("lineup") or []
        r["jugadores_listados"] += len(jugadores)
        for j in jugadores:
            for k in j.keys():
                claves_jugador[k] += 1
            pos = j.get("positions") or []
            if pos:
                r["jugadores_que_jugaron"] += 1
            if len(pos) > 1:
                r["jugadores_con_cambio_de_posicion"] += 1
            for p in pos:
                posiciones[p.get("position")] += 1
                motivos[("inicio", p.get("start_reason"))] += 1
                motivos[("fin", p.get("end_reason"))] += 1
            for c in j.get("cards") or []:
                tarjetas[c.get("card_type")] += 1
    return {"match_id": match_id, "stats": r, "posiciones": posiciones,
            "motivos": motivos, "tarjetas": tarjetas, "claves_jugador": claves_jugador}


def trabajo(args):
    """Punto de entrada del proceso hijo."""
    clase, ruta, match_id = args
    try:
        if clase == "events":
            res, ids = procesar_eventos(ruta, match_id, None)
            return clase, res, ids
        if clase == "frames360":
            res, uuids = procesar_360(ruta, match_id)
            return clase, res, uuids
        if clase == "lineups":
            return clase, procesar_lineups(ruta, match_id), None
    except Exception as exc:  # un archivo roto no tumba el inventario, pero se reporta
        return "error", {"ruta": ruta, "error": repr(exc)}, None
    return "ignorado", {"ruta": ruta}, None


# --------------------------------------------------------------------------
# Partidos (matches)
# --------------------------------------------------------------------------
def leer_partidos(rutas):
    partidos = {}
    for ruta in rutas:
        data = cargar(ruta)
        if isinstance(data, dict):
            data = [data] if "match_id" in data else list(data.values())
        for m in data:
            mid = m.get("match_id")
            if mid is None:
                continue
            ht, at = m.get("home_team") or {}, m.get("away_team") or {}

            def mgr(t):
                ms = t.get("managers") or []
                return [(x.get("id"), x.get("name"), x.get("nickname")) for x in ms]

            partidos[mid] = {
                "match_id": mid,
                "fecha": m.get("match_date"),
                "torneo": torneo_de_fecha(m.get("match_date")),
                "temporada": (m.get("season") or {}).get("season_name"),
                "season_id": (m.get("season") or {}).get("season_id"),
                "competicion": (m.get("competition") or {}).get("competition_name"),
                "etapa": (m.get("competition_stage") or {}).get("name"),
                "jornada": m.get("match_week"),
                "local": ht.get("home_team_name"),
                "visitante": at.get("away_team_name"),
                "goles_local": m.get("home_score"),
                "goles_visitante": m.get("away_score"),
                "dt_local": mgr(ht),
                "dt_visitante": mgr(at),
                "status": m.get("match_status"),
                "status_360": m.get("match_status_360"),
                "data_version": (m.get("metadata") or {}).get("data_version"),
                "shot_fidelity": (m.get("metadata") or {}).get("shot_fidelity_version"),
                "xy_fidelity": (m.get("metadata") or {}).get("xy_fidelity_version"),
                "estadio": (m.get("stadium") or {}).get("name"),
                "arbitro": (m.get("referee") or {}).get("name"),
                "claves": sorted(m.keys()),
            }
    return partidos


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default="data/raw_api", help="carpeta con los .json/.json.gz del API")
    ap.add_argument("--salida", default="reports/inventario", help="carpeta de salida (se crea)")
    ap.add_argument("--muestra", type=int, default=0, help="procesar solo N partidos al azar (0 = todos)")
    ap.add_argument("--semilla", type=int, default=20260923)
    ap.add_argument("--equipo", default=None, help="nombre EXACTO del equipo (valor de team.name, p. ej. 'América')")
    ap.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()

    t0 = time.time()
    if not os.path.isdir(args.raiz):
        sys.exit(f"ERROR: no existe la carpeta {args.raiz!r}")
    os.makedirs(args.salida, exist_ok=True)

    # 1) descubrir y clasificar
    rutas = []
    for d, _, fs in os.walk(args.raiz):
        for f in fs:
            if f.endswith(".json") or f.endswith(".json.gz"):
                rutas.append(os.path.join(d, f))
    rutas.sort()
    clases = defaultdict(list)
    for r in rutas:
        clases[olfatear(r)].append(r)
    print("Archivos por clase:", {k: len(v) for k, v in clases.items()}, flush=True)
    if not clases.get("events"):
        sys.exit("ERROR: no encontré archivos de eventos. Revisa --raiz. "
                 "(Una carpeta vacía no es un dato: es un fallo.)")

    partidos = leer_partidos(clases.get("matches", []))
    print(f"Partidos en metadatos: {len(partidos)}", flush=True)

    # 2) elegir qué partidos procesar
    def mid_de(r):
        return match_id_de_ruta(r)

    ev_por_mid = {mid_de(r): r for r in clases["events"] if mid_de(r) is not None}
    sin_mid = [r for r in clases["events"] if mid_de(r) is None]
    if sin_mid:
        print(f"AVISO: {len(sin_mid)} archivos de eventos sin match_id en el nombre; se omiten.")
    mids = sorted(ev_por_mid)
    if args.equipo:
        mids = [m for m in mids if m in partidos and args.equipo in (partidos[m]["local"], partidos[m]["visitante"])]
        if not mids:
            sys.exit(f"ERROR: ningún partido con equipo == {args.equipo!r}. Ojo: 'Club América' ≠ 'América'. "
                     f"Equipos vistos: {sorted({p['local'] for p in partidos.values()})}")
    if args.muestra and args.muestra < len(mids):
        mids = sorted(random.Random(args.semilla).sample(mids, args.muestra))
    mids_set = set(mids)
    print(f"Partidos de eventos a procesar: {len(mids)}", flush=True)

    tareas = [("events", ev_por_mid[m], m) for m in mids]
    for clase in ("frames360", "lineups"):
        for r in clases.get(clase, []):
            m = mid_de(r)
            if m in mids_set:
                tareas.append((clase, r, m))

    # 3) acumuladores globales
    campos: dict[str, StatCampo] = {}
    por_torneo_tipo_campo = defaultdict(Counter)     # torneo -> (tipo, ruta) -> n
    por_torneo_n_tipo = defaultdict(Counter)         # torneo -> tipo -> n
    por_torneo_num = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    por_torneo_partidos = Counter()
    calidad = Counter()
    formaciones = Counter()
    periodos = Counter()
    min_max_periodo = defaultdict(int)
    partido_stats = {}
    ids_evento_por_partido = {}
    stats360 = {}
    uuids360 = {}
    lineups = {"stats": Counter(), "posiciones": Counter(), "motivos": Counter(),
               "tarjetas": Counter(), "claves_jugador": Counter()}
    errores = []

    def fusionar_eventos(res):
        mid = res["match_id"]
        tor = partidos.get(mid, {}).get("torneo", "SIN_METADATOS")
        por_torneo_partidos[tor] += 1
        for k, sc in res["campos"].items():
            if k in campos:
                campos[k].fusionar(sc)
            else:
                campos[k] = sc
        por_torneo_tipo_campo[tor].update(res["tipo_campo"])
        por_torneo_n_tipo[tor].update(res["n_tipo"])
        for key, (s, n) in res["num_por_tipo"].items():
            acc = por_torneo_num[tor][key]
            acc[0] += s
            acc[1] += n
        calidad.update(res["calidad"])
        formaciones.update({(tor,) + k: v for k, v in res["formaciones"].items()})
        periodos.update(res["periodos"])
        for p, mm in res["min_max_periodo"].items():
            min_max_periodo[p] = max(min_max_periodo[p], mm)
        partido_stats[mid] = {"n_eventos": res["n_eventos"], "n_posesiones": res["n_posesiones"],
                              "n_tipo": res["n_tipo"]}

    hechos = 0
    with ProcessPoolExecutor(max_workers=args.procesos) as ex:
        futuros = [ex.submit(trabajo, t) for t in tareas]
        for fut in as_completed(futuros):
            clase, res, extra = fut.result()
            if clase == "events":
                fusionar_eventos(res)
                ids_evento_por_partido[res["match_id"]] = extra
            elif clase == "frames360":
                stats360[res["match_id"]] = res["stats"]
                uuids360[res["match_id"]] = extra
            elif clase == "lineups":
                for k in lineups:
                    lineups[k].update(res[k])
            elif clase == "error":
                errores.append(res)
            hechos += 1
            if hechos % 100 == 0:
                print(f"  {hechos}/{len(tareas)} archivos  ({time.time() - t0:.0f}s)", flush=True)

    # cruce eventos ↔ 360: qué fracción de eventos tiene freeze frame
    for mid, uu in uuids360.items():
        ids = ids_evento_por_partido.get(mid) or set()
        stats360[mid]["eventos_con_frame"] = len(uu & ids)
        stats360[mid]["frames_huerfanos"] = len(uu - ids)
    ids_evento_por_partido.clear()

    escribir_salidas(args, partidos, mids, campos, por_torneo_tipo_campo, por_torneo_n_tipo,
                     por_torneo_num, por_torneo_partidos, calidad, formaciones, periodos,
                     min_max_periodo, partido_stats, stats360, lineups, errores, clases, t0)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------
def fmt(x, nd=3):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return ""
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def escribir_csv(ruta, cabecera, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecera)
        w.writerows(filas)


def escribir_salidas(args, partidos, mids, campos, por_torneo_tipo_campo, por_torneo_n_tipo,
                     por_torneo_num, por_torneo_partidos, calidad, formaciones, periodos,
                     min_max_periodo, partido_stats, stats360, lineups, errores, clases, t0):
    S = args.salida
    torneos = sorted(por_torneo_partidos, key=orden_torneo)
    n_total_eventos = sum(ps["n_eventos"] for ps in partido_stats.values())
    n_tipo_total = Counter()
    for c in por_torneo_n_tipo.values():
        n_tipo_total.update(c)

    # --- catálogo de campos ---
    filas = []
    for ruta_c, sc in sorted(campos.items()):
        tipos_ev = sc.por_tipo_evento.most_common(4)
        # cobertura dentro del tipo de evento principal
        te0, n0 = tipos_ev[0] if tipos_ev else ("", 0)
        cobertura = n0 / n_tipo_total[te0] if n_tipo_total.get(te0) else None
        media = sc.suma / sc.nnum if sc.nnum else None
        sd = math.sqrt(max(sc.suma2 / sc.nnum - media ** 2, 0)) if sc.nnum else None
        top = "; ".join(f"{v}={c}" for v, c in sc.valores.most_common(8))
        filas.append([
            ruta_c, sc.n, fmt(sc.n / n_total_eventos if n_total_eventos else None, 4),
            "|".join(f"{t}:{c}" for t, c in sc.tipos.most_common()),
            "|".join(f"{t}:{c}" for t, c in tipos_ev), te0, fmt(cobertura, 4),
            fmt(sc.nmin if sc.nnum else None), fmt(sc.nmax if sc.nnum else None),
            fmt(media), fmt(sd),
            f">{MAX_DISTINTOS}" if sc.saturado else len(sc.valores), top,
        ])
    escribir_csv(os.path.join(S, "catalogo_campos.csv"),
                 ["ruta", "n", "frac_de_todos_los_eventos", "tipos_de_valor", "tipos_de_evento_top",
                  "tipo_evento_principal", "cobertura_en_su_tipo", "min", "max", "media", "sd",
                  "n_distintos", "valores_top"], filas)

    # --- eventos por partido por torneo (deriva de volumen) ---
    filas = []
    tipos_todos = sorted(n_tipo_total, key=lambda t: -n_tipo_total[t])
    for te in tipos_todos:
        fila = [te, n_tipo_total[te]]
        for tor in torneos:
            npart = por_torneo_partidos[tor]
            fila.append(fmt(por_torneo_n_tipo[tor][te] / npart if npart else None, 2))
        filas.append(fila)
    escribir_csv(os.path.join(S, "eventos_por_partido_por_torneo.csv"),
                 ["tipo_evento", "total"] + torneos, filas)

    # --- deriva de presencia de campos por torneo ---
    filas, alertas = [], []
    claves = set()
    for c in por_torneo_tipo_campo.values():
        claves.update(c)
    for (te, ruta_c) in sorted(claves):
        tasas = []
        for tor in torneos:
            den = por_torneo_n_tipo[tor][te]
            tasas.append(por_torneo_tipo_campo[tor][(te, ruta_c)] / den if den else None)
        validas = [t for t in tasas if t is not None]
        rango = (max(validas) - min(validas)) if len(validas) >= 2 else 0.0
        filas.append([te, ruta_c] + [fmt(t, 4) for t in tasas] + [fmt(rango, 4)])
        if rango >= UMBRAL_DERIVA and n_tipo_total[te] >= 1000:
            alertas.append((rango, te, ruta_c, tasas))
    escribir_csv(os.path.join(S, "presencia_campo_por_torneo.csv"),
                 ["tipo_evento", "ruta"] + torneos + ["rango"], filas)
    alertas.sort(reverse=True)

    # --- deriva numérica (media por torneo) ---
    filas = []
    claves = set()
    for d in por_torneo_num.values():
        claves.update(d)
    for (te, ruta_c) in sorted(claves):
        medias = []
        for tor in torneos:
            s, n = por_torneo_num[tor].get((te, ruta_c), (0.0, 0))
            medias.append(s / n if n else None)
        filas.append([te, ruta_c] + [fmt(m) for m in medias])
    escribir_csv(os.path.join(S, "media_numerica_por_torneo.csv"),
                 ["tipo_evento", "ruta"] + torneos, filas)

    # --- partidos ---
    filas = []
    for mid in sorted(partidos, key=lambda m: (partidos[m]["fecha"] or "", m)):
        p = partidos[mid]
        ps = partido_stats.get(mid, {})
        s3 = stats360.get(mid, {})
        filas.append([
            mid, p["fecha"], p["torneo"], p["temporada"], p["etapa"], p["jornada"], p["local"],
            p["visitante"], p["goles_local"], p["goles_visitante"],
            " / ".join(f"{n}" + (f" ({nn})" if nn else "") for _, n, nn in p["dt_local"]),
            " / ".join(f"{n}" + (f" ({nn})" if nn else "") for _, n, nn in p["dt_visitante"]),
            len(p["dt_local"]), len(p["dt_visitante"]),
            p["status"], p["status_360"], p["data_version"], p["xy_fidelity"], p["shot_fidelity"],
            ps.get("n_eventos", ""), ps.get("n_posesiones", ""),
            s3.get("frames", ""), fmt(s3["eventos_con_frame"] / ps["n_eventos"], 3)
            if s3 and ps.get("n_eventos") else "",
            "sí" if mid in partido_stats else "no",
        ])
    escribir_csv(os.path.join(S, "partidos.csv"),
                 ["match_id", "fecha", "torneo", "temporada", "etapa", "jornada", "local", "visitante",
                  "gl", "gv", "dt_local", "dt_visitante", "n_dt_local", "n_dt_visitante", "status",
                  "status_360", "data_version", "xy_fidelity", "shot_fidelity", "n_eventos",
                  "n_posesiones", "frames_360", "frac_eventos_con_360", "procesado"], filas)

    # --- entrenadores por equipo y torneo ---
    dt = defaultdict(Counter)
    for p in partidos.values():
        for eq, ms in ((p["local"], p["dt_local"]), (p["visitante"], p["dt_visitante"])):
            nombre = " + ".join(f"{n}[{i}]" for i, n, _ in ms) if ms else "SIN_MANAGER"
            dt[(eq, p["torneo"])][nombre] += 1
    filas = [[eq, tor, nombre, c] for (eq, tor), cnt in sorted(dt.items(), key=lambda kv: (kv[0][0] or "", orden_torneo(kv[0][1])))
             for nombre, c in cnt.most_common()]
    escribir_csv(os.path.join(S, "entrenadores_por_equipo_torneo.csv"),
                 ["equipo", "torneo", "entrenador[id]", "partidos"], filas)

    # --- formaciones ---
    filas = [[tor, eq, ev, form, c] for (tor, eq, ev, form), c in
             sorted(formaciones.items(), key=lambda kv: (orden_torneo(kv[0][0]), kv[0][1] or "", kv[0][2], -kv[1]))]
    escribir_csv(os.path.join(S, "formaciones.csv"), ["torneo", "equipo", "evento", "formacion", "n"], filas)

    # --- 360 por torneo ---
    agg360 = defaultdict(Counter)
    for mid, s in stats360.items():
        tor = partidos.get(mid, {}).get("torneo", "SIN_METADATOS")
        agg360[tor].update(s)
        agg360[tor]["partidos_con_360"] += 1
        agg360[tor]["eventos_totales"] += partido_stats.get(mid, {}).get("n_eventos", 0)
    filas = []
    for tor in sorted(agg360, key=orden_torneo):
        a = agg360[tor]
        fr = a["frames"] or 1
        filas.append([tor, a["partidos_con_360"], por_torneo_partidos.get(tor, 0), a["frames"],
                      fmt(a["eventos_con_frame"] / a["eventos_totales"] if a["eventos_totales"] else None),
                      fmt(a["jugadores"] / fr, 2), fmt(a["companeros"] / fr, 2), fmt(a["rivales"] / fr, 2),
                      fmt(a["con_portero"] / fr), fmt(a["area_visible_suma"] / a["con_area"] if a["con_area"] else None, 0),
                      a["frames_huerfanos"]])
    escribir_csv(os.path.join(S, "cobertura_360_por_torneo.csv"),
                 ["torneo", "partidos_con_360", "partidos_procesados", "frames", "frac_eventos_con_frame",
                  "jugadores_por_frame", "companeros_por_frame", "rivales_por_frame", "frac_con_portero",
                  "area_visible_media_m2", "frames_sin_evento"], filas)

    # --- alineaciones ---
    filas = [["posicion", k, v] for k, v in lineups["posiciones"].most_common()]
    filas += [[f"motivo_{a}", b, v] for (a, b), v in lineups["motivos"].most_common()]
    filas += [["tarjeta", k, v] for k, v in lineups["tarjetas"].most_common()]
    filas += [["clave_jugador", k, v] for k, v in lineups["claves_jugador"].most_common()]
    filas += [["resumen", k, v] for k, v in lineups["stats"].items()]
    escribir_csv(os.path.join(S, "alineaciones.csv"), ["grupo", "valor", "n"], filas)

    # --- calidad ---
    filas = [[k, v] for k, v in calidad.most_common()]
    filas += [[f"periodo={p}", c] for p, c in sorted(periodos.items(), key=lambda kv: str(kv[0]))]
    filas += [[f"minuto_max_periodo={p}", m] for p, m in sorted(min_max_periodo.items(), key=lambda kv: str(kv[0]))]
    filas += [[f"ERROR::{e['ruta']}", e["error"]] for e in errores]
    escribir_csv(os.path.join(S, "calidad.csv"), ["chequeo", "valor"], filas)

    # --- resumen legible ---
    escribir_md(args, S, partidos, mids, campos, torneos, por_torneo_partidos, n_tipo_total,
                n_total_eventos, alertas, calidad, periodos, min_max_periodo, stats360, errores,
                clases, dt, formaciones, t0)
    print(f"\nListo en {time.time() - t0:.0f}s. Revisa {os.path.join(S, 'INVENTARIO.md')}")


def escribir_md(args, S, partidos, mids, campos, torneos, por_torneo_partidos, n_tipo_total,
                n_total_eventos, alertas, calidad, periodos, min_max_periodo, stats360, errores,
                clases, dt, formaciones, t0):
    L = []
    a = L.append
    a(f"# Inventario de datos StatsBomb — {date.today().isoformat()}\n")
    a(f"Raíz: `{args.raiz}` · partidos procesados: **{len(mids)}**"
      + (f" (muestra aleatoria, semilla {args.semilla})" if args.muestra else "")
      + (f" · filtro equipo = `{args.equipo}`" if args.equipo else "") + "\n")
    a("Archivos por clase: " + ", ".join(f"{k}={len(v)}" for k, v in clases.items()) + "\n")
    a(f"Eventos: **{n_total_eventos:,}** · campos distintos (rutas aplanadas): **{len(campos)}**\n")
    if errores:
        a(f"\n**⚠ {len(errores)} archivos no se pudieron leer** (ver `calidad.csv`).\n")

    a("\n## Partidos por torneo (orden cronológico)\n")
    a("| torneo | partidos procesados | con 360 |")
    a("|---|---|---|")
    con360 = Counter(partidos.get(m, {}).get("torneo", "SIN_METADATOS") for m in stats360)
    for t in torneos:
        a(f"| {t} | {por_torneo_partidos[t]} | {con360.get(t, 0)} |")

    a("\n## Etapas de competición (para decidir liguilla sí/no)\n")
    et = Counter((p["etapa"], p["torneo"]) for p in partidos.values())
    for (e, t), c in sorted(et.items(), key=lambda kv: (orden_torneo(kv[0][1]), str(kv[0][0]))):
        a(f"- {t} · {e}: {c}")

    a("\n## Versiones de datos del proveedor (metadata)\n")
    ver = Counter((p["torneo"], p["data_version"], p["xy_fidelity"], p["shot_fidelity"]) for p in partidos.values())
    a("| torneo | data_version | xy_fidelity | shot_fidelity | partidos |")
    a("|---|---|---|---|---|")
    for (t, dv, xy, sf), c in sorted(ver.items(), key=lambda kv: orden_torneo(kv[0][0])):
        a(f"| {t} | {dv} | {xy} | {sf} | {c} |")

    a("\n## Tipos de evento\n")
    a("| tipo | total | por partido |")
    a("|---|---|---|")
    for te, c in n_tipo_total.most_common():
        a(f"| {te} | {c:,} | {c / max(len(mids), 1):.1f} |")

    a(f"\n## Campos cuya presencia cambia ≥ {UMBRAL_DERIVA:.0%} entre torneos (posible deriva del proveedor)\n")
    if not alertas:
        a("Ninguno (o un solo torneo en la muestra).")
    else:
        a("| rango | tipo | campo | " + " | ".join(torneos) + " |")
        a("|---|---|---|" + "---|" * len(torneos))
        for rango, te, ruta_c, tasas in alertas[:60]:
            a(f"| {rango:.2f} | {te} | `{ruta_c}` | " + " | ".join(fmt(t, 2) for t in tasas) + " |")
        if len(alertas) > 60:
            a(f"\n…y {len(alertas) - 60} más en `presencia_campo_por_torneo.csv`.")

    a("\n## Campos con valores categóricos (lo que puedes filtrar o cruzar)\n")
    for ruta_c, sc in sorted(campos.items()):
        if (sc.tipos.get("str") or sc.tipos.get("bool")) and not sc.saturado and len(sc.valores) >= 2 \
                and not ruta_c.endswith("id") and sc.n >= 50:
            vals = ", ".join(f"{v} ({c:,})" for v, c in sc.valores.most_common(12))
            a(f"- `{ruta_c}` [{len(sc.valores)}]: {vals}")

    a("\n## Controles de calidad\n")
    for k, v in calidad.most_common(30):
        a(f"- {k}: {v:,}")
    a("- periodos: " + ", ".join(f"{p}={c:,}" for p, c in sorted(periodos.items(), key=lambda kv: str(kv[0]))))
    a("- minuto máximo por periodo: " + ", ".join(f"{p}→{m}" for p, m in sorted(min_max_periodo.items(), key=lambda kv: str(kv[0]))))

    a("\n## Entrenadores (partidos con 0 o >1 managers)\n")
    raros = [(k, n) for k, c in dt.items() for n in c if n == "SIN_MANAGER" or "+" in n]
    a(f"{len(raros)} combinaciones equipo·torneo con manager vacío o múltiple (ver `entrenadores_por_equipo_torneo.csv`).")

    if args.equipo:
        a(f"\n## Sección del equipo: {args.equipo}\n")
        a("Entrenadores según `managers` de matches (todos los partidos en metadatos, no solo los procesados):\n")
        a("| torneo | entrenador[id] | partidos |")
        a("|---|---|---|")
        for (eq, tor), c in sorted(dt.items(), key=lambda kv: orden_torneo(kv[0][1])):
            if eq == args.equipo:
                for n, k in c.most_common():
                    a(f"| {tor} | {n} | {k} |")
        a("\nFormaciones de salida (Starting XI):")
        fs = Counter()
        for (tor, eq, ev, form), c in formaciones.items():
            if eq == args.equipo and ev == "Starting XI":
                fs[form] += c
        for form, c in fs.most_common():
            a(f"- {form}: {c}")

    a("\n## Archivos generados\n")
    for f in sorted(os.listdir(S)):
        a(f"- `{f}`")
    a(f"\nTiempo: {time.time() - t0:.0f}s")
    with open(os.path.join(S, "INVENTARIO.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
