#!/usr/bin/env python3
"""
actualizar_temporada.py — trae de StatsBomb los partidos NUEVOS de la liga (la temporada en curso):
la lista de partidos, los eventos y las alineaciones, en crudo, como los que entregó el hackathon.

- La competición se deduce de data/raw/statsbomb/matches (la que ya tienes); la temporada, del API
  (por omisión: la más reciente que ya tienes, que se REFRESCA porque su lista de partidos crece cada
  jornada, y las posteriores; nunca temporadas viejas que el hackathon no entregó).
- La lista de partidos de una temporada se reescribe sobre SU MISMO archivo (si ya existía), para que
  ningún match_id quede repetido entre archivos.
- Eventos y alineaciones: solo de partidos con match_status "available" que no estén en disco.
- Toda la liga, no solo un club: las comparaciones contra la liga, el Elo y la proyección necesitan a
  todos los equipos. Con --equipo "América" baja solo los de ese club (más rápido, menos completo).
- Credenciales SOLO de variables de entorno SB_USERNAME / SB_PASSWORD. Un 401/403 detiene todo.
- Reanudable y atómico (.tmp y rename); una respuesta vacía no se guarda.
- Los frames 360 de los partidos nuevos se bajan después con descargar_360.py (ya reanudable).

Uso:
  python actualizar_temporada.py --dry-run                 # qué bajaría, sin bajar nada
  python actualizar_temporada.py                           # toda la liga, temporada en curso
  python actualizar_temporada.py --equipo "América"        # solo ese club
  python actualizar_temporada.py --temporada 317           # una temporada concreta
"""
import argparse, glob, gzip, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HOST = "https://data.statsbombservices.com"
VERSIONES = {"competitions": "v4", "matches": "v6", "events": "v8", "lineups": "v4"}
_local = threading.local()


def _sesion(auth):
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.auth = auth
    return _local.s


def abrir(p):
    return gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")


def filas(d):
    return d if isinstance(d, list) else ([d] if isinstance(d, dict) and "match_id" in d else list(d.values()))


def escribir(ruta, data):
    tmp = ruta + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, ruta)


def versiones(auth):
    """Versión de cada endpoint según el API (con los valores conocidos como respaldo)."""
    v = dict(VERSIONES)
    try:
        r = requests.get(f"{HOST}/api/endpoint-versions", auth=auth, timeout=30)
        if r.status_code in (401, 403):
            sys.exit(f"ABORTA: credenciales rechazadas ({r.status_code}).")
        if r.status_code == 200:
            for k, val in r.json().items():
                for ep in v:
                    if ep in k and "360" not in k and val:
                        v[ep] = f"v{val}"
    except requests.RequestException as e:
        print("aviso: no pude leer endpoint-versions, uso", v, e)
    return v


def get(url, auth, parar):
    """GET con reintentos. Devuelve el JSON, None si no hay datos, o 'parar' ante 401/403."""
    for intento in range(5):
        if parar.is_set():
            return None
        try:
            r = _sesion(auth).get(url, timeout=120)
        except requests.RequestException:
            time.sleep(2 ** intento)
            continue
        if r.status_code in (401, 403):
            parar.set()
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** intento * 2)
            continue
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


def en_disco(raiz):
    """(competición, temporada) → archivo de matches que ya la contiene, y todos los match_id en disco."""
    mapa, ids = {}, set()
    for f in sorted(glob.glob(os.path.join(raiz, "matches", "*.json*"))):
        for m in filas(json.load(abrir(f))):
            clave = ((m.get("competition") or {}).get("competition_id"), (m.get("season") or {}).get("season_id"))
            mapa.setdefault(clave, f)
            ids.add(int(m["match_id"]))
    return mapa, ids


def del_equipo(m, equipo):
    if not equipo:
        return True
    e = equipo.lower()
    return any(e in ((m.get(k) or {}).get(f"{k}_name") or "").lower() for k in ("home_team", "away_team"))


