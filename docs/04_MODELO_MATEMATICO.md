# 04 — El modelo matemático, sección por sección

> Este documento demuestra, con el rigor de un apunte de curso, **por qué cada número
> del proyecto significa lo que decimos que significa**. Cada sección enuncia los objetos
> (definiciones), lo que se afirma de ellos (proposiciones) y por qué es cierto
> (demostraciones o, cuando la demostración es clásica, su esquema y la referencia).
> Al final de cada sección se indica el archivo del código que la implementa.
>
> Notación: vectores fila para distribuciones ($\mu$, $\pi$), columnas para funciones
> sobre estados ($t$, $V$, $h$); $\mathbf 1$ es el vector de unos; $\rho(\cdot)$ es el
> radio espectral; $\mathbb 1\{\cdot\}$ es la indicadora.

---

## 0. El objeto de estudio

Un partido es una sucesión de eventos de StatsBomb $e_1, e_2, \dots$, cada uno con tipo,
equipo, jugador, coordenadas $(x, y) \in [0,120]\times[0,80]$ en el marco de ataque de
quien lo ejecuta, y (si hay 360) la posición de los jugadores visibles. Todo el proyecto
responde una pregunta sobre esos objetos:

> ¿Qué hace el equipo de un técnico **distinto** de lo que haría la liga en las mismas
> circunstancias, y ese rasgo es suyo o de su plantel?

La respuesta se construye en tres capas: un **vocabulario** de la liga (§1–6), el
**técnico como mezcla** de ese vocabulario bajo contexto (§7–12) y una **capa de
fútbol** con métricas y geometría sobre los mismos objetos (§13–14).

---

## 1. De eventos a secuencias

**Definición 1.1 (acción).** Una acción es un evento de tipo `Pass`, `Carry` o `Shot`
ejecutado por el equipo en posesión. Su *origen* es su `location`; su *destino* es el
fin del pase (intentado, aunque falle), de la conducción o del remate.

**Definición 1.2 (malla y estados).** Sea $\mathcal Z = \{1,\dots,20\}$ la partición de la
cancha en una malla uniforme $5 \times 4$ (celdas de $24 \times 20$ m). Los estados son
$\mathcal S = \mathcal Z \cup \mathcal A$ con cuatro absorbentes
$\mathcal A = \{\text{GOL}, \text{REMATE}, \text{PÉRDIDA}, \text{FUERA}\}$.

**Definición 1.3 (transición).** Cada acción produce una transición $i \to j$: $i$ es la
zona del origen y $j$ la del destino si el equipo conserva el balón; si no, $j$ es el
absorbente correspondiente (remate con o sin gol, pase perdido, balón fuera). Si una
posesión termina en una zona sin evento que la cierre, se añade una transición
artificial a PÉRDIDA (*absorción terminal*).

**Definición 1.4 (secuencia).** Una secuencia es el tramo de una posesión desde su inicio
hasta su **primera** absorción. Una posesión con $m$ absorciones produce $m$ secuencias.

**Proposición 1.1.** Toda secuencia es una trayectoria de una cadena absorbente: visita
solo estados transitorios salvo en su último paso, que es absorbente.

*Demostración.* Por la definición 1.4 la secuencia se corta en la primera absorción;
por la absorción terminal, ninguna secuencia termina en un transitorio. $\square$

*Por qué importa.* Sin el corte (ADR-v2-14), una "posesión" de StatsBomb puede contener
varias absorciones (un remate que el mismo equipo recupera), y la cadena se estimaría
sobre trayectorias que ella misma declara imposibles: la duración esperada del modelo
quedaba por debajo de la observada en todos los tipos. Con el corte, $E[T]$ modelo
$=6.502$ contra $6.509$ observado.

*Código:* `possessions.build_transitions`, `possessions.segmentar_secuencias`.

---

## 2. La cadena absorbente y sus formas cerradas

Ordenando primero los 20 transitorios y después los 4 absorbentes, la matriz de
transición tiene la forma canónica

$$
P = \begin{pmatrix} Q & R \\ 0 & I \end{pmatrix},\qquad Q \in \mathbb R^{20\times 20},\ R \in \mathbb R^{20\times 4}.
$$

**Proposición 2.1 (la secuencia termina).** Si $\rho(Q) < 1$, entonces $Q^t \to 0$, la
serie $N = \sum_{t\ge 0} Q^t$ converge, $N = (I - Q)^{-1}$ y

$$
N_{ij} = E\Big[\textstyle\sum_{t\ge0} \mathbb 1\{X_t = j\} \,\Big|\, X_0 = i\Big],
$$

es decir, $N_{ij}$ es el número esperado de visitas a $j$ empezando en $i$.

*Demostración.* Por Gelfand, $\|Q^t\|^{1/t} \to \rho(Q) < 1$, así que $\sum_t \|Q^t\|$
converge y la serie de Neumann también. Multiplicando, $(I-Q)\sum_{t=0}^{T} Q^t = I - Q^{T+1}
\to I$, luego $N = (I-Q)^{-1}$. Además $(Q^t)_{ij} = \Pr(X_t = j \mid X_0 = i)$ para $j$
transitorio (el bloque $Q$ no deja volver desde un absorbente), y sumando sobre $t$ con
linealidad de la esperanza se obtiene la fórmula. $\square$

En los datos $\rho(Q) = 0.838$ (vocabulario 5×4): la secuencia termina con probabilidad 1.

**Proposición 2.2 (a dónde termina).** $B = NR$ satisface
$B_{ia} = \Pr(\text{absorber en } a \mid X_0 = i)$.

*Demostración (análisis de primer paso).* Condicionando al primer paso,
$B_{ia} = R_{ia} + \sum_j Q_{ij} B_{ja}$, es decir $B = R + QB$, de donde
$(I - Q) B = R$ y $B = NR$. $\square$

**Proposición 2.3 (cuánto dura).** Sea $T$ el número de acciones hasta absorber. Entonces
$t = E[T \mid X_0 = \cdot] = N\mathbf 1$ y, si la secuencia arranca con distribución
$\alpha$, $\Pr(T > t) = \alpha Q^{t}\mathbf 1$ (distribución *phase-type*).

*Demostración.* $T = \sum_{t\ge0}\mathbb 1\{X_t \in \mathcal Z\}$, y por 2.1
$E[T\mid X_0=i] = \sum_j N_{ij}$. Para la cola, $\{T > t\} = \{X_t \in \mathcal Z\}$ y
$\Pr(X_t \in \mathcal Z) = \alpha Q^t \mathbf 1$. $\square$

**Proposición 2.4 (valor de zona).** Sea $c_i$ el xG inmediato esperado de una acción que
parte de $i$ (xG de los remates desde $i$ entre las acciones desde $i$). Entonces
$V = Nc$ es el xG esperado que termina produciendo una secuencia que está en $i$.

*Demostración.* Primer paso: $V_i = c_i + \sum_j Q_{ij} V_j$, o sea $(I-Q)V = c$. $\square$

$V$ es el análogo, en forma cerrada, del *Expected Threat* (Singh, 2018): allí se itera
$V \leftarrow c + QV$ hasta converger; aquí se resuelve el sistema lineal.

**Proposición 2.5 (llegar a una región).** Sea $A \subset \mathcal Z$ (p. ej. "frente al
área") y $\bar A$ su complemento transitorio. Con $h_i = \Pr(\text{tocar } A \mid X_0 = i)$
y $g_i = E[\text{acciones hasta tocar } A;\ \text{toca } A \mid X_0 = i]$:

$$
(I - Q_{\bar A\bar A})\,h_{\bar A} = Q_{\bar A A}\mathbf 1,\qquad h_A = 1;\qquad
(I - Q_{\bar A\bar A})\,g_{\bar A} = h_{\bar A},\qquad g_A = 0,
$$

y $E[\text{acciones} \mid \text{llega}] = \mu g / \mu h$.

*Demostración.* Primer paso sobre la cadena en la que $A$ se vuelve absorbente:
$h_i = \sum_{j\in A} Q_{ij} + \sum_{j \in \bar A} Q_{ij} h_j$. Para $g$, cada paso dado en
una trayectoria que llega suma 1 acción: $g_i = \sum_j Q_{ij}(h_j + g_j)$ con $g_A = 0$,
que en $\bar A$ es $g = h + Q_{\bar A\bar A} g$ una vez usado $Q_{\bar AA}\mathbf 1 + Q_{\bar A\bar A}h = h$. $\square$

La matriz $I - Q_{\bar A\bar A}$ es invertible porque es una submatriz principal de
$I - Q$ con $\rho(Q_{\bar A\bar A}) \le \rho(Q) < 1$ (monotonía del radio espectral en
matrices no negativas).

**Proposición 2.6 (la cadena reiniciada y su estacionaria).** Si cada absorción se
reemplaza por un nuevo inicio con distribución $\mu$, la matriz resultante sobre los
transitorios es $\tilde P = Q + (R\mathbf 1)\mu$. Si $\tilde P$ es irreducible, su única
estacionaria es

$$
\tilde\pi = \frac{\mu N}{\mu N \mathbf 1}.
$$

*Demostración.* Sea $\nu = \mu N$. Entonces
$\nu \tilde P = \mu N Q + (\mu N R \mathbf 1)\mu$. Como $NQ = N - I$ y $NR\mathbf 1 = B\mathbf 1 = \mathbf 1$
(toda secuencia absorbe), $\nu\tilde P = \mu N - \mu + \mu = \nu$. La unicidad es
Perron-Frobenius para cadenas irreducibles finitas. $\square$

*Lectura.* La mezcla $\pi$ **no** es una estacionaria (la estacionaria de una cadena
absorbente vive en los absorbentes); la estacionaria de la cadena reiniciada es "dónde
vive el balón", y coincide con las visitas esperadas normalizadas (verificado en los
datos con error $2\cdot10^{-16}$).

