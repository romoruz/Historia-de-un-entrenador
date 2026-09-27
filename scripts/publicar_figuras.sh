#!/usr/bin/env bash
# Copia a docs/figuras/ las figuras que muestran los documentos (reports/ no se versiona).
# Son agregados (mapas, curvas, barras): no contienen eventos de StatsBomb.
#
# Uso (raíz del repo, después de correr todo para el foco):
#   bash scripts/publicar_figuras.sh                       # foco del config (Guillermo Almada)
#   bash scripts/publicar_figuras.sh "Guillermo Almada"
#   git add docs/figuras && git commit -m "Figuras de resultados" && git push
set -euo pipefail
cd "$(dirname "$0")/.."
FOCO="${1:-$(python -c "from dtcoach.config import Config; print(Config.load()['foco']['coach'])")}"
S=$(python -c "import sys; print(sys.argv[1].lower().replace(' ', '_'))" "$FOCO")
D=docs/figuras
mkdir -p "$D"
copiar () {  # origen destino
  if [ -f "$1" ]; then cp "$1" "$D/$2"; echo "  ✓ $2"; else echo "  · falta $1"; fi
}
echo "figuras de la liga (fase 1)"
copiar reports/mezcla/tipos_K3_visitas.png          vocabulario_visitas.png
copiar reports/mezcla/tipos_K3_inicio.png           vocabulario_inicio.png
copiar reports/mezcla/curva_k_5x4_p0.png            vocabulario_curva_k.png
copiar reports/fase1/yaglom_5x4.png                 vocabulario_yaglom.png
copiar reports/direccion/mezcla/curva_k_5x4_p0.png  experimento_direccion_curva_k.png
copiar reports/presion/mezcla/curva_k_5x4_p0.png    experimento_presion_curva_k.png
echo "figuras de $FOCO"
copiar reports/fase2/familias_$S.png                fase2_familias.png
copiar reports/fase2/contexto_$S.png                fase2_contexto.png
copiar reports/fase2/eficiencia_$S.png              fase2_eficiencia.png
copiar reports/fase3/por_club_$S.png                fase3_por_club.png
copiar reports/fase3/atlas_$S.png                   fase3_atlas.png
copiar reports/fase3/decisiones_$S.png              fase3_decisiones.png
copiar reports/fase3/xpts_$S.png                    fase3_xpts.png
H=reports/historia/$S
copiar $H/percentiles.png                           estilo_percentiles.png
copiar $H/valor_zona.png                            estilo_valor_zona.png
copiar $H/presion_360.png                           estilo_presion_360.png
copiar $H/recuperacion.png                          estilo_recuperacion.png
copiar $H/evolucion.png                             identidad_evolucion.png
copiar $H/bp_corner_propio.png                      balon_parado_corners_a_favor.png
copiar $H/bp_corner_rival.png                       balon_parado_corners_en_contra.png
for f in $H/red_*.png;        do [ -f "$f" ] && copiar "$f" "jugadores_$(basename "$f")"; done
for f in $H/simulacion_*.png; do [ -f "$f" ] && copiar "$f" "$(basename "$f")"; done
echo "listo: $(ls "$D" | wc -l) figuras en $D"
