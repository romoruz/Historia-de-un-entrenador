> ⚠️ CORRIDA SOBRE LA LIGA SINTÉTICA de `tests/liga_cruda.py` (60 réplicas, 1,792 s). Valida el código; NO es un resultado sobre Almada. En esta liga la mezcla reajustada coincide con la original solo en ~60 % de las secuencias (la liga sintética no es una mezcla de cadenas bien identificada), así que la inflación medida aquí NO se traslada a los datos reales.

# Mejora B — regresor generado en la fase 2 (Guillermo Prueba)

**EXPERIMENTO (ADR-v2-53), no adoptado.** Bootstrap por partido (estratificado) que reajusta la mezcla en cada réplica.

- réplicas: **60** (error relativo de una amplitud ≈ 9 %)
- acuerdo medio de las familias con la mezcla original: 0.599
- **inflación limpia** (doble / fijo): mediana 1.290, máxima 4.948
- inflación contra el IC publicado: mediana 1.380, máxima 4.373
- **veredicto:** NO DESPRECIABLE: los IC de H1–H8 están estrechos de más

| cantidad | estimación | amplitud actual | amplitud «fijo» | amplitud «doble» | inflación limpia | inflación vs actual |
|---|---|---|---|---|---|---|
| H1 Δπ · Directa | -0.0441 | 0.0140 | 0.0177 | 0.0604 | 3.41 | 4.33 |
| H1 Δπ · Circulación estéril | +0.0396 | 0.0195 | 0.0162 | 0.0615 | 3.81 | 3.16 |
| H1 Δπ · Ataque elaborado | +0.0045 | 0.0184 | 0.0170 | 0.0594 | 3.50 | 3.23 |
| H2 Δπ · Directa | -0.0092 | 0.0242 | 0.0185 | 0.0217 | 1.17 | 0.90 |
| H2 Δπ · Circulación estéril | +0.0062 | 0.0350 | 0.0217 | 0.0195 | 0.90 | 0.56 |
| H2 Δπ · Ataque elaborado | +0.0030 | 0.0172 | 0.0180 | 0.0206 | 1.15 | 1.20 |
| H3–H6 perdiendo vs empatando · Directa | -0.0022 | 0.0486 | 0.0641 | 0.0606 | 0.95 | 1.25 |
| H3–H6 perdiendo vs empatando · Circulación estéril | +0.0204 | 0.0637 | 0.0755 | 0.0777 | 1.03 | 1.22 |
| H3–H6 perdiendo vs empatando · Ataque elaborado | -0.0182 | 0.0558 | 0.0484 | 0.0777 | 1.61 | 1.39 |
| H3–H6 ganando vs empatando · Directa | +0.0009 | 0.0513 | 0.0546 | 0.0526 | 0.96 | 1.03 |
| H3–H6 ganando vs empatando · Circulación estéril | +0.0064 | 0.0498 | 0.0502 | 0.0514 | 1.02 | 1.03 |
| H3–H6 ganando vs empatando · Ataque elaborado | -0.0073 | 0.0390 | 0.0360 | 0.0587 | 1.63 | 1.51 |
| H3–H6 minuto 75+ vs 60-74 · Directa | +0.0039 | 0.0527 | 0.0636 | 0.0699 | 1.10 | 1.33 |
| H3–H6 minuto 75+ vs 60-74 · Circulación estéril | +0.0130 | 0.0545 | 0.0567 | 0.0669 | 1.18 | 1.23 |
| H3–H6 minuto 75+ vs 60-74 · Ataque elaborado | -0.0169 | 0.0468 | 0.0523 | 0.0801 | 1.53 | 1.71 |
| H3–H6 local vs visitante · Directa | -0.0074 | 0.0357 | 0.0325 | 0.0329 | 1.01 | 0.92 |
| H3–H6 local vs visitante · Circulación estéril | -0.0052 | 0.0369 | 0.0466 | 0.0493 | 1.06 | 1.34 |
| H3–H6 local vs visitante · Ataque elaborado | +0.0126 | 0.0347 | 0.0456 | 0.0469 | 1.03 | 1.35 |
| H3–H6 rival 100 Elo más fuerte vs igual · Directa | -0.0149 | 0.0754 | 0.0865 | 0.1241 | 1.44 | 1.65 |
| H3–H6 rival 100 Elo más fuerte vs igual · Circulación estéril | -0.0089 | 0.1127 | 0.1261 | 0.1327 | 1.05 | 1.18 |
| H3–H6 rival 100 Elo más fuerte vs igual · Ataque elaborado | +0.0238 | 0.1044 | 0.1287 | 0.1246 | 0.97 | 1.19 |
| H7/ataque · uso · Directa | -0.0421 | 0.0160 | 0.0164 | 0.0583 | 3.55 | 3.64 |
| H7/ataque · uso · Circulación estéril | +0.0375 | 0.0189 | 0.0163 | 0.0596 | 3.66 | 3.16 |
| H7/ataque · uso · Ataque elaborado | +0.0046 | 0.0193 | 0.0169 | 0.0591 | 3.50 | 3.06 |
| H7/ataque · xG por secuencia · Directa | +0.0030 | 0.0061 | 0.0059 | 0.0064 | 1.09 | 1.06 |
| H7/ataque · xG por secuencia · Circulación estéril | +0.0039 | 0.0027 | 0.0027 | 0.0050 | 1.85 | 1.88 |
| H7/ataque · xG por secuencia · Ataque elaborado | +0.0049 | 0.0034 | 0.0043 | 0.0055 | 1.29 | 1.61 |
| H7/ataque · P(remate) · Directa | +0.0399 | 0.0318 | 0.0366 | 0.0447 | 1.22 | 1.40 |
| H7/ataque · P(remate) · Circulación estéril | +0.0649 | 0.0229 | 0.0320 | 0.0433 | 1.35 | 1.89 |
| H7/ataque · P(remate) · Ataque elaborado | +0.0797 | 0.0286 | 0.0315 | 0.0514 | 1.63 | 1.80 |
| H7/ataque · xG por secuencia · total | +0.0033 | 0.0025 | 0.0029 | 0.0029 | 1.00 | 1.19 |
| H8/defensa · uso · Directa | -0.0106 | 0.0207 | 0.0175 | 0.0225 | 1.28 | 1.08 |
| H8/defensa · uso · Circulación estéril | +0.0061 | 0.0251 | 0.0196 | 0.0215 | 1.10 | 0.86 |
| H8/defensa · uso · Ataque elaborado | +0.0045 | 0.0176 | 0.0157 | 0.0244 | 1.55 | 1.38 |
| H8/defensa · xG por secuencia · Directa | -0.0115 | 0.0040 | 0.0028 | 0.0140 | 4.95 | 3.55 |
| H8/defensa · xG por secuencia · Circulación estéril | -0.0003 | 0.0023 | 0.0028 | 0.0099 | 3.52 | 4.37 |
| H8/defensa · xG por secuencia · Ataque elaborado | -0.0010 | 0.0027 | 0.0026 | 0.0076 | 2.96 | 2.82 |
| H8/defensa · P(remate) · Directa | -0.0602 | 0.0255 | 0.0237 | 0.0634 | 2.68 | 2.49 |
| H8/defensa · P(remate) · Circulación estéril | -0.0050 | 0.0324 | 0.0354 | 0.0579 | 1.64 | 1.79 |
| H8/defensa · P(remate) · Ataque elaborado | +0.0014 | 0.0323 | 0.0224 | 0.0358 | 1.60 | 1.11 |
| H8/defensa · xG por secuencia · total | -0.0043 | 0.0019 | 0.0018 | 0.0018 | 1.00 | 0.91 |

*«fijo» = misma remuestra con las r originales (calibra el bootstrap contra el IC publicado: ≈ 1 si es consistente); «doble» = mezcla reajustada. La inflación limpia aísla lo que añade la etapa 1.*