**Proposición 2.7 (vida media).** Si $\lambda_1 = \rho(Q)$ es el autovalor de Perron,
$\Pr(T > t) \sim C\,\lambda_1^{t}$ y la "vida media" es $\log(1/2)/\log\lambda_1$ acciones.
El autovector izquierdo asociado (normalizado) es la distribución *cuasi-estacionaria*
de Yaglom: dónde está el balón *condicionado a que la secuencia siga viva*.

**Irreversibilidad.** Con flujos observados $F_{ij}$ entre transitorios, la producción de
entropía

$$
\sigma = \tfrac12\sum_{i\ne j}(F_{ij} - F_{ji})\log\frac{F_{ij}}{F_{ji}} \;\ge 0
$$

se anula si y solo si hay balance detallado ($F_{ij} = F_{ji}$, criterio de Kolmogorov).
Cada sumando es $(a-b)\log(a/b) \ge 0$. En la liga, $\sigma > 0$ con enorme evidencia
($G^2 = 164$ mil, 190 gl): el juego tiene dirección, y el avance neto por acción
($\sum F_{ij}(x_j - x_i)/\sum F_{ij}$) la cuantifica en metros.

*Código:* `absorbing.py` (N, t, B, V), `markov.py` (llegada, reiniciada, espectro,
irreversibilidad, verificación de irreducibilidad y aperiodicidad sobre el grafo de lo
observado).

---

## 3. Estimar una cadena con pocos datos: el encogimiento

**Proposición 3.1 (encogimiento = moda posterior).** Si la fila $i$ tiene conteos
$C_{i\cdot}$ con $n_i = \sum_j C_{ij}$ y una distribución a priori de Dirichlet con
parámetros $\lambda \bar Q_{i\cdot} + 1$, la moda posterior es

$$
\hat P_{ij} = \frac{C_{ij} + \lambda \bar Q_{ij}}{n_i + \lambda}.
$$

*Demostración.* La log-posterior es $\sum_j (C_{ij} + \lambda\bar Q_{ij})\log P_{ij}$ más
una constante; maximizando con el multiplicador de $\sum_j P_{ij} = 1$ se obtiene
$P_{ij} \propto C_{ij} + \lambda\bar Q_{ij}$. $\square$

*Lectura.* $\lambda$ son "pseudo-acciones" de la liga: una fila con muchos datos casi
no se mueve; una con pocos se parece a la liga. La referencia $\bar Q$ **nunca contiene
al técnico que se evalúa** (no hay fuga del foco hacia su propia referencia).

*Código:* `estimate.shrink`.

---

## 4. El vocabulario: una mezcla de cadenas de Markov

**Modelo.** Cada secuencia $s = (z_1, \dots, z_{T+1})$ tiene un tipo oculto
$Y_s \in \{1,\dots,K\}$ con $\Pr(Y_s = k) = \pi_k$, y dado el tipo:

$$
\Pr(s \mid k) = \mu^k_{z_1}\; P^{0,k}_{z_1 z_2} \prod_{t\ge2} P^k_{z_t z_{t+1}}.
$$

$\mu^k$ es dónde arranca, $P^{0,k}$ la **primera** acción (el "primer toque" tras
recuperar o reponer se comporta distinto, ADR-v2-29) y $P^k$ el resto.

**Proposición 4.1 (EM-MAP).** Con los priors de Dirichlet del §3 (hacia la cadena de la
liga, $\lambda$ para $P$, $\lambda_0$ para $P^0$, $a_0$ para $\mu$), el algoritmo

* **Paso E:** $r_{sk} = \dfrac{\pi_k \Pr(s\mid k)}{\sum_l \pi_l \Pr(s\mid l)}$ (responsabilidades),
* **Paso M:** con $C^k_{ij} = \sum_s r_{sk}\,\#\{t\ge2: z_t=i, z_{t+1}=j\}$ y $C^{0,k}$ análogo para el primer paso,
  $$
  \pi_k = \tfrac1n\textstyle\sum_s r_{sk},\quad
  P^k_{ij} = \dfrac{C^k_{ij} + \lambda\bar Q_{ij}}{\sum_j C^k_{ij} + \lambda},\quad
  P^{0,k}_{ij} = \dfrac{C^{0,k}_{ij} + \lambda_0\bar Q^0_{ij}}{\sum_j C^{0,k}_{ij} + \lambda_0},\quad
  \mu^k_i = \dfrac{\sum_s r_{sk}\mathbb 1\{z_1=i\} + a_0\bar\mu_i}{\sum_s r_{sk} + a_0},
  $$

no decrece el objetivo $J = \sum_s \log\sum_k \pi_k\Pr(s\mid k) + \log\text{prior}$.

*Demostración (esquema clásico, Dempster-Laird-Rubin 1977).* Para cualquier
$r_{s\cdot}$ en el símplex, por Jensen,
$\log\sum_k \pi_k \Pr(s\mid k) \ge \sum_k r_{sk}\log\frac{\pi_k\Pr(s\mid k)}{r_{sk}}$, con
igualdad en el $r$ del paso E. El paso M maximiza esa cota inferior más el log-prior,
que se separa por filas y tiene la solución cerrada de la Prop. 3.1 aplicada a los
conteos ponderados. Cota ajustada + maximización de la cota ⇒ $J$ no decrece. $\square$

(El prior de $P^0$ es **fijo**; un prior jerárquico hacia la $P^k$ del mismo tipo acoplaba
los parámetros y rompía la monotonía: se vio en datos sintéticos. ADR-v2-29.)

**Las formas cerradas se conservan.** Tras el primer paso la dinámica es Markov con
$P^k$, así que cada tipo tiene su $N^k$, $B^k$, $V^k$ y, con $Q^0$ el bloque transitorio de
$P^0$:

$$
E[T\mid k] = \mu^k(\mathbf 1 + Q^{0,k} t^k),\qquad
\Pr(T > t\mid k) = (\mu^k Q^{0,k})(Q^k)^{t-1}\mathbf 1 \ (t\ge1).
$$

**Identificabilidad y reproducibilidad.** La verosimilitud de una mezcla es invariante a
permutar los tipos y tiene óptimos locales. Por eso:

1. *Inicialización en escalera* (ADR-v2-17): el ajuste de $K$ parte del de $K-1$
   partiendo un tipo en dos (perturbando su $\mu$ en direcciones opuestas); determinista.
2. *Criterio de reproducibilidad* (ADR-v2-30, 35): se repite desde varias semillas; los
   tipos se alinean por asignación óptima (algoritmo húngaro sobre la distancia entre
   parámetros) y $K$ es reproducible si (a) el rango del objetivo entre semillas es
   $\le 1.08\cdot10^{-4}$ por secuencia, (b) el **acuerdo suave** (fracción de masa de
   responsabilidad que cae en el mismo tipo alineado) es $\ge 0.95$ y (c) ningún tipo
   tiene $\pi_k < 1\%$.

**Resultado (§16 de 10_RESULTADOS).** Con 461,454 secuencias, $K = 3$ es reproducible
(acuerdo 0.997; rango de $J$ de $4\cdot10^{-6}$ por secuencia) y $K\ge4$ no lo es en ninguna
malla. La mezcla con paso inicial reproduce la duración: KS $= 0.0051$ (una sola cadena:
0.0597).

*Código:* `mezcla.py` (`ajustar`, `_m_step`, `reproducibilidad`, `bondad_largo`).

---

## 5. Elegir la malla sin hacer trampa

Comparar mallas por verosimilitud directa no es válido: "zona 7 de 20" y "zona 7 de 96"
son eventos distintos.

**Proposición 5.1 (puntaje en escala común).** Sea $a_j$ la fracción de cancha de la zona
$j$. El puntaje

$$
\mathrm{S}(\text{malla}) = \frac1n\sum_{\text{transiciones}}
\begin{cases} \log\big(\hat P(j\mid i)/a_j\big) & j \text{ transitorio}\\ \log \hat P(j\mid i) & j \text{ absorbente}\end{cases}
$$

es el logaritmo de una **densidad** sobre el mismo espacio (cancha × absorbentes) para
cualquier malla, y por lo tanto comparable entre mallas.

*Demostración.* $\hat P(j\mid i)/a_j$ define una densidad constante por pedazos en la
cancha (integra $\hat P(j\mid i)$ sobre la zona $j$), y los absorbentes son átomos. La
regla logarítmica es *propia* (Good 1952): su esperanza se maximiza con la densidad
verdadera, así que en partidos no vistos gana la malla que mejor describe dónde cae la
siguiente acción, no la que tiene más celdas. $\square$

La validación cruzada es **por partido** (las secuencias de un partido comparten rival y
marcador). Con esta regla y la de reproducibilidad (§4) se eligió $5\times4$.

*Código:* `mallado.py`.

---

## 6. ¿Hay memoria? Medirla fuera de muestra

La ganancia de log-verosimilitud en partidos no vistos del modelo de orden 2
$P(j\mid h, i)$ (encogido hacia el de orden 1) sobre el de orden 1 estima la
información que el pasado agrega al presente, **sin** el sesgo positivo de la
información mutua plug-in (que con muchas celdas se infla por tamaño de muestra).
Condicionando además al tipo (pesos $r_{sk}$) se mide qué parte de esa memoria explica la
heterogeneidad entre tipos.

