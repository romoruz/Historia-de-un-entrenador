# Informe técnico: método, resultados y comparación entre proyectos

**Proyecto:** `dtcoach` (Hackathon ISAC 2026, "La historia de un entrenador a través de los datos")
**Fecha:** 25 de septiembre de 2026
**Objeto de comparación:** repositorio `historia-de-un-entrenador` (mismo equipo), versión corregida del 24 de septiembre de 2026 (`REPORTE_FINAL.md`, `FRAMEWORK.md`).

---

## 0. Resumen ejecutivo

1. Los dos proyectos parten del mismo roadmap: cadena de Markov absorbente sobre una malla 5 × 4, con secuencias como unidad, encogimiento hacia la liga, Elo y bootstrap por partido. **Responden preguntas distintas.** El proyecto del compañero hace una descripción profunda de un caso (Almada en Pachuca) con muchas métricas futbolísticas. `dtcoach` construye un vocabulario común para toda la liga y contrasta hipótesis pre-registradas sobre dos técnicos y todos sus clubes.
2. **Sobre Almada, las conclusiones son mayormente compatibles.** Coinciden en tres puntos: su rasgo distintivo es defensivo, su ataque no se separa de la liga y no abandona su forma de jugar cuando va ganando. Hay **una tensión verificable**: el mecanismo defensivo. El compañero lo atribuye a presión y recuperación rápida; `dtcoach`, en Pachuca, no detecta que cambie la mezcla de jugadas del rival (H2 ⚪), pero sí que el rival genera menos xG por secuencia (H8 🟢).
3. **Ningún proyecto es superior en todas las dimensiones.** `dtcoach` es más sólido en validez inferencial, comparabilidad entre técnicos y separación técnico/plantel. El proyecto del compañero es más sólido en riqueza futbolística (PPDA, recuperación, 360, balón parado, roles), en narrativa y en el modelado de la memoria dentro de la secuencia.
4. **Este informe corrige una afirmación propia.** En `docs/10_RESULTADOS.md` se escribió que la sobredispersión de la duración "es heterogeneidad, no memoria". La evidencia sostiene una versión más débil: la heterogeneidad explica la cola y queda un efecto de primer paso, compatible con la memoria que modela el compañero.
5. Se propone un **proyecto conjunto** con ocho cambios concretos respaldados por literatura (sección 8). Los principales son: control por rival y agrupamiento por partido en las métricas defensivas del compañero; vocabulario enriquecido con un paso inicial propio (que concilia mezcla y memoria); efectos fijos de técnico y club con corrección de movilidad limitada; y bootstrap salvaje por conglomerados para etapas con pocos partidos.

---

## 1. Alcance, fuentes y advertencias

- **Fuentes de `dtcoach`:** código y reportes de `reports/fase2` y `reports/fase3`, `docs/10_RESULTADOS.md`, `docs/11_HIPOTESIS.md` y `docs/06_DECISIONES.md`.
- **Fuentes del compañero:** `REPORTE_FINAL.md` y `FRAMEWORK.md` (incluida la sección "Corrección C1 y C2") y las figuras entregadas. **No se revisó su código.**
- **Pendiente en `dtcoach`:** la fase 3a de Almada no incluye todavía su etapa en el América (7 partidos quedaron bajo el umbral de 8). Hay que correr `dtcoach fase3 --foco "Guillermo Almada" --min-partidos 7`.
- **Paridad de muestras no verificada.** Ambos reportan 139 partidos de Almada en Pachuca, pero el compañero usa solo fase regular y `dtcoach` incluye liguilla tras corregir las eras. Que el número coincida no garantiza que la lista de partidos coincida.
- **Conflicto de interés.** Este informe lo escribe el asistente de uno de los dos proyectos. Para mitigarlo: se reportan también los errores propios (secciones 2.6 y 6.1), se distingue lo verificado de lo inferido y cada crítica al otro proyecto incluye una forma de comprobarla.

