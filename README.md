# dtcoach — la historia de Guillermo Almada contada con datos

Proyecto para el **Hackathon ISAC 2026, "La Historia de un Entrenador a través de los Datos"**.
Usa los eventos y el 360 de StatsBomb de la Liga MX (1,767 partidos) para responder
**cómo juega Guillermo Almada, qué parte de eso es suyo y qué parte de sus planteles, y
si su idea viaja con él de club en club.**

> **¿Solo quieres los resultados?** → [`docs/RESULTADOS_ALMADA.md`](docs/RESULTADOS_ALMADA.md)
> (explicado para cualquiera, con dibujos).
> **¿Quieres la matemática?** → [`docs/04_MODELO_MATEMATICO.md`](docs/04_MODELO_MATEMATICO.md)
> (cada paso enunciado y demostrado).

---

## La idea en tres líneas

1. **Un idioma común para la liga.** Cada jugada es un paseo del balón por una malla de
   5×4 zonas que termina en remate, pérdida o salida. Una **mezcla de cadenas de Markov**
   aprendida sobre 461 mil jugadas encuentra tres maneras de atacar: 🏃 **Directa**,
   🔁 **Circulación estéril** y 🧩 **Ataque elaborado**.
2. **El técnico como una mezcla de ese idioma.** Cuánto usa cada familia su equipo,
   cuánto deja usar al rival y cómo cambia eso con el marcador, el rival y el minuto
   (logit multinomial fraccional con errores por partido y control del error por FDR).
3. **La capa de fútbol.** Las métricas del reto (presión, PPDA, bloque, transiciones,
   balón parado, redes de pase), medidas contra toda la liga, con percentiles entre
   técnicos, fiabilidad, pruebas de reconocimiento (¿se le distingue?) y un simulador
   de partido validado fuera de muestra.

Todo lo que se afirma pasó por **reglas escritas antes de ver los resultados**
([`docs/11_HIPOTESIS.md`](docs/11_HIPOTESIS.md)).

## Lo que encontramos (resumen)

| | resultado | evidencia |
|---|---|---|
| **Se le reconoce** | un clasificador distingue a sus equipos del resto con AUC 0.887 (2.º de 45 técnicos) y de su propio club con otros técnicos con 0.857 | 🟢 contra una nula por permutación |
| **Presiona encima** | más presión a ≤2 m del poseedor (percentil 94), PPDA 8.5 vs 10.3 de la liga | 🟢 |
| **Bloque estrecho** | la anchura de su bloque está en el percentil 1 y el área, en el 3 | 🟢 |
| **Ataque vertical** | saca largo (31.5 % en corto vs 47.1 %), conduce hacia adelante (percentil 99) y remata más (16.1 vs 13.3 por partido) | 🟢 |
| **El rival la pasa mal** | le rematan menos (11.9 vs 13.3) y le entran menos al área (9.5 vs 11.5) | 🟢 |
| **Balón parado defensivo** | marca al hombre y más cerca; le rematan 26 % menos por córner | 🟢 |
| **No se pone nervioso** | su mezcla reacciona menos que la de la liga al marcador y al rival | 🟢 (H3, H6, H8) |
| **Viaja con él** | ningún rasgo suyo da un salto al cambiar de club (Kalman con intervención) | 🔎 descriptivo |
| **Puntos** | 276 reales vs 257 esperados por el simulador | dentro del azar |

<p align="center">
  <img src="docs/figuras/estilo_percentiles.png" width="80%" alt="Percentiles de Almada frente a los técnicos de la liga"><br>
  <img src="docs/figuras/fase2_familias.png" width="48%" alt="Mezcla de familias de Almada contra la liga">
  <img src="docs/figuras/identidad_evolucion.png" width="48%" alt="Evolución de sus rasgos a través de sus clubes">
</p>

> Las figuras aparecen cuando se generan y publican con
> `bash scripts/publicar_figuras.sh "Guillermo Almada"` (ver abajo). Son agregados: no
> contienen datos crudos de StatsBomb.

---

