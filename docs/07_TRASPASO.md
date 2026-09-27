# 07 — Traspaso (cómo retomar este proyecto)

## Qué es esto en una frase

Construimos un **vocabulario de K tipos de secuencia de la Liga MX** (una mezcla
de cadenas de Markov absorbentes sobre 461 mil secuencias) y contamos a un
entrenador como **una mezcla particular de ese vocabulario**: qué tipos usa, qué
tipos le permiten sus rivales, cómo cambian con el contexto y con sus
decisiones, y si esa mezcla viaja con él cuando cambia de club.

## Orden de lectura

0. `../README.md` y `RESULTADOS_ALMADA.md` — qué es y qué encontró, en diez minutos.
1. `00_ROADMAP.md` — el plan. Manda sobre todo lo demás.
2. `02_ESTADO.md` — dónde estamos y **cuál es la siguiente acción**.
3. `10_RESULTADOS.md` — los hallazgos con su etiqueta 🟢🟡🔴⚪. **No cites un
   número sin leer su fila**; la §6 está explícitamente marcada como no citable.
4. `03_FRAMEWORK.md` — las definiciones (reto 5.6). Todo debe trazarse aquí.
5. `06_DECISIONES.md` — ADR-v2-01 a 35. No reabrir sin argumento nuevo.
6. `01_ARQUITECTURA.md` — qué hace cada archivo y qué se rompe al tocarlo.
6b. `04_MODELO_MATEMATICO.md` — cada paso del modelo, enunciado y demostrado.
7. `proyecto_viejo/` — solo lectura. Sus cifras **no** son citables: se
   calcularon con otra unidad (posesión, no secuencia) y otra referencia.

## Reglas de trabajo (heredadas, siguen valiendo)

- Antes de tocar nada: `source .venv/bin/activate && pytest -q`.
- Todo cambio lleva un test que capture **el número**, no que "corre sin error".
  Si el cambio es un contrato entre dos módulos, el test cruza los dos lados.
- Nada hardcodeado: va a `config/default.yaml`.
- Ninguna distancia o diferencia se reporta sin su nula.
- Nunca afirmar la nula: "no detectamos un efecto mayor a X", no "no hay efecto".
- Los tipos se nombran **después** de ver sus figuras.
- Los datos de StatsBomb son licenciados: `data/raw`, `interim` y `processed` no
  se versionan.

## Flujo de trabajo: todo pasa por git

Los cambios de código y documentación **no** se aplican con `tar` + `aplicar.sh`
desde Descargas: ese flujo dejó el config con "Tipo 1, 2, 3" mientras los
reportes locales ya tenían los nombres, y dejó el paquete instalado apuntando a
una copia en `/tmp`. La regla ahora:

1. Todo cambio vive en una rama (`git switch -c <tema>`), se prueba con
   `pytest -q` y entra a `main` por merge o PR.
2. En la máquina de análisis: `git pull` y `pip install -e .` desde **esta**
   carpeta (verifica con `python -c "import dtcoach; print(dtcoach.__file__)"`).
3. Los cambios al config (nombres, malla, K) se hacen con commit, nunca con un
   `sed` suelto en la terminal.
4. Los paquetes de revisión (`scripts/empaquetar_revision.sh`) y cualquier
   `.zip`/`.tar.gz` se comparten fuera del repo; el `.gitignore` los excluye.
5. Los datos de StatsBomb y `reports/` no se versionan; si algo de `reports/`
   es citable, su cifra va a `10_RESULTADOS.md`.

## El patrón de riesgo, otra vez

En la v1 hubo 20 bugs y **los 20 fueron silenciosos**. En la v2 van 3, también
silenciosos: un cuelgue por `fork`, una unidad de análisis mal definida y una
comparación de nombres demasiado estricta. Ninguno lanzó una excepción; los tres
producían números plausibles. **"Corre sin error" no significa nada en este
dominio.** Los tres se detectaron porque un número no cuadraba con otro
(E[T] modelo contra empírico, KS de la mezcla contra el de K=1). Mantén esos
contrastes cruzados: son el sistema inmune del proyecto.

## Mensaje para retomar

> Retomo `dtcoach` v2 (la historia de un entrenador con una mezcla de cadenas de
> Markov sobre eventos StatsBomb de Liga MX). Leí `00_ROADMAP`, `02_ESTADO`,
> `10_RESULTADOS` y `06_DECISIONES`. Entiendo que: la unidad es la **secuencia**,
> no la posesión (ADR-v2-14); la sobredispersión que rechazó a Markov es
> heterogeneidad entre tipos; K se elige por reproducibilidad, no por ajuste
> (ADR-v2-17); las eras corregidas viven en `eras_api_v2` y **hay que apuntar el
> config**; el técnico focal es Guillermo Almada. Quiero trabajar en [X]; antes corro
> `pytest -q`.