---

## 2. Método de `dtcoach`

### 2.1 Datos y unidad de análisis
- 1,767 partidos de Liga MX (6 temporadas, 19 equipos), 5.7 M de eventos y 3.0 M de transiciones.
- **Unidad: la secuencia**, es decir, el tramo de una posesión de StatsBomb hasta su primera absorción (gol, remate, pérdida o fuera). El 15.6 % de las posesiones contiene más de una absorción; tratarlas como una sola trayectoria sesgaba la duración esperada entre 10 y 20 % en todos los tipos.
- Validación (prueba de cierre): la duración media predicha por la cadena, αᵀN·1, es 6.502 contra 6.509 empírica.

### 2.2 Vocabulario de la liga: mezcla de cadenas de Markov
- Modelo: cada secuencia pertenece a un tipo latente k con su propia cadena (μᵏ, Pᵏ), en la línea de las mezclas de cadenas de primer orden estimadas por EM (Cadez et al., 2003).
- Estimación: EM-MAP con encogimiento de cada Pᵏ hacia la cadena de la liga (prior Dirichlet), inicializado por **escalera**: se sube de K−1 a K partiendo un tipo.
- **Selección de K por reproducibilidad, no por verosimilitud.** Con 461 mil secuencias, la verosimilitud fuera de muestra mejora con cada K adicional. Solo K = 2 y K = 3 dan el mismo óptimo desde semillas distintas (K = 3: acuerdo 0.993). De K = 4 a K = 9, el acuerdo cae a 0.48–0.58 y el KS no mejora (0.033–0.038). **K = 3.**
- Las tres familias: *Directa* (32 %, 3.3 acciones, el mayor xG por secuencia), *Circulación estéril* (27 %, 6.6 acciones, 90 % termina en pérdida) y *Ataque elaborado* (41 %, 9.0 acciones, progresa por bandas, la que más remata).

### 2.3 Modelo de contexto
- **Logit multinomial fraccional** (Papke y Wooldridge, 1996) de las responsabilidades de cada secuencia sobre marcador, tramo de minuto, localía, Elo propio − rival, origen de la secuencia y temporada. Es consistente si la media condicional está bien especificada, aunque la respuesta no sea multinomial.
- Dos indicadores en un solo modelo: **f** (el ataque del técnico) y **g** (sus rivales contra él). La referencia son los partidos donde el técnico no jugó.
- Varianza sandwich agrupada por partido. Los efectos se reportan en puntos porcentuales, promediados sobre las situaciones reales del técnico, con intervalos por simulación de los coeficientes.

### 2.4 Hipótesis pre-registradas
- H1–H8 (identidad, contexto, eficiencia), H9–H12 (¿viajan los rasgos entre clubes?) y H13–H17 (decisiones desde la banca), con Benjamini-Hochberg por familia y reglas de lenguaje fijadas por adelantado.
- **Enmiendas declaradas.** H13 se reformuló antes de ver datos reales: la versión original aplanaba un desplazamiento temporal sembrado y una intermedia producía separación. H9–H12 se registraron después de ver H1–H8 (declarado). La réplica sobre Almada se registró antes de correrla, declarando que el atlas ya mostraba dos números suyos.

### 2.5 Fase 3
- **Por club:** el mismo modelo para cada etapa del técnico, excluyendo sus otras etapas de la referencia. Un rasgo "viaja" si aparece en ambos clubes con el mismo signo.
- **Atlas** (exploratorio): 15 etapas con ≥ 50 partidos, para poner en escala los efectos.
- **Decisiones:** tiempo de cambio (logit en tiempo discreto con desviación suave del técnico), tipo de cambio (logit multinomial por nivel de puesto), reacomodos y rotación (bootstrap).
- **Simulador:** puntos esperados exactos por Poisson-binomial (error de 0.48 % en toda la liga) y escenarios de contexto.

### 2.6 Roadmap efectivamente seguido y errores encontrados

