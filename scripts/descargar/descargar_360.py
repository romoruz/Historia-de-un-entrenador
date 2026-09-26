#!/usr/bin/env python3
"""
descargar_360.py — baja los freeze frames 360 de StatsBomb, en crudo, un .json.gz por partido.

- Lee los match_id de data/raw/statsbomb/matches/*.json.gz (formato {match_id: partido}
  o lista) y solo pide los que dicen match_status_360 == "available".
- Credenciales SOLO de variables de entorno SB_USERNAME / SB_PASSWORD.
- Reanudable: si el archivo ya existe, se salta.
- Una respuesta vacía o un error NO se guarda (bug #15 del proyecto viejo):
  se registra en frames_fallidos.csv. Un 401/403 detiene todo.
- Escritura atómica (.tmp y luego rename): un corte no deja archivos a medias.

Uso:
  python descargar_360.py --dry-run
  python descargar_360.py --limite 3
  python descargar_360.py --excluir-temporadas 351
"""
import argparse, csv, glob, gzip, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HOST = "https://data.statsbombservices.com"

# Una sesion por hilo: reutiliza la conexion TLS (mas rapido y menos 429).
_local = threading.local()


def _sesion(auth):
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.auth = auth
    return _local.s


def abrir(p):
    return gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")


def partidos_con_360(dir_matches, excluir):
    ids, total = [], 0
    for f in sorted(glob.glob(os.path.join(dir_matches, "*.json*"))):
        d = json.load(abrir(f))
        filas = d if isinstance(d, list) else ([d] if "match_id" in d else list(d.values()))
        for m in filas:
            total += 1
            sid = (m.get("season") or {}).get("season_id")
            if sid in excluir:
                continue
            if m.get("match_status_360") == "available":
                ids.append(int(m["match_id"]))
    return sorted(set(ids)), total


def version_360(auth):
    try:
        r = requests.get(f"{HOST}/api/endpoint-versions", auth=auth, timeout=30)
        if r.status_code == 200:
            v = r.json().get("api_360_freeze_frames")
            if v:
                return f"v{v}"
        elif r.status_code in (401, 403):
            sys.exit(f"ABORTA: credenciales rechazadas ({r.status_code}).")
    except requests.RequestException as e:
        print("aviso: no pude leer endpoint-versions:", e)
    return "v2"


class Parar(Exception):
    pass


def bajar(mid, url_base, auth, destino, parar):
    if parar.is_set():
        return mid, "saltado", 0
    final = os.path.join(destino, f"{mid}.json.gz")
    if os.path.exists(final):
        return mid, "ya_existia", 0
    url = f"{url_base}/{mid}"
    ultimo = "sin_intentos"
    for intento in range(5):
        try:
            r = _sesion(auth).get(url, timeout=120)
        except requests.RequestException as e:
            time.sleep(2 ** intento)
            ultimo = f"red: {e}"
            continue
        if r.status_code in (401, 403):
            parar.set()
            return mid, f"http_{r.status_code}", 0
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** intento * 2)
            ultimo = f"http_{r.status_code}"
            continue
        if r.status_code != 200:
            return mid, f"http_{r.status_code}", 0
        try:
            data = r.json()
        except ValueError:
            return mid, "json_invalido", 0
        if not isinstance(data, list) or not data:
            return mid, "vacio", 0                       # no se cachea un vacío
        if "event_uuid" not in data[0]:
            return mid, "formato_inesperado", 0
        tmp = final + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, final)
        return mid, "ok", len(data)
    return mid, ultimo, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default="data/raw/statsbomb")
    ap.add_argument("--excluir-temporadas", type=int, nargs="*", default=[])
    ap.add_argument("--limite", type=int, default=0, help="solo los primeros N (prueba)")
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    ids, total = partidos_con_360(os.path.join(a.raiz, "matches"), set(a.excluir_temporadas))
    destino = os.path.join(a.raiz, "frames")
    os.makedirs(destino, exist_ok=True)
    ya = {int(f.split(".")[0]) for f in os.listdir(destino) if f.endswith(".json.gz")}
    print(f"partidos en matches: {total} · con 360 disponible: {len(ids)} · ya descargados: {len(ya & set(ids))}")
    if a.limite:
        ids = ids[: a.limite]
    if a.dry_run:
        print("dry-run: primeros ids ->", ids[:10])
        return
    if not ids:
        sys.exit("ABORTA: ningún partido con 360 disponible. Revisa --raiz.")

    user, pw = os.environ.get("SB_USERNAME"), os.environ.get("SB_PASSWORD")
    if not user or not pw:
        sys.exit("ABORTA: exporta SB_USERNAME y SB_PASSWORD (read -rs).")
    auth = (user, pw)
    v = version_360(auth)
    url_base = f"{HOST}/api/{v}/360-frames"
    print(f"endpoint: {url_base}/<match_id>")

    parar = threading.Event()
    cuenta, fallidos, t0 = {}, [], time.time()
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        futs = [ex.submit(bajar, m, url_base, auth, destino, parar) for m in ids]
        for i, fu in enumerate(as_completed(futs), 1):
            mid, estado, n = fu.result()
            cuenta[estado] = cuenta.get(estado, 0) + 1
            if estado not in ("ok", "ya_existia", "saltado"):
                fallidos.append((mid, estado))
            if i % 50 == 0 or i == len(ids):
                print(f"  {i}/{len(ids)}  {cuenta}  ({time.time()-t0:.0f}s)", flush=True)

    with open(os.path.join(a.raiz, "frames_fallidos.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["match_id", "estado"]); w.writerows(fallidos)
    print("\nRESUMEN:", cuenta)
    if parar.is_set():
        sys.exit("ABORTA: credenciales rechazadas a mitad de la descarga.")
    if fallidos:
        print(f"{len(fallidos)} fallidos en frames_fallidos.csv. Vuelve a correr: solo reintenta esos.")
        sys.exit(2)


if __name__ == "__main__":
    main()
