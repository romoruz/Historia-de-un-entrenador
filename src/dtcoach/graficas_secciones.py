"""Figuras de las secciones (ofensiva, defensa, rival, jugadores, balón parado, simulación).

Pensadas para quien no ve fútbol: cada figura dice en su título qué pregunta contesta y
en su pie cómo leerla. Misma paleta que `graficas_historia` (foco = azul, liga = naranja)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle

from .graficas import _cancha, _malla
from .graficas_historia import (
    DIVERGENTE,
    FOCO,
    LIGA,
    SERIES,
    SUPERFICIE,
    TINTA,
    TINTA2,
    _guardar,
)

GRIS = "#c9c8c3"


def _titulo(ax, t: str, pie: str | None = None, ancho: int = 90) -> None:
    """Título arriba y, debajo, en gris, cómo leer la figura (nunca encima de los ejes)."""
    lineas = textwrap.wrap(t, ancho)
    if pie:
        ax.set_title("\n".join(lineas), loc="left", fontsize=10, pad=8 + 11 * len(textwrap.wrap(pie, ancho + 20)))
        ax.text(0, 1.01, "\n".join(textwrap.wrap(pie, ancho + 20)), transform=ax.transAxes, fontsize=7.5,
                color=TINTA2, va="bottom")
    else:
        ax.set_title("\n".join(lineas), loc="left", fontsize=10)


# ======================================================================
# Ofensiva
# ======================================================================
def reparto(res: dict, grupos: dict[str, list[str]], etiquetas: dict[str, str], foco: str, path: Path,
            titulo: str) -> Path:
    """Barras 100 % apiladas foco contra liga para cada grupo de fracciones (cómo entra, quién asiste…)."""
    grupos = {g: [m for m in ms if m in res and np.isfinite(res[m]["foco"])] for g, ms in grupos.items()}
    grupos = {g: ms for g, ms in grupos.items() if ms}
    if not grupos:
        return path
    fig, axs = plt.subplots(len(grupos), 1, figsize=(8.5, 1.55 * len(grupos) + 0.6))
    axs = np.atleast_1d(axs)
    for ax, (g, ms) in zip(axs, grupos.items()):
        for fila, quien in enumerate(("foco", "liga")):
            izq = 0.0
            tot = sum(res[m][quien] for m in ms) or 1.0
            for k, m in enumerate(ms):
                v = res[m][quien] / tot
                ax.barh(fila, v, left=izq, color=SERIES[k % len(SERIES)], edgecolor=SUPERFICIE, height=0.7)
                if v >= 0.06:
                    ax.text(izq + v / 2, fila, f"{100 * v:.0f}%", ha="center", va="center", fontsize=7.5,
                            color="white")
                izq += v
        ax.set_yticks([0, 1], [foco, "liga"])
        ax.set_xlim(0, 1)
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.set_title(g, loc="left", fontsize=9)
        for k, m in enumerate(ms):
            ax.scatter([], [], color=SERIES[k % len(SERIES)], label=etiquetas.get(m, m), marker="s")
        ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=7.5)
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=10)
    return _guardar(fig, path)


def familias_cancha(fams: list[dict], familias: list[str], nx: int, ny: int, foco: str, path: Path) -> Path:
    """Una cancha por familia: dónde pasa el balón foco − liga (color) y el camino típico de cada uno."""
    K = len(fams)
    fig, axs = plt.subplots(1, K, figsize=(5.4 * K, 4.4))
    axs = np.atleast_1d(axs)
    lim = max(float(np.max(np.abs(np.array(f["foco"]["visitas"]) - np.array(f["liga"]["visitas"])))) for f in fams) \
        or 0.01
    for ax, f, nombre in zip(axs, fams, familias):
        D = _malla(np.array(f["foco"]["visitas"]) - np.array(f["liga"]["visitas"]), nx, ny)
        ax.imshow(D, extent=(0, 120, 80, 0), cmap=DIVERGENTE, vmin=-lim, vmax=lim, alpha=0.85)
        _cancha(ax)
        for quien, col, dz in (("liga", LIGA, -2.0), ("foco", FOCO, 2.0)):
            cam = f[quien]["camino"]
            pts = [((z // ny + 0.5) * 120 / nx, (z % ny + 0.5) * 80 / ny + dz) for z in cam]
            pts.append((119.0, 40.0 + dz))                                    # el remate
            for a, b in zip(pts[:-1], pts[1:]):
                ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=col, lw=2.2,
                                             zorder=4))
            ax.scatter(*pts[0], s=60, color=col, zorder=5, edgecolor=SUPERFICIE)
        ax.set_title(f"{nombre}\nflecha = la ruta más frecuente entre las zonas\n(cada jugada real se desvía de ella)",
                     loc="left", fontsize=8)
    fig.suptitle(f"Las tres maneras de atacar, dibujadas · azul = {foco} pasa el balón por ahí más que la liga "
                 f"(rojo, menos); flechas = el camino más probable hasta el remate (azul {foco}, naranja liga)",
                 x=0.01, ha="left", fontsize=10)
    fig.text(0.01, 0.01, "ataca hacia la derecha →", fontsize=8, color=TINTA2)
    return _guardar(fig, path)


# ======================================================================
# Defensa
# ======================================================================
def curva_presion(c: dict, foco: str, path: Path, marca: float = 2.0) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4))
    r = np.array(c["radios"])
    for nombre, col, lab in (("foco", FOCO, foco), ("liga", LIGA, "resto de la liga")):
        if nombre not in c:
            continue
        v = 100 * np.array(c[nombre])
        ax.plot(r, v, color=col, lw=2.4, label=lab)
        ax.fill_between(r, 100 * np.array(c[f"{nombre}_lo"]), 100 * np.array(c[f"{nombre}_hi"]), color=col,
                        alpha=0.15, lw=0)
    if "foco" in c and "liga" in c:
        i = int(np.argmin(np.abs(r - marca)))
        a, b = 100 * c["foco"][i], 100 * c["liga"][i]
        ax.axvline(marca, color=TINTA2, lw=0.8, ls="--")
        ax.annotate(f"a {marca:g} m: {a:.0f} de cada 100 toques\ncontra {b:.0f} en la liga", (marca, a),
                    xytext=(marca + 1.2, a - 12), fontsize=8.5, color=TINTA,
                    arrowprops=dict(arrowstyle="-", color=TINTA2))
    ax.set_xlabel("distancia del jugador más cercano al rival que toca el balón (m)")
    ax.set_ylabel("de cada 100 toques del rival, cuántos\ntienen a alguien así de cerca")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="lower right")
    _titulo(ax, "¿Qué tan encima está del rival? Cada vez que el rival toca el balón, medimos con las cámaras 360 "
                "a qué distancia está el defensor más cercano.",
            "Cuanto más arriba la curva azul respecto de la naranja, más veces el rival juega con alguien encima.")
    return _guardar(fig, path)


def pictograma(p_foco: float, p_liga: float, foco: str, path: Path, r: float = 2.0) -> Path:
    """Dos cuadrículas de 100 puntos: cuántos toques del rival tienen a un defensor a ≤ r m."""
    fig, axs = plt.subplots(1, 2, figsize=(8, 4.2))
    for ax, p, quien, col in ((axs[0], p_foco, foco, FOCO), (axs[1], p_liga, "resto de la liga", LIGA)):
        n = int(round(100 * p))
        k = 0
        for fila in range(10):
            for c_ in range(10):
                ax.scatter(c_, 9 - fila, s=110, color=col if k < n else "#e6e5e0", edgecolor=SUPERFICIE)
                k += 1
        ax.set_xlim(-0.8, 9.8)
        ax.set_ylim(-0.8, 9.8)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"{quien}\n{n} de cada 100", fontsize=10)
    fig.suptitle(f"Cada punto es un toque del rival. Pintado: tenía a un jugador encima (a {r:g} m o menos).",
                 x=0.01, ha="left", fontsize=10)
    return _guardar(fig, path)


def presion_tercios(res: dict, foco: str, path: Path) -> Path:
    ms = [("presion_tercio_alto", "cuando el rival\nsale desde atrás"), ("presion_tercio_medio", "en medio\ncampo"),
          ("presion_tercio_bajo", "cerca de su\npropia área")]
    ms = [(m, e) for m, e in ms if m in res]
    if not ms:
        return path
    fig, ax = plt.subplots(figsize=(7, 3.6))
    x = np.arange(len(ms))
    for d, quien, col, lab in ((-0.2, "foco", FOCO, foco), (0.2, "liga", LIGA, "liga")):
        v = [100 * res[m][quien] for m, _ in ms]
        ax.bar(x + d, v, width=0.38, color=col, label=lab)
        for xi, vi in zip(x + d, v):
            ax.text(xi, vi + 0.5, f"{vi:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x, [e for _, e in ms])
    ax.set_ylabel("toques del rival con alguien encima (%)")
    ax.legend(frameon=False)
    _titulo(ax, "¿Dónde aprieta? Presión encima (≤ 2 m) según la zona donde el rival tiene el balón")
    return _guardar(fig, path)


def esquema_bloque(path: Path) -> Path:
    """Dibujo explicativo: qué es el bloque y cómo se miden su altura, anchura y profundidad."""
    fig, ax = plt.subplots(figsize=(8, 5.2))
    _cancha(ax)
    d = np.array([[30, 18], [28, 32], [29, 48], [31, 62], [45, 25], [46, 55], [58, 40]], float)
    from scipy.spatial import ConvexHull
    h = ConvexHull(d)
    ax.add_patch(Polygon(d[h.vertices], closed=True, color=FOCO, alpha=0.18, lw=0))
    ax.add_patch(Polygon(d[h.vertices], closed=True, fill=False, ec=FOCO, lw=1.8))
    ax.scatter(d[:, 0], d[:, 1], s=120, color=FOCO, edgecolor=SUPERFICIE, zorder=4)
    ax.scatter([4], [40], s=120, color="#1baf7a", edgecolor=SUPERFICIE, zorder=4)
    ax.text(8, 44.5, "portero", ha="left", fontsize=8)
    ax.scatter([95], [40], s=90, color=LIGA, zorder=4)
    ax.text(95, 35.5, "el rival con\nel balón", ha="center", fontsize=8)
    ax.annotate("", (76, 18), (76, 62), arrowprops={"arrowstyle": "<->", "color": TINTA})
    ax.text(77.5, 40, "ANCHURA", rotation=90, va="center", fontsize=9)
    ax.annotate("", (28, 70), (58, 70), arrowprops=dict(arrowstyle="<->", color=TINTA))
    ax.text(43, 74, "PROFUNDIDAD", ha="center", fontsize=9)
    ax.annotate("", (0, 7), (38, 7), arrowprops=dict(arrowstyle="<->", color=TINTA2))
    ax.text(19, 5, "ALTURA (distancia media a su arco)", ha="center", fontsize=8.5, color=TINTA2)
    ax.text(40, 40, "ÁREA", ha="center", va="center", fontsize=10, color=FOCO, weight="bold")
    ax.set_title("Qué es el «bloque»: en cada foto de las cámaras 360, rodeamos con una liga elástica a los "
                 "defensores que se ven (sin el portero)\ny medimos qué tan ancho, qué tan profundo y qué tan lejos "
                 "de su arco queda. Un bloque estrecho cierra el centro.", loc="left", fontsize=9)
    return _guardar(fig, path)


def bloque_tipico(bt: dict, foco: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5.2))
    _cancha(ax)
    for quien, col, lab in (("liga", LIGA, "liga"), ("foco", FOCO, foco)):
        b = bt.get(quien)
        if not b or "altura" not in b:
            continue
        x0 = b["altura"] - b["profundidad"] / 2
        y0 = 40 - b["anchura"] / 2
        ax.add_patch(Rectangle((x0, y0), b["profundidad"], b["anchura"], fill=quien == "foco", color=col,
                               alpha=0.25 if quien == "foco" else 1, lw=2, ls="-" if quien == "foco" else "--",
                               ec=col))
        ax.text(x0 + b["profundidad"] + 1, y0 + (2 if quien == "foco" else b["anchura"] - 2),
                f"{lab}: {b['anchura']:.1f} m de ancho, {b['profundidad']:.1f} m de fondo,\n"
                f"a {b['altura']:.1f} m de su arco", fontsize=8, color=col, va="center")
    ax.set_title(f"El bloque típico sin balón: {foco} (relleno) contra la liga (línea)\n"
                 "solo fotos con la cámara abierta (se ve casi todo el ancho de la cancha)", loc="left", fontsize=9)
    ax.annotate("su arco", (1, 40), (6, 46), fontsize=8, color=TINTA2)
    return _guardar(fig, path)


# ======================================================================
# Rival
# ======================================================================
def rival_estratos(pts: dict, res: dict, metricas: list[tuple[str, str]], foco: str, path: Path) -> Path:
    """Puntos y algunas métricas del foco contra la liga en cada estrato de rival."""
    est = [e for e in ("debil", "medio", "fuerte") if e in pts]
    nombres = {"debil": "débiles", "medio": "medios", "fuerte": "fuertes"}
    paneles = [("pts", "puntos por partido")] + metricas
    fig, axs = plt.subplots(1, len(paneles), figsize=(3.2 * len(paneles), 3.6))
    axs = np.atleast_1d(axs)
    for ax, (m, tit) in zip(axs, paneles):
        x = np.arange(len(est))
        if m == "pts":
            vf = [pts[e]["pts"]["foco"] for e in est]
            vl = [pts[e]["pts"]["liga"] for e in est]
        else:
            vf = [res.get(e, {}).get(m, {}).get("foco", np.nan) for e in est]
            vl = [res.get(e, {}).get(m, {}).get("liga", np.nan) for e in est]
        ax.plot(x, vl, "-o", color=LIGA, label="liga")
        ax.plot(x, vf, "-o", color=FOCO, label=foco, lw=2.4)
        ax.set_xticks(x, [nombres[e] for e in est], fontsize=8)
        ax.set_title("\n".join(textwrap.wrap(tit, 26)), fontsize=9, loc="left")
    axs[0].legend(frameon=False, fontsize=8)
    fig.suptitle("¿Juega distinto según el rival? Rivales partidos por su Elo antes del partido: débiles (25 % más "
                 "bajo), medios y fuertes (25 % más alto)", x=0.01, y=1.04, ha="left", fontsize=10)
    fig.tight_layout()
    return _guardar(fig, path)


# ======================================================================
# Jugadores
# ======================================================================
def efecto_cambios(did: dict, nombres: dict, foco: str, path: Path) -> Path:
    t = did.get("todos")
    if not t:
        return path
    ms = [m for m in did["medidas"] if m in t]
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(ms) + 1.4))
    for i, m in enumerate(ms):
        v = t[m]
        ax.plot([v["lo"], v["hi"]], [i, i], color=FOCO, lw=2)
        ax.scatter(v["efecto"], i, color=FOCO, s=40, zorder=3)
    ax.axvline(0, color=TINTA2, lw=0.8, ls="--")
    ax.set_yticks(range(len(ms)), [nombres.get(m, m) for m in ms])
    ax.invert_yaxis()
    ax.set_xlabel("cambio en los 10 min siguientes, descontando lo que pasa en la liga en el mismo minuto y marcador")
    _titulo(ax, f"¿Qué cambia cuando {foco} hace un cambio? ({t['n']} cambios; punto = efecto, raya = IC 95 %)",
            "Si la raya cruza la línea punteada, no se distingue de lo que hacen los cambios de la liga.")
    return _guardar(fig, path)


# ======================================================================
# Balón parado
# ======================================================================
TEC = {"Inswinging": "cerrado", "Outswinging": "abierto", "Straight": "recto", "sin dato": "sin dato",
       "Through Ball": "filtrado"}


def rutinas_corner(rut: dict, foco: str, path: Path, zonas: dict) -> Path:
    tab = rut.get("rutinas") or []
    if not tab:
        return path
    tab = tab[:14]
    fig, ax = plt.subplots(figsize=(8.5, 0.42 * len(tab) + 1.6))
    for i, r in enumerate(tab):
        ax.plot([r["lo"], r["hi"]], [i, i], color=GRIS, lw=4, solid_capstyle="round")
        ax.scatter(r["xg_por_corner"], i, color=LIGA, s=40, zorder=3)
        ax.text(max(x["hi"] for x in tab) * 1.02, i, f"{foco}: {100 * r['uso_foco']:.0f} % de sus corners · liga "
                f"{100 * r['uso_liga']:.0f} %", va="center", fontsize=7.5, color=FOCO if r["uso_foco"] > r["uso_liga"]
                else TINTA2)
    ax.set_yticks(range(len(tab)), [f"{TEC.get(r['tecnica'], r['tecnica'])} → {zonas.get(r['zona'], r['zona'])}"
                                    for r in tab])
    ax.invert_yaxis()
    ax.set_xlabel("xG por corner en toda la liga (punto) con su IC 95 % (barra)")
    t = "¿Qué corners funcionan en la Liga MX? Cada fila es una rutina: cómo se patea (cerrado/abierto) y a dónde va."
    if "receta_arsenal" in rut:
        a = rut["receta_arsenal"]
        t += (f" La «receta Arsenal» (cerrado al área chica o primer palo con atacantes encima del portero): "
              f"{a['xg_receta']:.3f} contra {a['xg_resto']:.3f} xG por corner del resto; {foco} la usa en "
              f"{100 * a['uso_foco']:.0f} % de sus corners (liga {100 * a['uso_liga']:.0f} %).")
    _titulo(ax, t, ancho=110)
    return _guardar(fig, path)


def _arco(ax):
    kw = dict(color="#444", lw=1)
    ax.plot([120, 120], [30, 50], **kw)
    ax.plot([102, 102, 120], [18, 62, 62], **kw)
    ax.plot([102, 120], [18, 18], **kw)
    ax.plot([114, 114], [30, 50], **kw)
    ax.plot([114, 120], [30, 30], **kw)
    ax.plot([114, 120], [50, 50], **kw)
    ax.plot([120, 121.5, 121.5, 120], [36, 36, 44, 44], color=TINTA, lw=2)
    ax.set_xlim(95, 123)
    ax.set_ylim(66, 14)
    ax.set_aspect("equal")
    ax.axis("off")


def corner_defensivo(perfil: dict, foco: str, path: Path) -> Path:
    if not perfil:
        return path
    fig, axs = plt.subplots(1, 2, figsize=(9, 5))
    for ax, quien, col in ((axs[0], "foco", FOCO), (axs[1], "liga", LIGA)):
        p = perfil.get(quien)
        _arco(ax)
        if not p:
            continue
        ax.text(117, 40, f"{p['de_chica']:.1f}", ha="center", va="center", fontsize=13, color=col, weight="bold")
        ax.text(117, 53.5, "en el área\nchica", ha="center", va="center", fontsize=8, color=col)
        ax.text(107, 40, f"{p['de_area'] - p['de_chica']:.1f}", ha="center", va="center", fontsize=13, color=col,
                weight="bold")
        ax.text(107, 46, "en el resto\ndel área", ha="center", va="center", fontsize=8, color=col)
        ax.text(121.8, 33, f"1er palo\ncubierto\n{100 * p['palo_cercano']:.0f} %", ha="left", fontsize=7.5,
                color=TINTA2, va="center")
        ax.text(121.8, 47, f"2º palo\ncubierto\n{100 * p['palo_lejano']:.0f} %", ha="left", fontsize=7.5,
                color=TINTA2, va="center")
        tot = p["al_hombre"] + p["zonales"]
        ax.set_xlim(95, 127)
        t = (f"{foco if quien == 'foco' else 'liga'}: {p['de_area']:.1f} defensores en el área contra "
             f"{p['at_area']:.1f} atacantes; {100 * p['al_hombre'] / max(tot, 1e-9):.0f} % marcando al hombre "
             f"(a ≤ 2 m de su atacante) · {p['corners']} corners")
        ax.set_title("\n".join(textwrap.wrap(t, 48)), fontsize=8.5, loc="left")
    fig.suptitle("Cómo se para en los corners en contra (promedio en el momento del saque, cámaras 360)", x=0.01,
                 y=1.06, ha="left", fontsize=10)
    return _guardar(fig, path)


def linea_tiros_libres(f: np.ndarray, lg: np.ndarray, foco: str, path: Path) -> Path:
    if len(f) == 0 or len(lg) == 0:
        return path
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [1.3, 1]})
    b = np.arange(0, 36, 1.5)
    axs[0].hist(lg, bins=b, density=True, color=LIGA, alpha=0.55, label="liga")
    axs[0].hist(f, bins=b, density=True, histtype="step", color=FOCO, lw=2.4, label=foco)
    axs[0].axvline(np.median(f), color=FOCO, ls="--")
    axs[0].axvline(np.median(lg), color=LIGA, ls="--")
    axs[0].set_xlabel("metros desde su arco hasta la línea del fuera de lugar")
    axs[0].legend(frameon=False)
    _titulo(axs[0], "Tiros libres en contra: ¿qué tan adelantada pone la línea?",
            "Línea = el penúltimo defensor (portero incluido) sin contar a los que cuidan la línea de gol, en el "
            "momento del cobro.")
    ax = axs[1]
    _arco(ax)
    ax.set_xlim(80, 123)
    for v, col in ((np.median(f), FOCO), (np.median(lg), LIGA)):
        ax.plot([120 - v, 120 - v], [18, 62], color=col, lw=3)
    ax.set_title(f"línea mediana: {foco} a {np.median(f):.1f} m, liga a {np.median(lg):.1f} m", fontsize=8.5,
                 loc="left")
    return _guardar(fig, path)


FOCO_DEF = "#0d366b"                       # el foco defendiendo (mismo tono que el foco, más oscuro)
TERMINOS = {"prev": ("prevención", "#4a3aa7"), "lej": ("alejamiento", "#1baf7a"),
            "sup": ("supresión", "#eda100"), "port": ("portero y definición", "#e87ba4")}
GRUPO_COLOR = {"foco_ataque": FOCO, "foco_defensa": FOCO_DEF, "liga": LIGA}


def _grupo_nombre(g: str, foco: str) -> str:
    return {"foco_ataque": f"{foco} a favor", "foco_defensa": f"{foco} en contra", "liga": "liga"}[g]


def _chip(ax, x, y, color, texto, size=8, transform=None):
    """Cuadrito de color + texto en tinta (la identidad la lleva la marca, no el texto)."""
    tr = transform or ax.transData
    ax.text(x, y, "■", color=color, fontsize=size + 1, va="center", ha="left", transform=tr)
    ax.text(x, y, "    " + texto, color=TINTA, fontsize=size, va="center", ha="left", transform=tr)


def arbol_xdefensa(cad: dict, foco: str, familia: str, nombre: str, path: Path) -> Path:
    """El árbol de probabilidad del xDefense: saque → remate → gol, con los números de la liga y del foco,
    y a la derecha la demostración (probabilidad condicional y total, en cadena)."""
    c = cad.get(familia, {})
    if "liga" not in c:
        return path
    fig = plt.figure(figsize=(13, 5.6))
    ax = fig.add_axes([0.0, 0.0, 0.55, 0.88])
    tx = fig.add_axes([0.56, 0.0, 0.44, 0.88])
    for a in (ax, tx):
        a.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    nodos = {"C": (0.9, 5.0), "S": (5.6, 7.4), "noS": (5.6, 2.6), "G": (9.0, 9.2), "noG": (9.0, 5.8)}
    etiq = {"C": f"saque\n({nombre})", "S": "hay remate", "noS": "sin remate\n(la defensa ganó)",
            "G": "gol", "noG": "sin gol"}
    for a, b in (("C", "S"), ("C", "noS"), ("S", "G"), ("S", "noG")):
        ax.annotate("", xy=nodos[b], xytext=nodos[a],
                    arrowprops=dict(arrowstyle="-|>", color=TINTA2, lw=1.2, shrinkA=28, shrinkB=28))
    for k, (x, y) in nodos.items():
        ax.text(x, y, etiq[k], ha="center", va="center", fontsize=9, color=TINTA,
                bbox=dict(boxstyle="round,pad=0.45", fc=SUPERFICIE, ec=TINTA2, lw=0.8))
    grupos = [g for g in ("liga", "foco_defensa", "foco_ataque") if g in c]

    def bloque(x, y, clave, fmt):
        for i, g in enumerate(grupos):
            _chip(ax, x, y - 0.55 * i, GRUPO_COLOR[g], f"{_grupo_nombre(g, foco)}: {fmt(c[g][clave])}", size=7.5)
    bloque(0.3, 8.9, "p_obs", lambda v: f"{100 * v:.1f} %")
    ax.text(0.3, 9.55, "P(remate | saque)  → capa 1", fontsize=8.5, color=TINTA, weight="bold")
    bloque(5.9, 4.9, "v_obs", lambda v: f"{v:.3f}")
    ax.text(5.9, 5.55, "E[goles | remate]  → capa 2", fontsize=8.5, color=TINTA, weight="bold")
    bloque(0.3, 1.1, "g_obs", lambda v: f"{100 * v:.2f} goles por 100")
    ax.text(0.3, 1.75, "P(gol | saque) = producto de las dos", fontsize=8.5, color=TINTA, weight="bold")
    ax.set_title(f"xDefense (métrica propia del equipo): cómo se descompone un gol de {nombre}",
                 loc="left", fontsize=11, x=0.02)
    lineas = [
        (r"$\mathbf{1.\ Condicional}$  (no hay gol sin remate: $G\subseteq S$)", 9.6),
        (r"$P(G\mid C)=P(G\cap S\mid C)=P(S\mid C)\;P(G\mid S,C)$", 8.95),
        (r"$\mathbf{2.\ Total}$  (se parte en «hubo remate» / «no hubo»)", 8.1),
        (r"$P(G\mid C)=P(G\mid S,C)\,P(S\mid C)+P(G\mid \bar S,C)\,P(\bar S\mid C)$,  con $P(G\mid \bar S,C)=0$", 7.45),
        (r"$\mathbf{3.\ Recursión}$  (el rechace: 2.º, 3.er remate en la jugada)", 6.6),
        (r"$V_k=P(S_k\mid \ldots)\,[\,q_k+(1-q_k)\,V_{k+1}\,]$,   $P(G\mid C)=V_1$", 5.95),
        (r"$\mathbf{4.\ Lo\ que\ evita\ la\ defensa}$  (sumar y restar: exacto)", 5.1),
        (r"$\hat p\,\kappa-g\;=\;(\hat p-s)\,\kappa\;+\;s\,(\kappa-B)\;+\;s\,(B-F)\;+\;s\,(F-g)$", 4.45),
        (r"                  prevención      alejamiento    supresión     portero", 3.9),
    ]
    tx.set_xlim(0, 10)
    tx.set_ylim(0, 10)
    for t, y in lineas:
        tx.text(0.1, y, t, fontsize=9.5 if "$" in t else 7.5, color=TINTA if "$" in t else TINTA2, va="center")
    tx.text(0.1, 1.9, "p̂ = remate esperado (capa 1) · s = hubo remate · κ = lo que vale un saque con remate en\n"
                      "la liga · B, F = xG de sus remates sin y con la defensa (capa 2) · g = goles.\n"
                      "Positivo = gol que la defensa evitó; al atacar, el signo se invierte (xO).",
            fontsize=7.5, color=TINTA2, va="center")
    return _guardar(fig, path)


def goal_open_esquema(path: Path) -> Path:
    """Cómo se mide la capa 2: la parte del arco que ve el que remata, descontando la sombra de cada defensor."""
    from .xdefensa import goal_open
    sx, sy = 106.0, 33.0
    de = np.array([[111.0, 36.5], [113.5, 40.5], [110.0, 30.0]])
    gk = (118.8, 39.0)
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    ax.plot([120, 120], [36, 44], color=TINTA, lw=4, solid_capstyle="butt")
    ax.plot([102, 120, 120, 102, 102], [18, 18, 62, 62, 18], color=TINTA2, lw=0.8)
    ax.plot([114, 120, 120, 114, 114], [30, 30, 50, 50, 30], color=TINTA2, lw=0.8)
    ax.add_patch(Polygon([(sx, sy), (120, 36), (120, 44)], closed=True, color=FOCO, alpha=0.12, lw=0))
    for dx, dy in de:
        d = np.hypot(dx - sx, dy - sy)
        fi, al = np.arctan2(dy - sy, dx - sx), np.arcsin(0.5 / d)
        pts = [(sx, sy)] + [(120.0, sy + (120.0 - sx) * np.tan(fi + a)) for a in (-al, al)]
        ax.add_patch(Polygon(pts, closed=True, color=TINTA2, alpha=0.28, lw=0))
        ax.add_patch(plt.Circle((dx, dy), 0.5, color=LIGA, zorder=4))
    ax.add_patch(plt.Circle(gk, 0.5, color=TINTA, zorder=4))
    ax.scatter([sx], [sy], s=80, color=FOCO, zorder=5)
    go = goal_open(sx, sy, de)
    ax.text(sx - 0.5, sy - 1.6, "remata", ha="right", fontsize=8, color=TINTA)
    ax.text(gk[0] + 0.3, gk[1] - 1.1, "portero", ha="right", fontsize=8, color=TINTA)
    ax.text(107.5, 27.2, "defensores (disco de 0.5 m)", fontsize=7.5, color=TINTA2)
    ax.text(0.03, 0.04, f"arco que ve el que remata (goal_open): {100 * go:.0f} %\n"
                        "= 1 − (sombras de los defensores, sin contar dos veces\n   la parte donde se enciman) / (ángulo del arco)",
            fontsize=8, color=TINTA, transform=ax.transAxes,
            bbox=dict(boxstyle="round,pad=0.4", fc=SUPERFICIE, ec=GRIS, lw=0.8))
    ax.set_xlim(100, 122)
    ax.set_ylim(52, 24)
    ax.set_aspect("equal")
    ax.set_axis_off()
    _titulo(ax, "Capa 2 del xDefense: cuánto arco le tapa la defensa al que remata",
            "Azul claro = el ángulo del arco desde el remate; gris = la sombra de cada defensor. "
            "Cuanto menos arco libre, menos vale el remate (xG_full < xG_base).")
    return _guardar(fig, path)


def descomposicion(cad: dict, foco: str, path: Path, familias: dict[str, str]) -> Path:
    """Goles por 100 saques que el foco evita (en contra) o genera de más (a favor), partidos en los cuatro
    términos exactos. Barras apiladas divergentes; el rombo es el total con su IC 95 %."""
    filas = [(f, g) for f in familias for g in ("foco_defensa", "foco_ataque") if g in cad.get(f, {})]
    if not filas:
        return path
    fig, ax = plt.subplots(figsize=(9.5, 0.62 * len(filas) + 1.8))
    ys = np.arange(len(filas))[::-1]
    for y, (f, g) in zip(ys, filas):
        r = cad[f][g]
        pos = neg = 0.0
        for t, (_, col) in TERMINOS.items():
            v = r[t]["valor"]
            izq = pos if v >= 0 else neg + v
            ax.barh(y, abs(v), left=izq, height=0.56, color=col, edgecolor=SUPERFICIE, linewidth=2)
            if v >= 0:
                pos += v
            else:
                neg += v
        tot = r["total"]
        ax.plot([tot["lo"], tot["hi"]], [y, y], color=TINTA, lw=1.2, zorder=5)
        ax.scatter([tot["valor"]], [y], marker="D", s=38, color=TINTA, zorder=6, edgecolor=SUPERFICIE)
        ax.text(max(pos, tot["hi"]) + 0.08, y, f"total {tot['valor']:+.2f} [{tot['lo']:+.2f}, {tot['hi']:+.2f}]",
                va="center", fontsize=7.5, color=TINTA)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{familias[f]} · {'en contra (xD)' if g == 'foco_defensa' else 'a favor (xO)'}"
                        for f, g in filas], fontsize=8.5)
    ax.axvline(0, color=TINTA2, lw=0.8)
    ax.set_xlabel("goles por cada 100 saques respecto de lo esperado (+ = bueno para él)")
    for t, (nom, col) in TERMINOS.items():
        ax.barh([np.nan], [0], color=col, label=nom)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.1 - 0.5 / len(filas)))
    xl = ax.get_xlim()
    ax.set_xlim(xl[0], xl[1] + 0.35 * (xl[1] - xl[0]))
    _titulo(ax, f"¿De dónde salen los goles que {foco} evita y genera a balón parado?",
            "Cada barra suma los cuatro términos de la identidad exacta (a la derecha de 0, a su favor). "
            "Rombo y raya = el total con su IC 95 % por partidos.", ancho=80)
    return _guardar(fig, path)


def xdefensa_etapas(E, foco: str, path: Path, titulo: str, etiqueta: str) -> Path:
    """Todos los técnicos-club en filas (el mejor arriba): punto hueco = su valor crudo, punto lleno = el
    valor tras descontar el ruido (contraído), y la raya une los dos. El foco va en azul y en negritas."""
    if E is None or E.height == 0:
        return path
    E = E.sort("contraido", descending=True)
    n = E.height
    fig, ax = plt.subplots(figsize=(8.5, 0.2 * n + 1.9))
    y = np.arange(n)[::-1]
    th, c = E["theta"].to_numpy(), E["contraido"].to_numpy()
    es = (E["coach"] == foco).to_numpy()
    mu, tau2 = float(E["mu"][0]), float(E["tau2"][0])
    for k in range(n):
        col = FOCO if es[k] else GRIS
        ax.plot([th[k], c[k]], [y[k], y[k]], color=col, lw=1.6 if es[k] else 1.0, zorder=2)
        ax.scatter([th[k]], [y[k]], s=26 if es[k] else 14, facecolor=SUPERFICIE, edgecolor=col, lw=1.2, zorder=3)
        ax.scatter([c[k]], [y[k]], s=46 if es[k] else 18, color=col if es[k] else TINTA2, zorder=4)
    ax.axvline(mu, color=TINTA2, lw=0.8, ls="--")
    ax.set_yticks(y)
    etq = [f"{a} · {b}" for a, b in zip(E["coach"].to_list(), E["team"].to_list())]
    ax.set_yticklabels(etq, fontsize=6.5)
    for t, e in zip(ax.get_yticklabels(), es):
        if e:
            t.set_color(FOCO)
            t.set_fontweight("bold")
            t.set_fontsize(8)
    ax.set_ylim(-0.8, n - 0.2)
    ax.set_xlabel(etiqueta)
    puestos = [k + 1 for k in range(n) if es[k]]
    que = (f"{foco}: puesto {', '.join(map(str, puestos))} de {n} (1 = el mejor)" if puestos and tau2 > 0
           else f"{foco}: sin puesto (τ² = 0)" if puestos else "")
    ruido = ("τ² ≈ 0: no hay diferencias reales entre equipos; todos se contraen a la media (línea)."
             if tau2 < 1e-5 else f"Variación real entre equipos τ² = {tau2:.1e}.")
    _titulo(ax, f"{titulo} · {que}",
            f"Hueco = crudo; lleno = contraído (descontado el ruido de tener pocos saques, empírico-bayes). "
            f"Más a la derecha = mejor defensa. {ruido}", ancho=85)
    return _guardar(fig, path)


def mapa_xdefensa(Ep, Es, foco: str, path: Path, xlab: str, ylab: str) -> Path:
    """Cada técnico-club con sus dos capas (contraídas): arriba a la derecha niega el remate Y lo empeora."""
    if Ep is None or Es is None or Ep.height == 0 or Es.height == 0:
        return path
    import polars as pl
    D = Ep.select("coach", "team", pl.col("contraido").alias("x")).join(
        Es.select("coach", "team", pl.col("contraido").alias("y")), on=["coach", "team"])
    if D.height == 0:
        return path
    fig, ax = plt.subplots(figsize=(7.5, 5.6))
    es = (D["coach"] == foco).to_numpy()
    x, y = D["x"].to_numpy(), D["y"].to_numpy()
    ax.scatter(x[~es], y[~es], s=22, color=GRIS, edgecolor=SUPERFICIE, lw=1, zorder=3)
    ax.scatter(x[es], y[es], s=80, color=FOCO, edgecolor=SUPERFICIE, lw=2, zorder=4)
    for xi, yi, t in zip(x[es], y[es], D.filter(pl.Series(es))["team"].to_list()):
        ax.annotate(f"{foco} · {t}", (xi, yi), xytext=(8, 6), textcoords="offset points", fontsize=8,
                    color=TINTA, weight="bold")
    mx, my = float(Ep["mu"][0]), float(Es["mu"][0])
    ax.axvline(mx, color=TINTA2, lw=0.8, ls="--")
    ax.axhline(my, color=TINTA2, lw=0.8, ls="--")
    for (hx, hy, ha, va, t) in ((0.98, 0.97, "right", "top", "niega el remate\ny lo empeora"),
                                (0.02, 0.97, "left", "top", "concede remates,\npero los empeora"),
                                (0.98, 0.03, "right", "bottom", "niega el remate,\npero los que da salen limpios"),
                                (0.02, 0.03, "left", "bottom", "concede remates\ny salen limpios")):
        ax.text(hx, hy, t, transform=ax.transAxes, ha=ha, va=va, fontsize=7.5, color=TINTA2)
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    _titulo(ax, "Las dos capas del xDefense en todos los técnicos de la liga",
            "Cada punto es un técnico en un club (valores contraídos). Las líneas punteadas son la media de la liga. "
            "Si los puntos se aplastan en una línea horizontal, esa capa no distingue equipos.")
    return _guardar(fig, path)


def dispersion_etapas(D, foco: str, path: Path, xlab: str, ylab: str, titulo: str, pie: str) -> Path:
    """Técnicos-club: una medida contra otra, con la recta de mínimos cuadrados y r de Pearson."""
    if D is None or D.height < 5:
        return path
    import polars as pl
    D = D.filter(pl.col("x").is_finite() & pl.col("y").is_finite())
    x, y = D["x"].to_numpy(), D["y"].to_numpy()
    es = (D["coach"] == foco).to_numpy()
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    ax.scatter(x[~es], y[~es], s=22, color=GRIS, edgecolor=SUPERFICIE, lw=1, zorder=3, label="otros técnicos-club")
    ax.scatter(x[es], y[es], s=80, color=FOCO, edgecolor=SUPERFICIE, lw=2, zorder=4, label=foco)
    for xi, yi, t in zip(x[es], y[es], D.filter(pl.Series(es))["team"].to_list()):
        ax.annotate(t, (xi, yi), xytext=(8, 6), textcoords="offset points", fontsize=8, color=TINTA, weight="bold")
    if len(x) >= 5 and np.std(x) > 0:
        b1, b0 = np.polyfit(x, y, 1)
        xx = np.linspace(x.min(), x.max(), 20)
        ax.plot(xx, b0 + b1 * xx, color=TINTA2, lw=1, ls="--")
        r = np.corrcoef(x, y)[0, 1]
        ax.text(0.02, 0.97, f"r = {r:+.2f} ({len(x)} técnicos-club)", transform=ax.transAxes, fontsize=8,
                color=TINTA2, va="top")
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _titulo(ax, titulo, pie)
    return _guardar(fig, path)


def _barras_grupos(ax, vals: dict, foco: str, fmt="{:.2f}", escala=1.0):
    """Barras con IC para los tres grupos (foco a favor, foco en contra, liga) con etiqueta directa."""
    gs = [g for g in ("foco_ataque", "foco_defensa", "liga") if g in vals and vals[g] is not None]
    for k, g in enumerate(gs):
        v = vals[g]
        val, lo, hi = (v["valor"], v["lo"], v["hi"]) if isinstance(v, dict) else (v, np.nan, np.nan)
        ax.bar(k, escala * val, width=0.62, color=GRUPO_COLOR[g], edgecolor=SUPERFICIE, lw=2)
        if np.isfinite(lo):
            ax.plot([k, k], [escala * lo, escala * hi], color=TINTA, lw=1)
        top = escala * (hi if np.isfinite(hi) else val)
        ax.text(k, top, " " + fmt.format(escala * val), ha="center", va="bottom", fontsize=7.5, color=TINTA)
    ax.set_xticks(range(len(gs)))
    ax.set_xticklabels([_grupo_nombre(g, foco).replace(f"{foco} ", "Almada\n" if foco.endswith("Almada") else
                                                          f"{foco}\n") for g in gs], fontsize=7.5)
    ax.margins(y=0.18)


def tiros_libres(res: dict, foco: str, path: Path) -> Path:
    """Tiros libres: cuántos peligrosos, qué rinde el directo y qué barrera pone (a favor, en contra, liga)."""
    if not res or "liga" not in res:
        return path
    paneles = [("peligrosos por partido\n(a ≤ 30 m del arco)", {g: r["peligrosos_por_partido"] for g, r in res.items()},
                "{:.2f}", 1.0),
               ("xG por tiro libre directo", {g: r["directo"]["xg"] for g, r in res.items()}, "{:.3f}", 1.0),
               ("goles por cada 100\ntiros libres directos", {g: r["directo"]["gol"] for g, r in res.items()},
                "{:.1f}", 100.0)]
    if "goal_open" in res["liga"]["directo"]:
        paneles += [("% del arco que deja libre\nla barrera + el portero",
                     {g: r["directo"].get("goal_open") for g, r in res.items()}, "{:.0f}", 100.0),
                    ("jugadores en la barrera", {g: r["directo"].get("barrera") for g, r in res.items()}, "{:.1f}",
                     1.0)]
    fig, axs = plt.subplots(1, len(paneles), figsize=(3.0 * len(paneles), 3.6))
    for ax, (t, v, f, e) in zip(np.atleast_1d(axs), paneles):
        _barras_grupos(ax, v, foco, f, e)
        ax.set_title(t, fontsize=8.5, loc="left")
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    fig.suptitle(f"Tiros libres: {foco} a favor (azul), en contra (azul oscuro) y la liga (naranja) · raya = IC 95 %",
                 x=0.01, y=1.1, ha="left", fontsize=10)
    fig.text(0.01, -0.04, "En contra, la barrera y el arco libre son de SU defensa (los tiros libres que le cobran).",
             fontsize=7.5, color=TINTA2)
    return _guardar(fig, path)


def laterales(res: dict, foco: str, path: Path, tramo: str = "cuarto") -> Path:
    """Laterales en el último cuarto: el embudo (al área → primer toque → remate → segunda jugada → gol) y
    cuántos intervienen hasta el remate."""
    r = res.get(tramo, {})
    if "liga" not in r:
        return path
    pasos = [("al_area", "caen en el área"), ("primer_contacto", "primer toque propio"),
             ("remate", "terminan en remate"), ("segunda", "remate con ≥ 2 que intervienen"), ("gol", "gol")]
    gs = [g for g in ("foco_ataque", "foco_defensa", "liga") if g in r]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 4.3), gridspec_kw={"width_ratios": [2.2, 1]})
    h = 0.8 / len(gs)
    for k, (clave, nom) in enumerate(pasos):
        for i, g in enumerate(gs):
            v = r[g][clave]
            yy = k + (i - (len(gs) - 1) / 2) * h
            a1.barh(yy, 100 * v["valor"], height=h, color=GRUPO_COLOR[g], edgecolor=SUPERFICIE, lw=1.5,
                    label=_grupo_nombre(g, foco) if k == 0 else None)
            if np.isfinite(v["lo"]):
                a1.plot([100 * v["lo"], 100 * v["hi"]], [yy, yy], color=TINTA, lw=0.9)
            a1.text(100 * max(v["valor"], v["hi"] if np.isfinite(v["hi"]) else 0) + 0.8, yy,
                    f"{100 * v['valor']:.1f}", va="center", fontsize=7, color=TINTA)
    a1.set_yticks(range(len(pasos)))
    a1.set_yticklabels([p[1] for p in pasos], fontsize=8.5)
    a1.invert_yaxis()
    a1.set_xlabel("de cada 100 laterales")
    a1.legend(frameon=False, fontsize=8, loc="lower right")
    x0 = res.get("x_min", 90) if tramo == "cuarto" else res.get("x_octavo", 105)
    _titulo(a1, f"Laterales desde el último {'cuarto' if tramo == 'cuarto' else 'octavo'} de la cancha "
                f"(x ≥ {x0:.0f} m): de cada 100, cuántos llegan a cada paso",
            "Raya = IC 95 % por partidos. \"Primer toque propio\" se cuenta sobre los que alguien toca en ≤ 5 s.", ancho=80)
    cats, cols = ["1", "2", "3+"], ["#86b6ef", "#2a78d6", "#0d366b"]
    for i, g in enumerate(gs):
        d = r[g]["intervienen"]
        tot = sum(d.values()) or 1
        izq = 0.0
        for c, col in zip(cats, cols):
            v = 100 * d[c] / tot
            a2.barh(i, v, left=izq, height=0.6, color=col, edgecolor=SUPERFICIE, lw=2)
            if v >= 8:
                a2.text(izq + v / 2, i, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                        color="white" if col != "#86b6ef" else TINTA)
            izq += v
        a2.text(101, i, f"{tot} con remate", va="center", fontsize=7, color=TINTA2)
    a2.set_yticks(range(len(gs)))
    a2.set_yticklabels([_grupo_nombre(g, foco) for g in gs], fontsize=8)
    a2.invert_yaxis()
    a2.set_xlim(0, 125)
    a2.set_xticks([0, 50, 100])
    for c, col in zip(cats, cols):
        a2.barh([np.nan], [0], color=col, label=f"{c} {'jugador' if c == '1' else 'jugadores'}")
    a2.legend(frameon=False, fontsize=7.5, ncol=3, loc="lower left", bbox_to_anchor=(0, -0.32))
    _titulo(a2, "¿Cuántos intervienen hasta el remate?",
            "Sin contar al que saca. 2 = alguien la peina y otro remata.", ancho=45)
    return _guardar(fig, path)


# ======================================================================
# Simulación
# ======================================================================
def proyeccion(res: dict, path: Path) -> Path:
    esc = res["escenarios"]
    club, coach = res["club"], res["coach"]
    fig, axs = plt.subplots(1, 3, figsize=(14, 4))
    for nombre, col, lab in (("inercia", LIGA, "sin su efecto (plantel e inercia)"), ("con_el", FOCO, f"con {coach}")):
        d = np.array(esc[nombre]["dist_pts"], float)
        axs[0].plot(np.arange(len(d)), d / d.sum(), color=col, lw=2, label=lab)
        pos = np.array(esc[nombre]["dist_pos"], float)
        axs[1].bar(np.arange(1, len(pos) + 1) + (0.2 if nombre == "con_el" else -0.2), pos / pos.sum(), width=0.4,
                   color=col, label=lab)
    axs[0].set_xlabel(f"puntos de {club} en un torneo de {res['equipos'] - 1} partidos")
    axs[0].legend(frameon=False, fontsize=8)
    axs[0].set_title("¿Cuántos puntos haría?", loc="left", fontsize=9)
    axs[1].set_xlabel("posición final")
    axs[1].axvspan(0.5, 6.5, color="#1baf7a", alpha=0.07)
    axs[1].axvspan(6.5, 10.5, color="#eda100", alpha=0.07)
    axs[1].set_title("¿Dónde terminaría?\n(verde: liguilla directa; amarillo: play-in)", loc="left", fontsize=9)
    axs[1].set_xlim(0.5, res["equipos"] + 0.5)
    v = res.get("validacion") or {}
    if v.get("pred"):
        axs[2].scatter(v["pred"], v["real"], s=14, color=GRIS)
        m = max(max(v["pred"]), max(v["real"]))
        axs[2].plot([0, m], [0, m], color=TINTA2, ls="--", lw=0.8)
        axs[2].set_xlabel("puntos proyectados en sus primeros partidos")
        axs[2].set_ylabel("puntos reales")
        axs[2].set_title(f"¿Funciona la receta? {v['llegadas']} llegadas de\ntécnicos de la liga · cobertura del "
                         f"80 %: {100 * v['cobertura_80']:.0f} % · corr {v['correlacion']:.2f}", loc="left", fontsize=9)
    fig.suptitle(f"Proyección: {coach} en {club}, con los jugadores que encontró (10 mil torneos simulados)",
                 x=0.01, y=1.04, ha="left", fontsize=11)
    fig.tight_layout()
    return _guardar(fig, path)