## Instalación

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                   # 129 pruebas; si algo falla, no seguir
```

Hay un segundo entorno, separado, solo para descargar el 360 (así la descarga no toca el
entorno de análisis):

```bash
python3.12 -m venv .venv-sb && .venv-sb/bin/pip install requests
```

## Qué datos usa y qué descarga

| dato | origen | dónde queda |
|---|---|---|
| eventos, partidos, alineaciones | entregados para el hackathon; se verifican con `sha256sum -c data/MANIFIESTO_RAW.sha256` | `data/raw/statsbomb/{events,matches,lineups}/` |
| 360 (posición de los jugadores visibles en cada evento) | **se descarga** con `scripts/descargar/descargar_360.py` (reanudable, ~1,755 partidos) | `data/raw/statsbomb/frames/` |
| eras de técnicos (quién dirigió qué club y cuándo) | verificadas a mano, **versionadas** | `data/referencia/eras_api_v2/` |

Las credenciales van **solo** por variables de entorno. Escribe cada línea por separado;
no se ve lo que tecleas:

```bash
read -rs SB_USERNAME; export SB_USERNAME
read -rs SB_PASSWORD; export SB_PASSWORD
.venv-sb/bin/python scripts/descargar/descargar_360.py --dry-run
.venv-sb/bin/python scripts/descargar/descargar_360.py
```

⚠️ **Los datos de StatsBomb son licenciados.** `data/raw`, `data/interim`,
`data/processed` y `reports/` están en `.gitignore` y nunca se suben.

## De cero a la historia

```bash
source .venv/bin/activate

# 1. la liga (una sola vez)
dtcoach aplanar && dtcoach partidos && dtcoach fase0
bash scripts/vocabulario.sh                 # malla, K, mezcla, bondad y verificación de Markov
dtcoach elo

# 2. el técnico: contexto, clubes, decisiones (fases 2 y 3)
bash scripts/correr_foco.sh "Guillermo Almada" 7

# 3. el 360 y la capa de fútbol
dtcoach voronoi
bash scripts/historia.sh "Guillermo Almada"

# 4. publicar las figuras que usan los documentos
bash scripts/publicar_figuras.sh "Guillermo Almada"
```

Las salidas del técnico quedan en `reports/historia/Guillermo Almada/` (un `.md` por
componente del reto, sus `.json` y sus figuras). El foco por omisión está en
`config/default.yaml` (`foco.coach`).

## Mapa de la documentación

| documento | para qué |
|---|---|
| [`RESULTADOS_ALMADA.md`](docs/RESULTADOS_ALMADA.md) | los resultados, explicados de forma sencilla, con figuras |
| [`04_MODELO_MATEMATICO.md`](docs/04_MODELO_MATEMATICO.md) | el modelo sección por sección, con proposiciones y demostraciones |
| [`01_ARQUITECTURA.md`](docs/01_ARQUITECTURA.md) | qué datos entran, cómo fluyen, qué hace cada módulo |
| [`03_FRAMEWORK.md`](docs/03_FRAMEWORK.md) | definiciones exactas de cada métrica y objeto |
| [`11_HIPOTESIS.md`](docs/11_HIPOTESIS.md) | hipótesis H1–H17 y reglas de lectura, pre-registradas |
| [`10_RESULTADOS.md`](docs/10_RESULTADOS.md) | todas las cifras con su intervalo y su etiqueta 🟢🟡⚪🔎 |
| [`06_DECISIONES.md`](docs/06_DECISIONES.md) | por qué se eligió cada cosa (ADR) |
| [`12_NARRATIVA.md`](docs/12_NARRATIVA.md) | guion en lenguaje de cancha |
| [`00_ROADMAP.md`](docs/00_ROADMAP.md), [`02_ESTADO.md`](docs/02_ESTADO.md), [`07_TRASPASO.md`](docs/07_TRASPASO.md) | plan, estado y cómo retomar |

`docs/proyecto_viejo/` es la primera versión del proyecto, solo de consulta: sus cifras no
son citables.

## Estructura

```
config/          parámetros (default.yaml) y configuraciones de experimento
data/referencia/ eras de técnicos verificadas (lo único de data/ que se versiona)
docs/            documentación y figuras publicadas
scripts/         descargas y corridas completas (vocabulario, correr_foco, historia, publicar_figuras)
src/dtcoach/     el paquete (comando `dtcoach`)
tests/           129 pruebas: verdades exactas y ligas sintéticas con rasgos sembrados
```
