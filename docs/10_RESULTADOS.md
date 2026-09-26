# 10 — Resultados, Fase 1 (el vocabulario)

> Cada hallazgo lleva etiqueta: 🟢 probado (contraste con su nula) · 🟡 medido
> (número con su incertidumbre o validación cruzada) · ⚪ descriptivo ·
> 🔴 refutado. **Ningún número se cita sin leer su fila.**
> Corrida de referencia: 2026-09-24, `dtcoach fase0` + `cv-k` + `mezcla` + `bondad`.

---

## 1. El dataset

| cantidad | valor |
|---|---|
| partidos | 1,767 (6 temporadas, 19 equipos) |
| eventos aplanados | 5,744,380 |
| transiciones | 3,003,495 |
| posesiones StatsBomb | 388,115 |
| **secuencias** (unidad de la cadena, ADR-v2-14) | **461,454** |
| estados | 20 zonas (malla 5×4) + 4 absorbentes |
| cobertura 360 | > 99 % en los técnicos candidatos |

⚪ `coordinate_sanity` = 0.723: la tasa de gol crece hacia x = 120, así que el
marco de coordenadas y el espejo del rival están bien orientados.

---

## 2. 🟢 Una posesión de StatsBomb no es una secuencia de la cadena

**60,447 posesiones (15.6 %) contienen más de una absorción**: 65,667 pérdidas y
7,668 remates ocurren *a mitad* de posesión, y el mismo equipo sigue con el
balón (rebote, córner a favor, recuperación inmediata).

Evidencia de que importa, midiendo E[T] de la liga contra el modelo:

| unidad | E[T] modelo | E[T] empírico | error |
|---|---|---|---|
| posesión StatsBomb | 5.48 | 7.12 (sintético equivalente) | −23 % |
| **secuencia** | **6.502** | **6.509** | **−0.1 %** |

Con secuencias, el modelo reproduce además el xG por secuencia de **cada tipo**
hasta el tercer decimal. El test `test_cierre_de_flujo_K1` falla si esto se
rompe. Definición en el framework (§1 de `03_FRAMEWORK.md`).

---

## 3. 🟡 La sobredispersión que rechazó a Markov es, sobre todo, heterogeneidad

> **Corregido por ADR-v2-33.** La versión original decía "es heterogeneidad, no memoria". La mezcla reproduce la cola, pero no el arranque: queda un efecto de primer paso. La fase 1 v3 lo mide (memoria explicada por los tipos) y lo modela (P⁰).

El proyecto anterior rechazó la cadena de orden 1 porque la cola de la duración
era más pesada que la predicha, y concluyó "hace falta memoria". Con secuencias
y una mezcla, la cola se reproduce **sin memoria**:

| P(T > t) | t = 10 | t = 15 | t = 20 | KS |
|---|---|---|---|---|
| datos | 0.1825 | 0.0950 | 0.0509 | — |
| una cadena (K = 1) | 0.1911 | 0.0807 | 0.0336 | 0.0591 |
| mezcla K = 5 | 0.1838 | 0.0951 | 0.0508 | 0.0355 |
| **mezcla K = 3** (elegida) | 0.1857 | 0.0944 | **0.0492** | **0.0378** |

**Lectura:** Markov de primer orden falla *sobre la liga* porque promedia
jugadas de naturaleza distinta; **dentro de cada tipo de secuencia, Markov
basta**. Es el resultado que cierra la pregunta abierta de la versión anterior
y la razón de que no haga falta M2 (memoria) ni un HMM (ADR-v2-02).

🟡 **Residuo declarado:** el desajuste que queda se concentra en t = 1–3 (el
modelo predice 0.823 y se observa 0.859 en P(T > 1)). El primer paso de una
secuencia absorbe menos que una acción cualquiera desde la misma zona: un
"efecto primer toque". Se reporta como límite; extensión candidata, no
obligatoria: una fila de transición propia para el primer paso.

---

## 4. 🟡 K: la verosimilitud no lo elige sola

Validación cruzada por partido, 5 pliegues, diferencias **pareadas** (ADR-v2-10):

| K | nats/transición | mejora vs K−1 | t pareado | ganancia acumulada |
|---|---|---|---|---|
| 1 | −2.3224 | — | — | 0 % |
| 3 | −2.3072 | 0.0152 | 90.9 | 73 % |
| 4 | −2.3049 | 0.0024 | 34.9 | 84 % |
| 5 | −2.3032 | 0.0016 | 7.1 | 92 % |
| 6 | −2.3020 | 0.0012 | 5.6 | 98 % |
| 7 | −2.3015 | 0.0005 | 7.8 | 100 % |

