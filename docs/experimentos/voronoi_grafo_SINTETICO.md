> ⚠️ CORRIDA SOBRE LA LIGA SINTÉTICA de `tests/liga_cruda.py` (el contenedor no tiene los datos de StatsBomb). Valida el código; NO es un resultado sobre Almada. Umbrales relajados para la liga sintética (n ≥ 20 por jugador-etapa y n ≥ 15 por cruce); en la configuración real son 50 y 50.

# Mejora C — Voronoi × grafo de jugadores (Guillermo Prueba)

> **EXPLORATORIO (ADR-v2-54).** No es una hipótesis pre-registrada y NO entra al BH global. Nada de esto se narra como resultado.

**Lo que esto no puede decir.** El 360 es una *foto del evento*, no tracking: se mide con cuánto espacio **ejecutó** el jugador, no «qué tan bien recibe». Solo hay jugadores visibles en cámara (se exige ≥ 50 % del disco visible y que el actor del frame coincida con el evento a ≤ 2 m). Se descartan jugador-etapa con n < 20 acciones con 360.

- acciones con 360 usadas: **201,910** · jugador-etapa con n ≥ 20: **169**

## La liga: qué decide y cuánto vale según el espacio

Terciles del área local (m²): ≤ 61 · ≤ 106 · mayor.

| espacio | n | % pase | % conducción | % remate | pase perdido | ΔV⊥ intención | ΔV⊥ realizado |
|---|---|---|---|---|---|---|---|
| poco | 68,360 | 71.0 | 22.9 | 6.1 | 17.9 % | +0.00076 | +0.00074 |
| medio | 67,175 | 73.5 | 22.3 | 4.2 | 17.5 % | -0.00062 | -0.00058 |
| mucho | 66,375 | 75.3 | 21.4 | 3.3 | 17.1 % | -0.00016 | -0.00017 |

Pendiente de ΔV⊥(realizado) sobre el área, toda la liga: +0.00098 por 100 m².

## El grafo de pases de las etapas del foco, cruzado con el espacio

| par de variables (entre jugadores) | n | ρ de Spearman | p |
|---|---|---|---|
| area_vs_flujo | 26 | -0.16 | 0.446 |
| dv_vs_flujo | 26 | +0.19 | 0.343 |
| dv_vs_P_remate | 26 | +0.07 | 0.724 |
| area_vs_dv | 169 | +0.08 | 0.315 |

ν = por quién pasa el balón (cadena de jugadores); P(remate) = que la posesión termine en remate si el balón está en él. Con muestras así de chicas, las correlaciones son descriptivas.

## ¿Depende del entrenador? El único diseño identificable: el mismo jugador bajo distintos técnicos

- jugadores con ≥ 2 técnicos y n ≥ 15 acciones con 360 y ≥ 3 partidos con cada uno: **52** (con el foco: 26); umbral para concluir: 15.
- 78 pares jugador-técnico (z de Welch por partido): **media de z² = 1.21** (≈ 1 si el técnico no importa; nula por permutación 1.06), p de permutación = 0.218. El mismo jugador con técnicos distintos casi siempre cambia también de club, compañeros y época: esto NO separa técnico de contexto.

Tiempo: 3 s.