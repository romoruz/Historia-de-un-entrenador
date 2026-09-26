"""Figuras de la capa de fútbol (fases B–F). Paleta validada (skill dataviz, paleta de
referencia): foco = azul, liga = naranja; divergente azul↔rojo con punto medio gris;
secuencial en una sola rampa azul. Texto en tinta neutra, nunca en el color de la serie."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from .graficas import _cancha, _malla

FOCO, LIGA = "#2a78d6", "#eb6834"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
TINTA, TINTA2, SUPERFICIE = "#0b0b0b", "#52514e", "#fcfcfb"
DIVERGENTE = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
SECUENCIAL = LinearSegmentedColormap.from_list("seq", ["#f7f9fc", "#86b6ef", "#2a78d6", "#0d366b"])

plt.rcParams.update({"figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "text.color": TINTA,
                     "axes.labelcolor": TINTA2, "xtick.color": TINTA2, "ytick.color": TINTA2,
                     "axes.edgecolor": "#c9c8c3", "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 9})


def _guardar(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def percentiles(pct: dict, defs: dict, foco: str, path: Path, titulo: str) -> Path:
    """Una fila por métrica: percentil de cada etapa del foco entre todas las etapas de la liga."""
    metricas = [m for m in pct if pct[m]]
    if not metricas:
        return path
    clubes = sorted({p["team"] for m in metricas for p in pct[m]})
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(metricas) + 1.2))
    for i, m in enumerate(metricas):
        ax.plot([0, 100], [i, i], color="#e6e5e0", lw=1, zorder=0)
        for p in pct[m]:
            c = SERIES[clubes.index(p["team"]) % len(SERIES)]
            ax.scatter(p["percentil"], i, s=46, color=c, edgecolor=SUPERFICIE, linewidth=1.5, zorder=3)
    ax.axvline(50, color=TINTA2, lw=0.8, ls="--")
    ax.set_yticks(range(len(metricas)), [defs.get(m, {}).get("nombre", m) for m in metricas])
    ax.set_xlim(0, 100)
    ax.set_xlabel("percentil entre los técnicos de la liga (50 = mediana)")
    ax.invert_yaxis()
    for j, club in enumerate(clubes):
        ax.scatter([], [], color=SERIES[j % len(SERIES)], label=club, s=46)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.set_title(f"{titulo} · {foco}", loc="left")
    return _guardar(fig, path)


def diferencia_zonas(v_foco: list, v_liga: list, nx: int, ny: int, path: Path, titulo: str,
                     etiqueta: str) -> Path:
    A = _malla(np.array(v_foco) - np.array(v_liga), nx, ny)
    lim = float(np.nanmax(np.abs(A))) or 1.0
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    im = ax.imshow(A, extent=(0, 120, 80, 0), cmap=DIVERGENTE, vmin=-lim, vmax=lim, alpha=0.9)
    _cancha(ax)
    for z in range(nx * ny):
        ix, iy = divmod(z, ny)
        ax.text((ix + 0.5) * 120 / nx, (iy + 0.5) * 80 / ny, f"{v_foco[z] - v_liga[z]:+.3f}", ha="center",
                va="center", fontsize=7, color=TINTA)
    fig.colorbar(im, ax=ax, shrink=0.7, label=etiqueta)
    import textwrap
    ax.set_title("\n".join(textwrap.wrap(titulo, 70)), loc="left", fontsize=9)
    ax.annotate("ataca →", (104, 86), fontsize=8, color=TINTA2, annotation_clip=False)
    return _guardar(fig, path)


def curva_recuperacion(c: dict, foco: str, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 3.6))
    t = np.array(c["t"])
    for nombre, col, lab in (("foco", FOCO, foco), ("liga", LIGA, "liga")):
        ax.plot(t, c[nombre], color=col, lw=2, label=lab)
        if f"{nombre}_lo" in c:
            ax.fill_between(t, c[f"{nombre}_lo"], c[f"{nombre}_hi"], color=col, alpha=0.15, lw=0)
    ax.axvline(5, color=TINTA2, lw=0.8, ls="--")
    ax.set_xlabel("segundos desde la pérdida")
    ax.set_ylabel("P(aún sin recuperar)")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.set_title("Transición defensiva: cuánto tarda en recuperar tras perder", loc="left")
    return _guardar(fig, path)


def densidad_balon_parado(mp: dict, foco: str, tipo: str, lado: str, path: Path) -> Path:
    gx, gy = mp["gx"], mp["gy"]
    ext = (gx[0], gx[-1], gy[-1], gy[0])
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.8))
    vmax = max(mp["foco"]["remates"].max(), mp["liga"]["remates"].max()) or 1
    for ax, nombre, tit in ((axs[0], "foco", foco), (axs[1], "liga", "liga")):
        ax.imshow(mp[nombre]["remates"], extent=ext, cmap=SECUENCIAL, vmin=0, vmax=vmax)
        _cancha(ax)
        ax.set_xlim(gx[0], 122)
        ax.set_title(f"{tit}: {mp[nombre]['n_remates']} remates en {mp[nombre]['jugadas']} jugadas", loc="left",
                     fontsize=8)
    D = mp["foco"]["remates"] - mp["liga"]["remates"]
    lim = float(np.abs(D).max()) or 1
    im = axs[2].imshow(D, extent=ext, cmap=DIVERGENTE, vmin=-lim, vmax=lim)
    _cancha(axs[2])
    axs[2].set_xlim(gx[0], 122)
    axs[2].set_title("foco − liga (azul = más remates por jugada)", loc="left", fontsize=8)
    fig.colorbar(im, ax=axs[2], shrink=0.7, label="remates por jugada y m²")
    fig.suptitle(f"{tipo.replace('_', ' ')} · {'a favor' if lado == 'propio' else 'en contra'} · zonas de remate",
                 x=0.01, ha="left")
    return _guardar(fig, path)


def red_pases(cad: dict, titulo: str, path: Path, max_aristas: int = 30) -> Path:
    js = cad["jugadores"]
    W = np.array(cad["W"])
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    _cancha(ax)
    xy = np.array([[j["x_media"], j["y_media"]] for j in js])
    A = W + W.T
    iu = np.triu_indices(len(js), 1)
    orden = np.argsort(-A[iu])[:max_aristas]
    amax = A[iu][orden].max() if len(orden) else 1
    for k in orden:
        i, j = iu[0][k], iu[1][k]
        ax.plot(xy[[i, j], 0], xy[[i, j], 1], color=TINTA2, alpha=0.25 + 0.5 * A[i, j] / amax,
                lw=0.5 + 3 * A[i, j] / amax, zorder=1)
    fl = np.array([j["flujo"] for j in js])
    for i, j in enumerate(js):
        ax.scatter(*xy[i], s=80 + 1600 * fl[i], color=SERIES[j["grupo"] % len(SERIES)], edgecolor=SUPERFICIE,
                   linewidth=2, zorder=3)
        nombre = (j["player"] or "").split(" ")[-1]
        ax.text(xy[i, 0], xy[i, 1] + 4.5, nombre, ha="center", fontsize=7, color=TINTA, zorder=4)
    ax.set_title(f"{titulo}\ntamaño = por quién pasa el balón (estacionaria); color = grupo espectral",
                 loc="left", fontsize=9)
    return _guardar(fig, path)


def evolucion(ev: dict, series: list[str], nombres: dict, foco: str, path: Path) -> Path:
    series = [s for s in series if s in ev["series"]]
    if not series:
        return path
    n = len(series)
    fig, axs = plt.subplots(n, 1, figsize=(8, 1.7 * n + 0.6), sharex=True)
    axs = np.atleast_1d(axs)
    equipos = [p["team"] for p in ev["partidos"]]
    cortes = [i for i in range(1, len(equipos)) if equipos[i] != equipos[i - 1]]
    for ax, s in zip(axs, series):
        v = ev["series"][s]
        x = np.arange(len(v["nivel"]))
        ax.fill_between(x, v["lo"], v["hi"], color=FOCO, alpha=0.18, lw=0)
        ax.plot(x, v["nivel"], color=FOCO, lw=2)
        for c in cortes:
            ax.axvline(c - 0.5, color=TINTA2, lw=0.8, ls="--")
        ax.set_ylabel(nombres.get(s, s), fontsize=8, rotation=0, ha="right", va="center")
        ax.text(1.0, 0.95, f"q/r = {v['q_sobre_r']:.3f}", transform=ax.transAxes, ha="right", va="top",
                fontsize=7, color=TINTA2)
    axs[-1].set_xlabel("partido (orden cronológico); línea punteada = cambio de club")
    axs[0].set_title(f"Evolución partido a partido (nivel suavizado, Kalman + RTS) · {foco}", loc="left")
    return _guardar(fig, path)


def simulacion(s: dict, titulo: str, path: Path) -> Path:
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw={"width_ratios": [1, 1.4]})
    vals = [s["P_gana"], s["P_empata"], s["P_pierde"]]
    axs[0].barh(["gana", "empata", "pierde"], vals, color=[FOCO, "#c9c8c3", LIGA], height=0.6)
    for i, v in enumerate(vals):
        axs[0].text(v + 0.01, i, f"{100 * v:.0f} %", va="center", fontsize=8)
    axs[0].set_xlim(0, 1)
    axs[0].invert_yaxis()
    axs[0].set_title("resultado", loc="left")
    m = s["marcadores"]
    axs[1].bar([x["marcador"] for x in m], [x["P"] for x in m], color=FOCO, width=0.6)
    axs[1].set_title("marcadores más probables", loc="left")
    axs[1].set_ylabel("probabilidad")
    fig.suptitle(titulo, x=0.01, ha="left")
    return _guardar(fig, path)
