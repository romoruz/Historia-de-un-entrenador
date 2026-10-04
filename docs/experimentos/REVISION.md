# Revisión del proyecto: qué cambió después de la entrega y en qué estado queda

*Para quien no siguió el proceso. Lectura de cinco minutos. Estado final, integrado y corrido con los datos reales
(2026-10-03).*

## Qué es el proyecto

Describimos cómo juega un equipo partiendo cada posesión en «secuencias» de acciones (pases, conducciones, remates)
sobre una cancha dividida en 20 zonas. Las secuencias de toda la liga mexicana (467 mil) se agrupan en tres
**familias** con una mezcla de cadenas de Markov: *Directa* (corta, vertical), *Circulación estéril* (larga, que casi
no remata) y *Ataque elaborado* (larga, que sí llega). Sobre eso preguntamos qué hace distinto un entrenador, aquí
Guillermo Almada, con cuatro precauciones: comparar contra la liga en las mismas situaciones, separar al técnico del
plantel hasta donde se puede, propagar la incertidumbre por partido y no afirmar nada que no sobreviva a una
corrección por pruebas múltiples sobre las 730 afirmaciones del trabajo.

Después de la entrega probamos seis mejoras como experimento. Dos se integraron al modelo, tres quedaron como
documentación y una se rechazó. Todo se volvió a correr con los datos reales.

## Lo que se integró

- **Un quinto desenlace: «interrupción a favor».** Antes, una secuencia que terminaba porque al equipo le hacían
  falta, o porque ganaba un córner, un lateral o un penal, contaba como **pérdida** del balón. Eran 83,495 de 388,974
  «pérdidas» (21.5 %). Ahora tienen su propio desenlace, y cada reanudación vale lo que vale: un lateral en campo
  propio, 0.002 goles esperados; un córner, 0.02; un penal, 0.78.
  - **El xG no cambia.** El valor de la reanudación entra en el «valor de cada zona», pero no en el xG por secuencia
    con que se compara a los técnicos. Lo comprobamos sobre 3 millones de transiciones: es idéntico bit a bit.
  - **Las familias no cambian.** El modelo nuevo cumple los mismos criterios de estabilidad que el original (acuerdo
    entre semillas 0.998), y las familias son las mismas: el uso de Almada pasa de 35.7 / 26.1 / 39.3 % a
    35.6 / 25.4 / 38.9 %.
  - **Lo que sí cambia es cómo terminan las secuencias.** En cada familia, entre el 17 y el 20 % de lo que era pérdida
    es ahora interrupción a favor.
- **La incertidumbre de las familias.** Las familias se estiman, y los intervalos publicados no incluían ese error. Al
  incluirlo, la gran mayoría de las afirmaciones se sostienen, incluidas la identidad ofensiva y la defensiva de
  Almada, pero tres se retiraron del texto.
- **Un error corregido en el balón parado.** El cálculo de incertidumbre no fijaba el orden de los partidos, así que el
  mismo análisis daba p-valores algo distintos en cada corrida. Ya está corregido. Al volver a correrlo, solo se
  movieron p de esa sección, y un resultado pasó a demostrado: los tiros libres directos en contra le entran menos de
  lo esperado (3.45 goles por 100 contra 5.44). Lo narramos como frágil: son 87 tiros y no se puede separar el
  mérito del portero de la mala puntería del rival.

## El conteo de lo demostrado, sin trucos

Los resultados de Almada quedan con **243 afirmaciones demostradas**:

1. **246:** la demostración de la entrega.
2. **248:** el balón parado corregido agrega dos. El directo en contra y una afirmación de otra sección que cruzó el
   umbral sin que su propio p cambiara: la corrección por pruebas múltiples es global, y cuando unos p cambian, el
   umbral de los demás también se mueve.
3. **245:** el quinto desenlace quita tres.
4. **243:** se retiran dos más por la incertidumbre de las familias. La tercera que esa regla retira ya había caído en
   el paso 3.

Esa afirmación, «Almada remata más en sus secuencias de Circulación estéril», cayó por dos caminos independientes, y
eso dice mucho de lo frágil que era.

## Lo que quedó como documentación o se rechazó

- **Separar el mérito del portero del de quien remata.** La cuenta es exacta, pero no hay diferencias reales entre
  equipos: lo que se ve es azar. Se documenta y no se usa para narrar.
- **El supuesto de que el técnico cambia cuánto usa cada familia, no cómo la juega.** Es razonable para Directa y
  Ataque elaborado. Para Circulación estéril no se puede concluir, y queda como limitación declarada.
- **Cruzar el espacio con que ejecuta cada jugador con su papel en la red de pases.** Hay una señal, pero no se puede
  atribuir al entrenador. Queda como exploratorio.
- **Distinguir pase de conducción en el modelo.** Rechazado: hace inestables las familias, y por construcción no
  podía predecir mejor el balón.

## Limitaciones conocidas

- **Circulación estéril es la familia frágil.** Es la peor separada, la que más incertidumbre arrastra y la única
  donde el supuesto del modelo queda en duda. Cualquier frase sobre ella lleva esa advertencia.
- **La incertidumbre de las familias se midió con el modelo anterior** (cuatro desenlaces) y no se repitió. La
  condición para no repetirla, fijada antes de correr, era que las familias de los dos modelos coincidieran al menos
  en un 98 %. Coincidieron en un 98.15 %: **pasó, pero al filo**. Si se quiere cerrar del todo, se repite (unas
  8 horas).
- **Esa misma incertidumbre no se midió club por club.** Dos afirmaciones retiradas siguen marcadas como demostradas en
  su versión por club. No se narran.
- **Los criterios de estabilidad de la entrega se midieron con 461 mil secuencias**, antes de sumar 22 partidos de la
  temporada en curso. El modelo nuevo se midió con los 467 mil, y la mezcla publicada se reproduce exactamente sobre
  su propia muestra.
- **Nada es causal.** Todo es descriptivo y comparativo. Separar al entrenador del plantel se aproxima, pero no se
  identifica.

## Dónde está cada cosa

- Resultados: `docs/RESULTADOS_ALMADA.md`.
- Matemática: `docs/04_MODELO_MATEMATICO.md`, §1, §2, §4, §7.2 y §14.2.
- Decisiones: ADR-v2-52 a 73 en `docs/06_DECISIONES.md`.
- Integración, paso a paso: `INTEGRACION.md`.

Los resultados de cuatro desenlaces están archivados en `data/processed/archivo_4abs/` y `reports/archivo_4abs/`.
