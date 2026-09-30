# 01 — Arquitectura: qué hace cada pieza y cómo fluye la información

> Para el *porqué* matemático de cada paso, ver `04_MODELO_MATEMATICO.md`. Para las
> definiciones exactas de cada objeto, `03_FRAMEWORK.md`. Para las decisiones y su
> historia, `06_DECISIONES.md`.

## 1. Qué datos usa y de dónde salen

| dato | qué es | cómo llega | dónde vive |
|---|---|---|---|
| **Eventos** | cada pase, conducción, remate, duelo, presión, cambio… de 1,767 partidos de Liga MX (5.7 M eventos), un `.json.gz` por partido | descarga del API de StatsBomb entregada para el hackathon; su integridad se verifica con `sha256sum -c data/MANIFIESTO_RAW.sha256` | `data/raw/statsbomb/events/` |
| **Partidos** | fecha, torneo, marcador, técnicos (`managers`), estado del 360 | misma descarga | `data/raw/statsbomb/matches/` |
| **Alineaciones** | onces y puestos | misma descarga | `data/raw/statsbomb/lineups/` |
| **360** | en cada evento, la posición de los jugadores que ve la cámara y el área visible (1,755 partidos, 5.1 M frames) | `scripts/descargar/descargar_360.py` con credenciales de StatsBomb (`SB_USERNAME`, `SB_PASSWORD`); reanudable, un archivo por partido | `data/raw/statsbomb/frames/` |
| **Eras** | qué técnico dirigió cada club en cada fecha, **verificadas a mano** (el `managers` del API solo verifica) | versionadas en el repo | `data/referencia/eras_api_v2/` |

**Los datos de StatsBomb son licenciados y nunca se versionan** (`data/raw`, `data/interim`,
`data/processed` y `reports/` están en `.gitignore`). Lo único que se publica son
figuras agregadas (`docs/figuras/`) y las eras.

## 2. El flujo completo

```mermaid
flowchart TD
    subgraph DATOS["Datos crudos (no se versionan)"]
      E[eventos] ; M[partidos] ; F[frames 360]
    end
    E --> A[aplanar<br/>JSON → parquet plano]
    M --> P[partidos<br/>fecha, marcador, DT del API]
    A --> F0[fase0<br/>acciones → transiciones → secuencias<br/>+ eras + técnico por partido]
    P --> F0
    F0 --> V[vocabulario<br/>malla 5×4 · mezcla de K=3 cadenas<br/>reproducibilidad · bondad · Markov]
    V --> F2[fase 2<br/>el técnico como mezcla<br/>bajo contexto · H1–H8]
    P --> ELO[Elo previo al partido] --> F2
    F2 --> F3[fase 3<br/>por club H9–H12 · atlas]
    A --> DEC[fase 3b<br/>decisiones H13–H17 · xPts]
    E --> EX[extra<br/>centros, técnica, asistencias]
    F --> VOR[voronoi<br/>presión 360 por evento]
    F --> GEO[geometria<br/>bloque, ancho visible,<br/>frame del saque]
    A --> TAB[tabla-liga<br/>todas las métricas equipo-partido<br/>+ xDefense en dos capas]
    EX --> TAB
    VOR --> TAB
    GEO --> TAB
    V --> TAB
    TAB --> S1[1 identidad<br/>reconocimiento · rival por Elo · Kalman]
    F2 --> S1
    TAB --> S2[2 ofensiva<br/>salida · progresión · llegada · familias]
    TAB --> S3[3 defensa<br/>presión · bloque · transiciones]
    TAB --> S4[4 jugadores<br/>red · roles · sustituciones]
    DEC --> S4
    TAB --> S5[5 balón parado<br/>rutinas · xDefense · línea]
    ELO --> S6[6 simulación<br/>xPts · partido · proyección]
    V --> S6
    F2 --> BL[7 blindaje<br/>OBV · bootstrap de score · BH global]
    S1 & S2 & S3 & S4 & S5 & S6 & BL --> R[reports/historia/foco/sección/<br/>md · json · png]
    R --> PUB[publicar_figuras → docs/figuras/sección]
```

## 3. Cómo se corre, de cero a la historia

