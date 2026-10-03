# 06 — Decisiones v2

Las ADR del proyecto viejo (`archivo/proyecto_viejo/06_DECISIONS.md`) siguen vigentes
salvo que una de estas las sustituya. Numeración propia: `ADR-v2-NN`.

## ADR-v2-01 — La referencia es la liga del mismo torneo, sin el club
Con toda la Liga MX disponible, el prior y la línea base dejan de ser «los
rivales del América». El contraste del técnico es contra la liga del mismo
torneo excluyendo su club (la deriva del proveedor, ADR-53 viejo, obliga a
comparar dentro del torneo). Invalida la lectura vieja de λ*.

## ADR-v2-02 — El núcleo es una mezcla de cadenas, no M2 ni HMM
La cadena de orden 1 se rechazó por sobredispersión (§6 viejo: «al menos dos
poblaciones de posesión»). La mezcla modela esas poblaciones y da tipos
narrables con formas cerradas por tipo. M2 (memoria) y el HMM solo entran si
la mezcla NO pasa el KS de duración.

## ADR-v2-03 — La fase de origen sale del estado
`phase` es constante dentro de una posesión: en el estado solo parte la cadena
en 4 subcadenas y multiplica parámetros ×4. Estado = 20 zonas + 4 absorbentes.
El `play_pattern` se conserva en la tabla como covariable de los pesos.

## ADR-v2-04 — Bloque = partido
Pliegues de CV y bootstrap técnico-vs-liga por partido (`estimate.match_folds`).
Las posesiones de un partido comparten rival, marcador y árbitro. El bootstrap
por posesión del proyecto viejo tuvo cobertura 0.944 en su diseño; el nuevo
contraste es contra la liga y no se hereda esa validación sin repetirla.

## ADR-v2-05 — Valor de zona con xG, no con gol
$c_i$ = xG de remates desde $i$ / acciones desde $i$; $V = Nc$. Mezclar 1 para
el gol con xG para el fallo mete varianza del resultado sin información.

## ADR-v2-06 — K fuera de muestra; los tipos se nombran después
El LRT K vs K+1 no tiene nula χ² (frontera + no identificabilidad). K por
log-verosimilitud en partidos no vistos, regla de 1 error estándar, más el KS
de duración. Etiquetas fijadas ordenando por E[T]. Nombres solo tras ver
visitas, desenlaces y posesiones típicas.

## ADR-v2-07 — π de la mezcla no es una estacionaria
π_k es la proporción de posesiones de tipo k. La estacionaria de la cadena
absorbente es degenerada (masa solo en absorbentes); la de la cadena
reiniciada es ∝ αᵀN y es lo que reporta `Cadena.visitas` (hay test).

