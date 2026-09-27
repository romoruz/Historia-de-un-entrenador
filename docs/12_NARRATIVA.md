# 12 — Narrativa (Fase 4, borrador)

> **Foco actual: Guillermo Almada.** La historia pública es
> [`RESULTADOS_ALMADA.md`](RESULTADOS_ALMADA.md). La §2 de abajo (André Jardine) se
> conserva como **contraste**: un técnico que se adapta al plantel frente a uno cuya
> idea viaja con él.

> Guion en lenguaje de fútbol para jueces y lectores no técnicos. Cada frase
> se apoya en una fila de `10_RESULTADOS.md` (entre corchetes). El detalle
> técnico (nats, ρ(Q), W, q) **no** aparece aquí: vive en los documentos de
> método. Pendiente: ensayo con un lector ajeno y versión HTML.

---

## Reglas de estilo

- Sin fórmulas ni símbolos. Se dice "de cada 100 jugadas", no "pp" ni "π".
- Los niveles de evidencia se dicen en palabras:
  - 🟢 → "los datos lo muestran con claridad";
  - ⚪ → "no encontramos diferencia";
  - indicio → "hay una pista, pero todavía no alcanza".
- Nunca "no hay efecto": "no encontramos una diferencia mayor a X".
- Un número por idea y siempre en unidades de cancha: jugadas, metros, minutos, puntos.

---

## 1. El idioma común: tres maneras de atacar en la Liga MX

Revisamos 461 mil jugadas de 1,767 partidos de la Liga MX y encontramos que
casi todas se parecen a una de tres maneras de atacar [§16]:

| jugada | cómo se ve | cuánto dura | qué tan peligrosa |
|---|---|---|---|
| **Directa** | Recuperar y buscar el arco rápido: sale del área propia o nace de un robo arriba | unas 3–4 acciones | la más peligrosa por acción |
| **Circulación estéril** | Tocar en la mitad de la cancha sin entrar al último tercio | unas 7 acciones | casi nunca termina en remate (2–3 de cada 100) |
| **Ataque elaborado** | Construir y llegar por las bandas | unas 9 acciones | 8 de cada 10 llegan al último tercio |

Estas tres maneras salieron igual al repetir el cálculo desde puntos de
partida distintos. No las inventamos: son las que aparecen en los datos.

**Idea para el jurado:** cada equipo, y cada entrenador, es una *receta*
distinta con estos tres ingredientes.

## 2. André Jardine: su huella está en lo que le permite al rival

1. **Su firma es defensiva y viaja con él** [H2, H9]. Contra sus equipos,
   los rivales juegan unas **2 jugadas Directas menos de cada 100** y tienen
   que elaborar más. Pasó en San Luis y en el América. Entre 15 etapas de
   técnicos, sus dos etapas están en el **1.º y el 3.º lugar** de la liga en
   ese rasgo [atlas].
2. **En ataque se adapta al plantel** [H1, H12]. En el América elige lo
   mismo que la liga. En San Luis, con un plantel más modesto, reaccionaba
   más al marcador y al rival.
3. **La puntería es del América, no de él** [H7, H10, H11]. En el América
   su equipo convierte mejor sus jugadas, pero en San Luis eso no pasaba.
   Lo leemos como un mérito del plantel.
4. **Es paciente con la banca** [H13]. Hace su primer cambio **unos
   3 minutos después** que el promedio de la liga, y rota más su once [H17].
5. **Sus puntos son los que merecía** [xPts]. Sumó más de lo esperado, pero
   dentro de lo que explica la suerte.

## 3. Guillermo Almada: el técnico que calma el partido

1. **Sus rivales rinden menos** en la Directa y en el Ataque elaborado [H8.1, H8.3].
2. **Su equipo no se descompone con el marcador** [H3, H6]. Cuando la liga
   cambia su manera de jugar porque va ganando o perdiendo, o según el
   rival, el equipo de Almada cambia menos.
3. **Sus cambios son de pieza por pieza** [H15, H16]. Mete un jugador del
   mismo puesto y reacomoda poco.
4. **Hay una pista, pero todavía no alcanza**: cuando empata o pierde,
   parece mover la banca unos 2 minutos antes [H13, q = 0.106]. En el
   América lleva solo 7 partidos. Hay una pista de que juega más directo
   que en Pachuca, pero todavía es pronto para afirmarlo.

## 4. Por qué confiar en esto

- **Cambiamos la base y las conclusiones se quedaron** [§16]. Rehicimos por
  completo el cálculo de las tres maneras de atacar, y ninguna conclusión
  sobre Jardine o Almada cambió de sentido.
- **Las hipótesis se escribieron antes de ver los resultados**
  (`11_HIPOTESIS.md`), y cuando algo no alcanzó, lo decimos.
- **El modelo reproduce lo que pasa en la cancha**: cuánto duran las
  jugadas, cuántas llegan al área y en cuántas acciones [§16].

## 5. Límites que decimos en voz alta

- Describimos lo que pasó; no probamos causa y efecto.
- Siete partidos de Almada en el América no bastan para concluir.
- Hacia dónde va el balón depende de dónde venía, y el modelo actual
  todavía no lo aprovecha (extensión pendiente).

---

## Pendientes de la Fase 4

- [ ] Ensayo con un lector ajeno (alguien de fútbol, sin estadística) y anotar dónde se pierde.
- [ ] Una figura por idea, con títulos en lenguaje llano.
- [ ] Versión HTML del reporte.
- [ ] Congelar números y figuras.