**Resultado.** La memoria es real pero pequeña (+0.058 nats por acción, ≈3 % de la
incertidumbre) y los tipos explican solo el 4.5 %: la duración la explica la mezcla;
hacia dónde va el balón tiene memoria propia. Los experimentos de §14 la exploran.

*Código:* `markov.memoria_cv`.

---

## 7. El técnico como mezcla bajo contexto (fase 2)

Cada secuencia $s$ tiene responsabilidades $r_s \in \Delta^{K-1}$ y covariables $x_s$
(marcador, tramo de minuto, localía, diferencia de Elo, origen, temporada) más dos
indicadores: $f_s = 1$ si la ejecuta el equipo del foco (**ataque**) y $g_s = 1$ si la
ejecuta un rival contra él (**defensa**). La referencia ($f=g=0$) son solo partidos donde
el foco no jugó.

**Modelo (logit multinomial fraccional, Papke-Wooldridge 1996).**

$$
E[r_{sk}\mid x_s] = \pi_k(x_s;B) = \frac{\exp(x_s^\top b_k)}{\sum_l \exp(x_s^\top b_l)},\qquad b_{\text{ref}} = 0,
$$

estimado maximizando la cuasi-verosimilitud $\ell(B) = \sum_s\sum_k r_{sk}\log\pi_k(x_s;B)$.

**Proposición 7.1 (consistencia sin suponer la distribución).** Si la media está bien
especificada, $\hat B$ es consistente aunque $r_s$ no sea multinomial.

*Demostración (esquema).* El score de la secuencia es
$u_s(B) = x_s \otimes (r_s - \pi(x_s;B))$ (sin la columna de referencia). Si
$E[r_s\mid x_s] = \pi(x_s;B_0)$, entonces $E[u_s(B_0)] = 0$; $\ell$ es cóncava, así que
$B_0$ es el único maximizador de $E[\ell]$ y el estimador M es consistente (Newey-McFadden,
teorema 2.7). $\square$

**Proposición 7.2 (varianza robusta por partido).** Con $H = -\nabla^2\ell(\hat B)$ y
$U_g = \sum_{s\in g} u_s(\hat B)$ la suma de scores del partido $g$,

$$
\hat V = H^{-1}\Big(\textstyle\sum_{g=1}^{G} U_g U_g^\top\Big)H^{-1}\cdot\frac{G}{G-1}
$$

estima consistentemente la varianza de $\hat B$ cuando los partidos son independientes
pero las secuencias de un mismo partido no (sandwich de conglomerados).

*Esquema.* Expansión de Taylor del score alrededor de $B_0$:
$\hat B - B_0 \approx H^{-1}\sum_g U_g$, con $U_g$ independientes entre partidos. $\square$

**Pruebas.** Cada hipótesis de contexto es un conjunto de coeficientes del foco
($f\times$perdiendo, $f\times$ganando, …) y se prueba con Wald,
$W = \hat\beta^\top \hat V_{\beta}^{-1}\hat\beta \sim \chi^2_{\text{gl}}$.
Los **efectos en la cancha** no son coeficientes: son diferencias de probabilidad
promediadas sobre las propias secuencias del foco,

$$
\Delta\pi_k = \frac1{n_f}\sum_{s:f_s=1}\big[\pi_k(x_s, f{=}1) - \pi_k(x_s, f{=}0)\big],
$$

con intervalo por simulación de $B\sim N(\hat B,\hat V)$ (Krinsky-Robb). La reacción al
contexto se lee como diferencia en diferencias: cuánto cambia el foco al pasar de
empatar a perder, menos cuánto cambia la liga en las mismas secuencias.

**Eficiencia (H7, H8).** xG por secuencia dentro de cada familia,
$\sum_s r_{sk}\,xg_s / \sum_s r_{sk}$, foco contra liga, con bootstrap por partido (§9).

### 7.1 Limitación: las $r_{sk}$ son un regresor generado (ADR-v2-53)

Las responsabilidades $r_{sk}$ no se observan: son la salida del EM de la etapa 1 (la mezcla,
§4), $r_{sk}=\hat\pi_kL_k(s)/\sum_l\hat\pi_lL_l(s)$ con $\hat\pi,\hat P$ estimados. La Prop. 7.2
trata $r_s$ como dato: $\hat V$ solo contiene la variación de la etapa 2 (condicional a
$\hat\theta_1$). La varianza correcta de un estimador en dos etapas es
$V=V_2+G\,V_{1}\,G^\top$ con $G=\partial\hat\theta_2/\partial\theta_1$ (Murphy y Topel 1985), de modo
que **omitir el segundo término estrecha los IC** de H1–H8. El sesgo no es la preocupación (la
etapa 1 usa toda la liga y es muy precisa); sí lo es la sobreconfianza. Qué tan grande es: sin
medir. Se cuantifica con un bootstrap por partido que reajusta la mezcla en cada réplica
(`regresor_generado.py`, experimento, no adoptado): inflación limpia $=w_{\text{doble}}/w_{\text{fijo}}$,
amplitudes de percentiles 2.5–97.5 con y sin reajustar la etapa 1 sobre la misma remuestra.
Con $R$ réplicas el error relativo de una amplitud es $\approx1/\sqrt{2(R-1)}$ (5 % con 200).

### 7.2 Resultado sobre Almada: qué se cae (ADR-v2-57)

Con 100 réplicas (error relativo ≈ 7 %), la calibración del bootstrap contra el IC publicado es 0.997 (mediana de
$w_{\text{fijo}}/w_{\text{actual}}$) y la inflación limpia mediana es 1.073: **en la mayoría de las cantidades el
error de la etapa 1 es despreciable**. No en todas. Para decidir qué afirmación se sostiene, cada IC publicado se
ensancha a $w=\max(w_{\text{actual}},w_{\text{doble}})$ conservando su forma; nunca se estrecha porque el
bootstrap haya salido más angosto.

**Dejan de excluir el 0** (con la amplitud de la tabla de B; la tabla exacta con lo/hi la da
`regresor_generado_impacto.py`):

* **P(remate) del rival en Circulación estéril (H8, defensa):** −0.0055, amplitud 0.0043 → 0.0174 (inflación
  limpia 4.1). Era parte de la frase publicada «sus rivales rematan menos **en las tres** familias (… −0.5 pp en
  Circulación)». Con el error de la mezcla, esa tercera parte **no se sostiene**: Almada reduce el remate del rival
  en Directa (−3.1 pp) y en Ataque elaborado (−1.7 pp), que sobreviven, pero no se puede afirmar en Circulación estéril.
* **P(remate) propio en Circulación estéril (H7, ataque):** +0.0032, amplitud 0.0051 → 0.0278 (inflación limpia 5.3).
  No se sostiene.

**No cambia, contra lo que se sospechaba:** xG por secuencia del rival en Circulación estéril (H8, −0.0004): ya con
la amplitud publicada (0.0010) su IC contenía el 0; no estaba afirmado. Quedan **en el filo** (sobreviven por poco
con la aproximación simétrica, hay que confirmarlos con lo/hi exactos): H1 Δπ en Circulación estéril
(|e|/semiamplitud 1.10) y P(remate) propio en Directa (1.05).

Todo lo demás de H1–H8 que excluía el 0 lo sigue excluyendo, incluido «juega menos Circulación estéril» (−0.95 pp,
1.88), la mezcla defensiva en Directa y Ataque elaborado y la reacción al rival (H6).

**Dónde se concentra.** La inflación grande cae en uso, P(remate) y xG por secuencia de **Circulación estéril**
(2.7 a 5.3). La explicación propuesta es que esa familia es la peor separada por el EM y por eso es la que más paga
el error de primera etapa; se contrasta con la entropía de las $r_{sk}$ por familia (`regresor_generado_impacto.py`,
§3). *Pendiente de la corrida sobre los datos reales:* en la liga sintética la peor separada es Ataque elaborado,
así que la hipótesis no se da por buena hasta verla en Almada. El BH global de la demostración rehecho con estos
errores también está pendiente: por el BH, las dos caídas pueden arrastrar afirmaciones de otras secciones que
estaban en el margen.

*Código:* `contexto.py`, `pesos.py`, `hipotesis.py`, `perfil.py`.

---

## 8. Muchas pruebas a la vez: Benjamini-Hochberg

