# dtcoach — La historia de Guillermo Almada a través de los datos

Proyecto para el **Hackathon ISAC 2026 — "La Historia de un Entrenador a través de los Datos"**.

El reto pide contar, con datos, **quién es un entrenador**: cómo juega, qué decide y si su
huella es suya o de sus jugadores. Este repositorio lo hace para **Guillermo Almada**
(Santos Laguna → Pachuca → América, 166 partidos) con los eventos y el tracking 360 de
StatsBomb de **toda la Liga MX** (1,767 partidos, 5.7 millones de eventos). Toda comparación
se hace **contra la liga completa** y contra los otros 44 técnicos, no contra una opinión.

| Si buscas… | Abre |
|---|---|
| Los resultados, explicados sin tecnicismos y con gráficas | [`docs/RESULTADOS_ALMADA.md`](docs/RESULTADOS_ALMADA.md) |
| Todas las cifras con su intervalo, su prueba y su etiqueta de evidencia | [`docs/10_RESULTADOS.md`](docs/10_RESULTADOS.md) (§16 y §19) |
| La matemática del modelo, con proposiciones y demostraciones | [`docs/04_MODELO_MATEMATICO.md`](docs/04_MODELO_MATEMATICO.md) |
| Qué hace cada archivo y cómo fluyen los datos | [`docs/01_ARQUITECTURA.md`](docs/01_ARQUITECTURA.md) |
| Las hipótesis, escritas **antes** de ver los resultados | [`docs/11_HIPOTESIS.md`](docs/11_HIPOTESIS.md) |

---

## 1. La pregunta y cómo se responde

El proyecto contesta cuatro preguntas, en este orden:

1. **¿Almada tiene un estilo propio?** ¿Se distinguen sus partidos de los del resto de la liga?
2. **¿Cómo es ese estilo?** Ataque, defensa, transiciones, presión, bloque, balón parado, red de pases.
3. **¿Cambia con el partido?** Marcador, minuto, localía, fuerza del rival, decisiones desde la banca.
4. **¿Es suyo o del plantel?** ¿Su estilo se mantiene cuando cambia de club?

Para eso el proyecto tiene tres capas, cada una construida sobre la anterior.

**Capa 1 — Un idioma común para toda la liga (cadenas de Markov).** Cada jugada se modela
como un recorrido del balón por una malla de 5×4 zonas de la cancha que termina en remate,
pérdida o salida del balón (una *cadena de Markov absorbente*). Sobre las 461,454 jugadas de
la liga se ajusta una **mezcla de cadenas**, y el algoritmo encuentra que las jugadas se
agrupan en tres familias reproducibles:

| familia | qué es | duración media | termina en remate |
|---|---|---|---|
| 🏃 Directa | recuperar y buscar el arco rápido | 3–4 acciones | 14 % |
| 🔁 Circulación estéril | toques en medio campo sin llegar | ~7 acciones | 2–3 % |
| 🧩 Ataque elaborado | construir y llegar por las bandas | ~9 acciones | 12 % |

También se probó con 4, 5 o más familias y con estados más ricos (dirección de llegada,
presión 360). Esos modelos predicen un poco mejor, pero sus familias cambian de una corrida a
otra, así que no se adoptaron.

**Capa 2 — El técnico como una mezcla de ese idioma.** Cada técnico queda descrito por
**cuánto usa su equipo cada familia y cuánto se la deja usar al rival**, y por cómo cambian
esas proporciones con el marcador, el minuto, la localía y el Elo del rival. Se estima con un
logit multinomial fraccional, con errores agrupados por partido y bootstrap, y se controla la
tasa de falsos positivos con Benjamini-Hochberg. Son las hipótesis H1–H17.

**Capa 3 — La historia, sección por sección.** Las métricas que pide el reto, todas medidas
como "Almada contra la liga", con su percentil entre los 45 técnicos y su fiabilidad entre
mitades de la muestra, organizadas como el reto:

| sección | qué contesta | cómo |
|---|---|---|
| 1. **Identidad** | ¿se le reconoce?, ¿cambia con el marcador y el rival?, ¿viaja con él? | reconocimiento (AUC contra permutación), fase 2 (H1–H8), rivales fuertes/medios/débiles por Elo (H22), Kalman |
| 2. **Ofensiva** | cómo sale, por dónde avanza, cómo llega y qué remata | verticalidad, carriles, tipo de entrada y de asistencia, motivos de pase, el camino típico de cada familia (H18–H21) |
| 3. **Defensa** | presión, bloque y transiciones | curva de presión 360, presión por zona, bloque con control de cámara, recuperación tras pérdida |
| 4. **Jugadores** | roles, decisiones e impacto de los cambios | red de pases y roles espectrales, H13–H17, dif. en dif. de cada cambio (H23) |
| 5. **Balón parado** | corners, tiros libres y laterales largos, a favor y en contra | rutinas y "receta Arsenal", xDefense en dos capas con el 360 del cobro, marca al hombre, línea del fuera de lugar (H24–H26) |
| 6. **Simulación** | ¿sus puntos se explican?, ¿cómo le iría en el América? | xPts exactos, simulador de partido, proyección con el plantel que encontró, validada con todas las llegadas de la liga |

Las medidas que dependen de la posición de los jugadores salen del tracking 360 (Voronoi
local, envolvente convexa, algoritmo húngaro, visibilidad del arco).

**Regla de oro:** qué cuenta como "confirmado" se escribió antes de mirar los resultados
(`docs/11_HIPOTESIS.md`). Las etiquetas son:

- 🟢 confirmado, después de controlar los falsos positivos;
- 🟡 medido, pero no sobrevive ese control;
- ⚪ no detectado;
- 🔎 solo exploratorio.

## 2. Qué encontramos

| | resultado | evidencia |
|---|---|---|
| **Se le reconoce** | un clasificador distingue sus partidos con AUC 0.886 (4.º de 45 técnicos), y de los de Pachuca con otros técnicos con 0.857 | 🟢 contra permutación |
| **Presiona encima** | presión a ≤2 m del poseedor en el percentil 94; PPDA 8.5 contra 10.3 de la liga | 🟢 |
| **Bloque estrecho** | anchura del bloque en el percentil 1 y área en el percentil 3 | 🟢 |
| **Ataque vertical** | saca largo (31.5 % en corto contra 47.1 %), conduce hacia adelante (percentil 99), remata 16.1 contra 13.3 por partido | 🟢 |
| **Su rival sufre** | le rematan 11.9 veces por partido contra 13.3; el rival rinde menos en *Directa* y *Ataque elaborado* (H8) | 🟢 |
| **Ataque** | vertical (28 cm de cada metro hacia el arco, p88), entra al área conduciendo (47 % contra 37 %) y casi sin centros; remata de más lejos | 🟢 (H18, H20, H21) |
| **Balón parado** | marca al hombre, pegado y con menos gente en el área (H26); le rematan 14 % menos por córner, pero esos remates llegan algo más limpios (xDefense, H25). La "receta Arsenal" no da ventaja en la Liga MX | 🟢 / ⚪ |
| **Banca** | sus cambios no mueven el xG (H23 ⚪), pero su equipo juega menos Directa tras ellos | ⚪ |
| **En el América** | proyección de 29.6 puntos en 17 partidos y liguilla directa en 73 % de los torneos; la receta casi no le gana a la inercia y sus intervalos son estrechos | 🔎 exploratorio |
| **No se altera** | su mezcla reacciona menos que la de la liga al marcador y al rival (H3, H6) | 🟢 |
| **Banca conservadora** | cambios del mismo puesto y pocos reacomodos de formación (H15, H16) | 🟢 |
| **Viaja con él** | ningún rasgo suyo salta al cambiar de club | 🔎 descriptivo |
| **Puntos** | 276 reales contra 263 esperados por xG y 257 por estilo | dentro del azar |

**En una frase:** Almada impone la misma idea en cada club (aprieta encima, defiende
estrecho, sale largo y remata mucho). Es el segundo técnico más reconocible de la Liga MX y
su estilo no cambia ni con el marcador ni con el club.

<p align="center">
  <img src="docs/figuras/ofensiva/percentiles.png" width="85%" alt="Percentiles de Almada frente a los técnicos de la liga"><br>
  <em>Dónde queda Almada contra los 45 técnicos en cada rasgo.</em>
</p>
<p align="center">
  <img src="docs/figuras/identidad/familias.png" width="49%" alt="Mezcla de familias de Almada contra la liga">
  <img src="docs/figuras/identidad/evolucion.png" width="49%" alt="Evolución de sus rasgos a través de sus clubes">
</p>

**Lo que no se afirma:**

- Nada de esto es causal.
- En el América solo hay 7 partidos, así que todo lo de ese club es exploratorio.
- El 360 solo ve a los jugadores que están en cámara.
- xG y OBV son modelos del proveedor; por eso la eficiencia se revisa también con la tasa de
  remate, que no depende de ningún modelo.

