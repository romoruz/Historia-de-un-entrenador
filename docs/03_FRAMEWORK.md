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

---

## 5. Capa de fútbol (fases B–F): objetos y métricas

> Todo se mide sobre los MISMOS eventos que la cadena (`eventos.leer`): marco de
> ataque de quien ejecuta, tiempo reglamentario, destino de pases, conducciones y
> remates como en `extract_actions`. Umbrales en `config.futbol`.

### 5.1 Objetos nuevos

| objeto | definición operativa |
|---|---|
| **Equipo-partido** | la unidad de todas las métricas: un equipo en un partido, con su técnico (eras) y el técnico rival |
| **Métrica** | razón de sumas por equipo-partido (`m__n / m__d`): "por partido" si el denominador es 1, "por pase", "por corner", etc. si cuenta oportunidades |
| **Lado** | *propio* = lo que hace el equipo del técnico; *rival* = lo que hacen sus rivales contra él (lo concedido) |
| **Liga de referencia** | los equipo-partido de partidos donde el foco no jugó (ADR-v2-22) |
| **Acción progresiva** | pase completo de juego (sin balón parado) o conducción que termina ≥ 10 m más cerca del centro del arco y a ≤ 75 % de su distancia inicial |
| **Entrada** | pase completo o conducción que empieza fuera y termina dentro del último tercio (x ≥ 80) o del área (x ≥ 102, 18 ≤ y ≤ 62) |
| **Field tilt** | pases del equipo iniciados en su último tercio / los de ambos equipos |
| **PPDA** | pases del rival en su 60 % (x ≤ 72 en su marco) / acciones defensivas propias (Duel, Interception, Foul Committed) en x ≥ 48 del marco propio |
| **Recuperación** | Ball Recovery o Interception; su altura es la x en el marco propio |
| **Pérdida** | posesión propia sin remate seguida de una posesión rival en juego abierto (Regular Play) |
| **Recuperación tras pérdida** | la siguiente posesión propia en juego abierto, sin remate rival de por medio; tiempo = su inicio − el inicio de la posesión rival. Censurada si la secuencia la corta un balón parado, un remate rival o el fin del tiempo |
| **Transición ofensiva** | posesión propia en juego abierto que sigue a una del rival; se mide lo que produce en sus primeros 10 s |
| **Presión (360)** | una acción está presionada si un rival visible está a ≤ 2 m (distancia de `rasgos_360`, ADR-v2-36) |
| **Bloque (360)** | los jugadores visibles del equipo sin balón (sin portero), con ≥ 6 visibles: altura media, anchura, profundidad y área de su envolvente convexa, en su marco |
| **Jugada a balón parado** | un SAQUE (corner, tiro libre, lateral) con su desenlace en una ventana de 15 s; definición completa en §6 |
| **Marcaje (360)** | en el frame del saque, asignación óptima defensor–atacante dentro de x ≥ 96, 14 ≤ y ≤ 66 (algoritmo húngaro); §6 |
| **Etapa** | técnico-club; los percentiles y la fiabilidad usan etapas con ≥ 30 partidos |
| **Huella** | por equipo-partido: su mezcla de familias en ataque, la de sus rivales y las métricas estandarizadas contra la liga |

### 5.2 Cantidades derivadas

| cantidad | lectura en la cancha |
|---|---|
| P(llegar) y acciones hasta el último tercio o el área | desde el inicio de la secuencia, con la cadena del grupo encogida hacia la liga (primer paso, `markov.llegada`) |
| V = N c del grupo contra la liga | dónde el balón "vale" más para el técnico que para la liga |
| S(t) de la pérdida | Kaplan-Meier: P(aún sin recuperar a los t segundos) |
| Cadena sobre jugadores | N, ν (por quién pasa el balón), B (P(remate) desde cada jugador) |
| Grupos espectrales | comunidades del grafo de pases (laplaciano normalizado, eigengap) |
| AUC de reconocimiento | qué tan distinguible es su huella en partidos no vistos |
| Nivel local (Kalman + RTS) | la tendencia de cada rasgo partido a partido; q/r ≈ 0 = identidad estable |
| Simulación de partido | P(gana/empata/pierde), marcadores y dominio de xG a partir de la mezcla de ambos equipos |

### 5.3 Supuestos y límites adicionales

1. **Los umbrales son convenciones declaradas**, no descubrimientos: 10 m / 75 %
   (progresiva), 2 m (presión), 5 s y 10 s (transiciones), ≥ 6 defensores (bloque).
2. **El 360 no es tracking.** El bloque y el marcaje se miden con los jugadores
   visibles; con menos de 6 defensores visibles el frame no cuenta.
3. **OBV y xG son modelos del proveedor.** Por eso la eficiencia se contrasta con
   ambos y con la tasa de remate, que no depende de ningún modelo (fase A).