| etapa | resultado | errores propios detectados |
|---|---|---|
| Fase 1: vocabulario | K = 3 reproducible | cuelgue por `fork` y polars; posesión ≠ secuencia; comparación de nombres de DT (2,521 falsas discrepancias); K elegido con error estándar sin parear; k-means no reproducible |
| Fase 2: Jardine contra la liga | H1–H8 | ninguno en datos reales |
| Fase 3a: por club y atlas | la defensa de Jardine viaja | — |
| Fase 3b: decisiones y simulador | H13–H17, xPts | panel de cambios sin filas del foco (detectado con datos sintéticos); comandos del CLI borrados al editar (detectado por prueba nueva) |
| Réplica: Almada | H1–H17 | etapa del América excluida por umbral (pendiente) |

Todos los errores fueron silenciosos: ninguno lanzó una excepción. Todos se detectaron por contraste entre números o con datos sintéticos de verdad conocida. Hay 61 pruebas automatizadas.

---

## 3. Método del proyecto del compañero (resumen)

- Caso de estudio: Almada en Pachuca, 139 partidos de fase regular, 19,768 secuencias y 111,894 transiciones (tras la corrección C1).
- **M0:** cadena absorbente única (K = 1 en términos de `dtcoach`) con estados G, R, P y D (D incluye faltas, fueras de lugar y detenciones), encogimiento con λ ≈ 1,500 y prueba de cierre con 0.00 % de diferencia.
- **M1:** logit multinomial **por transición** con contexto e interacción del club (2.84 M de filas). Se valida fuera de muestra con una mejora de +0.00005 nats por fila.
- **M2:** memoria dentro de la secuencia (acciones acumuladas, acción previa, presión, origen en recuperación), adoptada porque M0 sigue rechazado por KS (D = 0.049) y porque mejora +0.024 por fila fuera de muestra.
- **Defensa:** vulnerabilidad por zona, PPDA (2.24 contra 2.67), tiempo de recuperación (mediana de 26 s contra 30 s, Kaplan-Meier y log-rank), cinco métricas de bloque con 360 y balón parado.
- **Otros:** NMF de roles (k = 5, validado contra la posición registrada), Kalman sobre PPDA (98 % ruido), xG propio (AUC 0.76) y un simulador de goles (KS p = 0.78).
- **Su "k":** no hay tipos de jugada. El único k del proyecto (k = 5) es el de roles de jugadores.

---

## 4. Comparación metodológica

| dimensión | compañero | `dtcoach` | valoración |
|---|---|---|---|
| pregunta | ¿cómo juega este equipo? | ¿en qué se distingue este técnico de la liga, y es él o el plantel? | complementarias |
| alcance | 1 técnico, 1 club | toda la liga; 2 técnicos, 5 etapas | `dtcoach` permite comparar |
| unidad | secuencia (tras C1) | secuencia | igual; falta verificar paridad de conteos |
| absorbentes | G, R, P, D (D amplio) | GOAL, SHOT, LOSS, OUT | **distinto**: una falta propia es D para uno y LOSS para el otro |
| modelo base | 1 cadena + contexto por transición + memoria | mezcla de 3 cadenas + contexto sobre la familia elegida | distinto grano: *cada pase* frente a *qué tipo de jugada* |
| no-Markov | memoria (M2) | heterogeneidad (mezcla) | ambos capturan una parte (sección 6.1) |
| control por rival | en M1 (ataque), no en la defensa | Elo en ataque y defensa | `dtcoach` más completo |
| inferencia | mezcla de bootstrap por partido y pruebas que suponen independencia (log-rank, z de proporciones, Mann-Whitney) | sandwich por partido, bootstrap por partido, BH | `dtcoach` más conservador |
| multiplicidad | sin corrección (p. ej., 20 zonas) | BH por familia | `dtcoach` |
| pre-registro | bitácora fechada, sin hipótesis fijadas antes | hipótesis fijadas antes, con enmiendas fechadas | `dtcoach` |
| riqueza futbolística | alta (PPDA, 360, balón parado, roles) | baja (3 familias, decisiones) | compañero |
| técnico contra plantel | no (lo declara) | sí, parcial (2 clubes por técnico) | `dtcoach` |
| narrativa | clara, orientada al lector | técnica | compañero |

