# Experimentos `exp/mejoras-6` — RESUMEN de las seis mejoras

Nada de esto cambia la entrega: el vocabulario oficial (5×4, K = 3), `config/default.yaml` y
`reports/{mezcla,fase1,fase2,fase3,historia}` siguen siendo la línea base. Todos los números son de las corridas
sobre los datos reales en la máquina del autor (2026-10-02 a 04). B se reporta con 200 réplicas. Copia versionada de
`reports/experimentos/RESUMEN.md`, que está en `.gitignore`.

| mejora | ¿pasó? | métrica antes | métrica después | delta | recomendación |
|---|---|---|---|---|---|
| **A** — supuesto «el técnico solo mueve π_k, no P^k» (04 §15.1–15.2; ADR-v2-52, 55) | Sí | percentil de Almada por exceso T/gl a n completo: 98 / 100 / 100, confundido con la potencia (ρ(exceso, partidos) = +0.43 / +0.65 / +0.69) | a igual n = 30 (mediana de 20 remuestras), exceso / TV: Directa 45 / 38 · **Circ. estéril 91 / 61** · Elaborado 70 / 33 | −53 / −9 / −30 puntos por exceso | **ADOPTAR la documentación**, no el modelo. Directa y Ataque elaborado: aproximación razonable. **Circulación estéril: no concluyente.** La regla se fijó antes de correr; no se usan los números de n = 40 |
| **B** — regresor generado (04 §7.1–7.2; ADR-v2-53, 57) | Sí (200 réplicas) | IC de H1–H8 con las r_sk como dato | 3 de 41 IC dejan de excluir el 0; en el BH global, demostradas 246 → 243 | −3 afirmaciones | **ADOPTAR la corrección** de la narrativa (sección de abajo). No cambia el método: retira lo que no aguanta |
| **C** — Voronoi × grafo de jugadores (exploratorio; ADR-v2-54) | Corrió | 13.3 y 13.5 sin cruzar | con más espacio, menos pase y menos remate (3.1 % → 0.4 %); mismo jugador bajo ≥ 2 técnicos: 720 jugadores, z² = 1.38 contra 1.19 de la nula, p = 0.002 | — | **NECESITA MÁS DATOS, de diseño:** cambiar de técnico casi siempre es cambiar de club, compañeros y época, así que no separa técnico de contexto. Se queda como exploratorio, fuera del BH |
| **D** — xGOT: portero y definición por separado (04 §16.7; ADR-v2-56, 58, 61) | Exacta y segura | un término «portero y definición» | 5 términos con error 1.9e-16; 0 de 730 veredictos cambian; Q de Cochran con p > 0.07 en las 24 combinaciones | **sin señal de equipo** | **RECHAZAR como métrica narrativa; ADOPTAR la documentación.** Las 2 o 3 pruebas nuevas «demostradas» no son narrables: bootstrap de 500 réplicas, pasos de 0.004, ruido de ±0.009. Encontró un error de la entrega: el bootstrap del balón parado no fijaba el orden de los partidos (ADR-v2-61, corregido) |
| **E** — arista marcada pase / conducción (04 §14.1; ADR-v2-59, 62) | **No** | acuerdo suave 0.997, rango de J 4e-6 | acuerdo suave **0.884**, rango de J **5.6e-4** por secuencia; KS 0.0036; E[T] 6.503 vs 6.509 | +0.0014 nats/acción con K = 3; **0 por construcción** con K = 1 | **RECHAZAR.** Falla (a). Al marginalizar la marca se recupera P(j\|i) exacta, así que la arista solo podía ganar identificando la familia; no se compara con dirección (+0.066). Además, Directa resultó ser la familia que MENOS conduce |
| **F** — quinto absorbente INTERRUPCIÓN_FAVOR (ADR-v2-60, 63, 65, 66) | **Sí, las tres variantes** | 21.47 % de la masa de PÉRDIDA son interrupciones a favor | acuerdo suave 0.998, rango de J ≈ 5e-6, KS 0.0048–0.0049, E[T] 6.502 vs 6.509; acuerdo con la mezcla oficial 0.981–0.983 | PÉRDIDA 83.2 % → 65.4 % con (ii) / 73.5 % con (iii) | **ADOPTAR (ii)** (con laterales, c = valor del balón parado), con (iii) como sensibilidad. (i) es la peor. Argumento abajo |

