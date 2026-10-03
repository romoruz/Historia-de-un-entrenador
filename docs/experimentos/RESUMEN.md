# Experimentos `exp/mejoras-6` — RESUMEN de las seis mejoras

Nada de esto cambia la entrega: el vocabulario oficial (5×4, K = 3), `config/default.yaml` y
`reports/{mezcla,fase1,fase2,fase3,historia}` siguen siendo la línea base. Los números son de las corridas sobre los
datos reales en la máquina del autor (2026-10-02 y 03). Lo que todavía no se corrió está marcado. Copia versionada de
`reports/experimentos/RESUMEN.md` (que está en `.gitignore`).

| mejora | ¿pasó? | métrica antes | métrica después | delta | recomendación |
|---|---|---|---|---|---|
| **A** — supuesto «el técnico solo mueve π_k, no P^k» (04 §15.1–15.2; ADR-v2-52, 55) | Sí | percentil de Almada por exceso T/gl a n completo: 98 / 100 / 100, confundido con la potencia (ρ(exceso, partidos) = +0.43 / +0.65 / +0.69) | a igual n = 30 (mediana de 20 remuestras), exceso / TV: Directa 45 / 38 · **Circ. estéril 91 / 61** · Elaborado 70 / 33 | −53 / −9 / −30 puntos por exceso | **ADOPTAR la documentación** (no el modelo): Directa y Elaborado = aproximación razonable; **Circulación estéril = no concluyente**. Regla fijada antes de correr; no se usan los números de n = 40 |
| **B** — regresor generado (04 §7.1–7.2; ADR-v2-53, 57) | Sí (100 réplicas; 200 en curso) | IC de H1–H8 con las r_sk como dato | calibración 0.997; inflación limpia mediana 1.073, máx. 5.3 (Circulación estéril) | 2 de 41 IC dejan de excluir el 0; en el BH global caen 3 afirmaciones y una cuarta (H2) depende de la regla | **ADOPTAR la corrección** de la narrativa (sección de abajo). No es un cambio de método: es retirar lo que no aguanta |
| **C** — Voronoi × grafo de jugadores (exploratorio; ADR-v2-54) | Corrió | 13.3 y 13.5 sin cruzar | con más espacio, menos pase y menos remate (3.1 % → 0.4 %); mismo jugador bajo ≥ 2 técnicos: 720 jugadores, z² = 1.38 contra 1.19 de la nula, p = 0.002 | — | **NECESITA MÁS DATOS, de diseño:** cambiar de técnico casi siempre es cambiar de club, compañeros y época. No separa técnico de contexto. Queda exploratorio, fuera del BH |
| **D** — xGOT: portero y definición por separado (04 §16.7; ADR-v2-56, 58, 61) | Exacta y segura | un término «portero y definición» | 5 términos, error 1.9e-16; 0 de 730 veredictos cambian; Q de Cochran con p > 0.07 en las 24 combinaciones | **sin señal de equipo** | **RECHAZAR como métrica narrativa; ADOPTAR la documentación.** Las 3 pruebas nuevas «demostradas» no son narrables (bootstrap de 500, pasos de 0.004, ruido ±0.009). De paso apareció un error de la entrega: el bootstrap del balón parado no fijaba el orden de los partidos (ADR-v2-61; corregido) |
| **E** — arista marcada pase / conducción (04 §14.1; ADR-v2-59, 62) | **No** | malla 5×4, K = 3: acuerdo suave 0.997, rango J 4e-6 | acuerdo suave **0.884**, rango J **5.6e-4** por secuencia; KS 0.0036, E[T] 6.503 vs 6.509 | +0.0014 nats/acción (K = 3); **0 por construcción** con K = 1 | **RECHAZAR.** Falla (a). La ganancia no se compara con dirección (+0.066) ni presión (+0.031): al marginalizar la marca se recupera P(j\|i) exacta, así que solo podía ganar identificando la familia. Además, Directa es la familia que MENOS conduce: la hipótesis previa era falsa |
| **F** — quinto absorbente INTERRUPCIÓN_FAVOR (ADR-v2-60, 63) | Compuerta sí; el resto, **sin correr** | PÉRDIDA incluye faltas recibidas y balones parados propios | 21.47 % de la masa de PÉRDIDA son interrupciones a favor (45 % de ellas, laterales) | — | **NECESITA MÁS DATOS:** primero `preparar` (zona y valor de cada reanudación, tres variantes, sin EM); `ajustar` después de B. Si alguna variante falla (a), RECHAZADA |

## Qué no sobrevive al propagar el error de primera etapa

Las responsabilidades r_sk salen de la mezcla (etapa 1), y los IC publicados de la fase 2 las trataron como datos. Con
el bootstrap que reajusta la mezcla en cada réplica (100 réplicas), cada IC se ensanchó a la amplitud «doble» y se
rehizo el BH global de las 730 afirmaciones. **Estas afirmaciones publicadas no se sostienen:**