---

## 5. Resultados sobre Almada, comparados

| tema | compañero | `dtcoach` | lectura |
|---|---|---|---|
| ataque, elección | M1 δ casi nulo | H1 🟡 (±0.5 pp) | **coinciden**: sin rasgo ofensivo fuerte |
| ataque, eficiencia | convierte más bajo presión (M2, μ = +0.26) | H7 ⚪ (xG por secuencia igual a la liga) | métricas distintas; no se contradicen |
| defensa, resultado | concede menos gol en 4 de 20 zonas; rival remata menos en balón parado | el rival genera −22 % de xG en *Directa* y −13 % en *Elaborado* (H8 🟢) | **coinciden**: el rival es menos peligroso |
| defensa, mecanismo | presiona más (PPDA), recupera antes | Pachuca: H2 ⚪ (el rival no cambia su mezcla de forma detectable); conjunto: el rival juega **más** *Directa* (+1.2 pp) | **tensión** (ver abajo) |
| al ir ganando | "amplifica su idea" (δ_G > 0) | la liga se va a lo directo (+5.0 pp) y Almada la mitad (+3.2 pp) | **coinciden**: no se encierra |
| rival fuerte | no reportado | amortigua la reacción de la liga (H6 🟢) | aporte de `dtcoach` |
| estabilidad temporal | Kalman: estable | no medido | aporte del compañero |
| banca | DiD no concluyente | 90 % cambios del mismo puesto; 1.40 contra 1.81 reacomodos; 4-2-3-1 en el 66 % (H15, H16 🟢) | aporte de `dtcoach` |
| jugadores | laterales en rol ofensivo (NMF) | no medido | aporte del compañero |
| balón parado | mejor en ataque y en defensa | no medido | aporte del compañero |
| resultados | fuera de alcance | +13.4 puntos sobre lo esperado, dentro del azar (z = 0.95) | aporte de `dtcoach` |

**La tensión, formulada de forma verificable.** Si la presión de Almada acortara las posesiones rivales, se esperaría más *Directa* rival en Pachuca contra la liga. `dtcoach` no lo detecta en Pachuca (W = 3.2, p = 0.20) después de controlar por Elo y temporada. Hay dos explicaciones compatibles con los datos, y ambas se pueden probar:
- **(a) Composición del calendario.** Pachuca fue un equipo fuerte, y compararlo contra "la liga" sin controlar la fuerza del rival atribuye al estilo parte de lo que es calendario. El compañero lo reconoce como limitación.
- **(b) Inferencia.** El log-rank sobre recuperaciones, las pruebas z de proporciones y las p ≈ 0 del 360 tratan como independientes eventos de un mismo partido, lo que infla la significancia.

Ninguna de las dos invalida el hallazgo del compañero, pero ambas pueden reducir su magnitud.

---

## 6. Evaluación crítica

### 6.1 `dtcoach`: debilidades