```bash
source .venv/bin/activate                 # Python 3.12, dtcoach instalado en modo editable
pytest -q                                 # pruebas rápidas; `pytest -m lento` corre la integral

# 1. los datos de toda la liga (una vez)
dtcoach aplanar && dtcoach partidos && dtcoach fase0
bash scripts/vocabulario.sh               # malla y K por las reglas pre-registradas; mezcla, bondad, Markov
dtcoach elo

# 2. el técnico (fases 2 y 3)
bash scripts/correr_foco.sh "Guillermo Almada" 7

# 3. la historia, sección por sección
.venv-sb/bin/python scripts/descargar/descargar_360.py      # si aún no están los frames
bash scripts/historia.sh "Guillermo Almada"   # una vez: extra, voronoi, geometria, tabla-liga;
                                              # luego identidad, ofensiva, defensa, jugadores,
                                              # balon-parado, simular, blindaje
# 4. publicar las figuras que muestran los documentos
bash scripts/publicar_figuras.sh "Guillermo Almada"
```

Todo lo que es de la liga se calcula **una vez** y se reutiliza (vocabulario, Elo, atlas,
tabla equipo-partido, rasgos 360). Cambiar de técnico solo corre lo del técnico.

## 4. El código

### Núcleo: de eventos a vocabulario

| archivo | qué hace | lo que se rompe si se toca mal |
|---|---|---|
| `config.py` | carga `config/default.yaml`; `hereda:` para configuraciones de experimento | todo: es el único lugar con parámetros |
| `aplanar.py` | JSON del API → parquet plano con esquema explícito | cualquier columna que falte aguas abajo |
| `ingest.py` | lectura y normalización del parquet | — |
| `partidos.py` | partidos, técnico del API por partido, verificación de eras | — |
| `eras.py` | asigna el técnico verificado a cada equipo-partido | **quién es el foco** |
| `grid.py` | malla y espacio de estados (zona × fase) | toda la cadena |
| `possessions.py` | acciones → transiciones → secuencias (ADR-v2-14) | **la validez de la cadena** |
| `estimate.py` | conteos, encogimiento, pliegues por partido | — |
| `absorbing.py` | N, t, B, V de una cadena absorbente | formas cerradas |
| `mezcla.py` | EM-MAP, escalera, reproducibilidad, resumen de tipos, bondad | el vocabulario |
| `mallado.py` | elección de malla por densidad predictiva | — |
| `markov.py` | verificación formal, espectro, irreversibilidad, llegada, memoria | — |

### El técnico: contexto, clubes, decisiones

| archivo | qué hace |
|---|---|
| `elo.py` | Elo previo al partido, K y ventaja local por log-pérdida |
| `contexto.py` | tabla por secuencia (responsabilidades, xG, contexto, f, g) y matriz de diseño |
| `pesos.py` | logit multinomial fraccional, sandwich por partido, Wald, bootstrap de score |
| `perfil.py` | perfiles crudos por familia con bootstrap por partido |
| `hipotesis.py` | H1–H8, BH, frases de cancha |
| `fase3.py` | por club (H9–H12) y atlas de todas las etapas |
| `decisiones.py` | tiempo y tipo de los cambios, reacomodos, rotación (H13–H17) |
| `simulador.py` | puntos esperados exactos (Poisson-binomial) y escenarios |

### La historia, por sección (fases A–G)