Todas las mejoras son positivas en los 5 pliegues: con 461 mil secuencias
siempre paga añadir un tipo. El KS tampoco separa (0.0363 / 0.0355 / 0.0342
para K = 4 / 5 / 6). **K se decide por reproducibilidad e interpretabilidad**
(ADR-v2-17), no por ajuste.

---

## 5. 🔴 → 🟢 Reproducibilidad: solo K ≤ 3 da tipos identificables

k-means dio 9 óptimos para K = 5 (se descartó, ADR-v2-17). Con la escalera y 3
semillas por K:

| K | rango de J | acuerdo mínimo | ¿reproducible? |
|---|---|---|---|
| 2 | 0.1 | 1.000 | ✅ |
| **3** | **7.8** | **0.993** | ✅ |
| 4 | 1,815.6 | 0.582 | ❌ |
| 5 | 1,225.0 | 0.567 | ❌ |
| 6 | 1,073.3 | 0.539 | ❌ |

Desde K = 4, soluciones que asignan distinto a más del 40 % de las secuencias
difieren en unos 0.003 nats por secuencia: los datos no las distinguen. **Se
fija K = 3** (ADR-v2-19). Ajusta casi igual que K = 5: KS 0.0378 contra 0.0355.

---

## 6. 🟡 El vocabulario: tres familias de secuencia (K = 3, reproducible)

| familia | π | E[T] modelo | E[T] empírico | P(remate) | xG/secuencia |
|---|---|---|---|---|---|
| 1 · **Directa** | 0.323 | 3.26 | 3.25 | 0.111 | **0.0143** |
| 2 · **Circulación estéril** | 0.266 | 6.63 | 6.61 | 0.031 | 0.0033 |
| 3 · **Ataque elaborado** | 0.411 | 8.97 | 9.00 | **0.144** | 0.0115 |

Nombres fijados al ver las figuras (ADR-v2-20):

- **Directa.** Nace en la salida propia y también en recuperaciones en el
  último tercio. Dura 3 acciones. Tiene el **mayor valor de zona frente al
  área** (0.13 xG) y el mayor xG por secuencia de la liga.
- **Circulación estéril.** Nace en medio campo y **retrocede**: visita campo
  propio y el centro, casi nunca el último tercio. El 90 % termina en pérdida.
- **Ataque elaborado.** Progresa **por las bandas**: sus zonas más visitadas son
  los carriles exteriores del tercio 72-96. Es la que más remata.

La lectura: dos ejes, duración y peligro, que no van juntos. La secuencia de
duración media es la más estéril, y la más corta es la más peligrosa por
secuencia.

**Curva de K (K = 2 a 9):** solo K = 2 y K = 3 son reproducibles; el KS no mejora
al subir K (0.033 a 0.038); el peso del tipo más chico cae de 0.30 (K = 3) a
0.07 (K = 9). Figura: `reports/mezcla/curva_k.png`.

---

## 7. 🟡 Las eras: de 2,916 discrepancias a 1

Contraste de las eras verificadas contra `managers` del API, por partido:

| causa | antes | ahora | qué es |
|---|---|---|---|
| formato de nombre | 2,521 | **0** | el API da el nombre legal; las eras, el de uso (ADR-v2-13) |
| A_borde | 151 | 151 | la era corta al acabar la fase regular; faltan liguilla y 2026/27 |
| A_sin_era | 74 | 74 | técnicos nuevos de 2026/27 e interinos |
| AB (sin dato en ninguna fuente) | 170 | 170 | el API no trae DT |
| **C (personas distintas)** | 395 | **1** | Mazatlán, 2022-03-13 |

⚠️ **Estado: las correcciones existen en `eras_api_v2` pero el pipeline todavía
usa `eras_api`.** Falta apuntar `rutas.eras_dir` y `rutas.exclusiones` en el
config (§ pasos pendientes de `02_ESTADO.md`).

---

## 8. 🟡 Técnico focal: André Jardine

| dt | partidos | clubes | fase regular | 360 |
|---|---|---|---|---|
| **Andre Jardine** | **178** | **2** (América 127, San Luis 51) | 148 | 0.994 |
| Guillermo Almada | 153 | 2 (Pachuca 136, Santos 17) | 136 | 1.00 |
| Nicolas Larcamon | 146 | 4 | 135 | 0.993 |