1. **Afirmación sobre Markov demasiado fuerte (a corregir).** La mezcla con K = 3 reproduce la cola de la duración, pero no pasa el KS con n = 461 mil (D = 0.038). El residuo está en los primeros pasos (P(T > 1): 0.821 modelado contra 0.859 empírico), que es exactamente lo que capturan las variables de memoria del compañero. Versión correcta: *la heterogeneidad entre tipos explica la cola; queda un efecto de primer paso.*
2. **Vocabulario grueso.** Tres familias definidas solo por zonas: sin tipo de acción, sin tiempo y sin 360. Pasar de K = 3 no es reproducible con este espacio de estados.
3. **Dos etapas de estimación.** Las responsabilidades se tratan como fijas en el modelo de contexto, así que los intervalos no propagan la incertidumbre de la mezcla.
4. **Pocos conglomerados.** Para Santos (20 partidos) y el América (7), el sandwich tiende a sobre-rechazar (Cameron, Gelbach y Miller, 2008). La regla de "no 🟢 con menos de 20" mitiga, pero no corrige.
5. **La eficiencia depende del xG del proveedor.** Los modelos de xG tienen sesgos que se confunden con la calidad de definición (Davis y Robberechts, 2024). H7 y H8 miden la calidad de las ocasiones según ese modelo, no la calidad real de ejecución.
6. **Separación técnico/plantel limitada.** Comparar dos clubes por técnico no es un modelo de efectos fijos. Con pocos movers, las estimaciones tipo AKM sufren sesgo de movilidad limitada (Andrews et al., 2008).
7. **H17 (rotación) confundida con el calendario.** El América juega competiciones que no están en los datos.
8. **FDR por familia, no global.** Hay cuatro familias de pruebas con BH separado.
9. **Calibración del modelo de contexto con un cociente error/ruido de 1.3–1.4.** El ruido estimado es una cota inferior, así que el cociente sugiere una especificación incompleta moderada (por ejemplo, faltan interacciones marcador × minuto).

### 6.2 Proyecto del compañero: debilidades

1. **Inferencia defensiva sin controlar por rival y sin agrupar por partido** (reconocido parcialmente). Afecta al PPDA, al log-rank, a las pruebas de proporciones del balón parado y al 360 (n "muy grande" con |d| de 0.05–0.16).
2. **"Cinco confirmaciones convergentes"** que en parte miden el mismo fenómeno (presión) con los mismos eventos. La conclusión debería presentarse como **un** hallazgo con varias lentes.
3. **Kaplan-Meier con remate rival como censura.** Es un riesgo competidor: lo correcto es la incidencia acumulada (Fine y Gray, 1999).
4. **M1 por transición:** 2.84 M de filas para un efecto fuera de muestra de +0.00005 nats por fila. El costo de complejidad no se justifica frente al beneficio.
5. **Sin corrección por comparaciones múltiples** (vulnerabilidad por zona, métricas 360).
6. **Un solo club:** no puede separar técnico de plantel (lo declara). Su exploración inicial no encontró huella de técnico a nivel liga con cuatro métodos. Eso es consistente con los efectos pequeños que mide `dtcoach` (ICC ≈ 1 % en el proyecto anterior del equipo).
7. **Definición amplia de D.** Una falta propia o un fuera de lugar entregan el balón al rival y funcionalmente son pérdidas. Esto afecta la comparabilidad de P y D.

### 6.3 Fortalezas que el proyecto conjunto debe conservar

- **Del compañero:** métricas defensivas interpretables (PPDA, recuperación, bloque 360), balón parado por primera secuencia, NMF validado contra la posición, Kalman, el protocolo de validación del simulador (una realización por partido), la bitácora de correcciones y la narrativa.
- **De `dtcoach`:** la unidad y la prueba de cierre, el vocabulario reproducible, el control por Elo en ataque y defensa, el pre-registro con enmiendas fechadas, BH, el diseño por clubes, las decisiones de banca, los xPts validados y las 61 pruebas con verdad conocida.

---

## 7. ¿Son iguales las conclusiones?

**En lo sustantivo, sí son compatibles.** Los dos concluyen que Almada no se distingue por qué ataca; que su equipo es defensivamente mejor de lo esperado; que no abandona su forma de jugar cuando va ganando; y que es estable (en el tiempo según el compañero, entre clubes en parte según `dtcoach`).

**Difieren en el mecanismo defensivo y en la explicación de la no-Markovianidad.** En el primer caso por diferencias de control e inferencia. En el segundo porque cada proyecto modeló una parte distinta de un mismo fenómeno.

