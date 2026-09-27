"""Figuras. Backend Agg (sin display). Coordenadas StatsBomb: y crece hacia ABAJO."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

L, W = 120.0, 80.0


def _cancha(ax):
    kw = dict(color="#444", lw=0.8)
    ax.plot([0, L, L, 0, 0], [0, 0, W, W, 0], **kw)
    ax.plot([L / 2, L / 2], [0, W], **kw)
    for x0, s in ((0, 1), (L, -1)):
        ax.plot([x0, x0 + s * 18, x0 + s * 18, x0], [18, 18, 62, 62], **kw)
        ax.plot([x0, x0 + s * 6, x0 + s * 6, x0], [30, 30, 50, 50], **kw)
    ax.add_patch(plt.Circle((L / 2, W / 2), 10, fill=False, **kw))
    ax.set_xlim(-2, L + 2)
    ax.set_ylim(W + 2, -2)   # y hacia abajo, como StatsBomb
    ax.set_aspect("equal")
    ax.axis("off")


def _malla(valores_zona, nx, ny):
    """Zona z = ix*ny + iy  ->  arreglo (ny, nx) para imshow."""
    A = np.zeros((ny, nx))
    for z, v in enumerate(valores_zona):
        ix, iy = divmod(z, ny)
        A[iy, ix] = v
    return A


def mapa_tipos(resumen: list[dict], nx: int, ny: int, path: Path, clave: str = "visitas_por_zona",
               etiqueta: str = "visitas") -> Path:
    K = len(resumen)
    cols = min(K, 4)
    filas = int(np.ceil(K / cols))
    fig, axes = plt.subplots(filas, cols, figsize=(4.2 * cols, 3.4 * filas), squeeze=False)
    vmax = max(max(t[clave]) for t in resumen)
    for ax, t in zip(axes.ravel(), resumen):
        A = _malla(t[clave], nx, ny)
        ax.imshow(A, extent=(0, L, W, 0), cmap="Greens", vmin=0, vmax=vmax, alpha=0.9,
                  interpolation="nearest")
        _cancha(ax)
        ax.annotate("", xy=(112, 76), xytext=(92, 76),
                    arrowprops=dict(arrowstyle="->", color="#444"))
        ax.set_title(
            f"Tipo {t['tipo']} · {100 * t['pi']:.0f}% de posesiones\n"
            f"E[T]={t['E_T_modelo']:.1f} · P(remate)={t['P_gol'] + t['P_remate_sin_gol']:.3f} · "
            f"xG/pos={t['xG_por_posesion_modelo']:.3f}",
            fontsize=9,
        )
    for ax in axes.ravel()[K:]:
        ax.axis("off")
    fig.suptitle(f"Vocabulario de posesiones de la Liga MX ({etiqueta} por zona; ataque →)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def curva_cv(res, path: Path) -> Path:
    K = res["K"].to_numpy()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    a1.plot(K, res["score"].to_numpy(), marker="o")
    a1.set_xlabel("K")
    a1.set_ylabel("log-verosimilitud fuera de muestra\n(nats / transición)")
    a1.set_title("Nivel")
    a2.plot(K, 100 * res["ganancia_acumulada"].to_numpy(), marker="o")
    a2.set_xlabel("K")
    a2.set_ylabel("% de la ganancia de K=1 al K máximo")
    a2.set_title("Ganancia acumulada (pliegues pareados)")
    a2.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def curva_estabilidad(tabla, path: Path) -> Path:
    """Tres paneles: ajuste (J), bondad (KS) y reproducibilidad (acuerdo) contra K."""
    K = tabla["K"].to_numpy()
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    ax[0].plot(K, tabla["nats_por_transicion"].to_numpy(), marker="o")
    ax[0].set_title("Log-verosimilitud de los datos\n(nats por transición, en muestra)")
    ax[1].plot(K, tabla["KS"].to_numpy(), marker="o", color="#c0392b")
    ax[1].set_title("KS de la duración (menor = mejor)")
    ac = tabla["acuerdo_minimo"].to_numpy()
    ax[2].plot(K, ac, marker="o", color="#27ae60")
    ax[2].axhline(0.95, ls="--", color="gray")
    ax[2].set_ylim(0, 1.02)
    ax[2].set_title("Reproducibilidad entre semillas")
    for a_ in ax:
        a_.set_xlabel("K (tipos de secuencia)")
        a_.set_xticks(K)
    rep = tabla.filter(tabla["reproducible"])["K"].to_list()
    fig.suptitle(f"Elección de K · reproducibles: {rep}", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


# ======================================================================
# Fase 2
# ======================================================================
COLOR_FOCO, COLOR_LIGA = "#1f4e9c", "#9aa3ad"
# matplotlib no dibuja emojis con las fuentes por defecto
ETIQUETA_TEXTO = {"🟢": "probado (FDR)", "🟡": "medido, no sobrevive FDR", "⚪": "no detectado",
                  "🔎": "exploratoria"}


def perfil_familias(res: dict, familias: list[str], foco: str, path: Path) -> Path:
    """Uso de cada familia: foco contra la liga EN SUS MISMAS SITUACIONES (modelo), ataque y defensa."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, h, titulo in ((axes[0], "H1", f"Ataque: secuencias de {foco}"),
                          (axes[1], "H2", "Defensa: secuencias de sus rivales")):
        e = res["hipotesis"][h]
        x = np.arange(len(familias))
        foco_pi, liga_pi = np.array(e["pi_foco"]), np.array(e["pi_liga"])
        err = np.array([np.array(e["delta_pi"]) - np.array(e["lo"]), np.array(e["hi"]) - np.array(e["delta_pi"])])
        ax.bar(x - 0.2, 100 * liga_pi, 0.4, color=COLOR_LIGA, label="liga, mismas situaciones")
        ax.bar(x + 0.2, 100 * foco_pi, 0.4, color=COLOR_FOCO, label=foco,
               yerr=100 * err, capsize=4, ecolor="#333")
        for i, (a, b) in enumerate(zip(foco_pi, liga_pi)):
            ax.text(i + 0.2, 100 * a + 1.5, f"{100 * (a - b):+.1f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(familias, fontsize=9)
        ax.set_title(f"{titulo}\n{ETIQUETA_TEXTO[e['etiqueta']]} · q = {e['q']:.3f}", fontsize=10)
        ax.set_ylabel("% de secuencias")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("¿Qué familias de secuencia usa? (barras de error: IC 95 % de la diferencia)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def efectos_contexto(res: dict, familias: list[str], foco: str, path: Path) -> Path:
    """Diferencia de diferencias: cuánto cambia el foco su mezcla por encima de lo que cambia la liga."""
    esc = list(res["contexto"])
    fig, axes = plt.subplots(1, len(familias), figsize=(4.2 * len(familias), 0.6 * len(esc) + 1.6), sharey=True)
    for k, ax in enumerate(np.atleast_1d(axes)):
        y = np.arange(len(esc))
        d = np.array([100 * res["contexto"][e]["dif"][k] for e in esc])
        lo = np.array([100 * res["contexto"][e]["lo"][k] for e in esc])
        hi = np.array([100 * res["contexto"][e]["hi"][k] for e in esc])
        col = [COLOR_FOCO if (l > 0 or h < 0) else COLOR_LIGA for l, h in zip(lo, hi)]
        ax.axvline(0, color="#444", lw=0.8)
        ax.hlines(y, lo, hi, color=col, lw=2)
        ax.scatter(d, y, color=col, zorder=3)
        ax.set_yticks(y)
        ax.set_yticklabels(esc, fontsize=9)
        ax.set_title(familias[k], fontsize=10)
        ax.set_xlabel("pp por encima de la reacción de la liga")
    fig.suptitle(f"¿Reacciona {foco} distinto que la liga al contexto? (azul: IC 95 % excluye 0)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def eficiencia(res: dict, familias: list[str], foco: str, path: Path) -> Path:
    K = len(familias)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, lado, titulo in ((axes[0], "ataque", "xG por secuencia que genera"),
                             (axes[1], "defensa", "xG por secuencia que concede")):
        pf = res["perfiles"][lado]
        x = np.arange(K)
        f_ = np.array(pf["foco"][K:2 * K])
        l_ = np.array(pf["liga"][K:2 * K])
        d, lo, hi = (np.array(pf[c][K:2 * K]) for c in ("dif", "lo", "hi"))
        ax.bar(x - 0.2, l_, 0.4, color=COLOR_LIGA, label="liga")
        ax.bar(x + 0.2, f_, 0.4, color=COLOR_FOCO, label=foco, yerr=[d - lo, hi - d], capsize=4, ecolor="#333")
        ax.set_xticks(x)
        ax.set_xticklabels(familias, fontsize=9)
        ax.set_title(f"{titulo}, dentro de cada familia", fontsize=10)
    axes[0].set_ylabel("xG por secuencia")
    axes[0].legend(fontsize=8)
    fig.suptitle("Eficiencia: ¿hace mejor (o concede menos) la MISMA clase de jugada?", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


# ======================================================================
# Fase 3
# ======================================================================
def comparar_clubes(res: dict, familias: list[str], coach: str, path: Path) -> Path:
    """Los rasgos de la fase 2 (defensa H2, eficiencia H7 y H8), club por club."""
    clubes = list(res["clubes"])
    K = len(familias)
    paneles = [("H2", "Defensa: Δ uso por sus rivales (pp)", 100, True),
               ("H7", "Eficiencia ofensiva: Δ xG por secuencia", 1, False),
               ("H8", "Eficiencia defensiva: Δ xG concedido", 1, False)]
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.2 + 0.25 * K), sharey=True)
    colores = [COLOR_FOCO, "#d4a017", "#2e8b57", "#8b2e5b"]
    y = np.arange(K)
    for ax, (h, titulo, esc, es_lista) in zip(axes, paneles):
        for ci, club in enumerate(clubes):
            H = res["clubes"][club]["hipotesis"]
            if es_lista:
                d = np.array(H[h]["delta_pi"]); lo = np.array(H[h]["lo"]); hi = np.array(H[h]["hi"])
            else:
                d = np.array([H[f"{h}.{k + 1}"]["dif"] for k in range(K)])
                lo = np.array([H[f"{h}.{k + 1}"]["lo"] for k in range(K)])
                hi = np.array([H[f"{h}.{k + 1}"]["hi"] for k in range(K)])
            off = (ci - (len(clubes) - 1) / 2) * 0.22
            ax.hlines(y + off, esc * lo, esc * hi, color=colores[ci % 4], lw=2)
            ax.scatter(esc * d, y + off, color=colores[ci % 4], zorder=3,
                       label=f"{club} ({res['clubes'][club]['partidos']} p.)")
        ax.axvline(0, color="#444", lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(familias)
        ax.set_title(titulo, fontsize=10)
    h_, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="lower center", ncol=len(clubes), fontsize=9, frameon=False)
    fig.suptitle(f"¿Viajan los rasgos de {coach} de un club a otro? (IC 95 %)", fontsize=11)
    fig.tight_layout(rect=(0, 0.08, 1, 0.9))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def mapa_atlas(tab, foco: str, familias: list[str], path: Path) -> Path:
    """Cada punto, una era (técnico × club). Ejes: cuánto se separa su mezcla de la liga."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    x, y = tab["norma_ataque_pp"].to_numpy(), tab["norma_defensa_pp"].to_numpy()
    es = (tab["coach"] == foco).to_numpy()
    axes[0].scatter(x[~es], y[~es], color=COLOR_LIGA, s=30)
    axes[0].scatter(x[es], y[es], color=COLOR_FOCO, s=70, zorder=3)
    for xi, yi, c, t_, e in zip(x, y, tab["coach"], tab["team"], es):
        axes[0].annotate(f"{c.split()[-1]} ({t_[:3]})", (xi, yi), fontsize=7 if not e else 9,
                         color="#222" if e else "#666", xytext=(3, 3), textcoords="offset points")
    axes[0].set_xlabel("cuánto se separa su ATAQUE de la liga (pp, distancia de variación total)")
    axes[0].set_ylabel("cuánto se separa lo que le hacen sus RIVALES (pp)")
    axes[0].set_title("Identidad: elección de familias")
    fam = familias[-1]
    xa, yd = tab[f"efic_ataque_{fam}"].to_numpy(), tab[f"efic_defensa_{fam}"].to_numpy()
    axes[1].axhline(0, color="#444", lw=0.6); axes[1].axvline(0, color="#444", lw=0.6)
    axes[1].scatter(xa[~es], yd[~es], color=COLOR_LIGA, s=30)
    axes[1].scatter(xa[es], yd[es], color=COLOR_FOCO, s=70, zorder=3)
    for xi, yi, c, t_, e in zip(xa, yd, tab["coach"], tab["team"], es):
        axes[1].annotate(f"{c.split()[-1]} ({t_[:3]})", (xi, yi), fontsize=7 if not e else 9,
                         color="#222" if e else "#666", xytext=(3, 3), textcoords="offset points")
    axes[1].set_xlabel(f"Δ xG que GENERA por secuencia de «{fam}»")
    axes[1].set_ylabel(f"Δ xG que CONCEDE por secuencia de «{fam}»")
    axes[1].set_title("Eficiencia (abajo a la derecha = mejor en ambos lados)")
    fig.suptitle("Atlas de técnicos de la Liga MX (exploratorio, eras con ≥ 50 partidos)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


# ======================================================================
# Fase 3b
# ======================================================================
def figura_decisiones(res: dict, foco: str, path: Path) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    # 1. minuto esperado del primer cambio
    ax = axes[0]
    pc = res["primer_cambio"]
    marc = list(pc)
    x = np.arange(len(marc))
    ax.bar(x - 0.2, [pc[m]["minuto_liga"] for m in marc], 0.4, color=COLOR_LIGA, label="liga")
    f_ = np.array([pc[m]["minuto_foco"] for m in marc])
    d = np.array([pc[m]["dif"] for m in marc])
    err = [d - np.array([pc[m]["lo"] for m in marc]), np.array([pc[m]["hi"] for m in marc]) - d]
    ax.bar(x + 0.2, f_, 0.4, color=COLOR_FOCO, label=foco, yerr=err, capsize=4)
    tope = f_ + np.array(err[1])
    for i, v in enumerate(d):
        ax.text(i + 0.2, tope[i] + 0.6, f"{v:+.1f}'", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(marc)
    ax.set_ylim(45, max(f_.max(), max(pc[m]["minuto_liga"] for m in marc)) + 6)
    ax.set_ylabel("minuto esperado del primer cambio (2º tiempo)")
    h = res["hipotesis"]
    ax.set_title(f"¿Cuándo cambia?  H13 {ETIQUETA_TEXTO[h['H13']['etiqueta']]}", fontsize=10)
    ax.legend(fontsize=8)
    # 2. tipo de cambio perdiendo
    ax = axes[1]
    tc = res["tipo_cambio"]["perdiendo"]
    tipos = ["defensivo", "mismo puesto", "ofensivo"]
    x = np.arange(3)
    ax.bar(x - 0.2, 100 * np.array(tc["P_liga"]), 0.4, color=COLOR_LIGA, label="liga")
    d = np.array(tc["dif"]); lo = np.array(tc["lo"]); hi = np.array(tc["hi"])
    ax.bar(x + 0.2, 100 * np.array(tc["P_foco"]), 0.4, color=COLOR_FOCO, label=foco,
           yerr=100 * np.array([d - lo, hi - d]), capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(tipos)
    ax.set_ylabel("% de sus cambios")
    ax.set_title(f"Cambios cuando va perdiendo  H15 {ETIQUETA_TEXTO[h['H15']['etiqueta']]}", fontsize=10)
    # 3. reacomodos y rotación
    ax = axes[2]
    et = ["reacomodos\npor partido", "rotación del once\n(1 − Jaccard)"]
    hh = [h["H16"], h["H17"]]
    x = np.arange(2)
    ax.bar(x - 0.2, [b["liga"] for b in hh], 0.4, color=COLOR_LIGA)
    ax.bar(x + 0.2, [b["foco"] for b in hh], 0.4, color=COLOR_FOCO,
           yerr=[[b["dif"] - b["lo"] for b in hh], [b["hi"] - b["dif"] for b in hh]], capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(et)
    ax.set_title(f"H16 {ETIQUETA_TEXTO[h['H16']['etiqueta']]} · H17 {ETIQUETA_TEXTO[h['H17']['etiqueta']]}", fontsize=10)
    fig.suptitle(f"Las decisiones de {foco} desde la banca, contra la liga (IC 95 % de la diferencia)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def figura_xpts(x, foco: str, path: Path) -> Path:
    d = x.sort("match_date")
    dif = np.cumsum((d["pts"] - d["xPts"]).to_numpy())
    sd = np.sqrt(np.cumsum(d["var_pts"].to_numpy()))
    n = np.arange(1, d.height + 1)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.fill_between(n, -1.96 * sd, 1.96 * sd, color=COLOR_LIGA, alpha=0.35, label="±1.96 DE (azar)")
    ax.plot(n, dif, color=COLOR_FOCO, lw=2, label="puntos reales − puntos esperados (acumulado)")
    ax.axhline(0, color="#444", lw=0.8)
    for club in d["team"].unique(maintain_order=True).to_list()[1:]:
        i = int(np.argmax(d["team"].to_numpy() == club))
        ax.axvline(i + 1, ls="--", color="#666")
        ax.text(i + 2, ax.get_ylim()[1] * 0.85, club, fontsize=8)
    ax.set_xlabel(f"partidos de {foco} (en orden)")
    ax.set_ylabel("puntos")
    ax.set_title("¿Sacó los puntos que su xG merecía? (xPts exactos por Poisson-binomial)", fontsize=10)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def figura_escenarios(esc, foco: str, path: Path) -> Path:
    sel = [("empatando", "0-29", True, "rival parejo"), ("empatando", "75+", False, "rival parejo"),
           ("perdiendo", "45-59", True, "rival parejo"), ("perdiendo", "75+", False, "rival más fuerte"),
           ("ganando", "45-59", False, "rival más fuerte"), ("ganando", "75+", True, "rival más débil")]
    filas = [esc.filter((pl.col("marcador") == a) & (pl.col("minuto") == b) & (pl.col("local") == c)
                        & (pl.col("rival") == dd)).row(0, named=True) for a, b, c, dd in sel]
    y = np.arange(len(filas))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    d = np.array([f["dif_xG_sec"] for f in filas])
    lo = np.array([f["lo"] for f in filas]); hi = np.array([f["hi"] for f in filas])
    col = [COLOR_FOCO if (l > 0 or h < 0) else COLOR_LIGA for l, h in zip(lo, hi)]
    ax.axvline(0, color="#444", lw=0.8)
    ax.hlines(y, lo, hi, color=col, lw=2)
    ax.scatter(d, y, color=col, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{f['marcador']}, min {f['minuto']}, {'local' if f['local'] else 'visitante'}, {f['rival']}"
                        for f in filas], fontsize=8)
    ax.set_xlabel("Δ xG por secuencia contra la liga en el mismo escenario")
    ax.set_title(f"Escenarios: ¿cuánto peligro produce el equipo de {foco}? (azul: IC excluye 0)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


# ======================================================================
# Fase 1 v3: mallado y métricas de Markov
# ======================================================================
def mapas_zona(valores: list, titulos: list[str], nx: int, ny: int, path: Path, titulo: str,
               cmap: str = "Greens") -> Path:
    n = len(valores)
    cols = min(n, 4)
    filas = int(np.ceil(n / cols))
    fig, axes = plt.subplots(filas, cols, figsize=(4.2 * cols, 3.3 * filas), squeeze=False)
    vmax = max(max(v) for v in valores)
    for ax, v, t in zip(axes.ravel(), valores, titulos):
        ax.imshow(_malla(v, nx, ny), extent=(0, L, W, 0), cmap=cmap, vmin=0, vmax=vmax, alpha=0.9,
                  interpolation="nearest")
        _cancha(ax)
        ax.set_title(t, fontsize=9)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.suptitle(titulo, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)


def figura_mallado(tab, ag: dict, elegida: str, path: Path) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.4))
    agt = ag["tabla"]
    a1.errorbar(agt["regiones"].to_numpy(), agt["score"].to_numpy(), yerr=agt["se"].to_numpy(),
                color=COLOR_LIGA, lw=1, label=f"agregación contigua desde {ag['nx']}×{ag['ny']}")
    for r in tab.iter_rows(named=True):
        col = COLOR_FOCO if r["malla"] == elegida else "#c0392b"
        a1.scatter(r["zonas"], r["score"], color=col, zorder=3, s=40)
        a1.annotate(r["malla"], (r["zonas"], r["score"]), fontsize=8, xytext=(4, -10), textcoords="offset points")
    a1.axvline(ag["R_opt"], ls="--", color="#666")
    a1.set_xscale("log")
    a1.set_xlabel("número de zonas")
    a1.set_ylabel("log-densidad predictiva fuera de muestra\n(nats por transición, vs. uniforme)")
    a1.set_title(f"Calibración del mallado · elegida: {elegida}", fontsize=10)
    a1.legend(fontsize=8)
    lab = ag["etiquetas"]
    nx, ny = ag["nx"], ag["ny"]
    A = np.zeros((ny, nx))
    for z, r in enumerate(lab):
        ix, iy = divmod(z, ny)
        A[iy, ix] = r
    rng = np.random.default_rng(0)
    perm = rng.permutation(lab.max() + 1)
    a2.imshow(perm[A.astype(int)], extent=(0, L, W, 0), cmap="tab20", interpolation="nearest", alpha=0.75)
    _cancha(a2)
    a2.set_title(f"Zonas que distinguen los datos: {ag['R_opt']} regiones (ataque →)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return Path(path)
