# 11 — Hipótesis (pre-registradas)

> Escrito **antes** de correr `dtcoach fase2` con datos reales (2026-09-24).
> Cambiar una hipótesis, su prueba o su regla de decisión **después** de ver los
> resultados invalida su etiqueta 🟢: pasa a ser exploratoria y se reporta así.

## El objeto

Toda hipótesis se formula en el **vocabulario de la fase 1**: tres familias de
secuencia de la Liga MX (ADR-v2-19).

| # | familia | % liga | acciones | P(remate) | xG/sec |
|---|---|---|---|---|---|
| 1 | **Directa** | 32 % | 3.3 | 0.111 | 0.014 |
| 2 | **Circulación estéril** | 27 % | 6.6 | 0.031 | 0.003 |
| 3 | **Ataque elaborado** | 41 % | 9.0 | 0.144 | 0.011 |

Técnico foco original: **André Jardine** (América 129 partidos, San Luis 54). Las mismas
reglas se aplicaron a **Guillermo Almada** desde la fase 2; el 2026-09-27, **después** de
ver los resultados de ambos, se decidió exponer a Almada. La decisión no cambia ninguna
regla ni ningún umbral.
Referencia: la **liga sin el foco**, es decir, las secuencias de los partidos
donde su equipo no jugó (ADR-v2-22).

## El modelo

Logit multinomial **fraccional** (Papke y Wooldridge, 1996) de las
responsabilidades rₛₖ sobre el contexto, en toda la liga:

- contexto: marcador (perdiendo / empatando / ganando), tramo de minuto
  (0-29, 30-44, 45-59, 60-74, 75+), localía, Elo propio − rival, origen de
  la secuencia (juego abierto, transición, reinicio, balón parado) y
  temporada (efecto fijo, controla la deriva del proveedor);
- **f** = la secuencia es del equipo del foco (ataque), con interacciones
  f × {perdiendo, ganando, minuto 75+, local, Elo};
- **g** = la secuencia es de un rival **contra** el foco (defensa), con g × local.

