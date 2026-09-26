# 01 — Arquitectura (v2)

## Árbol

```
Hackathon2026_v2/
├── .venv/                  análisis (Python 3.12, dtcoach editable)
├── .venv-sb/               descargas del API (solo requests); corre en paralelo
├── pyproject.toml · Makefile · requirements-sb.txt · README.md
├── config/default.yaml     ÚNICO lugar de parámetros
├── src/dtcoach/
│   ├── config.py           cargador YAML (única suposición de layout)
│   ├── aplanar.py          NUEVO  JSON crudo -> parquet plano
│   ├── partidos.py         NUEVO  matches -> partidos, DT por partido, verificación
│   ├── ingest.py           REUSO  (+ columnas opcionales v2)
│   ├── grid.py             REUSO  sin cambios
│   ├── possessions.py      REUSO  (+ play_pattern, xg, period, minute)
│   ├── eras.py             REUSO  sin cambios
│   ├── estimate.py         REUSO  (+ match_folds)
│   ├── inference.py        REUSO  sin cambios (bootstrap por partido: semana 2)
│   ├── absorbing.py        NUEVO  N, t, B, V=Nc, visitas, supervivencia
│   ├── mezcla.py           NUEVO  EM-MAP, CV de K, resumen de tipos, bondad
│   ├── graficas.py         NUEVO  mini-canchas por tipo, curva de CV
│   └── cli.py              NUEVO  un comando por paso
├── scripts/
│   ├── descargar/descargar_360.py      (del amigo, con sesión por hilo)
│   ├── descargar/explorar_datos_sb.py  (movido)
│   └── 23_potencia_tau2.py             REUSO sin cambios
├── tests/                  grid, absorbing, partidos, aplanar→fase0, mezcla
├── data/
│   ├── raw/statsbomb/{events,matches,frames}   NO se versiona
│   ├── interim/{events/, partidos.parquet, dt_por_partido.parquet}
│   ├── processed/{transitions.parquet, mezcla/}
│   └── referencia/eras_api/…   eras VERIFICADAS (sí se versionan)
│       └── historico/          eras viejas de un club (fechas derivadas)
├── reports/                JSON/CSV/PNG de cada comando
└── docs/
    ├── 00_ROADMAP.md · 01_ARQUITECTURA.md · 02_ESTADO.md · 06_DECISIONES.md
    └── proyecto_viejo/     SOLO LECTURA
```

## Grafo

```
aplanar ─► ingest ─► possessions ─► (eras + partidos) ─► transitions.parquet
                         ▲ grid                                  │
                                                                  ▼
                              estimate ─► mezcla ◄─ absorbing ─► graficas
```

## Contrato de artefactos

| archivo | escribe | lee | contenido |
|---|---|---|---|
| `data/interim/events/part-*.parquet` | aplanar | fase0 | un evento por fila, esquema `aplanar.SCHEMA` |
| `data/interim/partidos.parquet` | partidos | fase0 | un partido por fila, `match_date` Date |
| `data/interim/dt_por_partido.parquet` | partidos | fase0 | (match_id, team) → DT del API, local, rival, goles |
| `data/processed/transitions.parquet` | fase0 | cv-k, mezcla, bondad | transiciones de TODA la liga + `coach`, `coach_faced`, `local`, `rival` |
| `data/processed/mezcla/mezcla_K*.npz` | mezcla | bondad, semana 2 | `pi, mu, P, lam, a0, objetivo` |
| `data/processed/mezcla/responsabilidades_K*.parquet` | mezcla | semana 2 | una fila por posesión: meta + `r_1..r_K`, `tipo`, `largo` |
| `reports/verificacion_eras.csv` | fase0 | humano | discrepancias era verificada vs `managers` del API |
| `reports/mezcla/tipos_K*.json` | mezcla | reporte | por tipo: π, E[T], desenlaces, xG/pos (modelo y empírico), visitas, típicas |

**Reglas duras** (heredadas): todo cambio con un test que cruce los dos lados
del contrato; nada hardcodeado (va al config); ninguna distancia sin su nula;
nunca afirmar la nula; los tipos se nombran después de ver sus figuras.