| # | afirmación publicada | p publicado | p con el error de la etapa 1 | por qué cae |
|---|---|---|---|---|
| 1 | Almada remata **más** por secuencia de Circulación estéril que la liga (+0.32 pp) | 0.018 | **0.65** | su IC se abre de [+0.06, +0.57] pp a [−1.07, +1.71] pp: la inflación es de 5.5 veces |
| 2 | Sus rivales rematan **menos** por secuencia de Circulación estéril (−0.55 pp) | 0.0005 | **0.22** | IC de [−0.76, −0.33] pp a [−1.42, +0.32] pp; inflación de 4.1 |
| 3 | Cuando va ganando, sube **menos** su Directa que la liga (−1.7 pp) | 0.0145 | **0.021** | estaba a 0.002 del corte del BH (≈ 0.017); un 6 % más de error lo saca |
| 4 | H2: su identidad defensiva es distinta de la liga | 0.00012 | **0.027** con la regla conservadora; 0.0067 con la otra | sin la covarianza «doble» de sus tres componentes no hay forma exacta. Una demostración que depende de la regla no se narra |

**Qué hay que reescribir en `RESULTADOS_ALMADA.md`:**
- *«Su mezcla de familias es distinta (H1 y H2 🟢)»* pasa a **«Su mezcla ofensiva es distinta (H1 🟢)»**. H2 se retira
  como hipótesis demostrada, y con ella *«… y H2 en Santos Laguna»* del párrafo «Viaja».
- *«remata menos en las tres (P(remate) del rival: −3.1 pp en Directa, −1.7 pp en Elaborado, −0.5 pp en
  Circulación)»* pasa a **«sus rivales rematan menos en Directa (−3.1 pp) y en Ataque elaborado (−1.7 pp)»**. La
  Circulación estéril se borra.
- *«Cuando va ganando sube menos su Directa (−1.7 pp contra la liga)»* se borra. Lo que queda de H3 se reescribe con lo
  que sigue demostrado («baja menos su Ataque elaborado, +2.2 pp»).
- La P(remate) propia en Circulación estéril no estaba en el texto, pero sí en la lista de demostradas: sale de la lista.
- **Siguen en pie**, y así se dice: H1; «juega menos Circulación estéril» (−0.95 pp); «a sus rivales les sale más
  Directa (+1.8 pp) y menos Ataque elaborado (−2.0 pp)»; la P(remate) y el xG por secuencia del rival en Directa y en
  Ataque elaborado; la reacción al rival 100 Elo más fuerte (H6).

**Lo que no se cuenta como caída, y por qué.** La primera corrida de este cálculo listaba también «uso de Directa del
rival» y «P(remate) del rival en Directa». Fue un error de método: el z se sacaba de p de bootstrap en el piso
(1/2000), que subestiman su z. Con el z de su propio IC se sostienen (p 0.002 y 0.0005). Tampoco se cuentan las dos
cantidades cuyo IC «doble» salió más angosto que el publicado (un IC publicado nunca se estrecha).

**El patrón.** Las tres caídas firmes son de Circulación estéril o de un efecto que ya rozaba el corte. Circulación
estéril es la familia peor separada por la mezcla (impureza 0.48 contra 0.37; 43 % de sus secuencias con r máxima < 0.6)
y la única no concluyente en la prueba del supuesto (Mejora A). Cualquier afirmación sobre Circulación estéril que
quede en el documento debe llevar esa advertencia.

*Provisional:* calculado con la tabla de B a 100 réplicas y el método corregido. Se rehace con B a 200 réplicas y la
corrida de `regresor_generado_impacto.py`.

## Qué adoptaría y en qué orden

1. **La corrección de B, ya.** Son afirmaciones publicadas que no aguantan; las tres caídas firmes no dependen de B a 200.
2. **El orden fijo del bootstrap del balón parado** (ADR-v2-61) y volver a correr `balon-parado` y `demostracion` al
   integrar: sus p cambiaban de corrida a corrida dentro de ±0.01.
3. **A como limitación declarada** (§15.2): razonable en Directa y Elaborado, no concluyente en Circulación estéril.
4. **D solo como documento** (§16.7).
5. **F solo si alguna variante pasa el criterio.** (iii) o (ii) antes que (i), según lo que digan la zona y el valor
   de los laterales.
6. **E rechazada, C nunca como resultado** con este diseño.

## Qué falta correr (en la máquina con los datos)

```bash
# ya (no reajusta la mezcla):
nice python scripts/experimentos/regresor_generado_impacto.py             # B con el método corregido
nice python scripts/experimentos/xgot.py                                  # D con el orden del bootstrap fijo
nice python scripts/experimentos/absorbente5_variantes.py preparar --muestra 50
nice python scripts/experimentos/absorbente5_variantes.py preparar        # F: zona, valor y tres variantes
# cuando B termine las 200 réplicas:
nice python scripts/experimentos/regresor_generado_impacto.py             # otra vez, con los números finales de B
nice python scripts/experimentos/absorbente5_variantes.py ajustar --muestra 200 --semillas 1 2
nice python scripts/experimentos/absorbente5_variantes.py ajustar         # F: 12 ajustes de la mezcla
```
