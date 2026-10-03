# Revisión del proyecto: qué se probó después de la entrega y en qué estado queda

*Para quien no siguió el proceso. Lectura de cinco minutos.*

## Qué es el proyecto

Describimos cómo juega un equipo partiendo cada posesión en «secuencias» de acciones (pases, conducciones, remates)
sobre una cancha dividida en 20 zonas. Las secuencias de toda la liga mexicana (467 mil) se agrupan en tres
**familias** con una mezcla de cadenas de Markov: *Directa* (corta, vertical), *Circulación estéril* (larga, que casi
no remata) y *Ataque elaborado* (larga, que sí llega). Sobre eso preguntamos qué hace distinto un entrenador, aquí
Guillermo Almada, con cuatro precauciones: comparar contra la liga en las mismas situaciones, separar al técnico del
plantel hasta donde se puede, propagar la incertidumbre por partido y no afirmar nada que no sobreviva a una
corrección por pruebas múltiples sobre las 730 afirmaciones del trabajo.

Después de la entrega probamos seis mejoras como experimento, sin tocar los resultados publicados, y las evaluamos
con los datos reales.

## Qué sobrevivió

- **Un quinto desenlace: «interrupción a favor».** Antes, una secuencia que terminaba porque al equipo le hacían
  falta, o porque ganaba un córner, un lateral o un penal, contaba como **pérdida** del balón. Era el 21 % de todas
  las «pérdidas». Separarlo cumple los mismos criterios de estabilidad que el modelo original y no cambia las tres
  familias. Cada reanudación vale lo que vale: un lateral en campo propio, 0.002 goles esperados; un córner, 0.02; un
  penal, 0.78. Para Almada el efecto es favorable: pierde el balón menos de lo que parecía, y el 18.6 % de sus
  secuencias termina en una interrupción a favor (más que el 77 % de los entrenadores comparables). **Se adopta.**
- **La propagación del error de las familias.** Las familias se estiman, y los intervalos publicados no incluían ese
  error. Al incluirlo con un bootstrap de 200 réplicas que vuelve a estimar las familias, la gran mayoría de las
  afirmaciones se sostienen, incluidas la identidad ofensiva y la defensiva de Almada. **Se adopta como corrección.**

## Qué no sobrevivió

- **Tres afirmaciones publicadas se retiran** (246 → 243 demostradas):
  1. «Cuando va ganando, sube menos su juego Directo que la liga.» Estaba justo en el límite y no aguanta el error
     adicional.
  2. «Remata más en sus secuencias de Circulación estéril.»
  3. «Sus rivales rematan menos en sus secuencias de Circulación estéril.»
  Las dos últimas son de la familia peor separada por el modelo, que es la que más incertidumbre arrastra.
- **Separar el mérito del portero del de quien remata** (con la ubicación del remate en el arco). La cuenta es exacta,
  pero no hay diferencias reales entre equipos: lo que se ve es azar. Se documenta y no se usa para narrar.
- **Distinguir pase de conducción en el modelo.** Hace inestable el agrupamiento en familias (distintas semillas dan
  soluciones distintas) y casi no mejora la predicción. Además, por construcción, solo podía ayudar a reconocer la
  familia, no a predecir mejor la siguiente zona. Se rechaza.
- **Cruzar el espacio con que ejecuta cada jugador con su papel en la red de pases**, para ver si depende del
  entrenador. Hay una señal, pero cuando un jugador cambia de entrenador casi siempre cambia también de club,
  compañeros y temporada, así que no se puede atribuir al entrenador. Queda como exploratorio.

## Limitaciones conocidas

- **Supuesto del modelo.** El modelo supone que un entrenador cambia **cuánto** usa cada familia, no **cómo** juega
  dentro de ella. Comparado contra entrenadores con la misma cantidad de partidos, el supuesto es razonable para
  Directa y Ataque elaborado; para Circulación estéril no se puede concluir ni a favor ni en contra.
- **Circulación estéril es la familia frágil.** Es la peor separada, la que más incertidumbre arrastra y la única
  donde el supuesto queda en duda. Cualquier frase sobre ella necesita esa advertencia.
- **Medida algo conservadora.** El bootstrap por partido mide algo más de variabilidad (≈ 8 %) que la fórmula con la
  que se publicaron los intervalos. Parte de lo que atribuimos al error de estimar las familias puede venir de ahí. La
  conclusión no cambia, pero la magnitud de ese error está algo sobrestimada.
- **Un error corregido.** El cálculo de incertidumbre del balón parado no fijaba el orden de los partidos, así que el
  mismo análisis daba p-valores ligeramente distintos en cada corrida (±0.01). Ya está corregido. Hay que volver a
  correr esa sección y revisar las pocas afirmaciones que estaban en el límite.
- **Nada es causal.** Todo es descriptivo y comparativo. Separar al entrenador del plantel se aproxima, pero no se
  identifica.

## Qué falta para cerrar

Hay que confirmar con los datos reales que la optimización de velocidad del ajuste no cambió el modelo oficial. Hecho
eso, se integra en este orden: (1) las tres correcciones de texto; (2) la corrección del balón parado, volviendo a
correr esa sección; (3) la documentación de lo rechazado; (4) el quinto desenlace, volviendo a correr todo lo que
depende de las familias. El plan detallado, con comandos, está en `INTEGRACION.md`.