Con $m$ p-valores ordenados $p_{(1)}\le\dots\le p_{(m)}$, se rechazan las $k^*$ primeras,
$k^* = \max\{k: p_{(k)} \le k\alpha/m\}$. **Teorema (Benjamini-Hochberg 1995; Benjamini-Yekutieli 2001):**
bajo independencia o dependencia positiva, la proporción esperada de falsos
descubrimientos es $\le \alpha$. Etiquetas: 🟢 $q < \alpha$, 🟡 $p<\alpha$ sin sobrevivir,
⚪ no detectado (se reporta la mayor diferencia compatible con los datos, nunca "no hay
efecto"). Se aplica por familia de hipótesis y, como sensibilidad, a todas juntas.

*Código:* `inference.benjamini_hochberg`, `blindaje.bh_global`.

---

## 9. El bootstrap por partido

Para una métrica que es razón de sumas, $\theta = \sum_g A_g / \sum_g D_g$ (numerador y
denominador por partido), se remuestrean **partidos** con reemplazo —por separado los del
foco y los de la liga— y se recalcula la razón. El intervalo es el percentil (o el
básico, $2\hat\theta - q_{1-\alpha/2}$, en la fase 2) y el p bilateral es
$2\min\{\Pr^*(d\le0), \Pr^*(d\ge0)\}$.

*Por qué por partido:* el partido es la unidad independiente (ADR-v2-04). Remuestrear
secuencias trataría 130 secuencias de un mismo partido como 130 partidos y daría
intervalos demasiado estrechos.

*Por qué es barato:* como las métricas son razones de sumas, basta guardar
$(A_g, D_g)$ por partido; cada réplica es una suma de vectores.

*Código:* `comparar.foco_vs_liga`, `perfil.perfiles`.

---

## 10. Pocos partidos: el bootstrap de score

Con pocos conglomerados, el Wald sandwich sobre-rechaza (Cameron, Gelbach y Miller, 2008).
**Procedimiento (Kline y Santos, 2012):**

1. Ajustar el modelo **restringido** (sin las columnas probadas) → $\tilde B$.
2. Scores por partido $S_g$ de todos los coeficientes en $\tilde B$ y Hessiana $H$.
   Score **eficiente** de los probados (ortogonal a los estorbos):
   $\tilde S_g = S_{g,1} - H_{12}H_{22}^{-1} S_{g,2}$.
3. Estadístico $LM = \big(\sum_g\tilde S_g\big)^\top\big(\sum_g\tilde S_g\tilde S_g^\top\big)^{-1}\big(\sum_g\tilde S_g\big)$.
4. Réplicas con pesos de Rademacher $w_g\in\{\pm1\}$: $LM^* $ con $\sum_g w_g\tilde S_g$;
   $p = \Pr^*(LM^*\ge LM)$.

*Por qué funciona.* Bajo $H_0$ los $\tilde S_g$ tienen media cero y son independientes
entre partidos; multiplicarlos por signos aleatorios conserva su distribución conjunta
(simetría), y la distribución de $LM^*$ aproxima la de $LM$ sin suponer que $G$ es grande.

**Resultado.** Almada en el América (7 partidos): Wald $p\approx0$, bootstrap
$p = 0.80$. El Wald se equivocaba; por eso con < 20 partidos nunca hay 🟢.

*Código:* `pesos.score_bootstrap`.

---

## 11. ¿Es él o es el plantel? (fase 3)

Para cada club del foco se reajusta el modelo de la fase 2 **contra la misma
referencia**, excluyendo de ella los partidos de su otra etapa (si quedaran, el técnico se
compararía contra sí mismo). Un rasgo **viaja** si aparece con el mismo signo en ambos
clubes (H9–H11, pre-registradas). El *atlas* repite la fase 2 para cada técnico-club con
≥ 50 partidos y mide la "separación" como la norma $\|\Delta\pi\|$ en puntos porcentuales.

*Código:* `fase3.py`.

---

## 12. Decisiones desde la banca y puntos esperados

**Tiempo de los cambios (H13–H14).** Panel equipo-minuto (minutos 45–90) con
$h(m) = \Pr(\text{primer cambio en } m \mid \text{sin cambio antes})$ modelado como logit
en tiempo discreto (Allison 1982): la liga con escalones de 5 minutos y el foco con una
desviación suave (nivel + pendiente, 2 gl). La supervivencia $\prod_{u\le m}(1-h(u))$ da el
minuto esperado del primer cambio.

**Tipo de cambio (H15).** Multinomial sobre {defensivo, mismo puesto, ofensivo} según el
nivel de puesto del que sale y del que entra. **Reacomodos (H16)** y **rotación (H17,
exploratoria)** por bootstrap.

**Puntos esperados.** Si los remates de un equipo son Bernoulli($xg_i$) independientes,
sus goles siguen una Poisson-binomial con la recursión exacta

$$
f_s(k) = f_{s-1}(k)(1 - p_s) + f_{s-1}(k-1)\,p_s,
$$

(demostración: condicionar en el remate $s$), y con los dos equipos independientes,
$\text{xPts} = 3\Pr(\text{gana}) + \Pr(\text{empata})$ sale de convolucionar.

*Código:* `decisiones.py`, `simulador.py`.

---

## 13. La capa de fútbol: métricas, geometría, jugadores, identidad

### 13.1 Métricas como razones de sumas

Cada métrica del reto (progresivas, PPDA, field tilt, contrapresión, …; definiciones
exactas en `03_FRAMEWORK` §5) es $\theta = \sum_g A_g/\sum_g D_g$ por equipo-partido y se
compara con el motor del §9. Tres preguntas para cada una:

1. **Contra la liga** (bootstrap por partido, BH por bloque).
2. **Percentil entre técnicos:** la misma razón para cada técnico-club con ≥ 30 partidos
   y el rango del foco entre ellos.
3. **Fiabilidad entre mitades.** Para cada técnico-club, partidos pares e impares (por
   fecha) dan dos valores $X_1, X_2$; $r = \mathrm{corr}(X_1, X_2)$ entre técnicos.
   **Proposición (Spearman-Brown).** Si $X_i = T + E_i$ con errores independientes de
   igual varianza, la fiabilidad de la media $(X_1+X_2)/2$ es $\rho = 2r/(1+r)$.
   *Demostración:* $r = \sigma_T^2/(\sigma_T^2+\sigma_E^2)$ y
   $\rho = \sigma_T^2/(\sigma_T^2 + \sigma_E^2/2)$; despejando, $\rho = 2r/(1+r)$. $\square$
   Una métrica con $\rho < 0.5$ no describe a un técnico aunque salga significativa.

**Regla pre-registrada:** un **rasgo del técnico** exige las tres: 🟢, percentil ≤ 20 o
≥ 80 y $\rho\ge0.5$.

### 13.2 Transiciones: supervivencia de la pérdida

Tras perder el balón en juego abierto, $T$ = segundos hasta recuperarlo, censurado si
la secuencia la corta un balón parado, un remate rival o el fin del tiempo. El estimador
de Kaplan-Meier

$$
\hat S(u) = \prod_{t_j\le u}\Big(1 - \frac{d_j}{n_j}\Big)
$$

($d_j$ recuperaciones en $t_j$, $n_j$ en riesgo) es el estimador de máxima verosimilitud
no paramétrico bajo censura independiente (Kaplan-Meier 1958).

### 13.3 Geometría del 360

**Celda de Voronoi local.** Para el ejecutante en $p_c$ y los demás jugadores visibles
$\{p_i\}$, su celda es $V_c = \{q: \|q-p_c\|\le\|q-p_i\|\ \forall i\}$. Se mide
$\mu\big(V_c\cap B(p_c,R)\cap\Omega\big)$ con $R = 10$ m por cuadratura: $P = 128$ puntos
de área igual en el disco; un punto cuenta si ningún otro jugador está más cerca.
El error es $O(1/P)$ en área (regla de conteo sobre una región con frontera
poligonal). Los puntos fuera del área visible no cuentan y el área se reescala por la
fracción visible (supuesto: dentro del disco, lo no visto se parece a lo visto).

**Envolvente convexa del bloque.** Área por la fórmula del zapatero sobre los vértices
de Quickhull, $\tfrac12\big|\sum_i (x_iy_{i+1} - x_{i+1}y_i)\big|$; solo con ≥ 6
defensores visibles.

**Marcaje (asignación húngara).** Con $D_{ij}$ = distancia del defensor $i$ al atacante
$j$ en la zona de remate, se resuelve
$\min_X \sum_{ij} D_{ij}X_{ij}$ con $X$ de asignación. **Proposición:** el problema
relajado ($0\le X\le1$) tiene óptimo entero, porque la matriz de restricciones de un
grafo bipartito es totalmente unimodular (teorema de Birkhoff-von Neumann); el algoritmo
húngaro (Kuhn 1955) lo encuentra en $O(n^3)$. La distancia media de la asignación óptima
mide qué tan "al hombre" marca un equipo.

### 13.4 Balón parado: Poisson con exposición

Remates (o goles) de un equipo-partido desde un tipo de jugada:
$y\sim\text{Poisson}\big(n\cdot e^{\beta_0+\beta_1 f}\big)$, con $n$ el número de jugadas. Es un
GLM con enlace log y *offset* $\log n$; IRLS es Newton-Raphson sobre una verosimilitud
cóncava. $e^{\beta_1}$ es la **razón de tasas** (cuántas veces más remata el foco por
jugada). La varianza es sandwich por partido (válida con sobredispersión, que se reporta
con el cociente de Pearson). Las zonas de remate se estiman con un kernel gaussiano
normalizado por jugada: $\int \hat f = $ remates por jugada.

### 13.5 Jugadores: una cadena sobre jugadores y cortes espectrales

**Cadena sobre jugadores.** Estados = jugadores de una etapa; absorbentes = remate y
pérdida; $Q_{ij}$ = pases completos de $i$ a $j$ sobre las acciones de $i$. Todo el §2 se
aplica: $\nu = \mu N$ normalizado es **por quién pasa el balón**; $B = NR$ la probabilidad
de terminar en remate desde cada jugador.

**Roles.** Con $A = W + W^\top$ (pases entre jugadores) y el laplaciano normalizado
$L = I - D^{-1/2}AD^{-1/2}$, los autovectores de los $k$ menores autovalores resuelven la
relajación continua del **corte normalizado** (Shi-Malik 2000): partir el grafo en grupos
que se pasan mucho entre sí y poco con los demás. $k$ es el mayor salto entre
autovalores consecutivos (von Luxburg 2007); los grupos salen de k-means sobre los
autovectores normalizados.

**Impacto de los cambios.** Para el primer cambio del segundo tiempo,
$\Delta = (\text{xG u OBV en } [m, m+10)) - (\text{en } [m-10, m))$; el efecto es la
diferencia en diferencias contra el $\Delta$ medio de la liga en el mismo tramo de 5
minutos y con el mismo signo del marcador, con bootstrap por partido.

### 13.6 Identidad: ¿se le reconoce?

**Huella** de un equipo-partido: mezcla de familias en ataque y de sus rivales contra él
(§4) más las métricas del §13.1, estandarizadas. Un **logit con penalización L2**
(estimador MAP con prior gaussiano) aprende "¿es un partido del foco?".

**Proposición (AUC = Mann-Whitney).** Si $S^+$ y $S^-$ son los puntajes de un positivo y un
negativo al azar, $\text{AUC} = \Pr(S^+ > S^-) + \tfrac12\Pr(S^+=S^-) = U/(n_1n_0)$.
*Demostración:* el área bajo la curva ROC es la integral de la tasa de verdaderos
positivos sobre la de falsos positivos, que cuenta exactamente los pares
(positivo, negativo) bien ordenados. $\square$

El AUC se mide en partidos **no vistos** (pliegues por partido). **Nula por
permutación:** si las etiquetas no tuvieran relación con la huella, serían
intercambiables; permutarlas y repetir el procedimiento completo da la distribución exacta
del AUC bajo esa nula, y $p = (1+\#\{AUC^*\ge AUC\})/(1+B)$ es válido en muestra finita.
Contra el **mismo club con otros técnicos**, un AUC alto dice que se distingue el técnico,
no el plantel.

### 13.7 Evolución: un sistema dinámico con ruido

Modelo de nivel local (Harvey 1989): el estilo $\ell_t$ en el partido $t$ y lo observado $y_t$,

$$
\ell_t = \ell_{t-1} + w_t,\ w_t\sim N(0,q);\qquad y_t = \ell_t + v_t,\ v_t\sim N(0,r).
$$

**Filtro de Kalman.** Por condicionamiento gaussiano, con predicción
$m_{t|t-1} = m_{t-1}$, $p_{t|t-1} = p_{t-1} + q$ y ganancia $k_t = p_{t|t-1}/(p_{t|t-1}+r)$:
$m_t = m_{t|t-1} + k_t(y_t - m_{t|t-1})$, $p_t = (1-k_t)p_{t|t-1}$.
**Suavizado de Rauch-Tung-Striebel** hacia atrás, con $c_t = p_t/p_{t+1|t}$:
$\hat m_t = m_t + c_t(\hat m_{t+1} - m_{t+1|t})$. $q$ y $r$ por máxima verosimilitud con la
descomposición del error de predicción:
$\log L = -\tfrac12\sum_t\big[\log(2\pi s_t) + e_t^2/s_t\big]$, $s_t = p_{t|t-1}+r$.

**Cambio de club como intervención.** En el primer partido con el club nuevo se suma a
la varianza del estado un valor difuso ($10\,\mathrm{Var}(y)$): el nivel puede saltar ahí
sin inflar $q$ en el resto. El salto se lee como $\hat m_{t} - \hat m_{t-1}$ con
$z = \text{salto}/\sqrt{\hat p_t + \hat p_{t-1}}$ (conservador: ignora la covarianza
positiva entre estimaciones suavizadas contiguas). $q/r\approx0$ significa identidad estable.

### 13.8 Simulador de partido

Para un equipo A (técnico-club) atacando a B:

1. **Número de secuencias** $n\sim\text{Poisson}(\lambda)$, $\lambda = \lambda_A\lambda^{\text{concede}}_B/\bar\lambda$.
2. **Familias:** multinomial con $\pi\propto\pi_A\odot\pi^{\text{concede}}_B/\bar\pi$.
   Por el teorema de partición de Poisson, los conteos por familia son Poisson
   independientes con medias $\lambda\pi_k$.
3. **Remate** en la familia $k$ con probabilidad $p_k = \bar p_k(p_{A,k}/\bar p_k)(p^{\text{concede}}_{B,k}/\bar p_k)$,
   y **gol** por remate con probabilidad $g_k$ combinada igual (log-lineal, "log5").
4. Cada parámetro se encoge hacia la liga con $a$ pseudo-secuencias (Prop. 3.1).

**Validación dejando el partido fuera, exacta.** Los parámetros son funciones de sumas
por equipo-partido; restar la contribución de un partido a las sumas de su etapa da
exactamente los parámetros estimados sin él. Se mide la puntuación de Brier del resultado
contra la de las frecuencias base (habilidad $= 1 - \text{Brier}/\text{Brier}_{\text{base}}$).

*Código:* `comparar.py`, `futbol.py`, `geometria.py`, `balon_parado.py`, `jugadores.py`,
`identidad.py`, `simulacion.py`.

---

## 14. Los experimentos que se probaron y no se adoptaron

**Estado aumentado.** Se sustituyó el estado $z$ por $(z, \ell)$: $\ell$ = nivel de presión
(Voronoi local del 360, ADR-v2-36) o dirección de la acción que trajo el balón
(ADR-v2-37). Una cadena de orden 1 en el estado aumentado conserva todas las formas
cerradas del §2.

**Comparación justa.** El destino se evalúa en la escala común (zona o absorbente) de la
Prop. 5.1, marginalizando el nivel del destino:
$\hat P(z_j\mid s_i) = \sum_\ell \hat P((z_j,\ell)\mid s_i)$. Así el puntaje del estado
aumentado y el de la malla sola predicen **el mismo evento**, y la diferencia mide solo la
información del nivel en el origen.

**Resultado.** Los dos estados **predicen mejor** la siguiente acción (dirección
+0.066 nats, presión +0.031), pero **ningún $K\ge3$ es reproducible** con ellos: más
estados por tipo dejan menos datos por parámetro, y la mezcla pierde identificabilidad.
El vocabulario oficial se queda en $5\times4$, $K=3$: es el más rico que los datos sostienen.

*Código:* `direccion.py`, `voronoi.py`.

---

## 15. Lo que este modelo NO demuestra

* **Nada causal.** Todo es descriptivo y comparativo; separar técnico de plantel se
  aproxima con sus cambios de club, no se identifica.
* **Independencia entre partidos.** Es el supuesto de todos los intervalos.
* **Markov dentro de cada tipo.** Es una aproximación contrastada (duración, llegada,
  memoria residual pequeña), no una verdad.
* **El 360 no es tracking.** Instantáneas en el momento del evento; lo que la cámara no
  ve no se imputa.
* **xG y OBV son modelos del proveedor.** Por eso la eficiencia se contrasta con los dos y
  con la tasa de remate.
* **El técnico solo mueve $\pi_k$, no $P^k$ (supuesto, ADR-v2-52).** El modelo de la fase 2 deja que
  un técnico cambie los pesos de las tres familias, pero supone que cada familia, hecha por él, es
  la misma cadena de Markov que hace la liga: «Ataque elaborado» de Almada = «Ataque elaborado» de
  la liga, solo que más seguido. Nunca se había dicho. Si es falso, $\Delta\pi$ mezcla «hace
  distinto» con «lo hace más» y los efectos en la cancha de H1–H2 se interpretan de más. Se
  contrasta con una prueba de score (`supuesto_pk.py`, experimento, no adoptado; abajo §15.1).
* **Las responsabilidades $r_{sk}$ son una estimación, no un dato (generated regressor,
  ADR-v2-53).** Ver §7.1: el sandwich de la Prop. 7.2 las trata como observadas.

### 15.1 Prueba del supuesto $P^k_{\text{foco}}=P^k_{\text{liga}}$ (experimento, no adoptado)

Se perturba cada fila $i$ de la familia $k$ del foco: $P_{ij}(\theta)\propto P^k_{ij}e^{\theta_{ij}}$
($\theta_{i,\text{ref}}=0$). El score en $\theta=0$ de la secuencia $s$ es
$u_s(i,j)=r_{sk}\,(c_s(i,j)-n_s(i)P^k_{ij})$, con $c_s(i,j)$ las transiciones $i\to j$ y
$n_s(i)=\sum_jc_s(i,j)$.

**Proposición 15.1 (score bajo la nula).** Si $P^k_{\text{foco}}=P^k$ y la secuencia sigue la cadena
de la familia $k$ ($r_{sk}=1$), $E[u_s(i,j)]=0$ y los scores de filas distintas son incorrelacionados.

*Demostración.* Condicionado a visitar $i$ $n_s(i)$ veces, $E[c_s(i,j)\mid n_s(i)]=n_s(i)P^k_{ij}$ por
la propiedad de Markov, así que cada sumando del score tiene esperanza 0. Para filas $i\ne i'$, el
incremento de $i$ (en la visita $t$) tiene esperanza condicional 0 dado el pasado, y el de $i'$ en
una visita posterior es medible respecto de ese pasado; el producto es una diferencia de
martingala y su esperanza es 0. $\square$

Con $U_g=\sum_{s\in g}u_s$ (partido $g$), la varianza de conglomerados **sin centrar** es
$\hat V=\sum_gU_gU_g^\top$. Como $P^k_{\text{liga}}$ también se estima (con las secuencias de partidos
sin el foco), la varianza suma el error de esa estimación (delta): $V=V_f+c_i^2V_{\text{liga}}$,
$c_i=n_i^{f}/n_i^{\text{liga}}$. Sin ese término la prueba rechazaba 22 % al 5 % bajo $H_0$ en datos
sembrados. Por fila, $T_i=U_i^\top V_i^{-1}U_i$ y $F_i=T_i\frac{G-d_i}{(G-1)d_i}\sim F(d_i,G-d_i)$; las filas
de una familia se combinan con Fisher. *Código:* `supuesto_pk.py`.

Con ruido de plantel un Wald «rechaza» a casi cualquier técnico, así que además se reporta la
distancia (TV ponderada), el efecto en $E[T]$ y $P(\text{remate})$ de cambiar $P^k$, y el percentil
del foco entre los demás técnicos-club (nula empírica).


### 15.2 El percentil del foco, a igual tamaño (ADR-v2-55)

La primera corrida sobre Almada rechazó $H_0$ en las tres familias (exceso $T/\text{gl}$ de 2.3 a 3.2) y lo
puso en el percentil 98–100 de 44 técnicos-club. Ese percentil no se puede leer como magnitud: con una
desviación fija $\delta$ por fila, $E[T]\approx \text{gl}+n\,\delta^2$, y Almada tiene 168 partidos contra ≥ 30 de
la nula. La TV (0.035–0.046) no crece con $n$, pero tiene sesgo de muestreo hacia arriba con $n$ chico
($E\,|\hat p-p|>0$ aun si $p$ es el de la liga), así que favorece a los técnicos con menos partidos.

**Comparación honesta.** Cada unidad (técnico-club, y Almada completo y por club) se remuestrea a exactamente
$n$ partidos, $R=20$ veces, con su $P^k_{\text{liga}}$ estimada una vez; en cada sorteo se calcula el percentil de
Almada entre las demás unidades y se reporta la mediana, por exceso y por TV. A igual $n$, el exceso compara
$\delta^2$ y la TV compara distancias con el mismo sesgo.

**Regla, fijada antes de ver el resultado** (mediana a $n=30$):

* percentil ≤ 80 por exceso y por TV: Almada se desvía de la liga **como un técnico cualquiera**; el supuesto es
  una aproximación razonable, con la misma desviación que el ruido de plantel le da a todos, y queda como
  limitación declarada;
* percentil ≥ 95 por los dos: Almada **hace distinto** cada familia, no solo la usa más. El supuesto no se
  sostiene para él y quedan en duda las lecturas de la fase 2 que lo usan: (i) las responsabilidades $r_{sk}$
  de sus secuencias se calculan con las $P^k$ de la liga, así que si él hace cada familia distinto sus
  secuencias se **clasifican** con una vara ajena; (ii) por eso H1 y H2, que leen $\Delta\pi$ como «usa más tal
  familia», mezclan «la usa más» con «la hace distinta y se parece más a otra»; (iii) H3–H6, por la misma
  razón en cada contexto; (iv) H7 y H8 comparan xG por secuencia dentro de cada familia, que ya incorpora cómo
  la hace, así que su número se sostiene, pero hereda (i): la familia a la que se asigna cada secuencia.
  No dependen del supuesto la proyección (§19, Maher con xG) ni los escenarios del simulador, que usan la
  eficiencia del propio foco dentro de cada familia. Lo que mide el efecto en la cancha es pequeño:
  $\Delta E[T]\approx-1$ acción por posesión en Circulación estéril y Ataque elaborado, $\Delta P(\text{remate})\le 1$ pp;
* cualquier otra cosa: no concluyente; se reporta así.

*Resultado:* pendiente de la corrida sobre los datos reales (`supuesto_pk_n.py`).

---

## 16. Balón parado: el xDefense en dos capas

**Objeto.** Un centro a balón parado $C$ (corner, tiro libre al área, lateral largo; §6 del
framework), $S\in\{0,1\}$ = hubo remate del que saca en la ventana, $G\in\{0,1\}$ = hubo gol.

**Proposición 16.1 (descomposición).** $P(G=1\mid C)=P(S=1\mid C)\,P(G=1\mid S=1,C)$.

*Demostración.* $G=1\Rightarrow S=1$ (no hay gol sin remate), así que
$\{G=1\}=\{G=1\}\cap\{S=1\}$ y $P(G=1\mid C)=P(G=1,S=1\mid C)=P(S=1\mid C)P(G=1\mid S=1,C)$
por la definición de probabilidad condicional. $\square$

Cada factor es una capa: **prevención** (negar el remate) y **supresión** (empeorar el remate
que se concede). El trabajo previo del equipo solo tenía la foto del remate: la capa 1 era
invisible justo cuando la defensa gana (centro despejado, sin remate). Con el frame 360
**del cobro**, la capa 1 se observa en todos los centros.

**Capa 1.** $\hat p_i=\sigma(\hat\beta_0+x_i^\top\hat\beta)$ con $x_i$ = intención del cobro y
del ataque (tipo, lado, técnica, altura, zona, largo, posición, minuto; del 360: atacantes en
el área, en el área chica, encima del portero). Nada de la defensa ni del desenlace del pase
entra en $x_i$ (fuga del objetivo). El valor defensivo de un equipo $k$ sobre sus $n_k$
centros en contra:
$$xD^{\text{prev}}_k=\frac1{n_k}\sum_{i\in k}(\hat p_i-S_i).$$

**Proposición 16.2 (sin sesgo bajo la nula).** Si el modelo está bien calibrado,
$E[S_i\mid x_i]=p(x_i)$, y la defensa de $k$ es la promedio, entonces
$E[xD^{\text{prev}}_k\mid x]\to 0$ cuando $\hat p\to p$.

*Demostración.* $E[\hat p_i-S_i\mid x_i]=\hat p_i-p(x_i)$; con $\hat p$ consistente (logit
bien especificado, $n\to\infty$) el término tiende a 0 para cada $i$, y el promedio también. Si
la defensa de $k$ reduce el remate por un factor, $E[S_i\mid x_i,k]<p(x_i)$ y el valor
esperado es positivo. $\square$

Las $\hat p_i$ son **fuera de muestra** (validación cruzada por partido): con $\hat p_i$
ajustada incluyendo al propio $i$, el ajuste absorbería parte de $S_i$ y encogería el xD hacia 0.

**Capa 2.** Sobre los remates con foto, dos logits en la **misma** muestra:
$xG^{\text{base}}=E[G\mid a]$ (ataque: distancia, ángulo, cabeza, de primera, tipo de jugada) y
$xG^{\text{full}}=E[G\mid a,d]$ (más la defensa $d$). $xD^{\text{remate}}_i=xG^{\text{base}}_i-xG^{\text{full}}_i$.
Por la ley de la esperanza iterada, $E[xG^{\text{full}}\mid a]=xG^{\text{base}}$, así que
$E[xD^{\text{remate}}\mid a]=0$: el xD de supresión está **centrado en la defensa promedio**,
no en "un remate sin defensa".

**Proposición 16.3 (visibilidad del arco).** Sea $I=[\varphi_1,\varphi_2]$ el ángulo que
subtiende el arco desde el remate $s$ y $S_j=[\phi_j-\alpha_j,\phi_j+\alpha_j]\cap I$ la
sombra del defensor $j$ (disco de radio $r$ a distancia $d_j$, $\alpha_j=\arcsin(r/d_j)$).
Ordenar los $S_j$ por su inicio y fundir los que se tocan calcula $|\bigcup_j S_j|$ en
$O(m\log m)$.

*Demostración.* Tras ordenar, un barrido mantiene el intervalo abierto $[a,b]$; si el
siguiente empieza en $a'\le b$ se funde ($b\leftarrow\max(b,b')$), si no, $[a,b]$ es una
componente conexa de la unión (nada posterior empieza antes de $a'>b$) y su longitud se suma.
Las componentes son disjuntas y cubren la unión, así que la suma es su medida. $\square$

La tangente desde $s$ a un disco de radio $r$ con centro a distancia $d$ forma el ángulo
$\arcsin(r/d)$ con la recta a su centro; de ahí $\alpha_j$.

**Proposición 16.4 (contracción normal-normal; Efron & Morris 1975).** Si
$\theta_j\sim N(\mu,\tau^2)$ y $x_j\mid\theta_j\sim N(\theta_j,v_j)$, entonces
$E[\theta_j\mid x_j]=\mu+\frac{\tau^2}{\tau^2+v_j}(x_j-\mu)$.

*Demostración.* $(\theta_j,x_j)$ es normal bivariada con $\mathrm{Cov}=\tau^2$,
$\mathrm{Var}(x_j)=\tau^2+v_j$; la media condicional de una normal es
$\mu+\frac{\mathrm{Cov}}{\mathrm{Var}(x_j)}(x_j-\mu)$. $\square$

$\tau^2$ se estima por momentos (DerSimonian-Laird): con $w_j=1/v_j$ y
$Q=\sum_jw_j(x_j-\bar x_w)^2$, $E[Q]=(k-1)+\tau^2\big(\sum w_j-\sum w_j^2/\sum w_j\big)$, de donde
$\hat\tau^2=\max\{0,(Q-(k-1))/(\sum w_j-\sum w_j^2/\sum w_j)\}$. La varianza de cada $x_j$ (razón
de sumas de una etapa) sale del método delta por conglomerados:
$v_j=\frac{G}{G-1}\sum_m(n_m-\hat\theta_jd_m)^2/(\sum_md_m)^2$. Si $\hat\tau^2=0$, **no hay
variación real detectable entre equipos** y todos se contraen a $\mu$: es la conclusión del
trabajo previo con 51 goles, que aquí se vuelve a poner a prueba con toda la liga.

**Varianza común para métricas en goles.** Con goles, la $v_j$ del método delta está acoplada a
$x_j$: una etapa a la que casi no le hacen goles tiene $x_j$ alto (evitó goles) **y** $v_j$ chica, así
que pesa de más en $\hat\mu$ y en $\hat\tau^2$ y los sesga. Para los términos de la cadena (§16.6) se usa
la misma varianza por saque en todas las etapas, la de la liga:
$\hat\sigma^2=\sum_j\sum_m(n_m-\hat\theta_jd_m)^2/\sum_j\sum_md_m^2$ y $v_j=\hat\sigma^2\sum_md_m^2/(\sum_md_m)^2$,
que depende del volumen de la etapa pero no de su resultado. H24 y H25 se reportan con la varianza
propia, como se corrieron.

**Proposición 16.5 (la cadena: recursión de probabilidad condicional y total).** En la ventana de
un saque puede haber varios remates (el rechace vuelve). Sean $S_k$ = "hay un $k$-ésimo remate",
$G_k$ = "el $k$-ésimo entra" y $q_k=P(G_k\mid S_k,\bar G_1,\dots,\bar G_{k-1},C)$. Con
$V_k=P(\text{gol en los remates }k,k+1,\dots\mid S_1,\dots,S_{k-1}\text{ sin gol},C)$,
$$V_k=P(S_k\mid\cdot)\,\big[q_k+(1-q_k)\,V_{k+1}\big],\qquad P(G\mid C)=V_1 .$$

*Demostración.* Por probabilidad total sobre $S_k$ y $\bar S_k$: sin $k$-ésimo remate no hay gol en
adelante, así que solo queda el término $P(S_k\mid\cdot)\,P(\text{gol}\mid S_k,\cdot)$. Dado $S_k$,
otra vez por probabilidad total sobre $G_k$ y $\bar G_k$: o entra ($q_k$) o no entra ($1-q_k$) y la
jugada sigue, que es $V_{k+1}$ por definición. La recursión termina porque la ventana es finita
($V_{K+1}=0$). Con un solo remate posible, $V_1=P(S\mid C)\,q_1$: la Proposición 16.1. $\square$

Por linealidad, el número esperado de goles del saque es
$E[\text{goles}\mid C]=P(S\mid C)\,E\big[\sum_kG_k\mid S,C\big]$, que es lo que miden las dos capas
juntas: la capa 1 da $P(S\mid C)$ y la capa 2, la suma de $xG$ de los remates de la jugada.

**Proposición 16.6 (descomposición exacta en cuatro términos).** Para un saque $i$ de tipo $t$, sean
$\hat p_i$ su $P(S\mid C)$ de la capa 1 (fuera de muestra; $\hat p_i=1$ en el tiro libre directo, que
ya es un remate), $s_i\in\{0,1\}$ si hubo remate, $B_i=\sum xG^{\text{base}}$ y
$F_i=\sum xG^{\text{full}}$ de sus remates, $g_i$ sus goles y $\kappa_t$ = el promedio de $B$ en los
saques de tipo $t$ **con** remate de toda la liga (lo que vale un saque con remate). Entonces
$$\hat p_i\kappa_t-g_i=\underbrace{(\hat p_i-s_i)\kappa_t}_{\text{prevención}}
+\underbrace{s_i(\kappa_t-B_i)}_{\text{alejamiento}}
+\underbrace{s_i(B_i-F_i)}_{\text{supresión}}
+\underbrace{s_i(F_i-g_i)}_{\text{portero y definición}} .$$

*Demostración.* La suma de la derecha es telescópica:
$\hat p\kappa-s\kappa+s\kappa-sB+sB-sF+sF-sg=\hat p\kappa-sg$, y $sg=g$ porque sin remate no hay gol
($s=0\Rightarrow g=0$). $\square$

El lado izquierdo son los goles que la defensa evitó respecto de lo que se espera de ese saque con una
defensa promedio. Cada término contesta una pregunta: ¿negó el remate?, ¿lo empujó a un lugar peor?,
¿tapó el arco?, ¿atajó el portero? Para el que saca, los mismos términos con el signo cambiado
($xO=-xD$) son los goles que generó de más. Se promedian por equipo (razón de sumas) y se contraen por
etapa como en la Proposición 16.4. Un remate sin foto 360 entra con el xG del proveedor en $B$ y en
$F$: no aporta a la supresión.

Los términos no son independientes de cómo se escogen $\kappa_t$ y los modelos: el reparto entre
prevención y alejamiento depende de $\kappa_t$ (un promedio de la liga), pero **la suma no**. La capa 1
de los saques que no van al área (tiros libres cortos, laterales del último cuarto) es un modelo
**aparte**: el de los centros al área, pre-registrado para H24, no cambia.


### 16.7 Portero y definición, por separado (experimento xGOT, ADR-v2-56, no adoptado)

El cuarto término $s_i(F_i-g_i)$ junta el remate que el atacante mandó fuera y el que el portero atajó: no es
identificable como mérito del portero. Con la ubicación del balón en el plano de la portería, $(y,z)$, que
StatsBomb da en `shot.end_location` cuando el remate llega al arco, se define, para cada remate $r$,
$$xGOT_r=\begin{cases}E[G\mid\text{a puerta},(y,z)_r,\text{calidad previa}_r]&\text{si va a puerta}\\0&\text{si no}\end{cases}$$
(«a puerta» = `shot.outcome` ∈ {Goal, Saved, Saved to Post}) y $X_i=\sum_{r\in i}xGOT_r$.

**Proposición 16.7 (cinco términos, exacta).** Con los términos de la Prop. 16.6,
$$\hat p_i\kappa_t-g_i=\text{prevención}+\text{alejamiento}+\text{supresión}
+\underbrace{s_i(F_i-X_i)}_{\text{definición}}+\underbrace{s_i(X_i-g_i)}_{\text{portero}} .$$

*Demostración.* $s_i(F_i-X_i)+s_i(X_i-g_i)=s_i(F_i-g_i)$, el cuarto término de la Prop. 16.6, que ya es
exacta. $\square$

La exactitud no depende de que xGOT esté bien estimado: un mal xGOT solo reparte mal entre definición y
portero. Por eso se ajusta fuera de muestra con pliegues por partido (logit L2, como las dos capas), sobre todos
los remates a puerta de la liga, con la ubicación en el marco y la calidad previa del remate (el logit del xG con
que entra en $F$). Un remate a puerta sin $z$ entra con su propio xG (neutro para la definición). Si los
remates a puerta no traen $z$, el experimento se detiene: no se imputa nada con la $(x,y)$ en la cancha.
*Código:* `xgot.py`, `scripts/experimentos/xgot.py`.

**Resultado sobre Almada (corrida del 2026-10-02; ADR-v2-58).** La ubicación en el marco viene en el 100 % de los
15,138 remates a puerta (92.8 % dentro del marco), así que la partición se pudo hacer. Es **exacta** (error máximo
1.9e-16 sobre 55,001 saques) y **segura**: H24–H26 salen idénticas y, en el BH global, reemplazar las 18 pruebas de
«portero y definición» por 36 no cambia el veredicto de ninguna de las 730 afirmaciones (246 → 247 demostradas: la
nueva sería «xD portero en tiros libres que no van al área», q = 0.013). El AUC de xGOT (0.831 contra 0.735 del xG
previo) **no es una mejora de modelo**: xGOT usa dónde terminó el balón, información posterior al remate; no compiten.

Lo que no hay es **señal de equipo**: en todo el balón parado, τ² = 0 para definición y para portero en contra
(p de Cochran 0.57 y 0.48) y para portero a favor (0.92), y τ² ≈ 0.006 (p = 0.30) para la definición a favor: la
diferencia entre técnicos-club en esos términos es la del azar. Por tipo de saque, la primera corrida no sirve (un error
del experimento dejaba nulos los equipo-partidos sin saques de ese tipo y vaciaba la etapa: «no estimable»); está
corregido y pendiente de volver a correr.

**Decisión.** Se documenta y **no se adopta como métrica narrativa**: partir el término no cambia nada de lo publicado
y no revela variación entre equipos. Si la corrida corregida por tipo de saque encontrara τ² > 0 con p de Cochran < 0.05
en algún tipo, se reabre solo para ese tipo.

**Barrera.** En el tiro libre directo, la regla 13 obliga a la barrera a 9.15 m. Se cuentan los
defensores de campo a ≤ 12 m del balón cuya sombra (el disco de la Proposición 16.3) toca el ángulo
del arco; la fracción de arco libre es el `goal_open` de ese remate.

*Código:* `xdefensa.py` (`goal_open`, `barrera`, `capa1`, `capa2`, `descomposicion`, `cadena`,
`contraccion`, `por_etapa`).

## 17. Balón parado: marca y línea

**Marca al hombre.** En el área, la asignación óptima defensor–atacante (§13.3, algoritmo
húngaro; la matriz de asignación es totalmente unimodular, así que el óptimo del problema
lineal es entero) define, para cada defensor, su atacante. Un defensor marca al hombre si
esa distancia es $\le2$ m; el resto es zonal (o sobra). Es la operacionalización de la
distinción de Pulling, Robins & Rixon (2013).

**Línea del fuera de lugar.** Por la regla 11, un atacante está en fuera de juego si está
más cerca de la línea de meta que el balón y que el **penúltimo** rival. En el frame del tiro
libre, con las $x$ de los defensores visibles (portero incluido) ordenadas,
$\ell=x_{(n-1)}$ y $\text{altura}=120-\ell$. Se exige el portero visible: sin él, el
"penúltimo visible" puede no ser el penúltimo real. Un defensor que cuida el poste deja la línea
legal casi en el arco aunque el resto esté 15 m arriba; la **línea táctica** repite el cálculo
sin los defensores con $x\ge118$, y es la que describe lo que arma el técnico.

**Tasas.** Remates y goles por tipo de jugada, con exposición (§13.4). La receta Arsenal se
compara con el resto por bootstrap de partidos de la diferencia de medias; es descriptiva
(el equipo que la elige no es aleatorio).

## 18. Fase ofensiva: verticalidad, motivos y el camino típico

**Verticalidad.** $D=\sum_a(x^{\text{fin}}_a-x_a)/\sum_a\|\mathbf{p}^{\text{fin}}_a-\mathbf{p}_a\|\in[-1,1]$
(cada sumando del numerador está acotado por el del denominador). Como razón de sumas, entra
a la maquinaria del §13.1 sin cambios.

**Motivos.** Una cadena de tres pases enlazados involucra $(p_0,p_1,p_2,p_3)$ con
$p_{t}\neq p_{t+1}$. Reetiquetar por primera aparición es invariante a los nombres, y las
clases posibles son exactamente cinco: $p_2\in\{p_0,\text{nuevo}\}$ y $p_3\in\{p_1,\text{nuevo}\}$
si $p_2=p_0$ (ABAB, ABAC), o $p_3\in\{p_0,p_1,\text{nuevo}\}$ si $p_2$ es nuevo (ABCA, ABCB,
ABCD). Se cuentan ventanas deslizantes.

**Proposición 18.1 (camino típico).** En una cadena con transiciones $P$, el camino
$z_0\to\dots\to z_T\to\text{remate}$ de máxima probabilidad
$\prod_tP(z_t,z_{t+1})\cdot P(z_T,\text{remate})$ es el camino más corto con pesos
$w=-\log P\ge0$, y Dijkstra lo encuentra.

*Demostración.* $-\log$ es estrictamente decreciente, así que maximizar el producto equivale a
minimizar $\sum_t-\log P(z_t,z_{t+1})-\log P(z_T,\text{remate})$. Como $P\le1$, los pesos son
no negativos, la condición bajo la cual Dijkstra es exacto. Se resuelve desde $z_0$ hacia
todos los estados y se elige el $z_T$ que minimiza la distancia más $-\log P(z_T,\text{remate})$. $\square$

La cadena del foco en cada familia $k$ es $\hat P^{(k)}_{\text{foco}}=
\text{encoger}(C^{(k)}_{\text{foco}},P^{(k)}_{\text{liga}},\lambda)$ con los conteos ponderados por
la responsabilidad $r_{ik}$ de cada secuencia (§3–§4).

## 19. Contexto por rival, sustituciones y proyección

**Estratos (G2).** Dentro de cada estrato $e$ se estima $\delta_e=\text{foco}_e-\text{liga}_e$
(§13.1). Los partidos del foco en estratos distintos son disjuntos, así que
$\widehat{\mathrm{Var}}(\delta_f-\delta_d)=\widehat{\mathrm{Var}}(\delta_f)+\widehat{\mathrm{Var}}(\delta_d)$,
con cada varianza tomada del ancho de su IC bootstrap; $z=(\hat\delta_f-\hat\delta_d)/\widehat{\mathrm{sd}}$.

**Diferencias en diferencias emparejadas (G4).** Para el cambio $i$ en la celda $c(i)$,
$\Delta_i=Y_i^{\text{post}}-Y_i^{\text{pre}}$ y el efecto es
$\hat\tau=\frac1{n_f}\sum_{i\in f}\big(\Delta_i-\bar\Delta^{\text{liga}}_{c(i)}\big)$.
*Supuesto de identificación:* dentro de una celda (tramo de 5 min, signo del marcador), sin el
cambio del foco, su $\Delta$ esperado sería el de los cambios de la liga (tendencias paralelas
condicionales). Es exactamente el estimador de emparejamiento exacto por celda; su IC es por
bootstrap de partidos, remuestreando por separado los del foco y los de la liga.

**Proyección (G6).** El modelo multiplicativo $E[xG_{ij}]=\mu A_iD_jh^{\pm1}$ (Maher 1982)
tiene, por temporada, el punto fijo
$A_i=\sum xG_i/\sum\mu D_{r}h^{\pm}$, $D_i=\sum xGc_i/\sum\mu A_rh^{\mp}$, identificado hasta
una escala que se fija con media 1.

**Proposición 19.1 (por qué dejar fuera al equipo evaluado).** Si el ataque de $i$ se
multiplica por $k$ y sus $m$ partidos contra $j$ entran en la estimación de $D_j$, entonces
$\hat D_j$ crece aproximadamente en el factor $1+(k-1)\frac{m}{n_j}$, y el índice de ataque de
$i$, $xG_i/\sum\mu\hat D_j$, se subestima en ese mismo factor: la mejora se esconde a sí misma.

*Demostración.* $\hat D_j=\sum_{\text{rivales}}xGc_j/\sum\mu A$; los $m$ partidos contra $i$
aportan $k$ veces su valor esperado al numerador y el resto no cambia, así que el cociente
crece en $1+(k-1)m/n_j$ (primer orden, ignorando el reajuste de $A_i$ en el denominador,
que va en la misma dirección). $\square$

Por eso las fuerzas de los rivales se estiman **sin** los partidos del equipo evaluado. El
efecto de una llegada es $e=\log A_{\text{post}}-\log A_{\text{pre}}$; el del técnico se contrae
hacia la media de las llegadas de la liga (Prop. 16.4), que incluye la regresión a la media
posterior a un despido (van Ours & van Tuijl 2016). Los goles se simulan
$\text{Poisson}(\mu A_iD_jh^{\pm})$ independientes, y la validación proyecta **cada** llegada de
la liga con su propio efecto fuera del ajuste.

*Código:* `rival.py`, `sustituciones.py`, `proyeccion.py`.

## 20. La regla de demostración

**Una sola familia.** Sean $p_1,\dots,p_m$ las p de todas las afirmaciones (hipótesis, métricas,
efectos, pruebas), ordenadas $p_{(1)}\le\dots\le p_{(m)}$. BH rechaza las $k^*$ menores con
$k^*=\max\{k:p_{(k)}\le k\alpha/m\}$ y controla $E[V/\max(R,1)]\le\alpha$. La garantía vale con
independencia y con dependencia positiva de regresión (Benjamini & Yekutieli 2001), que es el caso de
métricas del mismo partido. $q_{(k)}=\min_{j\ge k}p_{(j)}m/j$.

**p de un efecto con IC.** Si el IC 95 % es $[\ell,u]$ y el estimador es aproximadamente normal,
$\widehat{ee}=(u-\ell)/(2\cdot1.96)$ y $p=2\Phi(-|\hat\delta|/\widehat{ee})$.

**Heterogeneidad (Cochran).** Con $w_j=1/v_j$, $Q=\sum_jw_j(x_j-\bar x_w)^2\sim\chi^2_{k-1}$ bajo
$\tau^2=0$. Si no se rechaza, el puesto de un técnico entre los demás no significa nada.

**Equivalencia (TOST).** Con margen $\delta$: $H_0:|\Delta|\ge\delta$ contra $H_1:|\Delta|<\delta$. Se
rechaza si las dos pruebas unilaterales al 5 % rechazan, es decir, si el IC del 90 % cabe en
$(-\delta,\delta)$; $p_{\text{TOST}}=\max\{P^*(\Delta^*\ge\delta),P^*(\Delta^*\le-\delta)\}$ por
bootstrap.

**Receta contra inercia (Diebold-Mariano).** Con pérdidas absolutas $d_i=|e^{\text{receta}}_i|-|e^{\text{inercia}}_i|$
en $n$ llegadas independientes, $t=\bar d/(s_d/\sqrt n)\sim t_{n-1}$ bajo $E[d]=0$. Como respaldo sin
normalidad, Wilcoxon de rangos con signo.

**Proposición 20.1 (intervalo conforme).** Sean $r_1,\dots,r_n$ los errores absolutos por partido de
$n$ llegadas intercambiables con una nueva, y $\hat q$ el $\lceil(n+1)(1-\alpha)\rceil$-ésimo menor.
Entonces $P(r_{n+1}\le\hat q)\ge1-\alpha$.

*Demostración.* Por intercambiabilidad, el rango de $r_{n+1}$ entre los $n+1$ errores es uniforme en
$\{1,\dots,n+1\}$ (con empates, a lo más uniforme). $r_{n+1}\le\hat q$ ocurre si su rango es
$\le\lceil(n+1)(1-\alpha)\rceil$, lo que pasa con probabilidad $\lceil(n+1)(1-\alpha)\rceil/(n+1)\ge1-\alpha$.
$\square$ (Vovk, Gammerman & Shafer 2005; Lei et al. 2018.)

La proyección $\pm\hat q$ puntos por partido cubre entonces al menos 80 %, que es lo que el intervalo del
simulador prometía y no cumplía.

*Código:* `demostracion.py`, `xdefensa.contraccion` (Q), `balon_parado.rutinas` (TOST),
`proyeccion.validar` (DM, binomial, conforme).

