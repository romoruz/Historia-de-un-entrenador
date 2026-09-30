#!/usr/bin/env bash
# Copia a docs/figuras/<sección>/ las figuras que muestran los documentos (reports/ no se versiona).
# Son agregados (mapas, curvas, barras): no contienen eventos de StatsBomb.
#
# Uso (raíz del repo, después de correr todo para el foco):
#   bash scripts/publicar_figuras.sh                       # foco del config
#   bash scripts/publicar_figuras.sh "Guillermo Almada"
#   git add docs/figuras && git commit -m "Figuras de resultados" && git push
set -euo pipefail
cd "$(dirname "$0")/.."
FOCO="${1:-$(python -c "from dtcoach.config import Config; print(Config.load()['foco']['coach'])")}"
S=$(python -c "import sys; print(sys.argv[1].lower().replace(' ', '_'))" "$FOCO")
D=docs/figuras
H=reports/historia/$S
rm -rf "$D"
copiar () {  # origen destino (relativo a docs/figuras)
  mkdir -p "$(dirname "$D/$2")"
  if [ -f "$1" ]; then cp "$1" "$D/$2"; echo "  ✓ $2"; else echo "  · falta $1"; fi
}
echo "vocabulario de la liga (fase 1)"
copiar reports/mezcla/tipos_K3_visitas.png          vocabulario/visitas.png
copiar reports/mezcla/tipos_K3_inicio.png           vocabulario/inicio.png
copiar reports/mezcla/curva_k_5x4_p0.png            vocabulario/curva_k.png
copiar reports/fase1/yaglom_5x4.png                 vocabulario/yaglom.png
copiar reports/direccion/mezcla/curva_k_5x4_p0.png  vocabulario/experimento_direccion_curva_k.png
copiar reports/presion/mezcla/curva_k_5x4_p0.png    vocabulario/experimento_presion_curva_k.png
echo "1. identidad"
copiar reports/fase2/familias_$S.png                identidad/familias.png
copiar reports/fase2/contexto_$S.png                identidad/contexto.png
copiar reports/fase2/eficiencia_$S.png              identidad/eficiencia.png
copiar reports/fase3/por_club_$S.png                identidad/por_club.png
copiar reports/fase3/atlas_$S.png                   identidad/atlas.png
copiar $H/identidad/evolucion.png                   identidad/evolucion.png
copiar $H/identidad/rival.png                       identidad/rival.png
echo "2. ofensiva"
for f in percentiles reparto familias_cancha valor_zona; do copiar $H/ofensiva/$f.png ofensiva/$f.png; done
echo "3. defensa"
for f in percentiles curva_presion pictograma_presion presion_tercios presion_zonas esquema_bloque bloque_tipico \
         recuperacion; do copiar $H/defensa/$f.png defensa/$f.png; done
echo "4. jugadores"
copiar reports/fase3/decisiones_$S.png              jugadores/decisiones.png
copiar $H/jugadores/efecto_cambios.png              jugadores/efecto_cambios.png
for f in $H/jugadores/red_*.png; do [ -f "$f" ] && copiar "$f" "jugadores/$(basename "$f")"; done
echo "5. balón parado"
for f in rutinas_corner corner_defensivo linea_tiros_libres xd_prev_etapas xd_remate_etapas zonas_corner_propio \
         zonas_corner_rival zonas_tl_centrado_propio zonas_tl_centrado_rival zonas_lateral_largo_propio \
         zonas_lateral_largo_rival arbol_corner arbol_tiro_libre arbol_lateral goal_open_esquema \
         descomposicion mapa_xdefensa marca_vs_remate tiros_libres laterales_cuarto laterales_octavo \
         xd_total_corner_etapas xo_total_corner_etapas xd_total_tiro_libre_etapas xd_total_lateral_etapas; do
  copiar $H/balon_parado/$f.png balon_parado/$f.png; done
echo "6. simulación"
copiar reports/fase3/xpts_$S.png                    simulacion/xpts.png
copiar $H/simulacion/proyeccion.png                 simulacion/proyeccion.png
for f in $H/simulacion/partido_tipo_*.png; do [ -f "$f" ] && copiar "$f" "simulacion/$(basename "$f")"; done
echo "listo: $(find "$D" -name '*.png' | wc -l) figuras en $D"
