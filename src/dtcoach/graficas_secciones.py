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
        ax.set_title(f"{nombre}\n{foco}: {100 * f['foco']['prob_camino']:.1f} % · liga: "
                     f"{100 * f['liga']['prob_camino']:.1f} %\nde sus secuencias siguen ese camino exacto",
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


def xdefensa_etapas(E, foco: str, path: Path, titulo: str, etiqueta: str) -> Path:
    """Oruga: θ contraído de cada técnico-club con su confiabilidad, el foco resaltado."""
    if E is None or E.height == 0:
        return path
    E = E.sort("contraido")
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(E.height)
    th, c = E["contraido"].to_numpy(), E["theta"].to_numpy()
    se = np.sqrt(E["var"].to_numpy())
    es = (E["coach"] == foco).to_numpy()
    ax.errorbar(x[~es], c[~es], yerr=1.96 * se[~es], fmt="none", ecolor="#e6e5e0", lw=1)
    ax.scatter(x[~es], th[~es], s=14, color=GRIS, zorder=3, label="otros técnicos (contraído)")
    ax.errorbar(x[es], c[es], yerr=1.96 * se[es], fmt="none", ecolor=FOCO, lw=1.4)
    ax.scatter(x[es], th[es], s=60, color=FOCO, zorder=4, label=f"{foco} (contraído; raya = crudo ± IC)")
    ax.axhline(float(E["mu"][0]), color=TINTA2, lw=0.8, ls="--")
    ax.set_xticks([])
    ax.set_xlabel("técnicos-club de la liga, ordenados")
    ax.set_ylabel(etiqueta)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _titulo(ax, titulo, "Contraído = descontado el ruido de tener pocos centros (empírico-bayes); arriba = mejor defensa.")
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