Jardine cumple los cuatro criterios del roadmap y es **mover**, así que habilita
el capítulo "¿es él o es el plantel?". Bono: **Almada dirige al América en
2026/27**, lo que da el contraste inverso (mismo plantel, otro técnico) y un
segundo mover de primer nivel para comparar.

---

## 9. Fase 2 — André Jardine contra la liga (hipótesis pre-registradas en `11_HIPOTESIS.md`)

Corrida del 2026-09-24. 461,454 secuencias; las de Jardine son 22,562 de ataque
y 22,526 de sus rivales, en 183 partidos (América 129, San Luis 54). Elo:
K = 20, h = 60, calibrado (E contra S dentro de 3 pp en cada quintil).
Ninguna columna del modelo resultó no estimable.

| id | pregunta | resultado | q (BH) | evidencia |
|---|---|---|---|---|
| H1 | identidad ofensiva | W = 11.2, gl 2 | 0.011 | 🟢 pero **pequeña** |
| H2 | identidad defensiva | W = 30.8, gl 2 | < 0.001 | 🟢 |
| H3 | reacción al marcador | W = 5.5, gl 4 | 0.315 | ⚪ |
| H4 | final del partido | W = 0.1, gl 2 | 0.939 | ⚪ |
| H5 | localía | W = 0.7, gl 2 | 0.770 | ⚪ |
| H6 | fuerza del rival | W = 2.3, gl 2 | 0.373 | ⚪ |
| H7.1 | eficiencia ofensiva · Directa | +0.0018 [−0.0005, +0.0040] | 0.169 | ⚪ |
| H7.2 | eficiencia ofensiva · Circulación estéril | +0.0015 [+0.0007, +0.0023] | 0.002 | 🟢 |
| H7.3 | eficiencia ofensiva · Ataque elaborado | +0.0020 [+0.0009, +0.0032] | 0.002 | 🟢 |
| H8.1 | eficiencia defensiva · Directa | −0.0018 [−0.0039, −0.0000] | 0.107 | ⚪ |
| H8.2 | eficiencia defensiva · Circulación estéril | −0.0004 [−0.0009, −0.0000] | 0.107 | ⚪ |
| H8.3 | eficiencia defensiva · Ataque elaborado | −0.0012 [−0.0021, −0.0004] | 0.013 | 🟢 |

### En la cancha

**Qué elige (H1, 🟢 pero pequeño).** En sus mismas situaciones, su equipo usa
+1.0 pp de *Directa* [+0.2, +1.8] y −0.7 pp de *Circulación estéril*
[−1.3, −0.2]. Es estadísticamente distinto de la liga, pero **su identidad no
está en qué tipo de jugada elige**. Para saber si 1 pp es mucho o poco para la
Liga MX, ver el atlas (fase 3, exploratorio).

**Qué le hacen (H2 🟢 + H8.3 🟢): la historia defensiva.** Contra Jardine, los
rivales juegan **−2.1 pp de *Directa*** [−2.9, −1.3] y **+2.7 pp de *Ataque
elaborado*** [+1.6, +3.6] que contra el resto de la liga, con la fuerza del
rival ya descontada por el Elo. Y cuando elaboran, generan **10 % menos xG**
(0.0102 contra 0.0113). Lectura: *le quita al rival la jugada directa, lo
obliga a elaborar y defiende bien esa elaboración.*

**Qué tan bien lo hace (H7 🟢).** Con las mismas jugadas genera más peligro:
**+18 % de xG** en *Ataque elaborado* (0.0134 contra 0.0113) y **+47 %** en
*Circulación estéril* (0.0048 contra 0.0032). ⚠ Es el rasgo más expuesto al
plantel: el América es de los planteles más caros de la liga. La fase 3 lo
contrasta con San Luis.

**Cuándo cambia (H3–H6 ⚪).** No detectamos que reaccione al marcador, al
minuto, a la localía ni al rival de forma distinta que la liga
(`reports/fase2/contexto_andre_jardine.png` tiene las cotas por familia).

**Combinación pre-registrada que aplica:** *identidad por encima de
reactividad* (H3–H6 ⚪), con la diferencia puesta en **cómo ejecuta y cómo
defiende**, no en qué elige.

---

## 10. Fase 3a — ¿Es él o es el plantel? (H9–H12 pre-registradas)

El mismo modelo de la fase 2, por separado para cada club de Jardine, contra la
misma liga y sin su otra etapa en la referencia.