4. **Una métrica que no se repite entre mitades de partidos no describe a un
   técnico** (fiabilidad de Spearman-Brown < 0.5), aunque salga significativa.
5. **El simulador es exploratorio**: supone independencia entre secuencias dado el
   estilo y no cambia la mezcla con el marcador dentro del partido.

---

## 6. Balón parado (G5)

> Código: `balon_parado.py`, `geometria.saque`, `xdefensa.py`. Umbrales en `config.futbol`.

| objeto | definición operativa |
|---|---|
| **Saque** | pase con `pass_type` Corner, Free Kick o Throw-in, o remate con `shot_type` Free Kick |
| **Tipos** | `corner`; `tl_directo` (el saque es el remate); `tl_centrado` (x ≥ 60 y destino en el área); `tl_otro` (x ≥ 60, destino fuera del área); `lateral_largo` (destino en el área); `lateral_zona` (x ≥ 80, destino fuera del área; en 5.4 solo los de x ≥ 90) |
| **Centro a balón parado** | corner, tiro libre al área o lateral largo: la unidad del xDefense |
| **Desenlace** | remates, xG y goles del equipo que saca en los 15 s siguientes, cortados en la siguiente reanudación de cualquier tipo (incluye la segunda jugada) |
| **Zona de destino** | con u = (y_fin − 40)·s, s = −1 si el saque viene de y < 40: *corto* (fuera del área), *primer palo* (u > 4), *segundo palo* (u < −4), *área chica* (\|u\| ≤ 4, x ≥ 114), *penal* (\|u\| ≤ 4, x < 114) |
| **Técnica** | cerrado (Inswinging), abierto (Outswinging), recto (Straight), de `dtcoach extra` |
| **Rutina** | técnica × zona de destino |
| **Primer contacto** | primer evento con balón tras el saque en ≤ 5 s (sin recepciones ni duelos): del que saca = ataque; del rival = defensa |
| **Frame del saque (360)** | atacantes y defensores en el área y en el área chica, poste cercano/lejano cubierto (defensor a ≤ 2 m), atacantes a ≤ 2 m del portero; solo cuenta con ≥ 80 % del área visible |
| **Marca al hombre / zonal** | defensor del área cuya asignación óptima (húngaro) está a ≤ 2 m de su atacante / el resto |
| **Línea del fuera de lugar** | legal: x del penúltimo defensor, portero incluido (regla 11), en el frame de un tiro libre; **táctica** (la que se narra): la misma sin los defensores parados sobre la línea de gol (x ≥ 118); altura = 120 − x (m desde su arco); solo con el portero visible |
| **Receta Arsenal** | corner cerrado al área chica o al primer palo con ≥ 1 atacante a ≤ 2 m del portero |
| **xD prevención** | Σ (p̂(remate) − remate) / centros en contra; p̂ de un logit L2 fuera de muestra con la INTENCIÓN del cobro y el ataque, sin rasgos de la defensa |
| **xD supresión** | Σ (xG_base − xG_full) / remates a balón parado concedidos; los dos modelos difieren solo en la geometría defensiva de la foto del remate |
| **Familias** | *corners*; *tiros libres* (`tl_directo`, `tl_centrado`, `tl_otro`); *laterales* (`lateral_largo`, `lateral_zona`) |
| **Lateral del último cuarto / octavo** | lateral sacado desde x ≥ 90 / x ≥ 105, vaya o no al área (5.4; `lateral_cuarto_x`, `lateral_octavo_x`) |
| **Área chica (laterales)** | el destino cae en el área chica de 6 yardas (x ≥ 114, 30 ≤ y ≤ 50); la zona "área chica" de los corners es solo su franja frente al arco |
| **Intervienen** | en una jugada con remate: jugadores distintos del que saca que tocan el balón entre el saque y el primer remate (remate incluido); 2 = peinada + remate |
| **Tiro libre peligroso** | a ≤ 30 m del centro del arco |
| **Barrera** | defensores de campo a ≤ 12 m del balón cuya sombra toca el arco, en el remate de un tiro libre directo |
| **Cadena del xDefense** | por saque, p̂κ − g = prevención + alejamiento + supresión + portero (04 §16.6), en goles por 100 saques; xD al defender, xO = −xD al atacar |
| **Visibilidad del arco** | fracción del ángulo del arco no tapada por defensores de campo entre el remate y el arco (discos de 0.5 m) |

**Supuestos declarados.** (1) El destino de un pase interceptado es donde se cortó: la zona
puede subestimar centros despejados. (2) La capa 1 no puede separar la defensa de la
calidad del cobro que el rival elige contra esa defensa. (3) El 360 ve una foto del saque,
no los bloqueos ni los movimientos. (4) La capa 2 se ajusta con todos los remates de la
liga: supone que la física del arco es la misma en juego abierto y a balón parado (el tipo
de jugada entra como covariable).

