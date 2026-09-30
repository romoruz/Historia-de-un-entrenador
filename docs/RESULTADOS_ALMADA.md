# Cómo juega Guillermo Almada — solo lo demostrado

> **Regla de este documento.** Solo se narra lo que sobrevive a **un único control de falsos positivos**
> (Benjamini-Hochberg, α = 0.05) aplicado a **730 afirmaciones**: hipótesis, cada métrica contra la liga, cada
> efecto con su intervalo y las pruebas de cada sección (`reports/historia/guillermo_almada/demostracion/`).
> Sobrevivieron **246**. Lo que no sobrevivió se dice como "no demostrado" y no se interpreta.
> Datos: Liga MX 2021/22 a 2026/27 (1,789 partidos hasta el 2026-11-23). Almada: 168 partidos
> (Pachuca 139, Santos Laguna 20, América 9). Con América (9 partidos) nada es demostrable por sí solo.
> Nada de esto es causa y efecto: describe lo que hizo su equipo, no separa al técnico de sus jugadores.
> Figuras en `docs/figuras/<sección>/`. Matemática en `04_MODELO_MATEMATICO.md`; regla en `11_HIPOTESIS.md`.

**Índice:** [1. Identidad](#1-identidad) · [2. Ataque](#2-ataque) · [3. Defensa](#3-defensa) ·
[4. Jugadores y banca](#4-jugadores-y-banca) · [5. Balón parado](#5-balón-parado) ·
[6. Simulación](#6-simulación-y-américa) · [No demostrado](#lo-que-no-se-demostró)

---

## 1. Identidad

* **Se le reconoce.** Un clasificador separa sus partidos de los del resto de la liga con AUC **0.882** y de los de
  Pachuca con otros técnicos con **0.847** (prueba de permutación, p = 0.005, el mínimo posible con 200
  permutaciones). Entre 45 técnicos-club queda **4.º** (AUC 0.893). Lo que más lo distingue: presión encima del
  rival, conducciones progresivas, saques de meta en corto (menos), entradas al último tercio.
* **Su mezcla de familias es distinta (H1 y H2 🟢).** El ataque y la defensa se reparten entre tres maneras de jugar
  (Directa, Circulación estéril, Ataque elaborado). Lo demostrado individualmente:
  * juega **menos Circulación estéril** (−0.95 pp);
  * a sus rivales les sale **más Directa** (+1.8 pp) y **menos Ataque elaborado** (−2.0 pp), y remata menos en
    las tres (P(remate) del rival: −3.1 pp en Directa, −1.7 pp en Elaborado, −0.5 pp en Circulación);
  * xG por secuencia del rival: **−0.0029 en Directa** y **−0.0014 en Ataque elaborado** (H8.1 y H8.3 🟢);
    en total −0.0017 por secuencia.
* **Reacciona menos que la liga (H3 y H6 🟢).** Cuando va ganando sube menos su Directa (−1.7 pp contra la liga) y
  baja menos su Ataque elaborado (+2.2 pp); contra un rival 100 Elo más fuerte, lo mismo (Directa −1.2 pp,
  Elaborado +2.1 pp, Circulación −0.9 pp). Su receta cambia menos que la de la liga con el marcador y con el rival.
* **Viaja.** H1 y H3 se sostienen tanto en Pachuca como en Santos Laguna; H6 en Pachuca y H2 en Santos Laguna. En
  América (9 partidos) no hay nada demostrable.

![Cuánto cambia Almada con el marcador y el rival, contra la liga](figuras/identidad/contexto.png)
![La receta de Almada partido a partido](figuras/identidad/evolucion.png)

---

## 2. Ataque

Las cifras son de Almada contra la liga (sin sus partidos); todas demostradas salvo que se diga lo contrario.

* **Sale largo y no con el portero.** Saques de meta en corto: 31.5 % contra 47.2 % (−15.7 pp). Con un rival a menos
  de 2 m completa menos pases (68.7 % contra 71.5 %).
* **Avanza vertical y conduciendo (H18 🟢).** De cada metro que recorre el balón, 28 cm van hacia el arco (la liga,
  25). Avanza a 2.78 m/s contra 2.47. Conduce hacia adelante 22.6 veces por partido contra 16.4; 39 % de sus
  progresiones son conduciendo (la liga, 32 %).
* **Llega al área conduciendo, no por centros (H20 🟢).** Entradas al área: 47 % conduciendo (la liga, 37 %), 15 %
  con centro (la liga, 20 %) y 34 % con otro pase (la liga, 39 %). Pisa la zona 14 (frente al área) 21.5 veces por
  partido contra 16.8. Entra al último tercio 49.0 veces contra 43.0 y al área 13.3 contra 11.5.
* **Sus remates son más de lejos y menos de cabeza.** Remata 16.2 veces por partido contra 13.3. Dentro del área:
  51 % contra 58 %; de cabeza: 15 % contra 20 %; de primera: 30 % contra 33 %; distancia media 21.2 m contra 19.8.
  Los asiste un centro en 12 % (la liga, 15 %) y otro pase en 59 % (la liga, 54 %).
* **Rinde más, aunque cada remate valga menos.** xG por partido 1.46 contra 1.30 y goles 1.58 contra 1.32.
* **Sus dibujos de tres pases (H21 🟢).** Usa más el ABCD (cuatro jugadores distintos): 62.4 % contra 59.6 %; y
  menos los que regresan (ABAC −0.7 pp, ABCA −0.9 pp, ABCB −0.8 pp). El balón avanza, no vuelve.
* **Llega en menos toques:** 2.49 acciones hasta el último tercio contra 2.84.
* **Lo que se hace con el balón lo ve la presión:** sus acciones con un rival a ≤ 2 m: 19.0 % contra 17.2 %.
* **No demostrado:** que progrese por carriles distintos (H19), pases progresivos por partido, xG por remate,
  remates de contraataque, xG de juego abierto, y todos los rasgos por tipo de rival (H22).

![Dónde queda Almada entre todos los técnicos en cada rasgo de ataque](figuras/ofensiva/percentiles.png)
![Cómo entra al área, qué asiste sus remates, por dónde progresa y qué pases repite](figuras/ofensiva/reparto.png)
![Las tres maneras de atacar de Almada contra la liga](figuras/ofensiva/familias_cancha.png)

---

## 3. Defensa

* **Aprieta encima, sobre todo arriba.** PPDA 8.50 contra 10.29 (menos pases del rival antes de robar). Hay un
  jugador suyo a menos de 2 m en 20.7 % de los toques del rival (la liga, 17.2 %). Cuando el rival sale desde su
  área: 15.3 % contra 12.3 %; en el medio: 20.7 % contra 16.2 %; cerca de su propia área: 26.5 % contra 24.4 %.
  Recupera 13.7 balones en el último tercio contra 12.0, presiona en campo rival en 31.8 % de sus presiones (la
  liga, 30.4 %) y tras recuperar remata en 10 s en 4.5 % de los casos (la liga, 3.7 %).
* **Bloque estrecho, y no es la cámara.** Anchura del bloque 36.8 m contra 38.5; solo con la cámara abierta (≥ 70 m
  visibles) 38.2 m contra 40.1 (−1.96 m [−2.24, −1.68]). Área de la envolvente 553 m² contra 584. Altura 48.3 m
  contra 47.1. Almada es el técnico con el bloque más angosto de la liga (percentil 1).
* **Sus rivales la pasan mal.** Le rematan 11.9 veces por partido contra 13.3 y le entran al área 9.4 veces contra
  11.5.
* **El costo:** cuando el rival logra salir, avanza más rápido (2.76 m/s contra 2.47).
* **No demostrado:** xG concedido global, profundidad del bloque, y que presione distinto según el rival (H22).

![De cada 100 toques del rival, cuántos tienen a un jugador de Almada encima](figuras/defensa/pictograma_presion.png)
![El bloque típico de Almada contra el de la liga](figuras/defensa/bloque_tipico.png)

---

## 4. Jugadores y banca

* **Hace cambios del mismo puesto (H15 🟢).** Empatando: mismo puesto 90 % (la liga, 78 %), defensivos 5 % (10 %),
  ofensivos 5 % (11 %). Perdiendo: ofensivos 12 % (la liga, 20 %), mismo puesto 81 % (72 %). Cambia jugadores, no
  el dibujo.
* **Reacomoda menos la formación (H16 🟢).** 1.42 reacomodos por partido contra 1.81 (−0.39 [−0.56, −0.23]); solo 38 % de
  sus cambios se siguen de un reacomodo en 3 min, contra 52 % en la liga.
* **Quién entra más:** Javier Eduardo López (46 veces), Illian Hernández (38), Marino Hinestroza (31), Roberto de
  la Rosa (31). Es descriptivo.
* **No demostrado:** que sus cambios muevan el xG, el OBV o la manera de atacar (H23; 493 cambios suyos contra 8,736
  de la liga), el momento de sus cambios (H13) ni su reacción al marcador desde la banca (H14). H17 (rotación del
  once) y la estabilidad del once **no se pueden demostrar** con estos datos: se confunden con el calendario
  (Copa y Concachampions no están).

![Las decisiones de Almada desde la banca, contra la liga](figuras/jugadores/decisiones.png)
![La red de pases de Almada en Pachuca](figuras/jugadores/red_pachuca.png)

---

## 5. Balón parado

### 5.1 El xDefense: nuestra métrica y cómo se calcula

> **El xDefense es una métrica nuestra**, construida en el equipo para medir la defensa de los corners y aquí
> extendida a toda la Liga MX, a corners, tiros libres y laterales, y al ataque (xO).

Para que te metan un gol de corner pasan dos cosas: **que te rematen** y **que ese remate entre**. La defensa se
mide en dos partes: **prevención** (¿te rematan menos de lo que debería pasar con ese tipo de centro?) y
**supresión** (cuando te rematan, ¿tu defensa hace el remate más difícil?). El trabajo previo solo tenía la foto del
remate, así que el centro despejado sin remate no se veía y con 51 goles no alcanzaba para distinguir equipos. Ahora
usamos la foto del momento del cobro (360) y toda la liga.

![El árbol de probabilidad del xDefense](figuras/balon_parado/arbol_corner.png)

**Demostración (probabilidad condicional y total).** $C$ = el saque, $S$ = hubo remate, $G$ = hubo gol.
1. *Condicional:* no hay gol sin remate ($G\subseteq S$), así que $P(G\mid C)=P(S\mid C)\,P(G\mid S,C)$: capa 1 por capa 2.
2. *Total:* $P(G\mid C)=P(G\mid S,C)P(S\mid C)+P(G\mid\bar S,C)P(\bar S\mid C)$, y el segundo término vale 0.
3. *Recursión (el rechace):* con $q_k$ la probabilidad de que entre el $k$-ésimo remate,
   $V_k=P(S_k)\,[q_k+(1-q_k)V_{k+1}]$ y $P(G\mid C)=V_1$.
4. *Cuatro pedazos exactos* (sumar y restar): $\hat p\kappa-g=(\hat p-s)\kappa+s(\kappa-B)+s(B-F)+s(F-g)$ =
   prevención + alejamiento + supresión + portero. Al atacar, el signo se invierte (xO).

Versión formal: `04_MODELO_MATEMATICO.md` §16.5–16.6.
![Cuánto arco le tapa la defensa al que remata](figuras/balon_parado/goal_open_esquema.png)

**Los modelos (toda la liga, fuera de muestra).** Capa 1, centros al área: 28,599 saques, 31.5 % con remate, AUC 0.632,
calibración 1.000. Capa 2: 47,267 remates, AUC sin defensa 0.758 y con defensa 0.786 (+0.027 [+0.022, +0.032]): la
posición de la defensa sí informa.

**Lo demostrado del xDefense:**
* **Supresión (H25 🟢) y al revés de lo esperado.** Los remates que concede valen **más** de lo que valdrían sin su
  defensa: −0.0048 de xG por remate [−0.0077, −0.0019]. En corners en contra: −0.30 goles por 100 corners
  [−0.48, −0.13]; en todo el balón parado en contra: −0.10 [−0.18, −0.04]. Concede menos remates, pero los que concede
  llegan más limpios.
* **Quién puede compararse.** Entre técnicos-club la prevención sí varía de verdad (Q de Cochran: corners p = 7·10⁻⁵,
  τ² = 0.067; centros al área p = 0.009, τ² = 2.9·10⁻⁴). La **supresión no**: sus técnicos no se distinguen (τ² ≈ 2.4·10⁻⁶),
  así que **no se da un puesto en supresión** (lo que decide un corner en contra es si te rematan).
* **No demostrado:** prevención de Almada (H24: +0.016 [−0.010, +0.043]), xD/xO totales por familia, el término
  del portero y del alejamiento, y cualquier xD de tiros libres y laterales.

![De dónde salen los goles que Almada evita y genera a balón parado](figuras/balon_parado/descomposicion.png)
![Las dos capas del xDefense en todos los técnicos](figuras/balon_parado/mapa_xdefensa.png)
![Supresión por técnico](figuras/balon_parado/xd_remate_etapas.png)

### 5.2 Corners

* **En contra: pone menos gente y marca al hombre (H26 🟢).** Defensores en el área 6.65 contra 8.67; en el área chica
  1.95 contra 3.14; primer palo cubierto 7.5 % contra 15.1 %; segundo palo 0.5 % contra 2.5 %. Marca al hombre (a ≤ 2 m)
  52.5 % contra 38.6 %, más pegado (2.21 m contra 2.71) y deja menos defensores sobrando (2.20 contra 2.96).
* **Le rematan 15 % menos por corner (en contra, razón 0.85 [0.75, 0.96])** y en 32.6 % de los corners (la liga, 36.7 %). Con la
  ventana de 15 s que incluye el rechace. A favor: razón 0.89 [0.81, 0.98] (remata menos por corner). Con remate a
  favor: 32.5 % contra 36.7 %.
* **A favor: más corners, más cortos y más cerrados.** 6.09 por partido contra 4.82. En corto 34.8 % contra 20.6 %;
  cerrados (inswinging) 58.6 % contra 43.6 %; abiertos 36.9 % contra 52.6 %. Al punto penal solo 16.0 % (la liga,
  25.6 %) y al segundo palo 7.9 % (13.5 %). Gana el primer contacto en 57.5 % (48.1 %), pero lo remata directo menos
  (15.1 % contra 19.0 %).
* **Manda menos gente al área:** 5.15 atacantes contra 5.48; en el área chica 0.92 contra 1.13; encima del portero
  0.05 contra 0.13.
* **¿Qué corners funcionan en la Liga MX?** El cerrado al punto penal (0.045 xG por corner, +0.011 contra el resto) y
  el abierto al punto penal (0.044, +0.011). Los cortos rinden mucho menos (sin dato → corto 0.026, abierto → corto
  0.011, cerrado → corto 0.007). **Almada manda menos corners al penal (donde más rinde) y más al corto (donde
  menos rinde).**
* **La "receta Arsenal"** (cerrado al área chica o primer palo con atacantes encima del portero): 417 corners, 0.037
  contra 0.035 de xG, +0.002 [−0.008, +0.012]. **No se demostró que rinda más ni que rinda igual** (con el margen
  de ±0.01 el intervalo no cabe). Almada la usa en 1 % de sus corners y la liga en 3 %. Con estos datos no hay razón
  para importarla; lo que sí se traslada es el método: medir qué rutina produce más en esta liga.
* **No demostrado:** xG por corner de Almada (0.030 contra 0.035), corners en contra por partido, primer contacto
  del rival, xD y xO de corners (salvo la supresión).

![Cómo se para en los corners en contra](figuras/balon_parado/corner_defensivo.png)
![¿Marcar al hombre evita remates?](figuras/balon_parado/marca_vs_remate.png)
![Qué corners producen más en la Liga MX y cuáles usa Almada](figuras/balon_parado/rutinas_corner.png)

### 5.3 Tiros libres

Reglas que importan: la barrera a 9.15 m (regla 13) y la línea del fuera de lugar (regla 11).

* **A favor:** cobra más tiros libres directos (0.76 por partido contra 0.52) y más en campo rival sin ir al área
  (4.02 contra 2.82), y menos al área (1.42 contra 1.82).
* **En contra:** le sacan más tiros libres al área (2.11 contra 1.82 por partido).
* **Defiende con menos gente en la línea (4.71 contra 5.28)** y pone una barrera más grande en los directos (3.24
  contra 2.71 jugadores).
* **No demostrado:** altura de la línea (14.8 m contra 14.2), fuera de lugar provocado, arco libre que deja la barrera,
  goles y xG de tiros libres, y todo xD/xO de tiros libres (incluido el directo).

![Tiros libres a favor, en contra y la liga](figuras/balon_parado/tiros_libres.png)
![Qué tan adelantada pone la línea](figuras/balon_parado/linea_tiros_libres.png)

### 5.4 Laterales en el último cuarto (x ≥ 90 m) y octavo (x ≥ 105 m)

* **A favor:** saca 6.01 laterales por partido desde el último cuarto contra 5.10; 28.5 % caen en el área (la liga,
  22.7 %); laterales largos al área 1.80 por partido contra 1.29. En contra: le sacan 5.74 (pero solo hay evidencia
  de volumen, no de peligro).
* **Caen en el área chica y terminan en remate con 2 o más que intervienen (Fisher exacta, q < 0.01).** Es lo que
  pidió el reto: a favor de Almada, 4 de 1,010 laterales del último cuarto (0.4 %) contra 6 de 16,962 en la liga
  (0.04 %); y 4 de 462 desde el octavo. **Son muy pocos casos (4) y 0 goles:** el patrón existe, pero no se puede
  hablar de efecto en goles.
* **Cuántos intervienen hasta el remate:** en los laterales con remate casi siempre intervienen 2 o más jugadores
  (Almada 114 de 141): la segunda jugada es la norma.
* **No demostrado:** que sus laterales terminen en más remates o goles, xG por lateral, y xD/xO de laterales (el de
  laterales largos al área a favor da −0.87 goles por 100 [−1.22, −0.19]: concreta menos de lo esperado, con 302
  saques y 1 gol; no entró al control y no se afirma).

![Laterales desde el último cuarto](figuras/balon_parado/laterales_cuarto.png)
![Lo mismo desde el último octavo](figuras/balon_parado/laterales_octavo.png)

---

## 6. Simulación y América

* **Puntos.** 280 puntos en 168 partidos contra 266.0 esperados por sus ocasiones (+14.0, p = 0.33) y 260.0 por su
  estilo: **no se demostró** que haya rendido más de lo que merecía. El modelo de partido sí predice (Brier 0.627
  contra 0.660 de las frecuencias).
* **Proyección en el América** (llegó el 2026-07-19). Plantel que encontró: ataque 1.11 y defensa 0.78 (1 =
  promedio). Su efecto de llegada (1 llegada previa, contraída hacia 70 de la liga): ataque +1 %, defensa −10 % de xG
  concedido. Con él: 1.48–0.97 xG por partido, **29.6 puntos en 17 partidos (intervalo conforme del 80 %: 21–38)**,
  posición media 5.0, liguilla directa 73 %; solo el plantel: 29.1 (21–37), 70 %. En sus 9 partidos reales: proyectado
  15.7 (conforme 11–20), real **20 puntos**.
* **¿Qué tanto creerle?** Sobre las 70 llegadas de la liga la proyección **se asocia con lo real** (correlación 0.62,
  p = 1.4·10⁻⁸, demostrado) pero **no se demostró que le gane a la inercia**: error 0.30 contra 0.31 puntos por partido
  (Diebold-Mariano p = 0.32). El intervalo del simulador cubría 67 % (no 80 %); por eso se usa el conforme, que cubre
  80 % por construcción. Se reporta como escenario, no como resultado: la diferencia entre "con Almada" y "solo el
  plantel" (0.5 puntos) está dentro de cualquier intervalo.

![Proyección de Almada en el América](figuras/simulacion/proyeccion.png)

---

## Lo que NO se demostró

Nada de esto se interpreta: sin evidencia suficiente, no se afirma ni que exista ni que no exista.

* Puntos por partido contra rivales fuertes, medios o débiles, y que ajuste su estilo al nivel del rival (H22).
* Progresar por carriles distintos (H19); xG por remate; xG de juego abierto; xG concedido global.
* Que sus cambios muevan el xG o el estilo (H23), el momento de sus cambios (H13) y su reacción al marcador desde la
  banca (H14).
* Prevención de corners de Almada (H24) y cualquier ventaja de la receta Arsenal; altura de la línea de fuera de
  lugar; xD/xO de tiros libres y laterales (salvo la supresión).
* Que la proyección mejore la inercia; si rindió más de lo que merecía.
* **No demostrables por diseño:** rotación del once (H17) y estabilidad del once (calendario incompleto).

## Límites

* **América: 9 partidos** y Santos Laguna: 20. Por eso ninguna afirmación del foco en esos clubes pasa el filtro de
  20 partidos.
* **Las cámaras 360 no ven a todos:** se mide solo con los jugadores que aparecen en cada foto (por eso el control de
  cámara del bloque).
* **xG y OBV son modelos del proveedor:** la eficiencia coincide en signo con xG, OBV y tasa de remate (blindaje).
* **Multiplicidad, no selección:** el control corrige por hacer muchas pruebas, no por haber formulado algunas
  preguntas (balón parado por familias, pruebas de la proyección) después de ver la fase G. Los partidos nuevos de la
  temporada (2026/27, incluidos 9 del América) sirven para confirmarlas fuera de la muestra en que se formularon.