**Cada proyecto aporta conclusiones que el otro no puede producir.** `dtcoach` aporta la banca, la comparación entre técnicos y los puntos contra lo merecido. El compañero aporta la presión, el bloque, el balón parado y los roles.

---

## 8. Propuesta para el proyecto conjunto (con respaldo bibliográfico)

| # | cambio | justificación | referencia |
|---|---|---|---|
| 1 | **Contrato común de absorbentes:** D solo para detenciones neutrales; falta propia y fuera de lugar son pérdida. Verificar paridad de secuencias por partido entre los dos códigos. | coherencia interna (reto 5.6) | — |
| 2 | **Vocabulario con paso inicial propio:** mezcla de cadenas en la que cada tipo tiene una fila de transición distinta para el primer paso, y opcionalmente estado = zona × tipo de acción. Estimación bayesiana con priors Dirichlet para cuantificar la incertidumbre de la partición. | concilia la mezcla (cola) con la memoria (arranque); modelo estándar de agrupamiento de secuencias categóricas | Cadez et al. (2003); Frühwirth-Schnatter y Pamminger (2010) |
| 3 | **Métricas defensivas del compañero en el marco inferencial común:** una fila por equipo-partido, regresión con Elo, localía y temporada, error estándar agrupado por partido; incidencia acumulada con riesgos competidores para la recuperación; métricas 360 agregadas por partido antes de probar. | elimina el control faltante y la pseudo-replicación | Fine y Gray (1999); Cameron, Gelbach y Miller (2008) |
| 4 | **Definición operativa de presión y contrapresión** basada en la literatura, no ad hoc. | la validez del constructo "presiona más" depende de la definición | Bauer y Anzer (2021) |
| 5 | **Técnico contra plantel con efectos fijos de dos vías** (técnico y club-temporada) sobre toda la liga, aprovechando la alta rotación de técnicos, con corrección por movilidad limitada. | es el diseño que se usa para separar la contribución del técnico | Muehlheusser et al. (2018); Andrews et al. (2008) |
| 6 | **Bootstrap salvaje por conglomerados** para etapas con menos de 30 partidos (Santos, América). | el sandwich sobre-rechaza con 5 a 30 conglomerados | Cameron, Gelbach y Miller (2008) |
| 7 | **Robustez de la eficiencia:** repetir H7 y H8 con OBV (incluido en el dataset) además de xG, y reportar si cambia la conclusión. | los sesgos del xG se confunden con la calidad de definición | Davis y Robberechts (2024) |
| 8 | **Una sola familia pre-registrada para el proyecto conjunto**, BH global y validación fuera de muestra por partido en todo modelo nuevo. | evita comparaciones múltiples encubiertas y fugas de información | Davis et al. (2024) |

**Complementos opcionales:**
- Contexto de formaciones dentro del partido en lugar de contar `Tactical Shift` (Bauer, Anzer y Shaw, 2023).
- Roles NMF para tipificar sustituciones por rol real y no por posición nominal (Decroos y Davis, 2019).
- Kalman también sobre los pesos de las familias por partido.
- Un marco MDP con verificación probabilística para escenarios defensivos del tipo "qué pasaría si" (Van Roy et al., 2023).

---

## 9. Proyecto definitivo propuesto