Varianza **sandwich agrupada por partido**. Efectos traducidos a probabilidad y
promediados sobre las propias secuencias del foco ("contra la liga **en sus
mismas situaciones**"); intervalos por simulación de los coeficientes.

## Las hipótesis

Todas son **bilaterales**: no afirmamos una dirección antes de ver los datos.
Se controla la tasa de falsos descubrimientos con **Benjamini-Hochberg** sobre
las 12 pruebas juntas, con α = 0.05.

| id | pregunta del reto | H₀ (lo que se intenta rechazar) | prueba |
|---|---|---|---|
| **H1** | ¿tiene identidad ofensiva? | en sus mismas situaciones, su equipo usa las 3 familias en la misma proporción que la liga | Wald sobre Δπ promedio, gl = 2 |
| **H2** | ¿tiene identidad defensiva? | sus rivales logran las 3 familias en la misma proporción que contra el resto de la liga | Wald sobre Δπ promedio, gl = 2 |
| **H3** | ¿reacciona al marcador distinto que la liga? | f × perdiendo = f × ganando = 0 | Wald, gl = 4 |
| **H4** | ¿cambia distinto al final del partido? | f × minuto 75+ = 0 | Wald, gl = 2 |
| **H5** | ¿juega distinto de local que de visitante, más que la liga? | f × local = 0 | Wald, gl = 2 |
| **H6** | ¿se adapta a la fuerza del rival más que la liga? | f × Elo = 0 | Wald, gl = 2 |
| **H7.k** | ¿ejecuta mejor la misma familia? (3 pruebas) | xG por secuencia dentro de la familia k = el de la liga | bootstrap por partido |
| **H8.k** | ¿concede menos dentro de la misma familia? (3 pruebas) | xG concedido por secuencia dentro de k = el de la liga | bootstrap por partido |

H1 y H2 dicen **qué** juega. H3 a H6 dicen **cuándo cambia**. H7 y H8 dicen
**qué tan bien** lo hace. La separación es deliberada: un equipo puede generar
más peligro porque elige jugadas más peligrosas (H1) o porque ejecuta mejor las
mismas jugadas (H7). Son dos historias distintas sobre un entrenador.

## Reglas de decisión y de lenguaje

| resultado | etiqueta | cómo se dice |
|---|---|---|
| q < 0.05 | 🟢 probado | "El equipo de Jardine usa X pp más *Ataque elaborado* que la liga en sus mismas situaciones (IC …)." |
| p < 0.05 pero q ≥ 0.05 | 🟡 medido | "Hay indicios de …, que no sobreviven a la corrección por comparaciones múltiples." |
| p ≥ 0.05 | ⚪ no detectado | "No detectamos una diferencia mayor a Y pp", con Y = la cota del IC. **Nunca** "no hay efecto". |

## Qué significa cada combinación (escrito antes de ver datos)

- **H1 🟢 y H3–H6 ⚪** → *identidad por encima de reactividad*: tiene una idea
  de juego propia y no la negocia con el marcador, el minuto ni el rival.
- **H1 ⚪ y H3–H6 algún 🟢** → *técnico reactivo*: su equipo se parece a la
  liga en promedio, pero cambia distinto según la situación.
- **H1 🟢 y H7 ⚪** → la diferencia está en **qué** elige, no en qué tan bien lo
  ejecuta.
- **H1 ⚪ y H7 🟢** → juega lo mismo que todos, **pero mejor**. El mérito
  estaría más en la ejecución, que también puede ser mérito del plantel.
- **Todo ⚪** → con este vocabulario, su equipo no se distingue de la liga.
  Se reporta con las cotas: es un resultado, no un fracaso.

## Lo que estas pruebas NO dicen

- **Nada causal.** "El equipo de Jardine" incluye su plantel, su club y su
  calendario. Separar al técnico del plantel es la fase 3 (Jardine en dos
  clubes).
- Las responsabilidades se tratan como fijas; no se propaga la incertidumbre
  de la mezcla (declarado en `pesos.py`).
- El contexto es el de **la secuencia** (marcador y minuto al inicio de la
  secuencia), no el del partido completo.

## Exploratorio (no entra a la FDR ni lleva 🟢)

Cualquier corte adicional que se haga después de ver los resultados: por
temporada, solo liguilla, solo América sin San Luis, otros técnicos. Se reporta
como ⚪ descriptivo con su IC.

---

# Fase 3 — ¿Es él o es el plantel? (pre-registrado el 2026-09-24, DESPUÉS de ver H1–H8 y ANTES de separar por club)

Resultados de la fase 2 que motivan estas pruebas: H2 🟢 (sus rivales juegan
menos *Directa* y más *Ataque elaborado*), H7.2 y H7.3 🟢 (su equipo genera más
xG dentro de las mismas familias), H8.3 🟢 (concede menos xG en el *Ataque
elaborado* rival). La amenaza: el América tiene un plantel caro, y "ejecutar
mejor" puede ser mérito de los jugadores.

Diseño: el mismo modelo de la fase 2, ajustado **por separado** para Jardine en
el América (129 partidos) y en San Luis (54), cada uno contra la misma liga
(partidos sin Jardine en ningún club). Los partidos de la otra etapa se
excluyen de la referencia.

| id | pregunta | se considera que "viaja" si… |
|---|---|---|
| **H9** | ¿viaja la identidad defensiva (H2)? | en **ambos** clubes el IC de Δπ excluye 0 **con el mismo signo** en *Directa* o en *Ataque elaborado* |
| **H10** | ¿viaja la eficiencia ofensiva (H7.2, H7.3)? | en **ambos** clubes el IC excluye 0 con el mismo signo |
| **H11** | ¿viaja la eficiencia defensiva (H8.3)? | ídem |
| **H12** | ¿su mezcla ofensiva cambia entre clubes? | la diferencia América − San Luis en Δπ ofensivo tiene IC que excluye 0 (aproximación: estimaciones independientes, referencia compartida) |

**Cómo se lee:** "viaja" apunta al técnico, porque el rasgo aparece con dos
planteles distintos. "Solo en el América" es compatible con el plantel. Con 54
partidos, San Luis tiene poca potencia, así que un ⚪ en San Luis se reporta
con su cota ("no detectamos más de X") y **no** como "no viaja".

## Atlas de técnicos (exploratorio, sin FDR ni 🟢)

El mismo modelo para cada era (técnico × club) con al menos 50 partidos. Sirve
para una sola cosa: poner en escala los efectos de Jardine ("¿1 pp es mucho?").
No se usa para afirmar nada de otros técnicos.

---

# Fase 3b — Sus decisiones (pre-registrado el 2026-09-24, antes de programar y de correr)

Hasta aquí medimos lo que hace **el equipo**. Esta fase mide lo que decide **el
técnico** desde la banca: cuándo cambia, qué tipo de cambio hace, cuándo
reacomoda la formación y cuánto rota. Es la parte del reto 5.3 ("uso de
jugadores, cambios en alineaciones, impacto de sustituciones").

Unidad: **equipo-partido** (y equipo-minuto para el tiempo de los cambios),
contra la liga sin el foco. Mismo control de contexto que la fase 2: marcador,
minuto, localía, Elo propio − rival y temporada. Varianza sandwich por partido.

| id | pregunta | H₀ | prueba |
|---|---|---|---|
| **H13** | ¿cambia antes o después que la liga? | el riesgo por minuto de abrir una ventana de cambios es el de la liga (f = 0 y f × tramo = 0) | logit en tiempo discreto por equipo-minuto (min. 45–90), Wald sobre f y f × tiempo, gl = 2 · *enmendada, ver abajo* |
| **H14** | ¿su banca reacciona al marcador distinto que la liga? | f × perdiendo = f × ganando = 0 en ese mismo modelo | Wald gl = 2 |
| **H15** | ¿qué tipo de cambio hace (ofensivo / mismo puesto / defensivo)? | f = f × perdiendo = 0 en un logit multinomial por sustitución | Wald gl = 4 |
| **H16** | ¿reacomoda la formación más o menos que la liga? | `Tactical Shift` por partido igual que la liga | bootstrap por partido |
| **H17** | ¿rota más o menos su once titular? | Jaccard entre onces consecutivos igual que la liga | bootstrap por partido |

Benjamini-Hochberg sobre H13–H17 (familia propia, α = 0.05). Mismas reglas de
lenguaje: 🟢 q < 0.05 · 🟡 p < 0.05 sin FDR · ⚪ "no detectamos más de X".

Definiciones declaradas antes de ver datos:
- **Ventana de cambio**: minuto en el que el equipo hace al menos una sustitución
  (varias en el mismo minuto son **una** decisión). Solo segundo tiempo; los
  cambios del primer tiempo cuentan como ventanas ya usadas (suelen ser lesiones).
- **Tipo de cambio**: nivel del puesto (portero 0, defensa 1, contención 2,
  medio 3, mediapunta y extremo 4, delantero 5). Ofensivo si el que entra juega
  ≥ 1 nivel más adelante que el que sale; defensivo si ≥ 1 más atrás; si no,
  mismo puesto. El puesto del que entra es el de su primer evento.
- **Rotación**: 1 − Jaccard entre los once titulares de partidos consecutivos del
  mismo técnico en el mismo club. No controla días de descanso (limitación).

## Exploratorio (sin FDR)

- **Puntos contra puntos esperados (xPts)**: con el xG de cada remate, los
  goles de cada equipo son Poisson-binomiales (exacto, sin simular). ¿Sacó sus
  equipos más o menos puntos que los que su xG y el de sus rivales predecían?
  Mide suerte y definición, no estilo. Validación previa: en toda la liga, la
  suma de xPts debe coincidir con la de puntos reales.
- **Escenarios**: el modelo de la fase 2 hacia adelante. "¿Qué mezcla de
  familias y cuánto xG por secuencia produce su equipo si va perdiendo al 75' de
  visitante contra un rival más fuerte?", contra la liga en el mismo escenario.
  Supuesto declarado: la eficiencia dentro de cada familia no depende del
  contexto.

**Enmienda a H13 (2026-09-24, antes de correr con datos reales).** Validando
con datos sintéticos se probaron tres versiones de la desviación del foco:

| versión | sin efecto sembrado | adelanto sembrado de 12 min |
|---|---|---|
| f proporcional (original, gl = 1) | — | estimaba 3 min: **aplana** el desplazamiento |
| escalones de 5 min (gl = 9) | rechazaba con p ≈ 1e-35 (**separación**) | −11.4 min |
| escalones gruesos (gl = 3) | 3 de 12 rechazos con p = 0 (separación en el tramo de referencia) | −11.1 min |
| **nivel + pendiente en el tiempo (gl = 2)** | **0 de 20 rechazos** | **−11.9 [−13.2, −10.8]**; con −5 sembrado, −4.6 [−6.2, −3.4] |

Versión final: la liga conserva tramos de 5 minutos y el foco se desvía con un
nivel f y una pendiente f × tiempo. La pregunta es la misma; cambia la prueba, y
todo se decidió sin haber visto datos reales (ADR-v2-25).

---

# Réplica: Guillermo Almada (pre-registrado el 2026-09-24, ANTES de correr)

**Mismas hipótesis H1–H17, mismas pruebas, mismas reglas de decisión y de
lenguaje**, aplicadas a Guillermo Almada con `scripts/correr_foco.sh`. No se
ajusta nada a partir de lo que salió con Jardine.

Etapas: Pachuca (~139 partidos, la principal), Santos (~17–20) y América (8,
temporada 2026/27 en curso). La fase 3a compara Pachuca contra cada una de las
otras dos (H9–H12 por par).

**Reglas específicas por el tamaño de muestra, fijadas antes de ver datos:**
- Un club con menos de 20 partidos del foco **no recibe 🟢** en ninguna prueba:
  la varianza sandwich se apoya en muy pocos conglomerados y sus IC tienden a
  quedar demasiado estrechos. Máximo 🟡, y se lee como exploratorio.
- Con menos de 30 partidos, un "no se detecta en ambos" (H9–H11) **no** se
  reporta como "no viaja", sino como "sin potencia para saberlo".
- El América con Almada (8 partidos) es un **primer vistazo**, no una conclusión.

**Lo que ya vimos antes de pre-registrar (se declara):** el atlas de la fase 3a
incluyó a Almada en Pachuca con 0.7 pp de separación ofensiva (p = 0.034) y
0.7 pp de separación defensiva (p = 0.17). Esos números salen de un ajuste sin
BH y con menos simulaciones; la fase 2 de Almada los recalcula con el diseño
completo.

---

# Fase 1 v3 — reglas de decisión (pre-registrado el 2026-09-25, ANTES de correr `scripts/fase1.sh`)

La fase 1 no prueba hipótesis sobre técnicos: construye el vocabulario. Sus tres
decisiones se toman con reglas fijadas aquí, para que ninguna se ajuste mirando
los resultados de las fases 2 y 3.

| decisión | regla | comando |
|---|---|---|
| **malla** | la rectangular de mayor log-densidad predictiva fuera de muestra (pliegues por partido); entre las que quedan a menos de 1 EE pareado de la mejor, la de **menos** zonas | `dtcoach mallado --aplicar` |
| **paso inicial** | con K = 3 provisional: se adopta si la mejora pareada de verosimilitud fuera de muestra tiene t > 2 **y** el KS de la duración baja | `dtcoach comparar-paso --K 3 --aplicar` |
| **K** | con la malla y la variante elegidas, el **mayor** K reproducible (rango de J < 50 y acuerdo suave ≥ 0.95 entre 3 semillas) | `dtcoach curva-k` |

**Cómo se leerán las métricas de la cadena** (fijado antes de verlas):
- *Memoria explicada por los tipos* ≥ 50 % → la no-Markovianidad es sobre todo heterogeneidad entre tipos de jugada; < 50 % → hay memoria real dentro de cada tipo. Se reporta con IC por bootstrap de partidos.
- *Primer toque*: si la información mutua del primer paso **condicionada al tipo** sigue siendo > 0 con IC que excluye 0, el efecto es real y justifica P⁰.
- *Llegada* (análisis de primer paso): el modelo se acepta como descripción si P(llega) y E[acciones | llega] quedan a menos de 0.02 y 0.2 acciones de lo observado.
- La *agregación contigua* es diagnóstica: si supera a la mejor malla rectangular por más de 1 EE, se reporta como línea de trabajo (particiones irregulares), sin cambiar el pipeline.

---

## Enmienda a la fase 1 v3 (2026-09-26, DESPUÉS de ver la corrida 12×8 y ANTES de correr `scripts/vocabulario.sh`)

**Qué pasó con las reglas originales** (corrida del 2026-09-25):
- *Malla:* el puntaje de densidad subió de forma monótona hasta 12×8, **el candidato más fino**, y la agregación contigua no fusionó ninguna celda. La regla eligió un borde: no encontró un óptimo, solo que la ubicación de la siguiente acción es predecible al menos a 10 m.
- *Paso inicial:* regla cumplida sin ambigüedad (t = 13.2; KS 0.043 → 0.007). **Se mantiene.**
- *K:* con 12×8 **ningún K cumplió la regla** (K = 2: acuerdo suave 0.979 pero rango de J = 130 > 50). El script eligió K = 2 con un valor por defecto que **no estaba pre-registrado**: error corregido (ahora se detiene).

**Por qué se enmienda y no se acepta 12×8.** La regla de la malla optimizaba predecir la siguiente ubicación, no el propósito de la fase 1: un vocabulario reproducible. Con 96 zonas el vocabulario no es reproducible para ningún K; con 5×4 lo era para K = 3. Hay un conflicto entre resolución espacial y estabilidad del vocabulario, y el propósito manda.

**Reglas enmendadas** (se declara que se fijaron conociendo los resultados de 12×8 y los anteriores de 5×4):
1. **Reproducibilidad:** rango de J entre semillas **por secuencia** ≤ 50 / 461,454 ≈ 1.08·10⁻⁴ (el umbral original, reescalado para no depender de la escala de J), acuerdo suave ≥ 0.95 y **cada tipo con al menos el 1 % de las secuencias** (un componente vacío no es una familia).
2. **Malla del vocabulario:** se prueban 8×5, 6×4 y 5×4 en ese orden (de la más fina a la más gruesa), con el paso inicial ya adoptado; se elige la **primera** cuyo mayor K reproducible sea ≥ 3, con ese K. Si ninguna llega a 3: la más fina con algún K reproducible. Si ninguna: se detiene.
3. **La corrida 12×8 se conserva** como resultado de resolución espacial y de las métricas formales que no dependen del vocabulario (verificación, irreversibilidad, llegada de la liga).
4. **Memoria:** la información mutua plug-in queda solo como diagnóstico. La medida oficial es la **ganancia de verosimilitud fuera de muestra** del orden 2 y del primer toque sobre el orden 1, sin y con condicionar al tipo (ADR-v2-34). La regla de lectura (≥ 50 % explicada por los tipos → domina la heterogeneidad) se mantiene.

# Experimento 360: zona × nivel de presión (pre-registrado el 2026-09-26, ANTES de correrlo con datos reales; ADR-v2-36)

Solo se ha corrido con datos sintéticos. Reglas:

1. **¿Mejora la cadena?** `dtcoach presion-cv` compara la malla sola (L = 1)
   contra los candidatos (cuantiles de la distancia al rival con L = 2–4;
   k-means sobre los tres rasgos con L = 2–5). Métrica: densidad predictiva del
   siguiente punto en partidos no vistos (ADR-v2-32). Se elige el mejor, y entre
   los que quedan a menos de 1 EE pareado de él, el de menos estados. **Hay
   mejora** si el elegido supera a la malla sola por más de 2 EE pareados. Si no
   la hay, el experimento termina y se queda la malla 5×4.
2. **¿Más tipos?** Con la regla 1 cumplida, `curva-k` (K = 2–5) sobre el control
   y sobre el estado aumentado, con el criterio de reproducibilidad de ADR-v2-35.
   **Se adopta el vocabulario con presión solo si su mayor K reproducible es ≥ 4
   y mayor que el del control.** Si no, el vocabulario oficial sigue siendo 5×4
   con K = 3, y la presión se reporta como resultado de la fase 1 (regla 1).
3. Si se adopta, los tipos se nombran después de ver sus figuras, y las fases 2 y
   3 se rehacen solo con partidos con 360; las conclusiones se comparan con las
   de la §16 de `10_RESULTADOS.md`, como se hizo en la réplica v3.

# Experimento dirección: zona × dirección de llegada (pre-registrado el 2026-09-26, ANTES de correrlo con datos reales; ADR-v2-37)

Solo se ha corrido con datos sintéticos. Reglas:

1. **¿Mejora la cadena?** `dtcoach direccion-cv`, con la misma métrica y regla
   que el experimento 360: hay mejora si el elegido supera a la malla sola por
   más de 2 EE pareados. Si no la hay, termina y se queda la malla 5×4.
2. **¿Sostiene el vocabulario?** `curva-k` (K = 2–5) sobre el estado aumentado.
   El control es la curva oficial de la malla 5×4 (misma muestra: no requiere
   360). **Se adopta si su mayor K reproducible es ≥ 3 y ≥ el del control.** El
   objetivo es absorber la memoria sin perder identificabilidad, no
   necesariamente más tipos.
3. **Se reporta (no decide):** la memoria residual, es decir, cuánto agrega la
   zona anterior una vez sabida la dirección, frente a lo que agrega sobre la
   malla sola.
4. **Combinación con el 360:** solo si los dos experimentos cumplen por separado
   sus reglas 1 y 2. El estado combinado (zona × dirección × presión) se evalúa
   con las mismas reglas, contra el mejor de los dos por separado.

# Capa de fútbol (fases A–F): reglas de lectura (pre-registradas el 2026-09-26, ANTES de correrlas con datos reales)

Solo se han corrido con datos sintéticos (126 pruebas, rasgos sembrados). Reglas:

1. **Diferencia con la liga (cada métrica).** Bootstrap por partido; BH dentro de
   cada bloque (ofensiva, defensiva, transiciones, 360, concedido, balón parado).
   🟢 q < 0.05 · 🟡 p < 0.05 sin sobrevivir BH · ⚪ no detectado. Sin 🟢 con menos
   de 20 partidos del foco en la muestra (ADR-v2-28).
2. **Rasgo del técnico.** Una métrica se narra como rasgo SOLO si cumple las tres:
   🟢 contra la liga, percentil ≤ 20 o ≥ 80 entre etapas, y fiabilidad entre mitades
   ≥ 0.5 en la liga. Si solo cumple la primera, se reporta como "diferencia en esta
   muestra", no como identidad.
3. **Técnico o plantel.** Un rasgo "viaja" si es 🟢 o 🟡 con el mismo signo en sus
   dos clubes (mismo criterio que H9–H11).
4. **Identidad (5.2).** Hay identidad reconocible si el AUC fuera de muestra contra
   la liga supera el percentil 95 de su nula por permutación. Contra su mismo club
   con otros técnicos, la misma regla responde "se distingue del club".
5. **Evolución.** q/r < 0.05: identidad estable en esa serie. Un cambio de club es
   claro si |z| > 2 (z conservador).
6. **Balón parado.** Razón de tasas con IC sandwich; 🟢 si el IC excluye 1 y
   sobrevive BH dentro de balón parado.
7. **Cambios.** El impacto del primer cambio es exploratorio salvo que el IC del DiD
   excluya 0 en xG propio o rival.
8. **Blindaje.** Si la eficiencia (H7, H8) no coincide en signo entre xG, OBV y tasa
   de remate, se narra como dependiente del modelo de xG. Si el p del bootstrap de
   score de H3–H6 no confirma el del Wald, manda el bootstrap. Las etiquetas del BH
   global se reportan junto a las de familia; si alguna baja, se dice.

## Enmienda: H17 pasa a exploratoria (2026-09-26, DESPUÉS de ver la fase 3b)

La rotación del once se confunde con el calendario de competiciones que no están
en los datos (Copa, Concachampions). No es una decisión por el resultado (H17 era
🟢 para Jardine y pasa a no contar), sino por la validez de la medida. H17 se reporta
con su estimación y su p, pero no entra a BH ni recibe 🟢.

# Fase G — las secciones nuevas (pre-registrado el 2026-09-29, ANTES de correrlas con datos reales)

Programadas y probadas solo con datos sintéticos (`tests/test_secciones.py`, efectos sembrados, y
`tests/test_integral.py`, el pipeline completo sobre una liga sintética). Foco: Guillermo Almada.

## Hipótesis

| id | sección | pregunta | métricas que deciden (03_FRAMEWORK) |
|---|---|---|---|
| H18 | ofensiva | ¿Ataca más vertical que la liga? | `directness`, `velocidad_avance` |
| H19 | ofensiva | ¿Progresa por carriles distintos a los de la liga? | `prog_banda`, `prog_interior`, `prog_centro` |
| H20 | ofensiva | ¿Llega al área y genera remates de otra manera? | `entrada_*` (centro, filtrado, atrás, conducción) y `asist_*` (centro, filtrado, atrás, sin pase) |
| H21 | ofensiva | ¿Sus motivos de pase difieren de los de la liga? | `motivo_ABAB`, `ABAC`, `ABCA`, `ABCB`, `ABCD` |
| H22 | identidad | ¿Su estilo se ajusta al nivel del rival distinto que la liga? | Δ = (foco − liga)_fuertes − (foco − liga)_débiles en `posesion`, `field_tilt`, `directness`, `remates`, `xg`, `ppda`, `presion_aplicada`, `altura_bloque`, `saque_corto` |
| H23 | jugadores | ¿Sus cambios cambian el juego distinto que los de la liga? | dif. en dif. emparejada de `xg_propio`, `obv_propio`, `xg_rival` (±10 min) |
| H24 | balón parado | Prevención: ¿niega remates en centros a balón parado más que la liga? | `xd_prev` |
| H25 | balón parado | Supresión: ¿empeora los remates que concede más que la liga? | `xd_remate` |
| H26 | balón parado | ¿Se organiza distinto que la liga (marca, línea, trampa)? | `al_hombre`, `dist_marca`, `altura_linea_tl`, `fuera_juego_tl` |

## Reglas

1. **p de una hipótesis.** El mínimo de los p de sus métricas (bootstrap por partido, como la
   capa de fútbol) por el número de métricas (Bonferroni dentro de la hipótesis). En H22, el
   p de cada Δ sale de la aproximación normal con los IC de cada estrato.
2. **Multiplicidad.** BH entre las hipótesis de cada sección (ofensiva: H18–H21; identidad: H22;
   jugadores: H23; balón parado: H24–H26) y, como sensibilidad, en el BH global del blindaje
   junto con H1–H17. 🟢 q < 0.05 · 🟡 p < 0.05 · ⚪ no detectado. Sin 🟢 con menos de 20 partidos
   del foco (ADR-v2-28).
3. **Lectura de H22.** 🟢 = "cambia con el rival de otra forma que la liga": se dice en qué métrica
   y en qué sentido. ⚪ = "se ajusta como todos": su idea no depende del rival más de lo normal.
   Los estratos son del Elo previo del rival con cortes de la liga (p25, p75), fijados antes.
4. **Lectura del xDefense (H24, H25).** Además de la etiqueta, se reporta la contracción
   empírico-bayesiana entre técnicos-club. Si τ² ≈ 0 (no hay variación real detectable entre
   equipos), se dice así aunque el foco salga 🟢 contra la liga: la diferencia es de esta
   muestra, no un rasgo que distinga técnicos. Es la lección del trabajo previo del equipo.
5. **Control de cámara del bloque.** El "bloque estrecho" se sostiene solo si la anchura con la
   cámara abierta (≥ 70 m de ancho visible) conserva el signo y excluye el 0. Si no, se retira
   la frase y se explica por qué.
6. **Receta Arsenal.** Descriptiva: se reporta la diferencia de xG por corner de la receta contra
   el resto de la liga con su IC; no entra a la FDR ni lleva 🟢. Nunca se afirma que una rutina
   "causa" goles: el equipo que la elige no es un equipo al azar.
7. **Proyección.** Exploratoria. Se cita solo junto con su validación sobre todas las llegadas de
   la liga (error por partido contra la inercia y cobertura del intervalo del 80 %). Si la
   receta no le gana a la inercia, se dice.
8. **Sustituciones: quién entra.** Descriptivo (pocos partidos por jugador); no se narra un
   "suplente de impacto" sin la dif. en dif. del conjunto.
