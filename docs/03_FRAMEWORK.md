# 03 — Framework analítico (reto 5.6)

> Cada elemento de la entrega debe poder trazarse hasta una definición de este
> documento. Si una figura o una métrica no se deriva de estos objetos, no entra.

---

## 1. Objetos

| objeto | definición operativa | dónde vive |
|---|---|---|
| **Evento** | acción registrada por StatsBomb; coordenadas en [0,120] × [0,80] desde el marco de ataque de quien la ejecuta (y crece hacia abajo) | `aplanar.py` |
| **Acción** | evento cuyo tipo es `Pass`, `Carry` o `Shot`, ejecutado por el equipo en posesión. Todo lo demás (recepción, presión, duelo) **no** genera transición | `config.possession.moving_types` |
| **Zona** | celda de una malla 5 × 4 uniforme (franjas en x: 0-24-48-72-96-120) | `grid.StateSpace` |
| **Estado** | zona ∈ {1..20}. La fase de origen **no** entra al estado (ADR-v2-03) | `grid.StateSpace` |
| **Absorbentes** | `GOAL`, `SHOT_NOGOAL`, `LOSS`, `OUT` | `grid.ABSORBING` |
| **Transición** | una por acción: (zona de inicio) → (zona final) si conserva la posesión, o → absorbente si la termina | `possessions.build_transitions` |
| **Absorción terminal** | si la última acción deja el balón en zona, se añade una transición artificial a `LOSS`. Sin ella, N = (I−Q)⁻¹ se infla | `_append_terminal_absorption` |
| **Posesión** | grupo (match_id, possession) de StatsBomb, restringido a las acciones del equipo en posesión | `poss_uid` |
| **Secuencia** ⭐ | tramo de una posesión desde su inicio hasta su **primera absorción**. Una posesión con dos absorciones son dos secuencias. **Es la unidad de la cadena y de todo lo que se reporta** (ADR-v2-14) | `seq_uid` |
| **Tipo de secuencia** | una de las K clases latentes de la mezcla, con su propia cadena (μᵏ, Pᵏ) y su peso πₖ | `mezcla.Mezcla` |
| **Fase ofensiva** | construcción: x < 48 · progresión: cruzar de x < 48 a x ≥ 72 · ocasión: absorber en `GOAL` o `SHOT_NOGOAL` | derivadas de la zona |
| **Origen** | de dónde nace la secuencia (`play_pattern`): juego abierto, transición, reinicio, balón parado. **Covariable de los pesos**, no parte del estado | columna `play_pattern` |
| **Era** | periodo continuo de un club bajo un mismo técnico, con fecha de inicio y fin | `data/referencia/eras_api_v2/` |

---

## 2. Cantidades derivadas (todas en forma cerrada)

Con P = [[Q, R], [0, I]] y ρ(Q) < 1:

| cantidad | fórmula | lectura en la cancha |
|---|---|---|
| N | (I − Q)⁻¹ = Σ Qᵏ | visitas esperadas a cada zona: dónde vive el balón |
| t | N·1 | acciones esperadas hasta que la secuencia termina |
| B | N·R | probabilidad de terminar en gol, remate, pérdida o fuera |
| **V** | N·c, con cᵢ = xG de remates desde i / acciones desde i | **xG esperado que termina produciendo una secuencia que pasa por i** (ADR-v2-05) |
| ν | αᵀN normalizado | distribución de visitas = estacionaria de la cadena **reiniciada** (ADR-v2-07) |
| S(t) | Σₖ πₖ μᵏᵀ Qₖᵗ 1 | supervivencia de la duración (phase-type), sin simular |

**π de la mezcla no es una distribución estacionaria**: es la proporción de
secuencias de cada tipo. La estacionaria de una cadena absorbente es degenerada
(toda su masa en los absorbentes).

---

## 3. Supuestos explícitos

1. **Markov dentro de cada tipo.** Se contrasta, no se asume: KS de la duración
   contra la phase-type (`dtcoach bondad`). Residuo conocido en t = 1–3.
2. **Un pase incompleto va a su destino intentado** (`end_location`). Es el
   criterio de Van Roy et al. (2023) y de xT.
3. **Una acción, una transición** (inicio → fin), sin encadenar fin → inicio.
   Evita que el arrastre del control contamine la cadena (Rudd 2011, Singh 2018).
4. **El encogimiento es hacia la liga del mismo torneo**, nunca hacia una
   referencia que contenga al foco (fuga de prior).
5. **El bloque de remuestreo es el partido**, no la posesión: las secuencias de
   un partido comparten rival, marcador y árbitro (ADR-v2-04).
6. **Las eras se toman de la fuente verificada**; el `managers` del API solo
   verifica. Las discrepancias se revisan a mano (ADR-v2-08).
7. **Los tipos se nombran después** de ver visitas, desenlaces y secuencias
   típicas, nunca antes (ADR-v2-06).

---

## 4. Alcance y límites

**Qué captura este framework**
- dónde vive el balón, cuánto dura una secuencia y qué peligro genera;
- qué tipos de secuencia existen en la Liga MX y en qué proporción los usa cada
  equipo, con y sin contexto;
- la fase defensiva, como la mezcla de tipos que los rivales logran ejecutar
  contra un equipo;
- las decisiones observables del técnico: alineación, formación, `Tactical
  Shift`, sustituciones, rotación.

**Qué queda fuera**
- Nada es **causal**: se describe lo que hizo un equipo, no se aísla la decisión
  del técnico del plantel, el presupuesto o el calendario.
- **Sin balón**: el movimiento de los jugadores solo entra vía 360, que son
  instantáneas en el momento de cada evento, **no tracking**: no hay velocidades
  ni trayectorias.
- Lo que la cámara no ve (fuera del `visible_area`) **no se imputa**.
- Un técnico con menos de ~60 partidos en un club no es analizable con esta
  malla. Es un hallazgo sobre la rotación de la Liga MX, no un defecto.
- La malla 5 × 4 es una elección prudente por esparsidad, no un límite
  matemático.