## 7. Fase ofensiva (G1)

> Código: `ofensiva.py`. Umbrales en `config.futbol`.

| objeto | definición operativa |
|---|---|
| **Carril** | banda (y < 18 o y > 62), interior (18–30 o 50–62), centro (30–50): las líneas del área y del área chica |
| **Pérdida en su tercio** | pase de juego fallado, Miscontrol o Dispossessed con x < 40 |
| **Pase largo** | pase de juego de ≥ 30 m |
| **Verticalidad (directness)** | Σ (x_fin − x) / Σ longitud en pases completos de juego y conducciones (Fernández-Navarro et al. 2016) |
| **Velocidad de avance** | Σ (x_max − x0) / Σ duración, en posesiones de juego que nacen antes de x = 60 |
| **Cambio de orientación** | pase completo de juego con \|Δy\| ≥ 35 m |
| **Tipo de entrada al área** | pase atrás (cut back), filtrado (through ball), centro (cross), conducción u otro pase, en ese orden de prioridad |
| **Zona 14** | 84 ≤ x < 102, 30 ≤ y ≤ 50 |
| **Asistencia de un remate** | el key pass de StatsBomb (`shot_key_pass_id`) con su tipo; sin key pass = remate individual o rechace |
| **Motivo de pase** | tres pases seguidos del equipo, cada uno recibido por quien da el siguiente; se reetiquetan los cuatro jugadores por orden de aparición (ABAB, ABAC, ABCA, ABCB, ABCD) |
| **Camino típico de una familia** | ruta de máxima probabilidad desde su zona de inicio más frecuente hasta el remate en la cadena de esa familia (Dijkstra con pesos −log P); la del foco usa su cadena encogida hacia la de la liga |

## 8. Contexto por nivel del rival (G2)

| objeto | definición operativa |
|---|---|
| **Estrato del rival** | por el Elo PREVIO del rival: fuerte (≥ p75 de la liga), medio, débil (≤ p25); cortes de toda la liga |
| **Ajuste al rival** | Δ = (foco − liga)_fuertes − (foco − liga)_débiles de una métrica; ≠ 0 = se ajusta distinto que la liga |

## 9. Fase defensiva, lo nuevo (G3)

| objeto | definición operativa |
|---|---|
| **Presión por tercio** | fracción de toques del rival con un defensor a ≤ 2 m según dónde toca: en su tercio (x < 40, presión alta), en el medio, o en el tercio del que defiende (x ≥ 80) |
| **Curva de presión** | para r = 0.5…8 m, P(el defensor más cercano está a ≤ r) en los toques del rival |
| **Cámara abierta** | frame cuya área visible cubre ≥ 70 m del ancho de la cancha: control del encuadre para el bloque |
| **Bloque típico** | medianas de altura, anchura y profundidad del bloque con la cámara abierta |

## 10. Sustituciones (G4)

| objeto | definición operativa |
|---|---|
| **Efecto de un cambio** | Δ = medida en los 10 min siguientes − en los 10 anteriores, menos el Δ medio de los cambios de la liga en la misma celda (tramo de 5 min × signo del marcador) |
| **Medidas** | xG propio, OBV propio, xG del rival, field tilt, fracción de secuencias de cada familia |
| **Reacomodo tras el cambio** | Tactical Shift del mismo equipo en ≤ 3 min después del cambio |
| **Quién entra** | suplentes del foco: entradas, minuto medio y xG del equipo por 90' con él en cancha contra antes (descriptivo) |

## 11. Proyección (G6)

| objeto | definición operativa |
|---|---|
| **Índices de un equipo** | ataque A y defensa D en una ventana: xG a favor (en contra) sobre el esperado ante sus rivales, con la fuerza de cada rival estimada por Maher SIN sus partidos contra el equipo y ajustada por localía |
| **Llegada** | un técnico nuevo en un club con ≥ 17 partidos antes y ≥ 17 con él |
| **Efecto de llegada** | log A(post) − log A(pre) y lo mismo con D |
| **Efecto del técnico** | la media de sus llegadas anteriores al club que se proyecta, contraída hacia la media de todas las llegadas de la liga (normal-normal) |
| **Plantel que encontró** | los índices del club en sus 17 partidos anteriores a la llegada |
| **Proyección** | torneo a una vuelta simulado 10 000 veces con goles ~ Poisson(xG esperado) |

**Supuestos declarados.** Los goles de un partido son Poisson independientes dado el xG
esperado (sin la corrección de Dixon-Coles de marcadores bajos); el efecto de un técnico
es multiplicativo y constante; los rivales conservan la fuerza de sus 17 partidos previos.