---

## 3. Requisitos

**Software**

| qué | versión | para qué |
|---|---|---|
| Python | ≥ 3.12 | todo |
| `polars` | ≥ 1.20 | tablas de eventos y transiciones (parquet, evaluación perezosa) |
| `numpy` | ≥ 2.0 | álgebra de las cadenas, EM, bootstraps |
| `scipy` | ≥ 1.13 | Voronoi, envolventes, algoritmo húngaro, distribuciones |
| `matplotlib` | ≥ 3.9 | todas las figuras |
| `pyyaml` | ≥ 6 | leer `config/default.yaml` |
| `orjson` | ≥ 3.10 | lectura rápida de los JSON de StatsBomb |
| `pytest`, `ruff` | ≥ 8, ≥ 0.6 | pruebas y estilo (extra `dev`) |
| `requests` | cualquiera | **solo** el descargador del 360, en un entorno aparte |

Las dependencias del paquete están declaradas en `pyproject.toml`; `requests` se instala
aparte, solo en el entorno de descarga. El análisis no usa GPU, redes neuronales ni servicios
externos; la única conexión es la descarga del 360.

**Datos** (licenciados, no están en el repo)

| dato | origen | ruta esperada |
|---|---|---|
| eventos, partidos, alineaciones (JSON de StatsBomb) | entregados por el hackathon; se verifica su integridad con `sha256sum -c data/MANIFIESTO_RAW.sha256` | `data/raw/statsbomb/{events,matches,lineups}/` |
| frames 360 | se descargan con `scripts/descargar/descargar_360.py` y credenciales de StatsBomb | `data/raw/statsbomb/frames/` |
| eras de técnicos (quién dirigió qué club y cuándo, verificadas a mano) | **incluidas en el repo** | `data/referencia/eras_api_v2/` |

⚠️ `data/raw`, `data/interim`, `data/processed` y `reports/` están en `.gitignore`: los datos de
StatsBomb **nunca** se suben. Lo único publicado son las eras y figuras agregadas (`docs/figuras/`).

## 4. Instalación

```bash
git clone https://github.com/romoruz/Historia-de-un-entrenador.git && cd Historia-de-un-entrenador

python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # instala el paquete y el comando `dtcoach`
pytest -q                        # 129 pruebas; si alguna falla, no sigas

# entorno aparte, solo para descargar el 360
python3.12 -m venv .venv-sb && .venv-sb/bin/pip install requests
```

La descarga del 360 se puede reanudar: si se corta, se vuelve a lanzar y sigue donde iba.
Las credenciales se leen de variables de entorno. Escribe cada línea por separado (no se ve
lo que tecleas):

```bash
read -rs SB_USERNAME; export SB_USERNAME
read -rs SB_PASSWORD; export SB_PASSWORD
.venv-sb/bin/python scripts/descargar/descargar_360.py --dry-run   # comprueba sin descargar
.venv-sb/bin/python scripts/descargar/descargar_360.py
```

## 5. Correr el análisis

Cada paso escribe lo que el siguiente lee. Lo de la liga se calcula **una vez** y se reutiliza.

| # | comando | qué hace | deja |
|---|---|---|---|
| 1 | `dtcoach aplanar` | JSON de StatsBomb → parquet plano | `data/interim/events/` |
| 2 | `dtcoach partidos` | fechas, marcadores, técnico por partido | `data/interim/partidos.parquet` |
| 3 | `dtcoach fase0` | eventos → transiciones → secuencias; asigna las eras | `data/processed/transitions.parquet` |
| 4 | `bash scripts/vocabulario.sh` | malla, número de familias, mezcla, reproducibilidad, bondad de ajuste y propiedades de la cadena | `data/processed/mezcla/`, `reports/mezcla/`, `reports/fase1/` |
| 5 | `dtcoach elo` | Elo previo a cada partido | `data/processed/elo.parquet` |
| 6 | `bash scripts/correr_foco.sh "Guillermo Almada" 7` | fase 2 (H1–H8), por club (H9–H12), atlas, decisiones (H13–H17), xPts | `reports/fase2/`, `reports/fase3/` |
| 7 | `bash scripts/historia.sh "Guillermo Almada"` | una vez: campos extra del JSON (`dtcoach extra`), 360 (`voronoi`, `geometria`) y la tabla de la liga; luego las siete secciones y la **demostración** (un solo BH sobre todo lo que se afirma) | `reports/historia/guillermo_almada/<sección>/` |
| 8 | `bash scripts/publicar_figuras.sh "Guillermo Almada"` | copia las figuras que usan los documentos | `docs/figuras/` |