## Mejora F: qué variante y por qué

El criterio del vocabulario no decide entre (i) y (ii). El EM no usa c (las recompensas solo entran en V = N c), así que
son **la misma mezcla**: mismos acuerdo, rango de J, KS, uso, pérdida e interrupción, por construcción. No es un error:
c sí llega a V (ΔV de la liga: 0 en (i), +0.0015 a +0.0059 en (ii)). Las métricas que se comparaban por percentil, salvo
`valor_inicio`, no dependen de c. El reporte ahora trae todas las métricas del foco en las tres variantes, incluida
`valor_zona` (V de la liga promediado por sus acciones), para que la diferencia se vea.

- **(i) es la peor.** Con c = 0, un penal (0.78 xG) y un lateral en campo propio (0.0023) cuentan igual.
- **(iii) no es la defendible.** El argumento para sacar los laterales fue que valen menos que una secuencia cualquiera
  (0.0023 a 0.0070 contra 0.0102). Pero con ese mismo criterio se sacarían los tiros libres de las columnas 1 a 3
  (0.0031 a 0.0058, el 66 % de los tiros libres a favor). La comparación que importa no es contra «seguir jugando»,
  sino contra la etiqueta que les queda en (iii): PÉRDIDA, es decir, el balón en poder del rival, que para el equipo
  vale 0 o menos. Un lateral a favor conserva el balón; llamarlo pérdida es el sesgo original.
- **(ii)** le da a cada reanudación su propio valor por tipo y zona, así que el lateral pesa poco y el penal mucho, sin
  llamar pérdida a lo que no lo es. En V, (ii) y (iii) casi coinciden (ΔV máx. +0.0059 contra +0.0057). Donde difieren
  es en B: (iii) deja 8 puntos más de masa en PÉRDIDA.

**Efecto sobre Almada: a su favor, no en su contra.** El percentil de pérdida es la fracción de técnicos-club que pierde
lo mismo o menos que él. Baja de 30 a 14 con (ii) y a 20 con (iii): una vez separadas las interrupciones a favor, pierde
el balón menos que antes respecto de los demás. La métrica nueva (fracción de secuencias que terminan en
INTERRUPCIÓN_FAVOR) dice lo mismo. **El número honesto es el de Almada · Pachuca, 18.6 %, percentil 77 con (ii)** (59 con
(iii)): la nula se forma con técnicos-club, y «Almada (todo)», con percentil 84, junta tres clubes contra unidades de un
solo club. Ningún percentil de uso de las familias se movió más de 5 puntos: F corrige el destino de las secuencias sin
cambiar el vocabulario.

## Qué no sobrevive al propagar el error de primera etapa

Las responsabilidades r_sk salen de la mezcla (etapa 1), y los IC publicados de la fase 2 las trataron como datos. Con
un bootstrap de **200 réplicas** que reajusta la mezcla en cada réplica, cada IC publicado se ensanchó a la amplitud
«doble» y se rehízo el BH global de las 730 afirmaciones. **Demostradas: 246 → 243. Estas tres no se sostienen:**

| # | afirmación | p publicado | p con el error de la etapa 1 | por qué cae |
|---|---|---|---|---|
| 1 | Cuando va ganando, Almada sube **menos** su Directa que la liga (−1.7 pp) | 0.0145 | **0.0316** | estaba a 0.002 del corte del BH (≈ 0.017); un error 6 % mayor la saca. Su IC «doble» aún excluye el 0, pero la regla de demostración del proyecto es el BH |
| 2 | Almada remata **más** por secuencia de Circulación estéril que la liga (+0.32 pp) | 0.0175 | **0.625** | su IC pasa de [+0.06, +0.57] pp a [−0.96, +1.59] pp |
| 3 | Sus rivales rematan **menos** por secuencia de Circulación estéril (−0.55 pp) | 0.0005 | **0.217** | su IC pasa de [−0.76, −0.33] pp a [−1.42, +0.32] pp |