| rasgo | América (129 p.) | San Luis (54 p.) | ¿viaja? |
|---|---|---|---|
| **defensa (H2):** rivales con menos *Directa* | −2.3 pp 🟢 | −1.9 pp | ✅ **H9: viaja** |
| **defensa (H2):** rivales con más *Ataque elaborado* | +2.6 pp 🟢 | +2.7 pp | ✅ **H9: viaja** |
| eficiencia ofensiva en *Ataque elaborado* (H7.3) | +0.0028 🟢 | −0.0001 [−0.0016, +0.0013] ⚪ | ❌ H10 |
| eficiencia defensiva en *Ataque elaborado* (H8.3) | −0.0020 🟢 | +0.0003 [−0.0015, +0.0020] ⚪ | ❌ H11 |
| identidad ofensiva (H1) | ⚪ (0.6 pp) | 🟢 (2.5 pp) | mezcla distinta: H12 en *Directa*, −2.2 pp [−3.8, −0.5] |
| adaptación a la fuerza del rival (H6) | ⚪ | 🟢 | solo en San Luis (exploratorio) |

**Atlas (exploratorio, 15 eras con ≥ 50 partidos).** Medida: distancia de
variación total entre la mezcla del técnico y la de la liga en sus mismas
situaciones.

- **Defensa:** sus dos etapas están entre las 4 más altas de 15 (América
  2.6 pp, San Luis 2.7 pp; solo Efraín Valdez las supera con 2.9 pp). Es su
  rasgo distintivo en la Liga MX.
- **Ataque:** América 0.6 pp, puesto 14 de 15 (de las más parecidas a la liga);
  San Luis 2.5 pp, puesto 4 de 15. Mediana de la liga: 1.3 pp.

### La historia

> **Su firma es defensiva y viaja con él.** Con dos planteles muy distintos, sus
> rivales renuncian a la jugada directa y tienen que elaborar. **En ataque se
> adapta a lo que tiene:** con un plantel modesto jugó más directo, más distinto
> a la liga y ajustándose al rival; con el América juega lo que juega la liga,
> pero lo ejecuta mejor, y esa ventaja de ejecución **no aparece** en San Luis,
> lo que es compatible con que la aporte el plantel.

Matices: la lectura de "se adaptó" (H6 y la magnitud de H12) es exploratoria.
El H1 🟢 del conjunto (fase 2) lo empuja San Luis: el América solo da ⚪. El H3
🟡 del América (reacción al marcador) no sobrevive a BH.

---

## 11. Fase 3b — Sus decisiones desde la banca (H13–H17 pre-registradas)

Datos: 136,740 equipo-minutos, 14,757 sustituciones (821 de Jardine) y 3,351
equipos-partido, siempre contra la liga sin el foco.

| id | pregunta | resultado | q (BH) | evidencia |
|---|---|---|---|---|
| **H13** | ¿cuándo cambia? | su primer cambio del 2º tiempo llega **~3 min después** que el de la liga | 0.005 | 🟢 |
| H14 | ¿su banca reacciona al marcador distinto? | adelanta sus cambios al perder, **igual que la liga** | 0.605 | ⚪ |
| H15 | ¿qué tipo de cambio hace? | misma mezcla que la liga (~70 % del mismo puesto) | 0.479 | ⚪ |
| H16 | ¿reacomoda más la formación? | 1.72 contra 1.80 reacomodos por partido | 0.479 | ⚪ |
| **H17** | ¿rota más su once? | 1 − Jaccard 0.398 contra 0.335: **~2.7 titulares distintos por partido contra ~2.2** | 0.003 | 🟢 |

**Primer cambio del 2º tiempo:** empatando, minuto 60.8 contra 58.0 (+2.9
[+1.2, +4.5]); perdiendo, 57.0 contra 55.0 (+2.1 [+0.4, +3.8]); ganando, 60.4
contra 57.3 (+3.1 [+1.2, +4.9]).

**Formación base:** 4-2-3-1 en el América (57 partidos), con 8 sistemas
distintos en total (4-4-2, 3-4-3, 4-3-3, 3-4-2-1…).

⚠ **H17 no controla el calendario.** El América juega Concachampions y Leagues
Cup, que no están en los datos. Más rotación puede ser una respuesta a más
partidos, no una idea del técnico.

## 12. Simulador (exploratorio)

**Validación de xPts:** en toda la liga, 4,833 puntos reales contra 4,856
esperados (error del 0.48 %). El método está bien calibrado.

