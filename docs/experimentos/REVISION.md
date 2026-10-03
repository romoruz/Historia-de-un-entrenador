# Revisión del proyecto: qué cambió después de la entrega y en qué estado queda

*Para quien no siguió el proceso. Lectura de cinco minutos.*

## Qué es el proyecto

Describimos cómo juega un equipo partiendo cada posesión en «secuencias» de acciones (pases, conducciones, remates)
sobre una cancha dividida en 20 zonas. Las secuencias de toda la liga mexicana (467 mil) se agrupan en tres
**familias** con una mezcla de cadenas de Markov: *Directa* (corta, vertical), *Circulación estéril* (larga, que casi
no remata) y *Ataque elaborado* (larga, que sí llega). Sobre eso preguntamos qué hace distinto un entrenador, aquí
Guillermo Almada, con cuatro precauciones: comparar contra la liga en las mismas situaciones, separar al técnico del
plantel hasta donde se puede, propagar la incertidumbre por partido y no afirmar nada que no sobreviva a una
corrección por pruebas múltiples sobre las 730 afirmaciones del trabajo.

Después de la entrega probamos seis mejoras como experimento y las evaluamos con los datos reales. Dos se integraron
al modelo, tres quedaron como documentación y una se rechazó.

## Lo que se integró

- **Un quinto desenlace: «interrupción a favor».** Antes, una secuencia que terminaba porque al equipo le hacían
  falta, o porque ganaba un córner, un lateral o un penal, contaba como **pérdida** del balón. Era el 21 % de todas
  las «pérdidas». Ahora tiene su propio desenlace, y cada reanudación vale lo que vale: un lateral en campo propio,
  0.002 goles esperados; un córner, 0.02; un penal, 0.78. Ese valor entra en el «valor de cada zona», pero **no** en el
  xG por secuencia con que se compara a los técnicos, que sigue siendo solo de remates. Una prueba comprueba que ese xG
  es idéntico antes y después. Para Almada el efecto es favorable: pierde el balón menos de lo que parecía, y con
  Pachuca el 18.6 % de sus secuencias termina en una interrupción a favor, más que el 77 % de los entrenadores
  comparables. Estos son los números del experimento; la corrida de integración los confirma.
- **La incertidumbre de las familias.** Las familias se estiman, y los intervalos publicados no incluían ese error. Al
  incluirlo con un bootstrap de 200 réplicas que vuelve a estimar las familias, la gran mayoría de las afirmaciones se
  sostienen, incluidas la identidad ofensiva y la defensiva de Almada. **Tres se retiraron del texto** (246 → 243):
  1. «Cuando va ganando, sube menos su juego Directo que la liga.» Estaba justo en el límite.
  2. «Remata más en sus secuencias de Circulación estéril.»
  3. «Sus rivales rematan menos en sus secuencias de Circulación estéril.»
- **Un error corregido en el balón parado.** El cálculo de incertidumbre no fijaba el orden de los partidos, así que
  el mismo análisis daba p-valores ligeramente distintos en cada corrida (±0.01). Está corregido, y la sección se
  vuelve a correr y se compara afirmación por afirmación con la publicada.

## Lo que quedó como documentación o se rechazó

- **Separar el mérito del portero del de quien remata.** La cuenta es exacta, pero no hay diferencias reales entre
  equipos: lo que se ve es azar. Se documenta y no se usa para narrar.
- **El supuesto de que el técnico cambia cuánto usa cada familia, no cómo la juega.** Comparado contra técnicos con
  los mismos partidos, es razonable para Directa y Ataque elaborado. Para Circulación estéril no se puede concluir: es
  una limitación declarada.
- **Cruzar el espacio con que ejecuta cada jugador con su papel en la red de pases.** Hay una señal, pero no se puede
  atribuir al entrenador (cambiar de técnico casi siempre es cambiar de club, compañeros y temporada). Exploratorio.
- **Distinguir pase de conducción en el modelo.** Rechazado: hace inestables las familias, y por construcción solo
  podía ayudar a reconocerlas, no a predecir mejor el balón.

## Limitaciones conocidas

- **Circulación estéril es la familia frágil.** Es la peor separada, la que más incertidumbre arrastra y la única
  donde el supuesto del modelo queda en duda. Cualquier frase sobre ella lleva esa advertencia.
- **La incertidumbre de las familias se midió con el modelo anterior** (cuatro desenlaces). No se repitió con cinco
  (serían 8 horas), por dos razones: el desenlace nuevo solo cambia el final de algunas secuencias, no cómo circula el
  balón, y la fragilidad viene de esto último. Si al regenerar las familias se mueven más de lo previsto (acuerdo
  menor a 0.98 con el modelo anterior sobre los mismos datos), se repite antes de narrar.
- **Los criterios de estabilidad publicados se midieron con 461 mil secuencias**, antes de sumar 22 partidos de la
  temporada en curso. Verificamos que sumar esos partidos mueve las familias tanto como cambiar la semilla aleatoria,
  es decir, nada que importe. El modelo nuevo se vuelve a medir con los 467 mil.
- **La medida de incertidumbre es algo conservadora.** El bootstrap por partido mide algo más de variabilidad (≈ 8 %)
  que la fórmula con que se publicaron los intervalos.
- **Nada es causal.** Todo es descriptivo y comparativo. Separar al entrenador del plantel se aproxima, pero no se
  identifica.

## Qué falta para cerrar

El código y los documentos ya están integrados. Falta correr con los datos reales, en dos tandas que se revisan por
separado (`bash scripts/integrar.sh paso2` y `paso4`), y reescribir los resultados de Almada solo con lo que la
demostración nueva marque como demostrado. Cada tanda tiene compuertas que detienen todo si algo no cuadra. El
detalle está en `INTEGRACION.md`.
