# 02 — Estado del proyecto

> Actualizado 2026-09-24, al cierre técnico de la Fase 1.
> Qué está hecho, qué falta y **cuál es la siguiente acción**.

---

## Estado

- Fase 1 v3 **cerrada**: 5×4, K = 3, paso inicial, familias nombradas (`10_RESULTADOS.md` §16).
- Fases 2 y 3 **rehechas** con el vocabulario v3 para Jardine y Almada: las conclusiones no cambian (robustez).
- Pendiente opcional: memoria por aumento de estado (la memoria real está en el destino, no en la duración); análisis por jugador (`player_id` ya está en las transiciones).

---

## Fase 1 — el vocabulario

| paso | estado |
|---|---|
| Aplanado de 1,767 partidos (5.7 M eventos) | ✅ |
| Partidos y DT por partido desde el API | ✅ |
| Fase 0: 3.0 M transiciones, 461,454 secuencias | ✅ |
| Secuencia como unidad de la cadena (ADR-v2-14) | ✅ validado (E[T] 6.502 vs 6.509) |
| Mezcla de cadenas: EM-MAP, CV de K, bondad | ✅ |
| Eras: de 2,916 discrepancias a 0 personas distintas; sin DT 0.25 % | ✅ aplicadas (`eras_api_v2`) |
| Inicialización reproducible (escalera) | ✅ K = 3 reproducible (acuerdo 0.993) |
| K elegido | ✅ K = 3 (ADR-v2-19) |
| Tipos nombrados | ✅ Directa · Circulación estéril · Ataque elaborado (ADR-v2-20) |
| Técnico focal | ✅ André Jardine (178 partidos, 2 clubes, 360 al 99.4 %) |

**Bugs de la v2 encontrados y corregidos: 4.** Los tres silenciosos, ninguno
lanzó una excepción:
1. `fork` + polars congelaba el aplanado (ADR-v2-09);
2. posesiones con varias absorciones sesgaban toda la cadena (ADR-v2-14);
3. la comparación de nombres de DT daba 2,521 falsas discrepancias (ADR-v2-13);
4. el panel de cambios perdía todas las filas del foco (ADR-v2-26), detectado con datos sintéticos.

---

## Fases siguientes

| fase | contenido | estado |
|---|---|---|
| 2 — contexto y defensa | H1–H8 con FDR sobre Jardine | ✅ corrida: H1 🟢 (pequeña), H2 🟢, H7.2–7.3 🟢, H8.3 🟢, H3–H6 ⚪ |
| 3a — ¿él o el plantel? | por club (H9–H12) y atlas | ✅ la defensa viaja (H9); la eficiencia es del América (H10, H11 ❌) |
| 3b — decisiones y simulador | H13–H17 y simulador | ✅ H13 🟢 (cambia ~3 min después), H17 🟢 (rota más), H14–H16 ⚪; xPts dentro del azar |
| 3b (plan original) | `decisiones.py` (riesgo de cambios y `Tactical Shift`, formación vs rival, rotación); movers (Jardine en 2 clubes, Almada en el América); figuras 360; simulador | ⬜ |
| 4 — narrativa | reporte HTML, ensayo con lector ajeno, congelar | ⬜ |

---

## Riesgos vivos

1. **K podría no ser reproducible con ningún valor.** Si `reproducibilidad`
   falla para 4, 5 y 6, el vocabulario se construye con el K más chico que sí lo
   sea, aunque ajuste peor. Un vocabulario inestable no se puede narrar.
2. **El contexto puede salir nulo.** En la versión anterior ningún ajuste al
   marcador sobrevivió a Benjamini-Hochberg. Comprimir 84 estados en K−1 pesos
   debería dar más potencia, pero si vuelve a salir nulo la historia es
   "identidad por encima de reactividad", que también es una conclusión.
3. **Cobertura 360 parcial en algunos torneos.** Verificar antes de prometer el
   capítulo de bloque defensivo.
4. **6.4 % de las filas sin DT asignado.** Debe bajar al aplicar `eras_api_v2`;
   si no baja, investigar antes de la Fase 2.