**Partidos nuevos de la temporada.** Con credenciales de StatsBomb (`read -rs SB_USERNAME; export
SB_USERNAME`, lo mismo con `SB_PASSWORD`), `bash scripts/actualizar_datos.sh "Guillermo Almada"` hace todo:
baja la lista de partidos, los eventos, las alineaciones y el 360 nuevos de la liga
(`scripts/descargar/actualizar_temporada.py`, prueba primero con `--dry-run`), alarga las eras vigentes
si el técnico del API es el mismo (`scripts/descargar/extender_eras.py`; un cambio de técnico se agrega
a mano), rehace lo de la liga **sin reajustar el vocabulario** (las familias significan lo mismo) y
vuelve a correr la historia completa y la demostración. Los archivos nuevos no están en
`data/MANIFIESTO_RAW.sha256` (ese manifiesto es el de la entrega del hackathon).

`historia.sh` corre las pruebas primero, calcula solo lo que falte de lo que es de toda la
liga y guarda un log fechado junto a las salidas. Cada sección también se corre sola
(`dtcoach identidad | ofensiva | defensa | jugadores | balon-parado | simular | blindaje | demostracion --foco "…"`). Para
analizar a otro técnico basta repetir los pasos 6–8 con su nombre exacto, tal como aparece en
las eras. Todos los parámetros (malla, K, encogimiento, semillas, umbrales) están en
`config/default.yaml`; ninguno está escrito en el código.

**Dónde leer las salidas del técnico:**

| archivo | contenido |
|---|---|
| `reports/fase2/RESULTADOS_guillermo_almada.md` | H1–H8: mezcla de familias, contexto, eficiencia |
| `reports/fase3/POR_CLUB_guillermo_almada.md` | H9–H12 y atlas: ¿es él o el plantel? |
| `reports/fase3/DECISIONES_guillermo_almada.md` | H13–H17: cambios, reacomodos, rotación |
| `reports/fase3/SIMULADOR_guillermo_almada.md` | puntos esperados y escenarios |
| `reports/historia/guillermo_almada/identidad/IDENTIDAD.md` | reconocimiento, contexto (H1–H8), rival por Elo (H22), evolución |
| `…/ofensiva/OFENSIVA.md` | salida, progresión, llegada, ocasión, motivos, familias dibujadas (H18–H21) |
| `…/defensa/DEFENSA.md` | presión, bloque con control de cámara, transiciones, lo concedido |
| `…/jugadores/JUGADORES.md` | red de pases, roles, decisiones (H13–H17), sustituciones (H23) |
| `…/balon_parado/BALON_PARADO.md` | corners, tiros libres, laterales largos, xDefense (H24–H26), receta Arsenal |
| `…/simulacion/SIMULACION.md` | xPts, simulador de partido y proyección en su club actual |
| `…/blindaje/BLINDAJE.md` | xG contra OBV, pocos partidos, BH global de todas las hipótesis |
| `…/demostracion/DEMOSTRACION.md` | **la regla de demostración:** todas las afirmaciones (hipótesis, métricas, efectos, pruebas) en un solo Benjamini-Hochberg; solo lo demostrado se narra |

Cada `.md` viene acompañado de sus `.json` (cifras exactas) y sus `.png`.

## 6. Mapa del repositorio

```
config/default.yaml        todos los parámetros; foco.coach = técnico que se analiza
config/{presion,direccion}.yaml   experimentos no adoptados (heredan de default)
data/MANIFIESTO_RAW.sha256 huellas de los datos crudos del hackathon
data/referencia/           eras de técnicos verificadas (lo único de data/ que se versiona)
scripts/                   vocabulario.sh, correr_foco.sh, historia.sh, publicar_figuras.sh
scripts/descargar/         descargador del 360
scripts/eras/              herramientas para revisar y corregir eras
scripts/experimentos/      corridas de los experimentos no adoptados (presión, dirección, malla)
src/dtcoach/               el paquete; `dtcoach --help` lista todos los comandos
tests/                     pruebas (ligas sintéticas con rasgos sembrados y una prueba integral)
docs/                      documentación; docs/figuras/<sección>/; docs/archivo/ (histórico)
```

