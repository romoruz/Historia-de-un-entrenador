# 00 — Roadmap final (v2)

> Hackathon ISAC 2026 · «La historia de un entrenador a través de los datos».
> Este documento manda. Si otro documento lo contradice, gana este.
>
> **Foco (2026-09-27): Guillermo Almada.** Las hipótesis se corrieron desde el principio
> sobre Jardine y Almada; se decidió exponer a Almada y dejar a Jardine como contraste.

## La idea en un párrafo

Construimos un **vocabulario de K tipos de posesión para toda la Liga MX**
(una mezcla de cadenas de Markov absorbentes) y contamos a un entrenador como
**una mezcla particular de ese vocabulario**: qué tipos usa su equipo, qué tipos
le permiten sus rivales, cómo cambia esa mezcla con el contexto y con sus
decisiones, y si esa mezcla viaja con él cuando cambia de club. Todo lo que ya
existe del proyecto viejo (presión, balón parado, jugadores, IC, BH) se cuelga
de ese eje como evidencia.

## La familia de modelos (anidada)

| capa | modelo | se acepta si… | estado |
|---|---|---|---|
| 0 | cadena de liga (20 zonas + 4 absorbentes), encogimiento | — | ✅ reutilizado |
| 1 | mezcla de K cadenas (EM-MAP) | log-verosimilitud fuera de muestra por partido (regla 1-EE) + KS de duración | ✅ código listo |
| 2 | pesos $\pi_k(x)$ por contexto + desviación del técnico $\delta_k$ | $G^2$ con bootstrap paramétrico por partido, BH | semana 2 |
| 3 | decisiones: formación, cambios, `Tactical Shift`; movers (AKM) | IC por bootstrap por partido | semana 3 |
| 4 | defensa (misma mezcla, perspectiva rival), presión, 360, balón parado | IC + BH | semanas 2–3 |
| 5 | simulador = la mezcla hacia adelante + Poisson-binomial | KS de duración, calibración | semana 3 |

$K=1$ es exactamente la cadena del proyecto viejo (hay test).

## Estado (2026-09-24)

Fase 1 técnicamente completa; faltan dos pasos de cierre (apuntar el config a
`eras_api_v2` y fijar K con el ajuste reproducible). Ver `02_ESTADO.md`.

## Fase 1 v3 (rediseño del 2026-09-25)

`bash scripts/fase1.sh` hace, en orden y con reglas pre-registradas:

1. **Mallado calibrado** por log-densidad predictiva fuera de muestra (ADR-v2-32),
   con agregación contigua como diagnóstico de cuántas zonas distinguen los datos.
2. **Paso inicial propio** (P⁰) si mejora la validación cruzada y el KS (ADR-v2-29).
3. **K** = el mayor K reproducible, con acuerdo suave (ADR-v2-30).
4. **Métricas formales**: verificación de la cadena, espectro y Yaglom,
   irreversibilidad, tiempos de llegada y memoria explicada por los tipos (ADR-v2-31).

## Semana 1 — el vocabulario (versión v2, histórica)

```bash
source .venv/bin/activate
dtcoach aplanar          # JSON crudo -> data/interim/events/*.parquet
dtcoach partidos         # matches -> partidos + DT por partido (API)
dtcoach fase0            # transiciones de TODA la liga con DT, rival, localía
#   -> revisar reports/verificacion_eras.csv y reports/cobertura_eras.csv
dtcoach cv-k             # curva de K (reports/mezcla/cv_k.png)
dtcoach mezcla --K <k>   # tipos, responsabilidades, figuras
dtcoach bondad --K 1 <k> --n-boot 200
```

Criterio de salida: (1) **modelo ≈ empírico** en E[T] y xG por secuencia, por
tipo — ✅ logrado; (2) KS de la mezcla < KS de K=1 — ✅ 0.036 vs 0.059;
(3) **ajuste reproducible entre semillas** (ADR-v2-17) — ⬜ pendiente;
(4) tipos nombrados tras ver las figuras — ⬜ pendiente.
M2 (memoria) y el HMM quedan descartados: la mezcla explica la cola sin ellos
(ADR-v2-02, `10_RESULTADOS.md` §3).

Pendientes menores: `λ` de la mezcla por CV (hoy fijo en 100); copiar
`min_carry_length` del config viejo.

## Semana 2 — contexto y defensa

- `pesos.py`: logit multinomial de las responsabilidades sobre
  $x$ = (marcador, periodo, localía, Elo del rival, origen de la posesión)
  en toda la liga, con interacción del técnico: $\gamma_k + x^\top\eta_k +
  \mathbb 1\{\text{técnico}\}(\gamma'_k + x^\top\delta_k)$. IRLS ponderado
  (reutilizar el patrón de `xg_remate.py`).
- Perfil defensivo: la MISMA mezcla aplicada a las posesiones de los rivales
  (`coach_faced`): qué tipos le logran contra él vs contra la liga.
- `elo.py`: Elo con K y ventaja de local por máxima verosimilitud.
- Bootstrap **por partido** (ADR-v2-04) para todos los IC técnico-vs-liga.
- Suelo de detección de la variación de pesos: `scripts/23_potencia_tau2.py`.
- Descarga 360 en paralelo (`.venv-sb`).

## Semana 3 — decisiones, 360 y simulador

- `decisiones.py`: riesgo discreto del 1er/2º cambio y de `Tactical Shift`
  con marcador variable en el tiempo; tipo de cambio (ofensivo/defensivo) por
  posición; formación inicial vs rival; rotación (Jaccard) vs descanso.
- Movers: mezcla del técnico en cada club que dirigió; AKM con caveat de
  movilidad limitada.
- 360: altura de línea, compacidad, jugadores por delante del balón, marcaje
  en balón parado rival. Solo dentro de `visible_area`.
- Simulador: escenarios con números aleatorios comunes; prob. del resultado
  por Poisson-binomial exacta.

## Semana 4 — la historia

Reporte HTML (patrón de `12_reporte_html.py` del proyecto viejo):

1. En un minuto: 3–4 principios, una frase de cancha cada uno.
2. El vocabulario de la Liga MX (K mini-canchas + posesión típica).
3. Cómo ataca: su mezcla vs la liga, con IC.
4. Cómo defiende: los tipos que le logran los rivales + presión + bloque 360.
5. Cuando el partido cambia: sus pesos por contexto vs la liga.
6. Sus decisiones: cambios y formaciones vs la liga.
7. ¿Es él o el plantel?: su mezcla en cada club (movers).
8. Balón parado y jugadores.
9. Simulador de escenarios.
10. Método y límites, etiquetas 🟢🟡🔴⚪.

Ensayo con un lector que no sepa de datos. Congelar.

## Elección del técnico focal

≥ 60 partidos de fase regular en un club; cobertura 360 alta
(`reports/inventario_full/cobertura_360_por_torneo.csv`); era verificada
(`eras_verificadas.csv`); de preferencia **mover** (dirigió ≥ 2 clubes en la
ventana, ver §31 de los resultados viejos).

## Lo que NO se hace

Transformers/LSTM/GNN (ADR-17 viejo sigue en pie); clustering de técnicos;
RL para optimizar; M2 con memoria y HMM **si** la mezcla pasa el KS.
