# Plan de integración de lo que se adopta de `exp/mejoras-6`

**Estado (ADR-v2-69 a 73): INTEGRADO Y CORRIDO.** Los pasos 1 a 4 se corrieron con los datos reales el 2026-10-03 y pasaron todas las compuertas: xG idéntico, criterio del §4, y acuerdo con cuatro absorbentes 0.9815, al filo del 0.98. `RESULTADOS_ALMADA.md` está reescrito: **243 demostradas** (el conteo, en ADR-v2-73). Cada paso dice qué cambia, con qué comandos y qué hay que
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
- **Volver a correr (`bash scripts/integrar.sh paso2`).** Se corre con el código del **paso 2**, con cuatro
  absorbentes y la mezcla publicada, porque el código del paso 4 cambia el espacio de estados. El script hace checkout
  del commit del paso 2 y al final regresa a `exp/mejoras-6`:

```bash
D=reports/historia/guillermo_almada
cp -a $D/demostracion $D/demostracion_antes_paso2          # la versión publicada, para comparar
cp -a $D/balon_parado $D/balon_parado_antes_paso2
pytest -q
dtcoach balon-parado --foco "Guillermo Almada"
dtcoach demostracion --foco "Guillermo Almada"
python scripts/experimentos/comparar_demostracion.py $D/demostracion_antes_paso2/demostracion.csv \
    $D/demostracion/demostracion.csv --titulo "Paso 2: balón parado con el orden fijo"
```

- **Verificar (ADR-v2-70):** en `COMPARAR.md`, solo deben moverse p de la sección `balon_parado`. Lo que cambie de
  veredicto se reescribe en `RESULTADOS_ALMADA.md` §5. Si cambia algo fuera de balón parado, PARAR.

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

## Paso 4 — El quinto absorbente INTERRUPCIÓN_FAVOR, variante (ii) (el único cambio al modelo; ADR-v2-72)

### 4.1 Código (hecho)

1. **`grid.ABSORBING`** suma `INTERRUPCION_FAVOR` al final, y `ABSORBING_4` es el de la entrega. Los índices de los
   cuatro de antes no cambian.
2. **`dtcoach fase0`** aplica `absorbente5.integrar` (Def. 1.5 de 04). Se clasifica después de la absorción terminal y
   del corte de secuencias. Solo cambia el destino de la última transición.
3. **La recompensa va en `valor_reanudacion`, no en `xg`.** `DatosPosesion.XV` la carga, y `Xc()` la suma al xG solo
   para c en V = N c. El «xG por secuencia» de H7–H8 (`contexto.tabla_secuencias`, `d.X`) no la ve.
4. **Pruebas:** `test_xg_por_secuencia_identico_antes_y_despues`, `test_integrar_solo_cambia_el_destino_final` y
   `test_quinto_absorbente_al_final`. `test_mezcla` fija cuatro absorbentes en su espacio sintético. `pytest -q`: 174.

### 4.2 Volver a correr, en este orden (`bash scripts/integrar.sh paso4`)

```bash
# 0. archivar lo de cuatro absorbentes (el archivo publicado NO se borra)
mkdir -p data/processed/archivo_4abs reports/archivo_4abs
cp -a data/processed/transitions.parquet data/processed/archivo_4abs/
cp -a data/processed/mezcla data/processed/archivo_4abs/
cp -a reports/mezcla reports/fase2 reports/fase3 reports/historia reports/archivo_4abs/
pytest -q                                       # 174
dtcoach fase0                                   # transiciones con el quinto absorbente y `valor_reanudacion`
dtcoach mezcla --K 3                            # el vocabulario nuevo (467,327 secuencias)
python scripts/experimentos/verificar_absorbente5.py \
    --antes data/processed/archivo_4abs/transitions.parquet \
    --publicada data/processed/archivo_4abs/mezcla/mezcla_K3.npz   # xG idéntico + 5 contra 4 sobre los mismos datos
dtcoach reproducibilidad --K 3 --semillas 1 2 3 # criterio (a) y (c), con 467,327 secuencias
dtcoach bondad --K 3                            # criterio (b): KS y E[T]
bash scripts/correr_foco.sh "Guillermo Almada"  # fase 2 (H1–H8), fase 3a, atlas, decisiones, simulador
bash scripts/historia.sh "Guillermo Almada"     # secciones 1–8, incluida la demostración
python scripts/experimentos/comparar_demostracion.py \
    reports/archivo_4abs/historia/guillermo_almada/demostracion/demostracion.csv \
    reports/historia/guillermo_almada/demostracion/demostracion.csv --titulo "Paso 4: cinco contra cuatro absorbentes"
```

