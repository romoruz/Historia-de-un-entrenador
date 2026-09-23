# Plan de cierre — arquitectura final y fusión con el proyecto de córners

> 2026-09-16. Plan, no ADR: las ADR-55 a 58 se escriben con sus predicciones
> **después** de la sonda (`scripts/34_sonda_cierre.py`) y **antes** de su
> código, y cada una se commitea sola. Entrega en noviembre.

## 1. El principio que ordena todo

El reto pide la historia de **un** entrenador. Cada pieza se calcula para las
53 eras analizables de los 18 clubes (esa es la referencia), pero **se
reporta** alrededor del entrenador del reto. La liga es el instrumento; la
historia es el resultado.

Un solo objeto en todo el framework (5.6, coherencia interna):

- **Posesión** = `possession` de StatsBomb dentro de un partido.
- **Estado** = zona 5×4 × fase (`open`, `transition`, `restart`, `set_piece`).
- **Cadena absorbente** sobre esos estados, con GOAL, SHOT_NOGOAL, LOSS y OUT.
- **Toda comparación** contra la liga sin el club, en los mismos torneos
  (ADR-53/54).
- **Toda incertidumbre** por bootstrap por partido, salvo que una ADR diga otra
  cosa.

## 2. La fusión: cadena de Markov + proyecto de córners

Tu proyecto descomponía

$$P(G\mid C) = P(S\mid C)\cdot P(G\mid S, C).$$

La cadena ya calcula el primer factor, sin modelo nuevo. Sea $\alpha_C$ la
distribución de los estados iniciales de las posesiones que nacen de córner
(`play_pattern = From Corner`), y $B = (I-Q)^{-1}R$ la matriz de absorción.
Entonces:

$$\underbrace{P(S\mid C)}_{\text{Capa 1: prevención}} = \alpha_C^\top\big(B_{\cdot,\text{GOAL}} + B_{\cdot,\text{SHOT}}\big),
\qquad
E[T\mid C] = \alpha_C^\top N\mathbf 1 .$$

Es la misma función `derivadas` de `08_ic_derivados.py`, con $\alpha$
restringido a córners. Eso tiene tres ventajas sobre la logística de tu
Capa 1:

1. **Coherencia**: es el mismo objeto que el resto del informe.
2. **Incluye las segundas jugadas**: la cadena sigue la posesión después del
   centro, que era la razón de tu `corner_id`.
3. **No hay fuga del objetivo**: la cadena no usa el desenlace del pase como
   predictor.

El segundo factor es tu Capa 2, que ya vive en `dtdecoder.xg_remate`:

$$P(G\mid S, C) \approx E\big[\,xG_{\text{full}}\mid \text{remate nacido de córner}\big],
\qquad xD_{\text{shot}} = xG_{\text{base}} - xG_{\text{full}}.$$

- **Ofensivo**: el club atacando. **Defensivo**: los rivales atacando contra el
  club, que es donde `goal_open` mide organización y marcaje (5.4).
- **La logística de intención del cobro** (técnica, altura, zona de destino) se
  conserva como **perfil descriptivo** ("cómo cobra"), no como predictor. Tu
  propio resultado mostró que no separa equipos.
- **Control del producto**: la cadena también da
  $\alpha_C^\top B_{\cdot,\text{GOAL}}$ directamente. Si difiere mucho de
  $P(S\mid C)\cdot E[xG\mid S,C]$, la aproximación (un remate por posesión,
  xG calibrado) falla, y se reporta.
- **Lo mismo vale para los tiros libres** (`From Free Kick`) y los saques de
  banda en campo rival.

**Qué no se hereda**: sklearn y PyMC (ADR-19), el ranking de equipos, y el
bootstrap por tiro (pasa a ser por partido).

## 3. Arquitectura final

```
data/prior_liga/transitions.parquet ─┐
data/api/eventos_api_ligamx/ ────────┤
data/raw_api/indice_partidos.csv ────┤
                                     ▼
 30  H4 · E[T] y xT por era vs liga (ADR-53)          → did_h4_v1.json          ✅
 33  D1 · presión por era vs liga (ADR-54)            → did_presion_v1.json     ⏳
 35  5.4 · balón parado: cadena + goal_open (ADR-55)  → balon_parado_v1.json
 36  5.2 · contexto: localía, marcador, momento,
          rival (ADR-56)                              → contexto_v1.json
 37  5.3 · jugadores: minutos, roles, sustituciones
          (ADR-57)                                    → jugadores_v1.json
 38  5.5 · métricas del proveedor por era: xG, OBV,
          pases progresivos, field tilt, validación
          B·GOAL vs xG                                → metricas_v1.json
 39  panorama y serie temporal del entrenador         → panorama_v2.json
                                     ▼
 12  reporte.html (ADR-58): narrativa centrada en el entrenador
```

`25`, `26` y `29` quedan como históricos: leen el volcado viejo o fueron
reemplazados.

## 4. Diseños previstos (se fijan en su ADR)

**ADR-55 · Balón parado.**
- Unidad (club, entrenador), ofensivo y defensivo.
- Cantidades: volumen por partido; $P(S\mid C)$ y $E[T\mid C]$ con la cadena;
  $E[xG\mid S,C]$; $xD_{shot}$ medio; mapas de destino y de remate.
- Todo relativo a la liga del mismo torneo.
- **Modelo de xG ajustado una sola vez sobre toda la liga**, fuera de pliegue,
  con indicador de balón parado. La regla 3 de `26` se mantiene.
- Familia pequeña, solo del entrenador del reto.

**ADR-56 · Contexto.**
- Localía y rival (tercio de la tabla del torneo) son etiquetas de partido:
  nula por permutación **entre partidos dentro del torneo**.
- Marcador y momento (bloques de 15 minutos) son etiquetas de posesión: nula
  por permutación **dentro del partido**.
- Marcador y momento se reportan cruzados.
- Métricas: E[T], P(remate), π de presión y volumen de balón parado.

**ADR-57 · Jugadores.**
- Minutos y roles por zona (usando `player_id` en las transiciones).
- Continuidad del once titular.
- Efecto de sustitución: antes y después del cambio en el mismo partido,
  comparado contra el efecto de sustitución de la liga **al mismo minuto**,
  porque el minuto y el marcador confunden.

**ADR-58 · Informe.**
- La estructura de `ROADMAP_CIERRE_RETO.md` §4.
- El framework explicado para el jurado.
- Cada cifra con su fuente JSON y su etiqueta 🟢🟡🔴⚪.
- Verificado por `verifica_reporte.py` y `humo_reporte.py`.

## 5. Secuencia de trabajo

1. **h2_16**: sonda. D1 humo → corrida completa (en paralelo).
2. **Balón parado**: ADR-55 borrador → commit → h2_17 (`35` + tests) → humo →
   corrida.
3. **Contexto**: ADR-56 → commit → h2_18 → humo → corrida.
4. **Métricas del proveedor y jugadores**: ADR-57 → h2_19 (`37`, `38`).
5. **Informe**: ADR-58 → h2_20 (`39`, reescritura de `12`) → verificación → push.

Cada corrida larga se lanza con `nohup python -u` y escribe a un archivo nuevo.
