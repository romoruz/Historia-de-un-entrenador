# Experimentos `exp/mejoras-6` — RESUMEN (tabla abierta: faltan tres mejoras más)

**Nada se adopta. Nada se corrió sobre Almada:** el contenedor de esta sesión no tiene `data/raw`, `data/interim` ni
`data/processed` (están en tu máquina). Las tres mejoras están **programadas, probadas y validadas con datos sembrados y
con la liga sintética de `tests/liga_cruda.py`**, y dejadas listas para correr sobre los datos reales. Los números de abajo
son de validación del código, no hallazgos. Rama local `exp/mejoras-6`, sin push; `config/default.yaml`, `data/` y
`reports/{mezcla,fase1,fase2,fase3,historia}` intactos. (Las pruebas del repo son 161, no 129; ahora 164.)

| mejora | ¿pasó? | métrica antes | métrica después | delta | recomendación |
|---|---|---|---|---|---|
| **A** — supuesto «el técnico solo mueve π_k, no P^k» (04 §15, ADR-v2-52) | Código sí. Sobre Almada: **no corrida** | supuesto sin decir ni probar | prueba de score: tamaño ≤ 5 % bajo H0 y potencia ≈ 70 % (sembrados, 70 partidos, perturbación del 40 % en una familia); liga sintética: otros técnicos exceso ≈ 1.0 (0.81–1.23), foco ≈ 3.1 | — | **NECESITA MÁS DATOS**: correr en tu máquina; el documento del supuesto ya se puede adoptar |
| **B** — regresor generado (04 §7.1, ADR-v2-53) | Código sí. Sobre Almada: **no corrida** | IC de H1–H8 con r_sk como dato | liga sintética (60 réplicas): inflación limpia mediana 1.29, máx. 4.9 → «no despreciable» **solo en la sintética**, donde la mezcla reajustada coincide con la original en ~60 % (familias poco identificadas) | no trasladable | **NECESITA MÁS DATOS**: correr con ≥ 200 réplicas sobre la liga real |
| **C** — Voronoi × grafo (exploratorio, ADR-v2-54) | Código sí. Sobre los datos reales: **no corrida** | 13.3 y 13.5 sin cruzar | liga sintética: pipeline completo y diseño «mismo jugador bajo distintos técnicos» (52 jugadores con ≥ 2; umbral 15) | — | **NECESITA MÁS DATOS**; sigue siendo exploratorio, fuera del BH global |

## Tiempos (esta sesión, reloj de pared)
- Lectura de ADR/modelo y diseño: ~6 min · construir la liga sintética del flujo (aplanar→fase2→voronoi): ~2 min (más una repetición por un error mío de `__main__`).
- **A:** código + prueba de tamaño/potencia ~20 min (1.ª versión anticonservadora: 22 % de rechazos al 5 %, corregida) · corrida sintética 3 s.
- **B:** código ~10 min · humo 38 s · corrida de 60 réplicas 1,792 s (≈ 30 s por réplica con 62 mil secuencias; con los 467 mil reales serán minutos por réplica: 200 réplicas ≈ horas, hay `--max-minutos` y `--reanudar`).
- **C:** código ~15 min (1.er diseño de «mismo jugador» descartado por mal definido) · corrida 3–5 s.
- `pytest` completo ≈ 1.5–2 min por vez (3 veces). Total ≈ 1 h 15 min.

## Qué quedó sin correr
- **Las tres sobre datos reales** (A: Almada; B: 200 réplicas; C: Voronoi real).
- Para correrlas: `python scripts/experimentos/{supuesto_pk,regresor_generado,voronoi_grafo}.py --config config/exp_mejoras.yaml [--muestra N]`.
- B con la liga real no tiene tiempo estimado confiable; C no incluye el cruce con todas las etapas, solo las del foco.