## ADR-v2-08 — Eras: se USAN las verificadas, el API solo VERIFICA
`data/referencia/eras_api/coach_eras_<club>.csv` es la fuente. `managers` del
API se contrasta en `reports/verificacion_eras.csv`. Discrepancias se revisan
a mano; nunca se corrigen en silencio (bug #14).

## ADR-v2-09 — `spawn`, no `fork`, en el aplanado
Polars es multihilo; `fork` con hilos vivos se congela sin error (se reprodujo
en los tests). Bug silencioso #1 de la v2, evitado.

## ADR-v2-10 — K no se elige con la regla 1-EE sin parear
Primera corrida real (354,428 posesiones, 5 pliegues por partido): la regla
1-EE sin parear dio K=5, pero las diferencias pliegue a pliegue entre K y K-1
son positivas en los 5 pliegues hasta K=8 (t de 69 a 10). Con esta muestra la
verosimilitud mejora con cualquier K razonable: no puede elegir sola. K se
elige por (1) ganancia acumulada pareada (K=4: 78 %, K=5: 87 %, K=6: 92 %),
(2) KS de duración, (3) tipos distintos y estables entre arranques del EM,
(4) interpretabilidad. Se reportan los cuatro. `cv_k` ahora guarda los
pliegues y el resumen pareado.

## ADR-v2-11 — `min_actions = 1`: las posesiones de una acción entran
Con `min_actions = 2` se descartaban las posesiones de UNA acción que termina
en absorbente (despeje, pelotazo perdido, robo inmediato). Dos problemas en la
primera corrida real: (1) el modelo, que no conoce ese truncamiento, subestimaba
E[T] y xG/posesión de TODOS los tipos a la vez (mismo signo en los 5); (2) en la
perspectiva defensiva esas posesiones son el producto de una presión exitosa
(bug #20 viejo). En un vocabulario de liga son una forma de jugar, no ruido.
`bondad.t_min = 1`. `resumen_tipos` sabe condicionar en `t_min = 2` para
comparar con el diseño viejo.

## ADR-v2-12 — Un K es admisible solo si sus arranques coinciden
Primera corrida: con K=5 los 4 arranques del EM llegaron al mismo objetivo
(ΔJ < 1); con K=4 y K=6 difirieron en cientos o miles y varios tocaron
`max_iter`. Un K sin arranques concordantes no tiene tipos: tiene óptimos
locales. `ajustar` reporta, por arranque, J, convergencia y fracción de
posesiones asignadas al mismo tipo que el mejor (tras emparejar etiquetas).
Criterio: todos convergen y acuerdo mínimo ≥ 0.9. `max_iter` sube a 1000.

## ADR-v2-13 — Nombres de DT: se comparan por tokens
El API trae el nombre legal completo; las eras, el de uso y un sufijo de etapa
(I, II). Comparar cadenas dio 2,521 falsas discrepancias. `mismo_dt`: sin
acentos, sin sufijo romano, un conjunto de tokens contenido en el otro.

## ADR-v2-14 — La unidad de la cadena es la SECUENCIA, no la posesión de StatsBomb
StatsBomb no cierra la posesión si el mismo equipo conserva el balón tras un
remate, un pase fallido o un balón fuera. La cadena absorbente termina en la
primera absorción. `segmentar_secuencias` corta cada posesión en una secuencia
por absorción (`seq_uid`); `poss_uid` se conserva. Evidencia: en la corrida con
`min_actions = 1`, E[T] del modelo quedaba 10–20 % por debajo del empírico en
todos los tipos y el KS de la mezcla (0.078) salía PEOR que el de K=1 (0.061);
con datos sintéticos, pegar secuencias como StatsBomb reproduce el síntoma
(E[T] 5.48 vs 7.12) y cortarlas lo elimina (5.49 vs 5.49). Test de cierre de
flujo en `test_mezcla.py`. Las ADR-v2-10 a 12 se revalidan después de este cambio.
Posible alcance: parte de la sobredispersión que rechazó Markov en el proyecto
viejo (§6) podría ser este artefacto. Se verifica, no se afirma.

## ADR-v2-15 — Estabilidad = reproducibilidad del óptimo + tarjetas (sustituye el criterio de ADR-v2-12)
Tras ADR-v2-14, ningún K cumplía "acuerdo ≥ 0.9 entre TODOS los arranques":
con 461 mil secuencias el EM tiene varios óptimos locales y un arranque malo
no dice nada del bueno. Criterio nuevo, con 10 arranques: (1) el mejor óptimo
debe alcanzarse al menos dos veces (|ΔJ| ≤ 50); (2) se reporta, por arranque,
la mayor diferencia en las tarjetas que se narran (π, E[T] relativa,
P(remate)). Si las tarjetas de los óptimos cercanos casi no cambian, la
historia es robusta aunque J difiera.

## ADR-v2-16 — Resultado: la sobredispersión es heterogeneidad
Con secuencias (ADR-v2-14) la cadena reproduce E[T] (6.502 vs 6.509) y xG por
secuencia en cada tipo. K=1 subestima la cola (P(T>20): 0.034 vs 0.051); la
mezcla la reproduce (0.051 con K=5) y el KS baja de 0.059 a 0.035. El residuo
se concentra en t = 1–3: el primer paso de una secuencia absorbe menos que
una acción cualquiera desde la misma zona ("efecto primer toque"). Lectura:
Markov de primer orden falla en la liga porque mezcla tipos de posesión;
dentro de cada tipo basta, salvo el primer paso. Extensión mínima candidata
(no obligatoria): fila de transición propia para el primer paso.

## ADR-v2-17 — El EM se inicializa por ESCALERA, no por k-means (sustituye ADR-v2-15)
Con 461 mil secuencias, 10 arranques de k-means para K=5 dieron 9 óptimos
locales distintos y el mejor apareció UNA vez; entre óptimos, E[T] de un tipo
variaba hasta 12 % y π hasta 0.013. Un vocabulario que depende de la semilla no
es un vocabulario. Se sustituye la inicialización: se ajusta K=1 y se sube de
K-1 a K PARTIENDO un tipo (se prueba partir cada uno con `n_corto` iteraciones
de EM y sigue el mejor). Es determinista dada la semilla y llega al mismo
óptimo desde semillas distintas. Criterio de aceptación de un K:
`dtcoach reproducibilidad --K k` con rango de J < 50 y acuerdo ≥ 0.95 entre
semillas. `init=kmeans` se conserva como contraste independiente.

## ADR-v2-18 — K = 4, 5 y 6 no son reproducibles; se baja al K más chico que lo sea
Primera corrida de `dtcoach reproducibilidad` (escalera, 3 semillas por K):

| K | rango de J entre semillas | acuerdo mínimo | máx. ΔE[T] relativa |
|---|---|---|---|
| 4 | 1,815.6 | 0.582 | 0.896 |
| 5 | 1,225.0 | 0.567 | 0.777 |
| 6 | 1,073.3 | 0.539 | 0.452 |

Ninguno cumple el criterio (rango < 50, acuerdo ≥ 0.95). Las diferencias de J
son del orden de 0.003 nats por secuencia: los datos casi no distinguen entre
particiones que asignan distinto a más del 40 % de las secuencias. Lectura:
a partir de K = 4 los "tipos" dividen un continuo de manera arbitraria; no son
objetos identificables. Decisión, prevista en `02_ESTADO.md` (riesgo 1): se usa
el K más chico que pase la prueba. Se evalúan K = 2 y K = 3 (K = 3 ya captura el
73 % de la ganancia de verosimilitud fuera de muestra). La estructura fina de
K = 5 queda como descripción ⚪, nunca como base de inferencia.

## ADR-v2-19 — K = 3: el vocabulario de la Liga MX tiene tres familias
`dtcoach reproducibilidad`: K = 2 (rango de J 0.1, acuerdo 1.000) y **K = 3
(rango 7.8, acuerdo 0.993)** pasan; K = 4, 5 y 6 no (ADR-v2-18). K = 3 ajusta
casi igual que K = 5 (KS 0.038 contra 0.035; E[T] 6.504 contra 6.509
empírico). Se fija **K = 3**. `dtcoach curva-k` produce la figura que lo
justifica (ajuste, KS y reproducibilidad contra K). Subir K no se descarta por
costo, sino porque los tipos adicionales no son identificables: con esta
muestra la verosimilitud siempre premia un tipo más, así que no puede ser el
criterio. La riqueza espacial no se pierde: cada familia tiene su propia
matriz Pᵏ de 20 × 24, su mapa de visitas y su valor de zona.

## ADR-v2-20 — Nombres de las tres familias (fase 1 cerrada)
Nombradas después de ver `tipos_K3_visitas.png` y `tipos_K3_inicio.png`
(ADR-v2-06): **1 · Directa** (nace en la salida propia o en recuperaciones en
el último tercio, dura 3.3 acciones y tiene el mayor valor de zona frente al
área), **2 · Circulación estéril** (nace en medio campo, retrocede, 90 % de
pérdidas, 0.003 xG por secuencia), **3 · Ataque elaborado** (progresa por los
carriles exteriores del tercio 72-96, la que más remata). La curva de K hasta
K = 9 confirma la elección: solo K = 2 y K = 3 son reproducibles, el KS no
mejora al subir K (0.033 a 0.038) y el peso del tipo más chico cae de 0.30 a 0.07.

## ADR-v2-21 — Contexto: logit multinomial fraccional con sandwich por partido
Sustituye al M1 del roadmap original (logit por transición). La respuesta es
el vector de responsabilidades, no una etiqueta: se usa el logit fraccional de
Papke y Wooldridge (1996), consistente si la media está bien especificada, con
varianza sandwich agrupada por partido (no supone la varianza multinomial y
respeta la dependencia entre secuencias del mismo partido). Se reportan
efectos en probabilidad promediados sobre las secuencias del foco, nunca
coeficientes. Columnas colineales se quitan y se reportan como "no estimables".

## ADR-v2-22 — Una sola referencia para ataque y defensa: los partidos sin el foco
El modelo lleva dos indicadores: f (ataque del foco) y g (sus rivales contra
él). La base, con f = g = 0, son exactamente las secuencias de partidos donde
el foco no jugó. Así el ataque y la defensa se comparan contra la misma liga,
y ninguna secuencia del foco contamina la referencia.

## ADR-v2-23 — Elo con K y h por log-pérdida
K y h minimizan la log-pérdida de los resultados (cuasi-verosimilitud
binomial con S ∈ {0, ½, 1}) después de un calentamiento de 150 partidos. Se usa
el Elo **previo** al partido. Se reporta la calibración (E contra S por
quintil) y se avisa si el óptimo cae en el borde de la rejilla.

## ADR-v2-24 — Fase 3: separar al técnico del plantel con sus dos clubes
Para cada club del foco se ajusta el mismo modelo de la fase 2 contra la misma
referencia, y los partidos de su OTRA etapa se excluyen de la referencia
(`fase3.reasignar_foco`): si quedaran, el técnico se compararía contra sí
mismo. Un rasgo "viaja" si aparece en ambos clubes con el mismo signo
(H9–H11, pre-registradas antes de correr). H12 compara la mezcla ofensiva entre
clubes con un SE aproximado (estimaciones independientes; la referencia
compartida es casi toda la liga, así que la correlación es despreciable, pero
no cero: declarado). El atlas de técnicos es exploratorio: solo pone en escala
los efectos del foco. Su medida resumen es la distancia de variación total
entre la mezcla del técnico y la de la liga en sus mismas situaciones, en pp.

## ADR-v2-25 — Tiempo de los cambios: desviación suave del foco
El logit en tiempo discreto con un efecto f proporcional subestimaba un
adelanto sembrado de 12 minutos (traducía 3). Escalones por tramo para el foco
lo recuperaban, pero producían separación en tramos sin cambios del foco y
rechazaban sin efecto (p ≈ 1e-35). Versión final: la liga con tramos de 5
minutos y el foco con nivel + pendiente en el tiempo (gl = 2). En 20 réplicas
sin efecto, 0 rechazos; con −12 y −5 minutos sembrados, estima −11.9 y −4.6.
Enmienda hecha ANTES de correr con datos reales y registrada en `11_HIPOTESIS.md`.

## ADR-v2-26 — El panel de cambios se arma con la tabla completa (bug silencioso #4 de la v2)
Para la referencia se excluyen los rivales del foco, pero el marcador de cada
minuto necesita al rival. Armar el panel con la tabla ya filtrada descartaba
TODAS las filas del foco sin error: f quedaba en cero, la columna se marcaba
"no estimable" y H13 habría salido ⚪ con datos reales. Se detectó con una
prueba sintética antes de tocar datos reales. Ahora el panel se arma completo y
se filtra después, y `correr_decisiones` falla si el foco no tiene filas.
Prueba de regresión: `test_el_panel_conserva_las_filas_del_foco`.

## ADR-v2-27 — Simulador: xPts exactos y escenarios con doble incertidumbre
Los puntos esperados salen de la Poisson-binomial exacta de los remates de cada
equipo (sin simular), con validación en toda la liga (puntos reales contra
esperados). Los escenarios usan el modelo de contexto de la fase 2 y la
eficiencia por familia; su IC combina la incertidumbre de la mezcla y la de la
eficiencia del foco. Supuesto declarado: la eficiencia dentro de cada familia
no depende del contexto. Todo el simulador es exploratorio.

## ADR-v2-28 — Réplica sobre otros técnicos y política de muestras chicas
`scripts/correr_foco.sh "Nombre"` replica las fases 2, 3a, 3b, el simulador y el
resaltado del atlas para cualquier técnico, sin rehacer lo que es de toda la liga
(vocabulario, eras, Elo, atlas). La fase 3a admite N clubes: el de más partidos
es el principal y se compara contra cada uno. Con menos de 20 partidos del foco
en un club no se asigna 🟢 (sandwich con pocos conglomerados); con menos de 30,
un rasgo que "no se detecta en ambos" se reporta como "sin potencia", no como
"no viaja".

## ADR-v2-29 — Paso inicial propio, arranque atado y prior fijo
La mezcla con una sola P por tipo sobreestimaba las secuencias de una acción
(P(T > 1): 0.821 modelado contra 0.859 observado). Se añade una matriz P⁰ por
tipo para la primera acción de cada secuencia; la dinámica posterior sigue
siendo Markov y las formas cerradas se conservan (E[T] = μ(1 + Q₀t), etc.).
Validación con datos sintéticos:
- con primer toque real, P⁰ baja el KS de 0.048 a 0.005 y reproduce P(T > 1);
- **sin** primer toque, arrancar la escalera con P⁰ libre desordenaba la mezcla
  (tipo corto con E[T] 1.91 contra 1.43 real): P⁰ da a cada tipo otra forma de
  explicar secuencias cortas. Solución: los tipos se encuentran con el modelo
  atado (P⁰ = P) y después se libera P⁰ continuando el EM (monótono);
- un prior jerárquico (P⁰ hacia la P del mismo tipo) rompía la monotonía del
  EM (hasta −5.8e-4 relativo): se descarta y se usa un prior fijo hacia los
  primeros pasos de la liga.
Si se usa o no se decide con datos (regla en `11_HIPOTESIS.md`, fase 1 v3).

## ADR-v2-30 — Reproducibilidad con acuerdo SUAVE
El acuerdo "duro" (mismo tipo más probable) castiga empates: en datos
sintéticos, dos soluciones con ΔJ = 0.08 tenían 699 desacuerdos duros, todos en
secuencias ambiguas (responsabilidad entre 0.35 y 0.65); el acuerdo suave
(1 − distancia media entre responsabilidades) era 0.98. Criterio de K: rango de
J < 50 y acuerdo suave ≥ 0.95. El duro se sigue reportando.

## ADR-v2-31 — Métricas formales de la cadena: qué sí y qué no
**Sí**, cada una con validación contra los datos: verificación formal de la
cadena reiniciada (ρ(Q) < 1, irreducibilidad y aperiodicidad sobre el grafo de
lo OBSERVADO —sobre la P encogida serían trivialmente ciertas—, estacionaria =
μᵀN normalizada); espectro (vida media en acciones, distribución de Yaglom);
irreversibilidad por producción de entropía y G² de balance detallado; análisis
de primer paso (probabilidad y tiempo de llegada a un objetivo); memoria de
orden 2 y de primer toque por información mutua condicional (Anderson y
Goodman), **sin y con condicionar al tipo**.
**No**: MCMC (la posterior por fila es Dirichlet y se muestrea exacta, y la
incertidumbre relevante la da el bootstrap por partido); "demostrar
reversibilidad" (la cadena no es reversible por construcción: se mide cuánto
no lo es).

## ADR-v2-32 — Calibración del mallado por densidad predictiva
Las verosimilitudes de mallas distintas no son comparables (cambia el espacio
muestral). Se compara la log-densidad predictiva del siguiente punto en el
campo continuo, P(zona)/área(zona), fuera de muestra por partido. Además, una
agregación contigua voraz desde celdas de 10 × 10 m (fusiones de regiones
vecinas que menos información pierden; lumpability de Kemeny-Snell, agregación
KL de Deng, Mehta y Meyn) dice cuántas zonas distinguen realmente los datos y
dónde. La malla del pipeline sigue siendo rectangular.

## ADR-v2-33 — Corrección de ADR-v2-16
ADR-v2-16 afirmaba "la sobredispersión es heterogeneidad, no memoria". Es
demasiado fuerte: la mezcla reproduce la cola de la duración, pero no pasa el
KS con n = 461 mil y el residuo está en los primeros pasos. Versión correcta:
*la heterogeneidad entre tipos explica la cola; queda un efecto de primer paso*.
La fase 1 v3 lo mide directamente (memoria explicada por los tipos, ADR-v2-31)
y lo modela (P⁰, ADR-v2-29).

## ADR-v2-34 — La memoria se mide fuera de muestra, no con información mutua plug-in
Con la malla 12×8, la tabla de orden 2 tiene ≈ 920 mil celdas para 2.5 millones
de tripletas: la información mutua plug-in se infla por muestra finita, la
corrección de Miller-Madow no alcanza, el IC por bootstrap [0.187, 0.190] no
contenía la estimación (0.162) y la "memoria explicada por el tipo" salió
negativa (−29.4 % en primer toque), lo cual es imposible para la cantidad
poblacional. Sustituto: ganancia de log-verosimilitud en partidos no vistos del
modelo de orden 2 (y del de primer toque) sobre el de orden 1, con encogimiento
hacia el orden 1, sin y con condicionar al tipo. Validado con datos sintéticos:
sin memoria no gana; con orden 2 sí; con dos tipos de primer orden mezclados,
más del 70 % de la ganancia desaparece al condicionar al tipo.

## ADR-v2-35 — Malla del vocabulario y criterio de reproducibilidad (enmienda)
Ver la enmienda con fecha en `11_HIPOTESIS.md`. Resumen: la malla calibrada por
densidad (12×8) quedó en el borde y con ella ningún K fue reproducible. La malla
del vocabulario pasa a ser la más fina, entre 8×5, 6×4 y 5×4, con K reproducible
≥ 3. La reproducibilidad usa el umbral de J por secuencia (1.08·10⁻⁴), acuerdo
suave ≥ 0.95 y π mínimo ≥ 1 %. El script ya no elige un K por defecto cuando
ninguno cumple: se detiene. Otros tres errores corregidos en la misma revisión:
(1) las métricas por tipo usaban nombres de familias de otro K; (2) las pruebas
dependían de `config.pitch`, que el pipeline cambia; (3) el caché de `curva-k`
reutilizaba filas calculadas con el criterio anterior.

## ADR-v2-36 — Experimento: estado zona × nivel de presión desde el 360 (Voronoi local)
**Propuesta evaluada:** sustituir la malla por estados "topológicos" (control
aislado, disputa, ruptura) obtenidos agrupando rasgos de la teselación de
Voronoi, para que la mezcla sostenga K ≥ 4.

**Qué se adoptó y qué no:**
- El estado es el **producto zona × nivel**, no solo el nivel. Sin la zona se
  pierden el valor de zona, la llegada al área y el xG por lugar. El nivel ocupa
  el eje de "fase" que `StateSpace` ya soporta, así que la mezcla, `markov` y las
  figuras funcionan sin cambios.
- La celda de Voronoi se **recorta a un disco de R = 10 m**, a la cancha y al
  área visible de la cámara: el 360 solo trae a los jugadores visibles, y la
  celda completa sería un artefacto del encuadre. Rasgos: distancia al rival más
  cercano, rivales a menos de 5 m y área local de la celda.
- **No DBSCAN** (deja acciones "ruido" sin estado y depende de un ε arbitrario)
  **ni GMM con BIC** (con millones de puntos el BIC elige muchas componentes por
  tamaño de muestra, no por dinámica). Los niveles salen de cuantiles o k-means y
  su número se elige por **validación cruzada por partido en la escala común de
  ADR-v2-32**: densidad predictiva del siguiente punto (zona o absorbente), con
  1 EE pareado hacia menos estados.
- La "ruptura" (el pase que cruza la línea) es una propiedad de la **acción**,
  no del estado; queda fuera de este experimento.
- La comparación de K se hace contra un **control con la misma muestra**
  (partidos con 360, L = 1): si no, un cambio en K podría venir de cambiar de
  partidos y no de cambiar de estado.

**Advertencia registrada antes de correr:** en la fase 1 v3, mallas más finas
dieron *menos* K reproducibles (8×5 y 12×8: ninguno). Más estados = más
parámetros por tipo. Que la presión separe mejor los tipos es una hipótesis, no
una consecuencia.

Aislado en `config/presion.yaml` y `config/presion_base.yaml` (heredan de
`default.yaml`); se descarta borrando `data/processed/presion`,
`data/interim/rasgos_360.parquet` y `reports/presion*`.

## ADR-v2-37 — Experimento: aumento de estado direccional (zona × dirección de llegada)
**Motivo:** la v3 midió memoria real en el destino del balón (+0.058 nats por
acción con la zona anterior; los tipos explican solo el 4.5 %). Un estado
(zona, dirección de la acción que trajo el balón) mete esa memoria en una cadena
de **primer orden**: N, V = N c, la llegada y la vida media siguen en forma cerrada.

**Diseño:**
- Nivel = dirección de la acción anterior de la secuencia, o "inicio" en la
  primera. El destino de la acción t es (zona final, dirección de t): se conoce
  con la propia acción. Los estados "inicio" solo son de arranque (ahí vive P⁰).
- Candidatos: adelante / lateral / atrás con umbral ε ∈ {2, 5, 10} m en x;
  4 y 8 sectores de ángulo. Se eligen por la CV en escala común (ADR-v2-32), con
  1 EE hacia menos estados.
- Referencias que NO compiten como vocabulario: `previa` (nivel = zona anterior,
  420 estados: la memoria de la v3 en esta escala) y `<elegido>+previa` (la
  **memoria residual** una vez sabida la dirección).
- La dirección sale de las coordenadas de la MISMA extracción que las
  transiciones (`possessions.extract_actions`), no de los centroides.

**Descartado de la propuesta original:** la analogía de fluidos (Picard,
Poincaré-Bendixson, campos vectoriales) no aporta cálculo; K y d no se optimizan
juntos por verosimilitud (d por predicción, K por reproducibilidad, ADR-v2-35);
el "90 % de pérdida en circulación estéril" no es una cifra del proyecto.

**Cambio colateral:** `markov.verificar` mide la irreducibilidad solo entre
estados OBSERVADOS (y reporta `estados_sin_observar`). Con un estado aumentado
hay combinaciones que nunca ocurren (arrancar una secuencia en el área rival) y
cada una contaba como una componente. En la malla 5×4 sin aumentar no cambia nada.

## ADR-v2-38 — La capa de fútbol: un motor, tres preguntas por métrica
Cada métrica del reto (5.1, 5.4, 5.5) es una razón de sumas por equipo-partido.
Una sola maquinaria (`comparar.py`) responde para todas: (1) foco contra la liga
sin sus partidos, con bootstrap por partido; (2) percentil entre todas las etapas
técnico-club con ≥ 30 partidos (la comparación con OTROS técnicos, sin elegirlos a
mano); (3) fiabilidad entre mitades de partidos (Spearman-Brown), que separa un
rasgo de un técnico de una diferencia de muestra. El "lado rival" de cada métrica
es lo que le hacen al foco (la fase defensiva sin inventar objetos nuevos). Las
métricas de la cadena (llegada, V = Nc) usan la misma malla y el mismo encogimiento
que la fase 1: nada contradice al vocabulario.

## ADR-v2-39 — Matemática de la capa de fútbol: qué sí y qué no
Sí: cadenas absorbentes (llegada, valor, cadena sobre jugadores), álgebra lineal
(N, espectro, laplaciano), geometría computacional (Voronoi local, envolvente
convexa, asignación húngara), procesos de Poisson (tasas a balón parado, llegada de
secuencias en el simulador), supervivencia (Kaplan-Meier), un sistema dinámico
lineal con ruido (nivel local con Kalman y RTS), un clasificador supervisado
interpretable (logit L2 con AUC fuera de muestra y permutación) e inferencia por
bootstrap de partidos. No: GNN y RNN (≈ 180 partidos por técnico, sin etiqueta
natural y sin lectura de cancha), topología algebraica (sin tracking no hay
trayectorias). Cada herramienta entra solo si responde una pregunta del reto con
algo que un aficionado pueda leer.

## ADR-v2-40 — Blindaje
(1) Eficiencia con xG, OBV y tasa de remate; (2) bootstrap de score por conglomerado
(Kline y Santos, 2012) para H3–H6, porque el Wald sandwich sobre-rechaza con pocos
partidos (en la liga sintética sin efecto de contexto: Wald p = 0.003, bootstrap
p = 0.39); (3) BH global sobre todas las hipótesis del foco como sensibilidad;
(4) splines cúbicos restringidos de minuto y Elo más marcador × minuto en la parte
de la liga, como sensibilidad de la calibración 1.3–1.4 (`fase2.suave`, apagado por
defecto: los resultados oficiales no cambian).

## ADR-v2-41 — La historia se organiza por las secciones del reto
Cada comando es una sección (identidad, ofensiva, defensa, jugadores, balón parado,
simulación, blindaje) con su carpeta en `reports/historia/<foco>/` y en `docs/figuras/`.
Lo que es de toda la liga (campos extra, 360, tabla equipo-partido, xDefense) se calcula
una vez en `tabla-liga`, que guarda una versión junto a la tabla y se rehace sola si cambia
lo que calcula o si llegan insumos nuevos (extra, 360). Motivo: el jurado lee el reto por
secciones, y un resultado debe poder encontrarse donde el reto lo pide.

## ADR-v2-42 — Campos extra del JSON en una tabla lateral (`dtcoach extra`)
Centros, pases filtrados, pases atrás, técnica del cobro, asistencias y remates de primera
se leen de los mismos JSON y se guardan aparte, con la llave (match_id, id). Rehacer el
aplanado obligaría a rehacer el vocabulario y las fases 2–3 sin ganar nada. Sin la tabla,
las métricas que la usan se reportan "sin datos"; nunca se imputan.

## ADR-v2-43 — Balón parado: jugada = saque con ventana, y xDefense en dos capas
La jugada es el SAQUE, con su desenlace en 15 s cortados en la siguiente reanudación (no la
posesión de StatsBomb, que corta en el primer despeje y pierde la segunda jugada). La defensa
se mide en dos capas (Prop. 16.1): prevención con el frame 360 del cobro (corrige el sesgo
de selección del trabajo previo, que solo veía la foto del remate) y supresión con la foto
del remate (visibilidad del arco). Las dos con predicciones fuera de muestra por partido y
contracción empírico-bayesiana entre técnicos-club. PyMC no entra: la contracción
normal-normal responde la misma pregunta ("¿hay variación real entre equipos?") sin otra
dependencia, y el jerárquico bayesiano queda como extensión documentada.

## ADR-v2-44 — Receta Arsenal: se prueba en la Liga MX, no se importa
No hay datos de la Premier. Lo que se puede decir con datos es si la receta (corner cerrado
al área chica o primer palo con atacantes encima del portero) rinde más que el resto en la
Liga MX y si el foco la usa. Es descriptivo: el equipo que elige una rutina no es aleatorio.

## ADR-v2-45 — Contexto por nivel del rival con cortes de la liga
Rivales fuertes, medios y débiles por el Elo previo con los percentiles 25 y 75 de toda la
liga, fijados antes de mirar al foco. Dentro de cada estrato, foco contra liga en el mismo
estrato; la pregunta del reto ("¿ajusta según el rival?") es la diferencia de diferencias
fuertes − débiles contra la de la liga (H22).

## ADR-v2-46 — Bloque: control del encuadre de la cámara
El 360 solo ve lo que enfoca la cámara. El "bloque estrecho" se afirma solo si sobrevive en
frames con ≥ 70 m de ancho visible; si no, se retira. `geometria` guarda el ancho visible de
cada frame.

## ADR-v2-47 — Sustituciones: todas, emparejadas por celda
El efecto de un cambio es una dif. en dif. contra los cambios de la liga en la misma celda
(tramo de 5 min × signo del marcador), para todos los cambios y por tipo (como H15), con
medidas de juego (field tilt, mezcla de familias) además de xG y OBV. Reemplaza al efecto
solo del primer cambio del segundo tiempo.

## ADR-v2-48 — Proyección: plantel que encontró × efecto de llegada contraído
"¿Cómo le iría en su club actual?" se responde con un modelo multiplicativo de xG (Maher):
los índices del club en sus 17 partidos anteriores a la llegada (el plantel), por el efecto
de llegada del técnico medido en sus llegadas anteriores y contraído hacia la media de todas
las llegadas de la liga (que incluye la regresión a la media tras un despido). La fuerza de
los rivales se estima SIN los partidos del equipo evaluado (Prop. 19.1: si no, una mejora se
esconde a sí misma). La receta se valida proyectando cada llegada de la liga; si no le gana a
la inercia, se dice.

## ADR-v2-49 — Balón parado por familias: la cadena completa del xDefense, a favor y en contra
El xDefense (métrica propia) se extiende de "dos capas en los centros" a la **cadena completa**
de cada saque: por probabilidad total en cadena (04 §16.5), los goles que evita una defensa se
parten exactamente en prevención, alejamiento, supresión y portero (§16.6). Se reporta por
familia (corners, tiros libres, laterales), para el foco defendiendo (xD) y atacando (xO = −xD) y
para la liga. Tres decisiones: (1) la capa 1 de los saques que no van al área es un modelo
**aparte**, así el pre-registrado de H24 no cambia; (2) los laterales de la sección 5.4 son los
sacados desde el último cuarto (x ≥ 90, `lateral_cuarto_x`) y se separa el último octavo (x ≥ 105);
`lateral_min_x` se queda en 80 porque define los tipos de saque de H24–H26 (una primera versión lo
subió a 90 y movió H25 en la cuarta cifra: se revirtió); (3) la "segunda jugada" se mide contando cuántos jugadores intervienen entre
el saque y el remate. Todo esto se agregó después de la corrida de la fase G: es exploratorio.
Además: (4) los conteos por partido del balón parado cuentan todos los partidos del equipo, también
los que no tuvieron ese saque (antes el promedio solo tomaba los partidos con ≥ 1: "tiros libres
directos por partido" salía casi al doble); (5) la contracción por etapa de las métricas en goles
usa una varianza común por saque, porque la propia de cada etapa está acoplada a la media (04 §16.4).

## ADR-v2-50 — Regla de demostración: un solo BH sobre todo lo que se afirma
Cada sección etiquetaba sus métricas con un BH por bloque, y lo exploratorio quedaba fuera del
control global. Ahora `dtcoach demostracion` junta en una sola familia:

- hipótesis;
- comparaciones de métricas;
- efectos con IC;
- pruebas declaradas.

Solo lo que sobrevive (q < 0.05, ≥ 20 partidos del foco) se narra. Pruebas nuevas para que todo lo que
se dice tenga una:

- Q de Cochran de heterogeneidad antes de dar un puesto entre técnicos;
- p por bootstrap para cada término de la cadena;
- rutinas contra el resto;
- TOST para "la receta Arsenal no rinde más";
- Fisher para los laterales al área chica;
- Diebold-Mariano para "la receta proyecta mejor que la inercia";
- binomial para la cobertura del intervalo.

Los intervalos de la proyección pasan a ser conformes (cuantil de los errores de las llegadas de la
liga), porque los del simulador cubrían 67 % en vez de 80 %.

## ADR-v2-51 — Partidos nuevos de la temporada: se descargan y se suman sin reajustar el vocabulario
La temporada en curso se trae del API de StatsBomb (`actualizar_temporada.py`). Toda la liga, no solo el
América: las comparaciones, el Elo y la proyección necesitan a todos. Detalles:

- **Eras:** las vigentes se alargan solo si el `managers` del API es la misma persona
  (`extender_eras.py`). Un cambio de técnico se agrega a mano, como el resto de las eras verificadas.
- **Vocabulario:** la mezcla de tres familias NO se reajusta. La guardada se aplica a las secuencias
  nuevas, así una familia significa lo mismo antes y después, y los resultados son comparables.
- **Uso de lo nuevo:** los partidos nuevos (sobre todo los del América de Almada) son datos que no se
  vieron al formular las preguntas de la fase G. Sirven para confirmar lo que se demostró con la muestra
  anterior.

## ADR-v2-52 — EXPERIMENTO (no adoptado): el supuesto «el técnico solo mueve π_k, no P^k» se dice y se prueba
Rama `exp/mejoras-6`, sin push. Config `config/exp_mejoras.yaml` (hereda de default; no se toca).
El modelo de la fase 2 supone que cada familia hecha por el foco es la cadena P^k de la liga. Se
documenta en 04 §15 y se prueba con un score de H0: P^k_foco = P^k_liga por familia (y, aparte, el
primer toque P0^k), varianza de conglomerados por partido más el error de estimar P^k_liga (que el
primer intento omitió y volvía anticonservadora a la prueba: 22 % de rechazos al 5 % bajo H0 en
datos sembrados). Salidas en `reports/experimentos/supuesto_pk/`. Nada de la entrega cambia. Se
decide con el resultado sobre Almada (RESUMEN.md).

## ADR-v2-53 — EXPERIMENTO (no adoptado): regresor generado en la fase 2, documentado y cuantificado
Rama `exp/mejoras-6`, sin push. Las r_sk salen del EM de la etapa 1 y el sandwich de la Prop. 7.2 las
trata como dato: no propaga el error de primera etapa (04 §7.1). Se cuantifica con un bootstrap por
partido, estratificado, que **reajusta la mezcla** en cada réplica (arranque en escalera, semilla
fija por réplica `seed + 1000 + b`), con las familias alineadas por asignación húngara. La misma
remuestra se evalúa con las r originales («fijo»), de modo que la inflación limpia
(w_doble / w_fijo) aísla el efecto de la etapa 1 y la razón w_fijo / w_actual calibra el propio
bootstrap. Regla: < 1.1 = despreciable. Con menos de 50 réplicas el veredicto es «necesita más
réplicas». Costo: cada réplica reajusta la mezcla (minutos con los 467 mil secuencias reales), así que
`--max-minutos` y `--reanudar`. Salidas en `reports/experimentos/regresor_generado/`.

## ADR-v2-54 — EXPERIMENTO EXPLORATORIO (no adoptado): Voronoi × grafo de jugadores
Rama `exp/mejoras-6`, sin push. Une el espacio con que cada jugador EJECUTA (área Voronoi local, R = 10 m,
128 puntos; 13.3) con lo que decide (pase / conducción / remate) y con el valor de zona V = N c de la
Prop. 2.4 (cadena de toda la liga, fases promediadas con el peso de sus visitas), y lo cruza con el grafo de
pases (ν, P(remate | balón en él), grupo espectral; 13.5). Medida: ΔV de intención y realizado, residualizada
contra la media de la liga en la misma (zona de origen × tipo) para que «decidir bien» no sea «estar cerca
del arco». Reglas escritas en el reporte: el 360 es foto del evento (se mide con cuánto espacio EJECUTÓ, no
cómo recibe); solo jugadores en cámara (≥ 50 % del disco visible, actor del frame a ≤ 2 m del evento); n < 50
por jugador-etapa se descarta; exploratorio, fuera del BH global y de las hipótesis pre-registradas.
«¿Depende del técnico?»: solo con el MISMO jugador bajo ≥ 2 técnicos (n ≥ 50 y ≥ 3 partidos con cada uno);
con menos de 15 jugadores no se concluye. El estadístico es z² de Welch por partido por par, con nula por
permutación dentro del jugador; un primer diseño (diferencia ordenada por n) se descartó porque su media no
medía al técnico. No separa técnico de club/compañeros/época. Salidas en `reports/experimentos/voronoi_grafo/`.

## ADR-v2-55 — EXPERIMENTO (no adoptado): el percentil de la Mejora A se compara a igual número de partidos
Rama `exp/mejoras-6`. La corrida de la Mejora A sobre Almada dio percentil 98, 100 y 100 entre 44 técnicos-club,
pero Almada tiene 168 partidos y la nula ≥ 30. El exceso T/gl crece con n cuando hay una desviación fija
(E[T] ≈ gl + n·δ²), así que ese percentil mezcla efecto con potencia. La TV no crece con n pero está sesgada hacia
arriba con n chico: tampoco compara limpio. Decisión: el número que se reporta es el percentil con TODAS las
unidades remuestreadas a exactamente n partidos (n = 30 y 40, 20 remuestras, la nula P^k_liga de cada unidad
estimada una vez con su liga completa), mediana de los sorteos, por exceso y por TV, y además Almada por club.
Regla de lectura fijada ANTES de correr sobre los datos reales, con la mediana a n = 30: ≤ 80 por los dos →
aproximación razonable (limitación); ≥ 95 por los dos → el supuesto no se sostiene para Almada; lo demás → no
concluyente, sin elegir rama. Script `scripts/experimentos/supuesto_pk_n.py` (no reajusta la mezcla). Prueba con
datos sembrados: misma desviación en todos, foco con 5× partidos → percentil ≥ 85 a n completo y < 85 a igual n.

## ADR-v2-56 — EXPERIMENTO (no adoptado): «portero y definición» se parte en dos con xGOT
Rama `exp/mejoras-6`. El cuarto término de la Prop. 16.6, s(F − g), mezcla remates fuera (definición) con
atajadas (portero). Decisión del experimento: (1) primero se VERIFICA que los remates a puerta traen la altura z en
el plano de la portería (`shot.end_location` [x, y, z]; ≥ 90 % de los a puerta con z, ≥ 90 % dentro del marco, z
con más de 10 valores); si no, el script se detiene y no se inventa nada con la (x, y) en la cancha. «A puerta» se
deduce del `shot.outcome` (Goal, Saved, Saved to Post): StatsBomb no trae un booleano aparte. (2) xGOT por remate,
logit L2 fuera de muestra con pliegues por partido, sobre los remates a puerta de toda la liga (ubicación en el
marco + logit del xG previo + cabeza); fuera = 0. (3) definición = s(F − xGOT), portero = s(xGOT − g); la suma de
los cinco términos es exacta (prueba con error < 1e-10). (4) τ² de cada término nuevo por técnico-club con la
Prop. 16.4 y la varianza común. (5) H24–H26 no usan el cuarto término: se vuelven a correr para comprobarlo, y el BH
global de la demostración se recalcula con las pruebas de la cadena «portero y definición» reemplazadas por las dos
nuevas, para ver si alguna etiqueta cambiaría. Solo lee la tabla de la liga y la cadena del xDefense; no toca
reports/historia ni la mezcla. Salidas en `reports/experimentos/xgot/`.

## ADR-v2-57 — Consecuencias de la Mejora B: los IC de la fase 2 con la amplitud «doble»
Rama `exp/mejoras-6`. Con las 100 réplicas de B, cada IC publicado de H1–H8 se ensancha a w = máx(w_actual, w_doble)
conservando su forma: un IC publicado nunca se estrecha porque el bootstrap salga más angosto (dos cantidades
«ganarían» significancia si se permitiera; no se cuentan). El BH global de la demostración se rehace escalando el z de
cada p de la fase 2 por f = w / w_actual (p' = 2Φ(−z/f); con f = 1 la p no cambia); las Wald H1–H6 con el f más
grande de sus componentes (W' = W/f², conservador). Sensibilidad: f = máx(1, inflación limpia). La separación de las
familias se mide con la entropía de las r_sk. Script `scripts/experimentos/regresor_generado_impacto.py` (solo lee).
Resultado en 04 §7.2.

## ADR-v2-58 — xGOT (Mejora D): exacta y segura, pero sin señal de equipo; se documenta y no se narra
Rama `exp/mejoras-6`. Resultado sobre Almada en 04 §16.7: partición exacta, 0 veredictos cambian, τ² = 0 (o ≈ 0, p > 0.3)
en «todo el balón parado» para definición y portero. Se documenta y no se adopta como métrica narrativa. Dos
correcciones del experimento: (1) los equipo-partidos sin saques de un tipo se cuentan como 0 de 0 (antes quedaban nulos
y vaciaban la etapa: las filas por tipo de saque de la primera corrida no son válidas); (2) `xdefensa.contraccion`
devuelve «no estimable» (μ, τ² = NaN, `estimable: False`) cuando hay menos de dos etapas con varianza positiva, sin
dividir entre cero. Con dos o más etapas el cálculo no cambia, así que los números de la entrega no se mueven.

