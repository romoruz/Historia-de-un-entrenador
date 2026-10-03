# Plan de integración de lo que se adopta de `exp/mejoras-6`

Este documento es solo el plan; todavía no se integra nada. Cada paso dice qué cambia, con qué comandos y qué hay que
volver a correr. Los pasos van del menos invasivo al más invasivo: si un paso falla su verificación, los siguientes
esperan. Todos los comandos son desde la raíz del repo, con el venv activo.

## Paso 0 — Compuerta: la optimización de `mezcla.py` no cambió el vocabulario

`mezcla.py` (ADR-v2-64) lo usa el pipeline de la entrega, y su equivalencia bit a bit solo se verificó en la liga
sintética. Antes de integrar nada, hay que verificarla sobre el vocabulario oficial:

```bash
python scripts/experimentos/verificar_mezcla.py          # dos ajustes K = 3 completos (nuevo y previo); minutos
cat reports/experimentos/verificar_mezcla/VERIFICAR.md
```

- **Decisiva:** «nuevo vs previo» debe salir idéntico bit a bit (J, π, P, P0, μ, iteraciones y acuerdo suave = 1). Si
  no sale así, **PARAR**: no se integra nada y se revisa la optimización.
- **Secundaria:** «nuevo vs publicado». Si nuevo = previo pero los dos difieren de lo publicado, la causa no es la
  optimización: son datos o código posteriores a la publicación, y se revisa aparte antes del paso 4.
- **Corrida real (2026-10-03):** nuevo = previo bit a bit, pero los dos difieren de lo publicado porque los datos
  crecieron (ADR-v2-68). Antes del paso 1, la mezcla guardada debe reproducirse bit a bit sobre su propia muestra:

```bash
python scripts/experimentos/reproducir_publicada.py      # si no sale «SE REPRODUCE», PARAR
```

- **En el paso 4** (§4.2), el acuerdo ≈ 0.98 se compara contra un reajuste con **cuatro** absorbentes sobre los mismos
  datos de hoy, y no contra la mezcla guardada, para no confundir el absorbente nuevo con los datos nuevos.

## Paso 1 — Correcciones de la narrativa (solo documentos; no se vuelve a correr nada)

Las tres afirmaciones que no sobreviven al error de la etapa 1 (04 §7.2, 200 réplicas). Se edita
`docs/RESULTADOS_ALMADA.md`, sección 1:

| dónde | dice hoy | debe decir |
|---|---|---|
| «Su mezcla de familias es distinta» | «…y remata menos en las tres (P(remate) del rival: −3.1 pp en Directa, −1.7 pp en Elaborado, −0.5 pp en Circulación)» | «…y sus rivales rematan menos en Directa (−3.1 pp) y en Ataque elaborado (−1.7 pp)» |
| «Reacciona menos que la liga» | «Cuando va ganando sube menos su Directa (−1.7 pp contra la liga) y baja menos su Ataque elaborado (+2.2 pp)» | «Cuando va ganando, baja menos su Ataque elaborado que la liga (+2.2 pp)» |
| lista de demostradas (si se publica) | incluye la P(remate) propia en Circulación estéril | se quita |

H2 y «Viaja» quedan como están. Se agrega una nota al pie: «Tres afirmaciones de la versión anterior se retiraron al
propagar el error de estimar las familias (ver 04 §7.2)».

Además se integran a `docs/04_MODELO_MATEMATICO.md` §7.1–7.2 y los ADR-v2-53 y 57.

## Paso 2 — El orden de los partidos en el bootstrap del balón parado (ADR-v2-61; código de la entrega)

- **Archivos:** `src/dtcoach/xdefensa.py` (`cadena`: `.sort("match_id")` antes de remuestrear) y
  `src/dtcoach/balon_parado.py` (`razon_boot`, lo mismo). Hoy los p de la cadena del xDefense cambian entre corridas
  con la misma semilla.
- **Prueba:** `test_razon_boot_no_depende_del_orden`.
- **Volver a correr:**

```bash
pytest -q
dtcoach balon-parado --foco "Guillermo Almada"
dtcoach demostracion --foco "Guillermo Almada"
```

- **Verificar:** comparar `reports/historia/guillermo_almada/demostracion/demostracion.csv` contra la versión anterior
  (guárdala antes de correr). Las afirmaciones de la cadena que cambien de veredicto estaban dentro del ruido de Monte
  Carlo (±0.01 en p) y se reescriben en `RESULTADOS_ALMADA.md` §5 según el nuevo veredicto. Esa versión es la
  reproducible.

## Paso 3 — Documentación de A, D y E (solo documentos)

Se integran a `docs/04_MODELO_MATEMATICO.md`, con sus ADR:

- **§15 + §15.1–15.2 (A):** el supuesto «el técnico solo mueve π_k» se declara como limitación. Es razonable en Directa
  y en Ataque elaborado, y no concluyente en Circulación estéril. ADR-v2-52 y 55.
- **§14.1 (E):** la arista marcada se rechaza, junto a presión y dirección, con la razón: al marginalizar la marca se
  recupera P(j|i) exacta. ADR-v2-59 y 62.
- **§16.7 (D):** la partición portero/definición es exacta y segura, pero no tiene señal de equipo; se documenta y no
  se narra. ADR-v2-56, 58 y 61.

El código experimental (`supuesto_pk*.py`, `arista.py`, `xgot.py`, `voronoi_grafo.py`) puede quedarse en
`scripts/experimentos/` y en `src/dtcoach/` como herramienta. No entra en ninguna corrida de la entrega.

