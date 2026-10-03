# Experimentos `exp/mejoras-6` — RESUMEN de las seis mejoras

Nada de esto cambia la entrega: el vocabulario oficial (5×4, K = 3), `config/default.yaml` y
`reports/{mezcla,fase1,fase2,fase3,historia}` siguen siendo la línea base. Los números «Almada» son de las corridas
sobre los datos reales en la máquina del autor (2026-10-02); lo que aún no se corrió con los datos reales se dice.
Copia versionada de `reports/experimentos/RESUMEN.md` (que está en `.gitignore`).

| mejora | ¿pasó? | métrica antes | métrica después | delta | recomendación |
|---|---|---|---|---|---|
| **A** — supuesto «el técnico solo mueve π_k, no P^k» (04 §15.1–15.2; ADR-v2-52, 55) | Sí (corrida sobre Almada) | percentil de Almada por exceso T/gl, a n completo: 98 / 100 / 100 (Directa / Circ. estéril / Elaborado), confundido con potencia (ρ(exceso, partidos) = +0.43, +0.65, +0.69) | a igual n = 30 (20 remuestras, mediana), exceso / TV: 45 / 38 · **91 / 61** · 70 / 33 | −53 / −9 / −30 puntos por exceso | **ADOPTAR la documentación**: Directa y Ataque elaborado = aproximación razonable (limitación declarada); **Circulación estéril = no concluyente** (regla fijada antes de correr; no se usan los números de n = 40). Ningún cambio de modelo |
| **B** — regresor generado (04 §7.1–7.2; ADR-v2-53, 57) | Sí (100 réplicas) | IC de H1–H8 con las r_sk como dato | calibración 0.997; inflación limpia mediana 1.073 (máx. 5.3, en Circulación estéril) | 2 de 41 cantidades dejan de excluir el 0 | **ADOPTAR la corrección**: retirar «remata menos en las tres (… −0.5 pp en Circulación)» y la P(remate) propia en Circulación estéril; el resto se sostiene. El BH global rehecho y la prueba de la entropía (¿por qué Circ. estéril?) están **pendientes** de `regresor_generado_impacto.py` |
| **C** — Voronoi × grafo de jugadores (exploratorio; ADR-v2-54) | Corrió | 13.3 y 13.5 sin cruzar | liga: con más espacio, menos pase y menos remate (3.1 % → 0.4 %), ΔV realizado +0.00055 por 100 m²; mismo jugador bajo ≥ 2 técnicos: 720 jugadores, z² = 1.38 contra 1.19 de la nula, p = 0.002 | — | **NECESITA MÁS DATOS** (de diseño, no de volumen): hay señal, pero cambiar de técnico casi siempre es cambiar de club, compañeros y época; no separa técnico de contexto. Se queda exploratorio, fuera del BH |
| **D** — xGOT: portero y definición por separado (04 §16.7; ADR-v2-56, 58) | Exacta y segura | un solo término «portero y definición» | 5 términos, error 1.9e-16; 0 veredictos cambian (246 → 247 demostradas); τ² = 0 o ≈ 0 (p > 0.3) en «todo el balón parado» | sin señal de equipo | **RECHAZAR como métrica narrativa; ADOPTAR la documentación.** Por tipo de saque la 1.ª corrida no vale (error del experimento, corregido); si la corrida corregida diera τ² > 0 con p < 0.05 en algún tipo, se reabre solo ese |
| **E** — arista marcada pase / conducción (04 §14.1; ADR-v2-59) | **Sin correr sobre los datos reales** | malla 5×4, K = 3: acuerdo 0.997, KS 0.0051, E[T] 6.502 vs 6.509 | — | — | **NECESITA MÁS DATOS.** Expectativa previa, por la Prop. 14.2: con una cadena la ganancia es 0 por construcción; con la mezcla solo puede ganar por reconocer mejor la familia, y los parámetros por fila suben de 23 a 95: el riesgo de perder la reproducibilidad (que mató a dirección y presión) es real. Si falla (a): RECHAZADA |
| **F** — quinto absorbente INTERRUPCIÓN_FAVOR (ADR-v2-60) | **Solo la compuerta, sin correr sobre los datos reales** | PÉRDIDA incluye faltas recibidas y balones parados propios | — | — | **NECESITA MÁS DATOS**: si la fracción de PÉRDIDA que es interrupción a favor es < 3 %, NO RENTABLE y no se toca el EM. Solo si pasa se programa el reajuste |

## Qué adoptaría y en qué orden

1. **B, la corrección (ya).** No es una mejora de método sino una afirmación publicada que no aguanta el error de la
   primera etapa: «sus rivales rematan menos en las tres familias» debe decir «en Directa y en Ataque elaborado». Antes
   de reescribir `RESULTADOS_ALMADA.md`, correr `regresor_generado_impacto.py`: el BH global puede arrastrar alguna
   afirmación más que estaba en el margen, y hay dos cantidades en el filo (H1 Δπ Circ. estéril, P(remate) propia en
   Directa) que se confirman con lo/hi exactos.
2. **A, la limitación (documento).** §15.2 ya está escrita: el supuesto es razonable en Directa y Ataque elaborado y no
   concluyente en Circulación estéril. Coincide con B: **Circulación estéril es la familia frágil** (la que más paga el error de la
   primera etapa en B y la única no concluyente en A; que sea además la peor separada por el EM está por verse con la
   entropía de `regresor_generado_impacto.py`). Cualquier frase sobre Circulación estéril debería
   llevar esa advertencia.
3. **D, solo el documento** (§16.7): la partición es correcta pero no hay variación entre equipos que contar.
4. **E y F, solo si pasan su criterio** con los datos reales; F antes que E si la compuerta pasa, porque corrige una
   mala clasificación (una falta recibida contada como pérdida) y no añade parámetros por fila.
5. **C, nunca como resultado** con este diseño.

## Tiempos (reloj de pared)
- Corridas en la máquina del autor: A 13 s · A (igual n) 105 s · B 37 réplicas en 7,303 s + 63 en 10,439 s (≈ 2.9 h;
  ~160 s por réplica) · C 74 s · D 3 s.
- Esta sesión (código, pruebas y documentación): Tarea 0 (B) ~25 min · Tarea 1 (D) ~15 min · E ~45 min · compuerta de F ~15 min.

## Qué queda sin correr (en la máquina con los datos)
```bash
nice python scripts/experimentos/regresor_generado_impacto.py        # B: tabla exacta, BH global, entropía (~1 min)
nice python scripts/experimentos/xgot.py                             # D corregido por tipo de saque (segundos)
nice python scripts/experimentos/absorbente5.py --muestra 50         # F: compuerta, humo
nice python scripts/experimentos/absorbente5.py                      # F: compuerta (segundos)
nice python scripts/experimentos/arista.py --muestra 200 --semillas 1 2 --folds 2   # E: humo
nice python scripts/experimentos/arista.py                           # E: completa (decenas de minutos)
```