**Jardine:** 306 puntos en 183 partidos contra 296.1 esperados (**+9.9**,
z = +0.68, p = 0.49). **Es azar**: sus equipos sacaron los puntos que su xG y el
de sus rivales merecían. La curva acumulada nunca sale de la banda de ±1.96 DE.

**Escenarios:** en las 54 combinaciones de marcador, minuto, localía y rival, su
equipo produce unos +0.002 xG por secuencia más que la liga en el mismo
escenario, **casi constante**. No es un defecto: con H3–H6 ⚪ su mezcla no
responde al contexto distinto que la liga, así que toda la diferencia viene de
la eficiencia (H7), que la fase 3a mostró que es del América y no viaja.

**Calibración del modelo de contexto:** error medio de 2.01 pp (distancia de
variación total, predicha contra observada) en 28 celdas con ≥ 300 secuencias
de Jardine. Ver `SIMULADOR_andre_jardine.md` para el ruido de muestreo esperado
con esos tamaños de celda.

## 13. El retrato completo de André Jardine

> Escrito con el vocabulario v2. Con el v3 se sostiene (§16), con un matiz en el punto 4: en San Luis sí reaccionaba al marcador y al rival (H3 🟢, H6 🟢); en el América, no.

1. **Su firma es defensiva y viaja con él** (H2 🟢, H9 ✅). Contra sus
   equipos, los rivales renuncian a la jugada directa y tienen que elaborar,
   y el atlas lo pone entre las etapas más distintas de la liga en ese rasgo.
2. **En ataque, se adapta a lo que tiene** (H1, H12, atlas). En San Luis jugó
   más directo y distinto a la liga; en el América juega lo que juega la liga.
3. **La ejecución superior es del América** (H7, H8 🟢 en el América; H10,
   H11 ❌). Compatible con el plantel, no con el técnico.
4. **No negocia su idea con el partido** (H3–H6, H14 ⚪) y **es paciente con la
   banca** (H13 🟢: tarda ~3 min más en su primer cambio). Rota más su once
   (H17 🟢), con la advertencia del calendario.
5. **Sus resultados son los que merecía** (xPts: +9.9, dentro del azar).

---

## 14. Lo que este bloque NO dice

- Nada sobre el estilo de ningún técnico: la Fase 1 construye el vocabulario de
  la liga, no describe a nadie. Eso es la Fase 2.
- Nada causal. π, δ y las tarjetas describen lo que hizo un equipo; no aíslan
  decisiones del técnico del plantel ni del calendario.
- Los nombres de los tipos (*Directa*, *Circulación estéril*, *Ataque
  elaborado*) resumen sus figuras y sus secuencias típicas con el ajuste
  reproducible (ADR-v2-06, ADR-v2-20); son etiquetas, no definiciones.

---

## 15. Fase 1 v3 — corrida con malla 12×8 (2026-09-25)

**Válido y citable:**
- 🟢 **Paso inicial (P⁰):** validación cruzada pareada t = 13.2; KS de la duración 0.043 → 0.007; P(T > 1) modelado 0.8589 contra 0.8589 observado. Con K = 2 y P⁰, la supervivencia coincide con lo observado dentro de ~0.01 en todos los t (KS 0.011; K = 1: 0.056).
- 🟢 **Verificación formal:** ρ(Q) = 0.835 (vida media 3.85 acciones); irreducible y aperiódica sobre lo observado; estacionaria de la cadena reiniciada = visitas μᵀN (error 6·10⁻¹⁷).
- 🟢 **Irreversibilidad:** lejos del balance detallado (G² = 304 mil, 4,200 gl); σ = 0.244 nats por transición y avance neto de +2.7 m por acción en la liga.
- 🟡 **Llegada (primer paso):** último tercio, P = 0.501 modelado (K = 1) contra 0.488 observado; frente al área, P = 0.127 contra 0.127, pero **E[acciones | llega] = 5.36 contra 6.02** (no cumple la tolerancia de 0.2). Combinando los dos tipos de la mezcla, P(último tercio) = 0.489 y E(área) = 5.72: la heterogeneidad reduce la brecha.
- ⚪ **Resolución espacial:** la log-densidad predictiva crece de forma monótona hasta 12×8 y la agregación contigua no fusiona ninguna celda: la ubicación de la siguiente acción es predecible al menos a 10 m. No se encontró un óptimo (el candidato más fino ganó).

**No válido (retirado):**
- 🔴 Memoria por información mutua plug-in (sesgo de muestra finita; ADR-v2-34).
- 🔴 K = 2 con 12×8 como vocabulario: ningún K cumplió la regla y el script eligió por defecto (ADR-v2-35).
- 🔴 Los nombres "Directa" y "Circulación estéril" en `MARKOV.md` de esa corrida: eran de otro K.