| sección | archivo | qué hace |
|---|---|---|
| común | `eventos.py` | lectura única de eventos (coordenadas, reloj) y tabla de posesiones |
| común | `extra.py` | `dtcoach extra`: centros, pases filtrados, pases atrás, técnica, asistencias (tabla lateral) |
| común | `comparar.py` | motor: foco contra liga, percentiles entre técnicos, fiabilidad entre mitades |
| común | `futbol.py` | métricas base (volumen, presión, transiciones, 360), llegada y valor con la cadena |
| común | `voronoi.py`, `geometria.py` | 360: rival más cercano y Voronoi local; bloque, ancho visible y frame del saque |
| 1 identidad | `identidad.py` | huella, reconocimiento (logit L2, AUC, permutación), evolución (Kalman + RTS) |
| 1 identidad | `rival.py` | estratos por Elo del rival, foco contra liga en cada uno, ajuste distinto (H22) |
| 2 ofensiva | `ofensiva.py` | salida, progresión, llegada, ocasión, motivos de pase, camino típico por familia |
| 3 defensa | `defensa.py` | presión por tercio, curva de presión, bloque con control de cámara |
| 4 jugadores | `jugadores.py` | cadena sobre jugadores, roles espectrales, protagonistas |
| 4 jugadores | `sustituciones.py` | dif. en dif. emparejada de cada cambio, quién entra, reacomodo tras el cambio |
| 5 balón parado | `balon_parado.py` | saques, tipos, zonas, primer contacto, rutinas, receta Arsenal, Poisson con exposición |
| 5 balón parado | `xdefensa.py` | xDefense en dos capas, visibilidad del arco, contracción empírico-bayesiana |
| 6 simulación | `simulacion.py`, `proyeccion.py` | simulador de partido; proyección en el club actual validada con todas las llegadas |
| 7 blindaje | `blindaje.py` | eficiencia con OBV, BH global de todas las hipótesis |
| salida | `graficas.py`, `graficas_historia.py`, `graficas_secciones.py` | figuras (paleta validada) |
| salida | `cli.py`, `cli_historia.py` | los comandos `dtcoach …` (un comando por sección) |

### Experimentos (probados, no adoptados; aislados en `config/presion*.yaml` y `config/direccion.yaml`)

| archivo | qué probó |
|---|---|
| `voronoi.py` (parte de la cadena) | estado zona × nivel de presión |
| `direccion.py` | estado zona × dirección de llegada |

## 5. Artefactos intermedios

| archivo | escribe | lee |
|---|---|---|
| `data/interim/events/part-*.parquet` | `aplanar` | casi todo |
| `data/interim/partidos.parquet` | `partidos` | fase0, Elo, simulador |
| `data/processed/transitions.parquet` | `fase0` | vocabulario, fase 2, capa de fútbol |
| `data/processed/mezcla/mezcla_K3.npz` | `mezcla` | fase 2, simulador |
| `data/processed/elo.parquet` | `elo` | fase 2, decisiones |
| `data/interim/eventos_extra.parquet` | `extra` | tabla de la liga (ofensiva, balón parado) |
| `data/interim/rasgos_360.parquet` | `voronoi` | tabla de la liga, defensa |
| `data/interim/bloque_360.parquet`, `saques_360.parquet` | `geometria` | tabla de la liga, defensa, balón parado |
| `data/processed/futbol/equipo_partido.parquet` (+ `.json` con su versión) | `tabla-liga` (una vez; se rehace sola si cambia lo que calcula o llegan insumos nuevos) | todas las secciones |
| `data/processed/futbol/bp_jugadas.parquet`, `xd_capa1.parquet`, `xd_capa2.parquet`, `xdefensa.json` | `tabla-liga` | balón parado |
| `reports/fase2/`, `reports/fase3/`, `reports/historia/<foco>/<sección>/` | cada comando | humanos y el informe |

## 6. Cómo se sabe que funciona

* **Pruebas rápidas** (`pytest -q`) contra verdades conocidas: cuentas exactas en partidos
  armados a mano, áreas contra fórmulas analíticas, y rasgos **sembrados** en ligas
  sintéticas (`tests/sinteticos.py`, `tests/test_secciones.py`) que cada método debe encontrar
  sin inventar nada donde no se sembró.
* **Prueba integral** (`pytest -m lento`, minutos): `tests/liga_cruda.py` escribe una liga
  sintética en el formato CRUDO de StatsBomb (eventos, partidos, 360) con sus eras, y el
  pipeline completo corre de `aplanar` a las siete secciones.
* **Contrastes cruzados en los datos reales:** $E[T]$ del modelo contra el observado, KS de
  la duración, llegada modelada contra observada, estacionaria contra visitas, actor del
  frame 360 contra la ubicación del evento (mediana 0 m).
* **Reglas pre-registradas** (`11_HIPOTESIS.md`) escritas antes de ver cada resultado; las
  enmiendas llevan fecha y dicen si fueron antes o después de ver los datos.
