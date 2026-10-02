> ⚠️ CORRIDA SOBRE LA LIGA SINTÉTICA de `tests/liga_cruda.py` (el contenedor no tiene los datos de StatsBomb). Valida el código; NO es un resultado sobre Almada.

# Mejora A — ¿el técnico solo mueve π_k? Prueba de score de H0: P^k_foco = P^k_liga (Guillermo Prueba)

**EXPERIMENTO (ADR-v2-52), no adoptado.** Matemática en `src/dtcoach/supuesto_pk.py` y `04_MODELO_MATEMATICO.md` §15.

Secuencias de ataque del foco: 5,325 en 28 partidos.

| familia | filas probadas | p Fisher (P) | p mín. Bonferroni | exceso T/gl | TV media | ΔE[T] | ΔP(remate) | percentil entre técnicos | p Fisher (P0, 1.er toque) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16 | 1.13e-07 | 0.0677 | 3.13 | 0.116 | -0.25 | +4.0 pp | 100 | 0.0138 |
| 2 | 16 | 2.28e-08 | 0.0783 | 3.27 | 0.112 | -0.23 | +6.1 pp | 100 | 0.000188 |
| 3 | 16 | 1.23e-07 | 0.0531 | 3.04 | 0.108 | -0.22 | +7.8 pp | 100 | 0.00665 |

*exceso = ΣT/Σgl (≈ 1 bajo H0). Percentil = qué parte de los técnicos-club con ≥ 8 partidos se desvía MENOS que el foco (misma prueba). TV = distancia de variación total media de las filas probadas. ΔE[T] y ΔP(remate): efecto de cambiar P^k de la liga por la del foco (encogida).*

Técnicos-club de la nula empírica: 11. Tiempo: 2 s.