Las tres caen con las dos reglas usadas para escalar las Wald (f máximo y f del componente dominante).

**H2 no cae.** En cálculos anteriores (37 y 100 réplicas, y con un primer método que escalaba el z de p de bootstrap en
el piso) parecía caer o dependía de la regla, y en este mismo documento se dio por caída. Con el método corregido y 200
réplicas, H2 se sostiene con las dos reglas. Queda corregido aquí.

**Qué hay que reescribir en `RESULTADOS_ALMADA.md`:**
- *«… y remata menos en las tres (P(remate) del rival: −3.1 pp en Directa, −1.7 pp en Elaborado, −0.5 pp en
  Circulación)»* debe decir **«sus rivales rematan menos en Directa (−3.1 pp) y en Ataque elaborado (−1.7 pp)»**: se borra
  la Circulación estéril.
- *«Cuando va ganando sube menos su Directa (−1.7 pp contra la liga) y baja menos su Ataque elaborado (+2.2 pp)»* debe
  decir **«cuando va ganando, baja menos su Ataque elaborado que la liga (+2.2 pp)»**: se borra la Directa.
- La P(remate) propia en Circulación estéril no está en el texto, pero sí en la lista de demostradas: sale de la lista.
- **Siguen en pie y así se dice:** H1 y H2; «juega menos Circulación estéril» (−0.95 pp); «a sus rivales les sale más
  Directa (+1.8 pp) y menos Ataque elaborado (−2.0 pp)»; la P(remate) y el xG por secuencia del rival en Directa y en
  Ataque elaborado; la reacción ante un rival 100 Elo más fuerte (H6); «Viaja», sin cambios.

**Lo frágil, aunque no caiga.** La P(remate) propia en Directa (+1.03 pp) sigue demostrada en el BH porque su p de
bootstrap está en el piso, pero su IC «doble» toca el 0 ([−0.03, +2.06] pp). No está en el texto publicado, y si se
agrega debe llevar esa advertencia.

**Limitación que no se esconde.** La razón entre el bootstrap sin reajustar la mezcla y el IC publicado
(w_fijo / w_actual) era 0.997 con 100 réplicas y es **1.084** con 200. Parte de la amplitud «doble» no es error de la
etapa 1, sino que el bootstrap por partido es algo más ancho que el sandwich publicado. Con la inflación limpia
(w_doble / w_fijo), que aísla la etapa 1, caen las mismas tres afirmaciones más H3. La conclusión no depende de esa
elección, pero la magnitud de la inflación atribuida a la etapa 1 está sobrestimada en ~8 %.

**El patrón.** Dos de las tres caídas son de Circulación estéril. Es la familia peor separada por la mezcla (impureza
0.48 contra 0.37; 43 % de sus secuencias con r máxima < 0.6), la de mayor inflación limpia (máx. 4.94) y la única no
concluyente en la prueba del supuesto (Mejora A). Toda afirmación sobre Circulación estéril que quede en el documento
debe llevar esa advertencia.

## Qué adoptaría y en qué orden

1. **La corrección de B**: las tres frases de arriba. No dependen de más corridas.
2. **El orden fijo del bootstrap del balón parado** (ADR-v2-61). Al integrar, volver a correr `balon-parado` y
   `demostracion`, porque sus p cambiaban de corrida a corrida dentro de ±0.01.
3. **F con la variante (ii)**: pasa el criterio, no cambia el vocabulario y corrige una clasificación que era falsa
   (una falta o un lateral a favor contados como pérdida). Hay que volver a correr la fase 2 y las secciones con el
   absorbente nuevo antes de narrar algo con él.
4. **A como limitación declarada** (§15.2): razonable en Directa y Elaborado, no concluyente en Circulación estéril.
5. **D solo como documento** (§16.7).
6. **E rechazada; C nunca como resultado** con este diseño.
