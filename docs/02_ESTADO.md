# 02 — Estado del proyecto

> Actualizado 2026-09-29: fase G programada (secciones nuevas) y probada con datos sintéticos; falta correrla con datos reales.
> Qué está hecho, qué falta y **cuál es la siguiente acción**.

---

## Estado

- **Foco: Guillermo Almada** (decidido 2026-09-27; Jardine queda como contraste en `12_NARRATIVA` §2).
- **Capa de fútbol (fases A–F) implementada y corrida** con datos reales (129 pruebas): estilo de juego,
  360 (presión, bloque, marcaje), transiciones, balón parado, jugadores, identidad y evolución, simulador
  y blindaje. Resultados en `RESULTADOS_ALMADA.md` y `10_RESULTADOS` §19.
- Decisiones, simulador y blindaje de Almada **recorridos** (2026-09-27).
- **Fase G programada** (2026-09-29, ADR-v2-41 a 48; hipótesis H18–H26 pre-registradas): la historia
  por secciones; ofensiva completa (salida, progresión, llegada, ocasión, motivos, familias dibujadas);
  rival por Elo; defensa explicada con control de cámara; sustituciones a fondo; balón parado completo
  con xDefense en dos capas, línea del fuera de lugar y receta Arsenal; proyección en el club actual.
  Probada con pruebas sembradas y con una prueba integral (liga sintética en formato crudo).
- **Fase G corrida con datos reales** (2026-09-30): 7 secciones, 46 figuras publicadas y BH global
  sobre 61 hipótesis. Resultados en `RESULTADOS_ALMADA.md` y `10_RESULTADOS` §20.
- **Balón parado reorganizado (2026-09-30, ADR-v2-49):**
  - secciones 5.1 (el xDefense, métrica propia: árbol, demostración y cuatro términos exactos), 5.2 corners,
    5.3 tiros libres y 5.4 laterales del último cuarto;
  - cada una con el foco a favor, en contra y la liga;
  - exploratorio. Falta correrlo con datos reales: la tabla de la liga se rehace sola (versión 6).
- **Siguiente acción:** correr `bash scripts/historia.sh "Guillermo Almada"` y `bash scripts/publicar_figuras.sh`,
  llenar los ⏳ de la sección 5, y después el informe HTML final. Para regenerar la figura de familias y el ranking del xDefense
  (ahora puesto 1 = mejor), volver a correr `dtcoach ofensiva` y `dtcoach balon-parado`, y publicar las figuras.

- Fase 1 v3 **cerrada**: 5×4, K = 3, paso inicial, familias nombradas (`10_RESULTADOS.md` §16).
- Fases 2 y 3 **rehechas** con el vocabulario v3 para Jardine y Almada: las conclusiones no cambian (robustez).
- Experimento 360 (ADR-v2-36): corrido. Mejora la predicción (+0.031), no sostiene el vocabulario (`10_RESULTADOS` §18).
- Experimento dirección (ADR-v2-37): corrido. Mejora la predicción (+0.066), no sostiene el vocabulario (`10_RESULTADOS` §17). **El vocabulario oficial sigue siendo 5×4, K = 3.**
- Pendiente opcional: memoria por aumento de estado (ahora cubierto por ADR-v2-37) (la memoria real está en el destino, no en la duración); análisis por jugador (`player_id` ya está en las transiciones).

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
| Inicialización reproducible (escalera) | ✅ K = 3 reproducible (v3: acuerdo suave 0.997) |
| Malla y paso inicial (v3) | ✅ 5×4 por la regla enmendada (ADR-v2-35); P⁰ por tipo (KS 0.0051) |
| K elegido | ✅ K = 3 (ADR-v2-19; confirmado en v3) |
| Tipos nombrados | ✅ Directa · Circulación estéril · Ataque elaborado (ADR-v2-20; confirmados con las figuras v3 y ya en `config/default.yaml`) |
| Técnico focal | ✅ Guillermo Almada (antes André Jardine; se cambió el 2026-09-27) |

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
| 2 — contexto y defensa | H1–H8 con FDR sobre Jardine y Almada | ✅ v3: Jardine H1 ⚪ (antes 🟢 pequeña), H2 🟢, H7 🟢, H3–H6 ⚪ en conjunto (🟢 H3 y H6 solo en San Luis); Almada H3 🟢, H6 🟢, H8.1 y H8.3 🟢 |
| 3a — ¿él o el plantel? | por club (H9–H12) y atlas | ✅ v3: la defensa de Jardine viaja (H9); la eficiencia es del América (H10, H11 ❌); atlas 1.º (San Luis) y 3.º (América) de 15. Almada en el América (7 partidos): exploratorio |
| 3b — decisiones y simulador | H13–H17 y simulador | ✅ v3 (no dependen del vocabulario): Jardine H13 🟢 (~3 min después), H17 🟢; Almada (corrida 2026-09-27) H15, H16 🟢, H13 ⚪ (q = 0.085, indicio), H14 ⚪, H17 🔎; xPts de ambos dentro del azar |
| 3b (pendiente) | figuras 360 | ⬜ |
| 4 — narrativa | guion en lenguaje llano (`12_NARRATIVA.md`, borrador), reporte HTML, ensayo con lector ajeno, congelar | 🟡 borrador del guion |

---

## Riesgos vivos

1. ~~K podría no ser reproducible con ningún valor.~~ Resuelto: K = 3 es
   reproducible en 5×4; K = 4 y 5 no lo son en ninguna malla probada.
2. **El contexto puede salir nulo.** En la versión anterior ningún ajuste al
   marcador sobrevivió a Benjamini-Hochberg. Comprimir 84 estados en K−1 pesos
   debería dar más potencia, pero si vuelve a salir nulo la historia es
   "identidad por encima de reactividad", que también es una conclusión.
3. **Cobertura 360 parcial en algunos torneos.** Verificar antes de prometer el
   capítulo de bloque defensivo.
4. ~~6.4 % de las filas sin DT asignado.~~ Resuelto con `eras_api_v2` (0.25 %).
5. **Almada en el América tiene 7 partidos.** Todo lo de ese club es
   exploratorio hasta que haya más partidos.