**El código, por capa** (el detalle y las dependencias entre módulos están en `docs/01_ARQUITECTURA.md`):

| capa | módulos clave |
|---|---|
| Datos | `aplanar.py` (JSON → parquet), `partidos.py`, `eras.py` (quién es el técnico en cada partido), `eventos.py` |
| Cadena y vocabulario | `grid.py` (malla), `possessions.py` (secuencias), `absorbing.py` (fórmulas cerradas de la cadena), `mezcla.py` (EM y reproducibilidad), `mallado.py`, `markov.py` |
| El técnico | `elo.py`, `contexto.py`, `pesos.py` (logit fraccional y bootstrap), `hipotesis.py` (H1–H8 y BH), `fase3.py`, `decisiones.py`, `simulador.py` |
| Común a las secciones | `comparar.py` (motor foco contra liga), `eventos.py`, `extra.py` (campos extra del JSON), `futbol.py` (tabla equipo-partido base), `voronoi.py` y `geometria.py` (360) |
| 1. Identidad | `identidad.py` (reconocimiento, Kalman), `rival.py` (estratos por Elo) |
| 2. Ofensiva | `ofensiva.py` (salida, progresión, llegada, ocasión, motivos, camino típico) |
| 3. Defensa | `defensa.py` (curva de presión, presión por tercio, bloque con control de cámara) |
| 4. Jugadores | `jugadores.py` (red, roles), `decisiones.py` (H13–H17), `sustituciones.py` (dif. en dif.) |
| 5. Balón parado | `balon_parado.py` (jugadas, rutinas, tasas), `xdefensa.py` (dos capas, visibilidad del arco, empírico-bayes) |
| 6. Simulación | `simulador.py` (xPts), `simulacion.py` (partido), `proyeccion.py` (club actual) |
| Robustez y salida | `blindaje.py`, `graficas.py`, `graficas_historia.py`, `graficas_secciones.py`, `cli.py`, `cli_historia.py` |

## 7. Documentación

Orden de lectura recomendado:

1. [`RESULTADOS_ALMADA.md`](docs/RESULTADOS_ALMADA.md): la historia, con las figuras.
2. [`11_HIPOTESIS.md`](docs/11_HIPOTESIS.md): qué se preguntó y con qué regla se contesta.
3. [`10_RESULTADOS.md`](docs/10_RESULTADOS.md): cada cifra con su intervalo y su prueba.
4. [`04_MODELO_MATEMATICO.md`](docs/04_MODELO_MATEMATICO.md): por qué cada método mide lo que dice medir.
5. [`03_FRAMEWORK.md`](docs/03_FRAMEWORK.md): la definición exacta de cada métrica.
6. [`01_ARQUITECTURA.md`](docs/01_ARQUITECTURA.md): el código y el flujo de datos.
7. [`06_DECISIONES.md`](docs/06_DECISIONES.md): por qué se eligió cada cosa y qué se descartó.

Para retomar el trabajo:

- [`02_ESTADO.md`](docs/02_ESTADO.md): qué falta.
- [`07_TRASPASO.md`](docs/07_TRASPASO.md): reglas de trabajo.
- [`00_ROADMAP.md`](docs/00_ROADMAP.md): el plan.

[`12_NARRATIVA.md`](docs/12_NARRATIVA.md) es el guion para la presentación. `docs/archivo/`
guarda la primera versión del proyecto y el informe de comparación: solo como referencia, sus
cifras no son citables.

## 8. Cómo se sabe que funciona

- **Pruebas contra verdades conocidas:**
  - cuentas exactas en partidos armados a mano;
  - áreas comparadas con fórmulas analíticas;
  - ligas sintéticas (`tests/sinteticos.py`) con rasgos sembrados, que cada método debe
    encontrar sin inventar nada donde no se sembró;
  - una **prueba integral** (`pytest -m lento`): una liga sintética en el formato crudo de
    StatsBomb (eventos, partidos, 360 y eras) recorre el pipeline entero, del JSON a las siete
    secciones.
- **Contrastes con los datos reales:**
  - duración esperada de la cadena contra la observada;
  - llegada al área modelada contra la observada;
  - validación del simulador dejando cada partido fuera;
  - xPts de toda la liga contra sus puntos reales (error del 0.48 %).
- **Robustez:**
  - eficiencia medida con xG, OBV y tasa de remate;
  - bootstrap de score donde hay pocos partidos;
  - control de falsos positivos sobre las 52 hipótesis juntas (ninguna etiqueta cambia).
