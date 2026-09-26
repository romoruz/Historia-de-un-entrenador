# dtcoach — la historia de un entrenador (Hackathon ISAC 2026, v2)

Vocabulario de tipos de posesión de toda la Liga MX (mezcla de cadenas de
Markov) y cada entrenador como una mezcla particular de ese vocabulario.

**Lee primero `docs/00_ROADMAP.md`.** Arquitectura en `docs/01_ARQUITECTURA.md`,
decisiones en `docs/06_DECISIONES.md`, estado en `docs/02_ESTADO.md`.
El proyecto viejo está en `docs/proyecto_viejo/` (solo lectura).

## Dos entornos

```bash
source .venv/bin/activate        # análisis: dtcoach, pytest
.venv-sb/bin/python scripts/descargar/descargar_360.py --dry-run   # descargas, otra terminal
```

## Semana 1

```bash
source .venv/bin/activate
pytest -q
dtcoach aplanar && dtcoach partidos && dtcoach fase0
dtcoach cv-k
dtcoach mezcla --K <k>
dtcoach bondad --K 1 <k> --n-boot 200
```

## 360 (en paralelo, otra terminal)

```bash
read -rs SB_USERNAME; export SB_USERNAME
read -rs SB_PASSWORD; export SB_PASSWORD
.venv-sb/bin/python scripts/descargar/descargar_360.py --dry-run
.venv-sb/bin/python scripts/descargar/descargar_360.py --limite 3
.venv-sb/bin/python scripts/descargar/descargar_360.py
```

Los datos de StatsBomb son licenciados: `data/raw`, `data/interim` y
`data/processed` no se versionan.

## La historia de un entrenador (capa de fútbol, fases A–F)

```bash
source .venv/bin/activate
bash scripts/correr_foco.sh "Andre Jardine" 30     # fases 2 y 3 (si no se han corrido)
bash scripts/historia.sh "Andre Jardine"           # estilo, 360, balón parado, jugadores, identidad, simulador, blindaje
bash scripts/historia.sh "Guillermo Almada"
```

Salidas por técnico en `reports/historia/<foco>/`: un `.md` por componente del reto, sus `.json` y figuras.
Definiciones en `docs/03_FRAMEWORK.md` §5; reglas de lectura en `docs/11_HIPOTESIS.md`.