---

## 16. Vocabulario v3 (malla 5×4, K = 3, paso inicial) y réplica de las fases 2 y 3 (2026-09-25)

### El vocabulario

Elegido por la regla enmendada (ADR-v2-35): 8×5 sin K reproducible, 6×4 con K = 2, **5×4 con K = 3** (acuerdo suave 0.997; rango de J 1.9, es decir 4·10⁻⁶ por secuencia). Paso inicial adoptado (t = 13.2). Duración: **KS 0.0051** (con una sola cadena, 0.0597).

| familia | % | acciones | P(remate) | xG/sec | vida media | avance por acción | llega frente al área |
|---|---|---|---|---|---|---|---|
| **Directa** | 36 % | 3.5 | 0.140 | **0.0144** | 1.7 | **+3.4 m** | 17 % en 2.2 acciones |
| **Circulación estéril** | 26 % | 6.7 | **0.025** | 0.0026 | 4.4 | +2.9 m | 5 % |
| **Ataque elaborado** | 38 % | 9.2 | 0.122 | 0.0114 | 5.9 | +2.3 m | 22 % en 8.4 acciones (82 % llega al último tercio) |

Nombres confirmados con `tipos_K3_inicio.png` y `tipos_K3_visitas.png`: la *Directa* nace en el área propia y en las esquinas del último tercio; la *Circulación estéril* vive entre los metros 24 y 72 y casi no inicia en el último tercio; el *Ataque elaborado* concentra sus visitas en los carriles exteriores del tercio 72–96.

**Propiedades de la cadena (5×4):** termina con probabilidad 1 (ρ = 0.838), irreducible y aperiódica sobre lo observado, estacionaria = μᵀN (error 2·10⁻¹⁶), fuertemente irreversible (G² = 164 mil, 190 gl). La llegada modelada con la mezcla cumple la tolerancia pre-registrada (frente al área: 5.75 acciones contra 5.88 observadas); con una sola cadena, no (5.21).

**Memoria (fuera de muestra):** conocer la zona anterior mejora la predicción de la siguiente en +0.058 nats por acción (≈ 3 % de la incertidumbre), y **los tipos explican solo el 4.5 %**. 🟢 La duración la explica la heterogeneidad; **hacia dónde va el balón tiene memoria real dentro de cada tipo**. Corrige la lectura original de ADR-v2-16 (ver ADR-v2-33).

### Robustez: las conclusiones de las fases 2 y 3 no cambian con el vocabulario

| conclusión | v2 (5×4, K = 3, sin P⁰) | v3 |
|---|---|---|
| Jardine: rivales con menos *Directa* y más *Elaborado* (H2) | 🟢 −2.1 / +2.7 pp | 🟢 −2.0 / +2.4 pp |
| Jardine: ese rasgo viaja entre clubes (H9) | ✅ | ✅ |
| Jardine: eficiencia ofensiva en *Circulación* y *Elaborado* (H7) | 🟢 | 🟢 |
| Jardine: la eficiencia no viaja a San Luis (H10, H11) | ❌ | ❌ |
| Jardine: atlas, separación defensiva | top 4 de 15 | **1.º (San Luis) y 3.º (América)** |
| Almada: rivales rinden menos en *Directa* y *Elaborado* (H8.1, H8.3) | 🟢 | 🟢 |
| Almada: amortigua la reacción de la liga al marcador y al rival (H3, H6) | 🟢 | 🟢 |
| Almada: cambios del mismo puesto y pocos reacomodos (H15, H16) | 🟢 | 🟢 |
| xPts de ambos | dentro del azar | idéntico |

**Cambios y novedades:**
- El H1 conjunto de Jardine pasa a ⚪ (W = 2.5). En San Luis salen además H3 🟢 y H6 🟢: allí reaccionaba al marcador y al rival; en el América, no.
- Almada en el América (7 partidos): exploratorio, sin 🟢 (regla pre-registrada). El W = 61 de H3 ilustra el problema de pocos conglomerados. Indicio: +2.6 pp de *Directa* respecto a Pachuca [+0.3, +4.9].
- Banca: Jardine abre su primer cambio ~3 min después que la liga (H13 🟢); Almada ~2 min antes empatando o perdiendo, pero su prueba conjunta no sobrevive a BH (q = 0.106): indicio, no conclusión.