| capa | contenido | origen | criterio de aceptación |
|---|---|---|---|
| datos y unidad | secuencias, absorbentes del contrato, eras verificadas, Elo | ambos | paridad de conteos por partido entre códigos; prueba de cierre < 1 % |
| vocabulario | mezcla con paso inicial | `dtcoach` + memoria del compañero | reproducible entre semillas (acuerdo ≥ 0.95); KS mejor que K = 3 actual en t = 1–3 |
| ataque y contexto | logit fraccional con f y g | `dtcoach` | calibración con cociente error/ruido ≤ 1.2 |
| defensa | PPDA, recuperación (riesgos competidores), bloque 360, balón parado, en regresión por equipo-partido con Elo | compañero, con la inferencia de `dtcoach` | IC agrupados por partido; BH global |
| técnico contra plantel | efectos fijos de dos vías con corrección de movilidad limitada; comparación por clubes | `dtcoach` | IC por bootstrap salvaje en etapas cortas |
| jugadores y banca | NMF de roles; tiempo y tipo de cambio por rol | ambos | validación contra posición registrada |
| tiempo | Kalman sobre PPDA y pesos de familias | compañero | razón de varianzas con IC |
| resultados | xPts exactos; simulador validado | ambos | error de liga < 1 %; KS de goles por partido |
| narrativa | reporte del compañero con las etiquetas de evidencia de `dtcoach` | ambos | un lector sin formación técnica identifica los 3 principios del técnico |

---

## 10. Limitaciones de este informe

- No se revisó el código del compañero; sus números se toman de sus documentos.
- La paridad entre las muestras de ambos proyectos no está verificada.
- La etapa de Almada en el América no está incluida en la fase 3a de `dtcoach`.
- Las críticas cuantitativas al proyecto del compañero (sección 6.2) señalan riesgos. Su magnitud real solo se conoce al rehacer los análisis con controles y agrupamiento.

---

## Referencias

- Andrews, M., Gill, L., Schank, T. y Upward, R. (2008). High wage workers and low wage firms: negative assortative matching or limited mobility bias? *Journal of the Royal Statistical Society A*, 171(3), 673–697.
- Bauer, P. y Anzer, G. (2021). Data-driven detection of counterpressing in professional football. *Data Mining and Knowledge Discovery*, 35(5), 2009–2049.
- Bauer, P., Anzer, G. y Shaw, L. (2023). Putting team formations in association football into context. *Journal of Sports Analytics*, 9(1), 39–59.
- Benjamini, Y. y Hochberg, Y. (1995). Controlling the false discovery rate. *Journal of the Royal Statistical Society B*, 57(1), 289–300.
- Cadez, I., Heckerman, D., Meek, C., Smyth, P. y White, S. (2003). Model-based clustering and visualization of navigation patterns on a web site. *Data Mining and Knowledge Discovery*, 7(4), 399–424.
- Cameron, A. C., Gelbach, J. B. y Miller, D. L. (2008). Bootstrap-based improvements for inference with clustered errors. *Review of Economics and Statistics*, 90(3), 414–427.
- Davis, J. y Robberechts, P. (2024). Biases in expected goals models confound finishing ability. arXiv:2401.09940.
- Davis, J., Bransen, L., Devos, L., Jaspers, A., Meert, W., Robberechts, P., Van Haaren, J. y Van Roy, M. (2024). Methodology and evaluation in sports analytics: challenges, approaches, and lessons learned. *Machine Learning*, 113(9), 6977–7010.
- Decroos, T. y Davis, J. (2019). Player vectors: characterizing soccer players' playing style from match event streams. *ECML-PKDD*.
- Fine, J. P. y Gray, R. J. (1999). A proportional hazards model for the subdistribution of a competing risk. *Journal of the American Statistical Association*, 94(446), 496–509.
- Frühwirth-Schnatter, S. y Pamminger, C. (2010). Model-based clustering of categorical time series. *Bayesian Analysis*, 5(2), 345–368.
- Muehlheusser, G., Schneemann, S., Sliwka, D. y Wallmeier, N. (2018). The contribution of managers to organizational success: evidence from German soccer. *Journal of Sports Economics*, 19(6), 786–819.
- Papke, L. E. y Wooldridge, J. M. (1996). Econometric methods for fractional response variables with an application to 401(k) plan participation rates. *Journal of Applied Econometrics*, 11(6), 619–632.
- Van Roy, M., Robberechts, P., Yang, W.-C., De Raedt, L. y Davis, J. (2023). A Markov framework for learning and reasoning about strategies in professional soccer. *Journal of Artificial Intelligence Research*, 77, 517–562.
