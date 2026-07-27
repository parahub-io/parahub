/**
 * OSM POI visibility toggle for the base map style.
 *
 * The liberty styles render OSM POIs via four symbol layers over the `poi`
 * source-layer (poi_z14/poi_z15/poi_z16 + poi_transit); light and dark styles
 * share the same layer ids. Unlike the data-overlay toggles (mesh/gov/church)
 * nothing is fetched or added here — the layers already live in the style
 * JSON, so the toggle is pure `setLayoutProperty('visibility')` over them.
 *
 * applyVisibility must run from BOTH useMapLayerStack registration paths:
 * setStyle reloads the style JSON, which resets layout properties to the JSON
 * defaults (visible) — without the reapply, POIs resurrect on a theme flip.
 *
 * Hidden layers drop out of queryRenderedFeatures, so the click dispatcher
 * and hover highlight degrade to no-ops on their own — no gating needed there.
 */

const POI_LAYER_IDS = ['poi_z14', 'poi_z15', 'poi_z16', 'poi_transit']

export function useMapPoiVisibility() {
  const poiEnabled = useLocalPref('poi_enabled', true)

  function applyVisibility(map: any) {
    if (!map) return
    const visibility = poiEnabled.value ? 'visible' : 'none'
    for (const id of POI_LAYER_IDS) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility)
    }
  }

  function toggle() {
    poiEnabled.value = !poiEnabled.value
    applyVisibility(useMapStore().mapInstance)
  }

  return { poiEnabled, applyVisibility, toggle }
}