**Compuertas, en orden. Si una falla, PARAR:**
1. `verificar_absorbente5.py` sale con 0: xG por secuencia idéntico bit a bit y acuerdo con cuatro absorbentes
   ≥ 0.95. Si avisa «repetir B» (acuerdo < 0.98 o impureza que cambia > 0.02), B se repite antes de narrar (04 §7.2).
2. `reproducibilidad`: acuerdo suave ≥ 0.95, rango de J ≤ 1.08e-4 por secuencia y π mín ≥ 1 %. El experimento dio
   0.998 y ≈ 5e-6.
3. `bondad`: KS ≤ 0.0051 y |E[T] modelo − observado| ≤ 0.02. El experimento dio 0.0049, y 6.502 contra 6.509.

La malla (5×4) no se vuelve a elegir: el absorbente nuevo no tiene área y no cambia la partición.

### 4.3 Qué secciones de 04 se reescribieron (hecho)

- **§1:** Def. 1.2 con cinco absorbentes; Def. 1.5 (interrupción a favor) y el valor de la reanudación.
- **§2:** R de 20 × 5. En la Prop. 2.4, c = (xG de remates + valor de la reanudación) / acciones, y por qué v va en c y
  no en el xG de la secuencia.
- **§4:** el criterio de la entrega se midió con 461,454 secuencias y cuatro absorbentes. El vocabulario nuevo se mide
  con 467,327 y se compara contra cuatro absorbentes sobre los mismos datos.
- **§7.2:** los números de B son del vocabulario de cuatro absorbentes. Por qué no se repite, y la condición para
  repetirlo (limitación declarada).
- **§14.2:** F, el único experimento adoptado.

### 4.4 Qué resultados de Almada se regeneran y qué se espera

- **Se regeneran** (con `correr_foco.sh` + `historia.sh`):
  - `RESULTADOS_ALMADA.md` §1 (identidad: H1–H6 y familias), §2 y §3 en lo que use familias (perfiles de ataque y de
    defensa: H7 y H8), §6 (simulación y escenarios: usan las familias y V) y la **demostración completa**.
  - `reports/mezcla/` (tipos, estabilidad), `reports/fase2/`, `reports/fase3/` y `reports/historia/`.
- **No deberían cambiar** (verificarlo con `comparar_demostracion.py`): §4 (jugadores), §5 (balón parado: el xDefense
  se calcula con eventos, no con la cadena), y las métricas de eventos de §2 y §3. Si cambian, es por la demostración
  global (un BH sobre todo) y no por el absorbente.
- **Esperado, según el experimento:**
  - El uso de las familias no se mueve más de 5 puntos de percentil.
  - El percentil de PÉRDIDA de Almada baja de 30 a 14: pierde menos que antes respecto de los demás. Es un efecto
    **a su favor**.
  - Aparece una métrica nueva: con Pachuca, el 18.6 % de sus secuencias termina en INTERRUPCIÓN, percentil 77 entre
    técnicos-club. El 84 de «Almada (todo)» no es comparable.
  - El xG por secuencia (H7–H8) es idéntico **por secuencia**. Sus efectos por familia pueden moverse un poco, porque
    se ponderan con las r_sk nuevas.
- **Reglas al reescribir `RESULTADOS_ALMADA.md`:**
  - Solo lo que la demostración nueva marque como demostrado.
  - Las tres afirmaciones de ADR-v2-69 siguen retiradas aunque vuelvan a salir.
  - Cualquier frase sobre «pérdidas» de la cadena usa la definición nueva.

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