## Paso 4 — El quinto absorbente INTERRUPCIÓN_FAVOR, variante (ii) (el único cambio al modelo)

### 4.1 Código

1. **`src/dtcoach/grid.py`:** `ABSORBING = ("GOAL", "SHOT_NOGOAL", "LOSS", "OUT", "INTERRUPCION_FAVOR")`. Va AL FINAL,
   así que los índices de los cuatro absorbentes actuales no cambian (`cli.py:944`, `voronoi_grafo.py:49`,
   `mezcla._es_remate` y `ofensiva.py:268` siguen valiendo).
2. **`src/dtcoach/possessions.py`, `build_transitions`:** después de `_append_terminal_absorption` y de segmentar las
   secuencias, se reclasifica la última transición de cada secuencia que termina en LOSS y que la reanuda el mismo
   equipo a balón parado (lateral, tiro libre, córner o penal; o un `Foul Won` propio antes de la siguiente acción).
   La regla y el código están en `src/dtcoach/absorbente5.py` (`clasificar`, `variante`) y se mueven ahí.
   **Laterales incluidos.**
3. **La recompensa, en una columna aparte.** El valor de la reanudación, E[xG | tipo, zona] con el encogimiento de
   `absorbente5.valor`, va en una columna nueva `valor_reanudacion`, **no** en `xg`. En el experimento se metió en `xg`.
   Integrado así, contaminaría el «xG por secuencia» de la fase 2 (`contexto.py` lo lee de `d.X`) y los IC de H7–H8. La
   columna nueva solo entra en `c` cuando se calcula V = N c (`absorbing.recompensa_xg` y quien la llame para V:
   `mezcla.inicio`, `voronoi_grafo.valor_de_zonas`). Hace falta una prueba que asegure que «xG por secuencia» no cambia
   al agregar la columna.
4. **Pruebas:** adaptar las de `possessions` y `grid` que cuentan absorbentes (n_states = n_transient + 5) y portar
   `test_absorbente5_variante_y_valor`.

### 4.2 Volver a correr, en este orden

```bash
pytest -q
dtcoach fase0                                   # transiciones con el quinto absorbente
dtcoach mezcla --K 3                            # el vocabulario
dtcoach reproducibilidad --K 3 --semillas 1 2 3 # criterio (a)
dtcoach bondad --K 3                            # criterio (b) y (c)
bash scripts/correr_foco.sh "Guillermo Almada"  # fase 2 (H1–H8), fase 3a, atlas, decisiones, simulador
bash scripts/historia.sh "Guillermo Almada"     # secciones 1–8, incluida la demostración
```

- **Verificar:** el criterio del vocabulario debe repetir lo del experimento (acuerdo suave ≈ 0.998, rango de J ≈ 5e-6,
  KS ≈ 0.0049, E[T] 6.502 contra 6.509) y el acuerdo con la mezcla anterior debe ser ≈ 0.98. Si no, PARAR.
- La malla (5×4, §5) no se vuelve a elegir: el absorbente nuevo no tiene área y no cambia la partición. Es opcional
  confirmarlo con `dtcoach mallado`.

### 4.3 Qué secciones de 04 se reescriben

- **§1:** la Def. 1.3 suma el absorbente nuevo y una definición de «interrupción a favor», con la regla de clasificación.
- **§2:** B = N R con cinco columnas; c = (xG de los remates + valor de la reanudación) / acciones; V = N c.
- **§4:** el resultado del vocabulario (acuerdo, rango de J, KS, E[T]) con los números nuevos.
- **§7.2:** las tres caídas se calcularon con el vocabulario anterior. Con el nuevo, lo riguroso es repetir B, 200
  réplicas, unas 8 h con la optimización. Si no se repite, se dice que §7.2 corresponde al vocabulario anterior.
- **§14:** se agrega F como experimento que **sí** se adoptó.

### 4.4 Qué resultados de Almada se regeneran y qué se espera

- **Se regeneran:** `RESULTADOS_ALMADA.md` §1 (identidad y familias: H1–H6), §2 y §3 en lo que use familias, §6
  (simulación y escenarios) y la demostración completa.
- **No se tocan:** §4 (jugadores) y §5 (balón parado: el xDefense se calcula con eventos, no con la cadena), salvo por
  la demostración global.
- **Esperado, según el experimento:**
  - El uso de las familias no se mueve más de 5 puntos de percentil.
  - La fracción de secuencias que terminan en PÉRDIDA baja de 82.5 % a 63.9 % en Pachuca, y su percentil de 30 a 20:
    pierde menos que antes respecto de los demás, **a favor** de Almada.
  - Aparece una métrica nueva: en Pachuca, el 18.6 % de sus secuencias termina en interrupción a favor, percentil 77
    entre técnicos-club.
  - Cualquier afirmación del texto que hable de «pérdidas» en términos de la cadena se revisa con la definición nueva.

## Paso 5 — Cierre

```bash
dtcoach demostracion --foco "Guillermo Almada"
pytest -q
```

- `docs/RESULTADOS_ALMADA.md` se reescribe solo con lo que la demostración nueva marque como demostrado (la regla no
  cambia).
- `docs/02_ESTADO.md` y `docs/10_RESULTADOS.md` se actualizan con la fecha de integración y los ADR adoptados (52, 53,
  55, 57, 61, 64, 65, 66).
- El merge a `main` se decide aparte, con autorización explícita.