## Añadidos de la Fase 1

| archivo | qué hace |
|---|---|
| `src/dtcoach/possessions.py::segmentar_secuencias` | corta cada posesión en secuencias, una por absorción (ADR-v2-14). **Es la pieza que hace válida la cadena** |
| `src/dtcoach/mezcla.py::ajustar(init="escalera")` | sube de K−1 a K partiendo un tipo; determinista y reproducible (ADR-v2-17) |
| `src/dtcoach/mezcla.py::reproducibilidad` | ¿la escalera llega al mismo óptimo desde otras semillas? |
| `scripts/aplicar_bordes.py` | propone eras corregidas en `eras_api_v2`; no pisa nada sin `--rehacer` |
| `scripts/revisar_eras.py` | clasifica discrepancias era vs API en A_borde / A_sin_era / AB / C |
| `scripts/candidatos_dt.py` | candidatos a técnico focal: partidos, clubes, mover, cobertura 360 |

Comandos: `dtcoach {aplanar, partidos, fase0, cv-k, mezcla, reproducibilidad, bondad}`.

Columnas nuevas en `transitions.parquet`: `seq_uid`, `seq_n` (secuencia),
`play_pattern`, `xg`, `period`, `minute`, `local`, `rival`, `coach`, `coach_faced`.

## Añadidos de la Fase 2

| archivo | qué hace |
|---|---|
| `elo.py` | Elo de toda la liga; K y h por log-pérdida; Elo previo al partido; calibración |
| `contexto.py` | tabla por secuencia: responsabilidades, xG, contexto, Elo, f (ataque del foco), g (defensa del foco); matriz de diseño |
| `pesos.py` | logit multinomial fraccional, sandwich por partido, Wald, efectos en probabilidad por simulación, columnas no estimables |
| `perfil.py` | perfiles crudos con bootstrap estratificado por partido (uso, xG y remate dentro de cada familia) |
| `hipotesis.py` | H1–H8, Benjamini-Hochberg, etiquetas y frases de cancha |

Comandos nuevos: `dtcoach elo`, `dtcoach fase2 [--foco "Nombre"]`.
Artefactos: `data/processed/elo.parquet`, `reports/fase2/*`.

## Añadidos de la Fase 3a

| archivo | qué hace |
|---|---|
| `fase3.py` | `reasignar_foco` (cualquier técnico, opcionalmente un club; excluye sus otras etapas de la referencia), `por_club` (H9–H12), `atlas` (todas las eras, exploratorio) |

Comandos: `dtcoach fase3 [--foco] [--min-partidos 30]`, `dtcoach atlas [--min-partidos 50]`.

## Añadidos de la Fase 3b

| archivo | qué hace |
|---|---|
| `decisiones.py` | panel equipo-minuto (tiempo de los cambios, H13–H14), tipo de cambio por nivel de puesto (H15), reacomodos y rotación del once (H16–H17), BH propio |
| `simulador.py` | Poisson-binomial exacta, xPts por equipo-partido con validación de liga, escenarios de contexto, calibración del modelo de contexto |
| `hipotesis.modelo_contexto` | el ajuste de la fase 2, reutilizable (lo usa el simulador) |

Comandos: `dtcoach decisiones [--foco]`, `dtcoach simulador [--foco]`.

## Experimento 360 (ADR-v2-36, aislado)

| archivo | qué hace |
|---|---|
| `voronoi.py` | rasgos por freeze frame (celda de Voronoi local, rival más cercano), discretización en niveles, recodificación zona × nivel (`aumentar`), validación cruzada en la escala común |
| `config/presion.yaml` · `config/presion_base.yaml` | heredan de `default.yaml` (`hereda:`); rutas propias; experimento y control con la misma muestra |
| `scripts/presion.sh` | corre el experimento completo con las reglas pre-registradas |

Comandos: `dtcoach voronoi`, `dtcoach presion-cv`, `dtcoach --config config/presion.yaml presion-aplicar`.
Artefactos: `data/interim/rasgos_360.parquet`, `data/processed/presion/`, `reports/presion*/`,
`reports/fase1/presion_cv.{csv,json}`.