def bajar_partido(mid, v, auth, raiz, parar):
    out = {}
    for ep, carpeta, clave in (("events", "events", "event"), ("lineups", "lineups", "lineup")):
        final = os.path.join(raiz, carpeta, f"{mid}.json.gz")
        if os.path.exists(final):
            out[ep] = "ya_existia"
            continue
        data = get(f"{HOST}/api/{v[ep]}/{ep}/{mid}", auth, parar)
        if not data:
            out[ep] = "vacio_o_error"
            continue
        if ep == "events" and not (isinstance(data, list) and "type" in data[0]):
            out[ep] = "formato_inesperado"
            continue
        escribir(final, data)
        out[ep] = "ok"
    return mid, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default="data/raw/statsbomb")
    ap.add_argument("--competicion", type=int, default=None, help="por omisión, la de tus archivos de matches")
    ap.add_argument("--temporada", type=int, nargs="*", default=None)
    ap.add_argument("--equipo", default=None, help='p. ej. "América": solo sus partidos')
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    user, pw = os.environ.get("SB_USERNAME"), os.environ.get("SB_PASSWORD")
    if not user or not pw:
        sys.exit("ABORTA: exporta SB_USERNAME y SB_PASSWORD (read -rs).")
    auth = (user, pw)
    parar = threading.Event()
    for c in ("matches", "events", "lineups"):
        os.makedirs(os.path.join(a.raiz, c), exist_ok=True)
    mapa, ids_disco = en_disco(a.raiz)
    comps = {c for c, _ in mapa if c is not None}
    comp = a.competicion or (next(iter(comps)) if len(comps) == 1 else None)
    if comp is None:
        sys.exit(f"ABORTA: hay varias competiciones en disco {sorted(comps)}; indica --competicion.")
    v = versiones(auth)
    print(f"competición {comp} · endpoints {v}")

    # temporadas: las pedidas, o las del API que faltan más la más reciente (se refresca)
    if a.temporada:
        temporadas = a.temporada
    else:
        cs = get(f"{HOST}/api/{v['competitions']}/competitions", auth, parar) or []
        if parar.is_set():
            sys.exit("ABORTA: credenciales rechazadas.")
        suyas = sorted((c for c in cs if c.get("competition_id") == comp),
                       key=lambda c: c.get("season_name") or "")
        if not suyas:
            sys.exit(f"ABORTA: el API no lista temporadas de la competición {comp}.")
        # la temporada más reciente que ya tienes (se refresca) y las posteriores; nunca las viejas que el
        # hackathon no entregó
        en_disco_ = [i for i, c in enumerate(suyas) if (comp, c["season_id"]) in mapa]
        desde = en_disco_[-1] if en_disco_ else len(suyas) - 1
        temporadas = [c["season_id"] for c in suyas[desde:]]
        print("temporadas a revisar:", [(c["season_id"], c.get("season_name")) for c in suyas
                                        if c["season_id"] in temporadas])

    nuevos = []
    for sid in temporadas:
        ms = get(f"{HOST}/api/{v['matches']}/competitions/{comp}/seasons/{sid}/matches", auth, parar)
        if parar.is_set():
            sys.exit("ABORTA: credenciales rechazadas.")
        if not ms:
            print(f"  temporada {sid}: sin partidos")
            continue
        destino = mapa.get((comp, sid)) or os.path.join(a.raiz, "matches", f"{comp}_{sid}.json.gz")
        disp = [m for m in ms if m.get("match_status") == "available" and del_equipo(m, a.equipo)]
        faltan = [m for m in disp if int(m["match_id"]) not in ids_disco
                  or not os.path.exists(os.path.join(a.raiz, "events", f"{m['match_id']}.json.gz"))]
        ult = max((m.get("match_date") or "") for m in ms)
        print(f"  temporada {sid}: {len(ms)} partidos en el API ({len(disp)} disponibles"
              f"{' de ' + a.equipo if a.equipo else ''}; último {ult}) · nuevos: {len(faltan)} → {os.path.basename(destino)}")
        if not a.dry_run:
            escribir(destino, ms)        # la lista completa de la temporada, en su mismo archivo
        nuevos += [int(m["match_id"]) for m in faltan]
    if a.dry_run:
        print(f"dry-run: bajaría eventos y alineaciones de {len(nuevos)} partidos: {nuevos[:10]}…")
        return
    cuenta, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        futs = [ex.submit(bajar_partido, m, v, auth, a.raiz, parar) for m in nuevos]
        for i, fu in enumerate(as_completed(futs), 1):
            _, est = fu.result()
            for ep, e in est.items():
                cuenta[f"{ep}:{e}"] = cuenta.get(f"{ep}:{e}", 0) + 1
            if i % 20 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)}  {cuenta}  ({time.time() - t0:.0f}s)", flush=True)
    if parar.is_set():
        sys.exit("ABORTA: credenciales rechazadas a mitad de la descarga.")
    print("\nRESUMEN:", cuenta)
    print("Siguiente: .venv-sb/bin/python scripts/descargar/descargar_360.py   (360 de los partidos nuevos)\n"
          "           python scripts/descargar/extender_eras.py               (técnicos de los partidos nuevos)")


if __name__ == "__main__":
    main()
