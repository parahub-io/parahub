/**
 * useMap3DTiles — OGC 3D Tiles via deck.gl Tile3DLayer + MapboxOverlay
 *
 * Renders OpenSky aerial mesh tilesets on the MapLibre map.
 * deck.gl handles ECEF↔Mercator projection, frustum culling and LOD selection
 * internally — we just declaratively add the layer.
 *
 * History:
 *   - Old impl used Three.js + 3d-tiles-renderer with a MapLibre custom layer.
 *     The base THREE.Camera had no ECEF pose, so frustum culling failed and
 *     no children tiles ever loaded. Also called map.triggerRepaint() in
 *     render() → 100% CPU loop. Replaced with deck.gl 2026-04-07.
 */

import { MapboxOverlay } from '@deck.gl/mapbox'
import { Tile3DLayer } from '@deck.gl/geo-layers'
import { Tiles3DLoader } from '@loaders.gl/3d-tiles'

// Bump `?v=` whenever the per-mission tileset.json schema changes (LOD chain
// edits etc.). Old responses had max-age=604800 so existing browser disk
// caches won't pick up server-side changes for a week — a fresh URL bypasses
// disk cache. This applies to the root tileset only; per-mission URIs in the
// generated root tileset carry their own `?v=…` (see geo/tiles3d_generator.py).
const TILESET_VERSION = 4
const TILESET_URL = `/api/v1/geo/opensky/3dtiles/tileset.json?v=${TILESET_VERSION}`

export function useMap3DTiles() {
  const mapStore = useMapStore()
  const tiles3dEnabled = ref(false)
  const tiles3dLoading = ref(false)

  let overlay: MapboxOverlay | null = null
  let pitchBefore: number | null = null
  let maxPitchBefore: number | null = null
  let rasterOpacityBefore: number | null = null

  // deck.gl Tile3DLayer + MapLibre rendering breaks at pitch >45° + zoom ≥17.
  // Cause: unknown (frustum is normal, selectedTiles populated, but draw call
  // produces transparent pixels). Until upstream fix, cap pitch while 3D is on.
  const MAX_PITCH_3D = 45

  // Per-mission tileset.json has lod1 as the leaf (lod0 was dropped backend-side
  // — see geo/tiles3d_generator.py). At this threshold:
  //   z14 (city): lod3 selected (SSE≈2)
  //   z18 (browse): lod1 selected (SSE≈91)
  //   z22 (close-up): lod1 selected (SSE huge but no further children to refine into)
  // loaders.gl default of 8 would force aggressive refinement and pre-fetch the
  // whole REPLACE chain on every visible mission at low zoom — 200 keeps the
  // city view at lod3 (≈4 MB per mission) and only escalates near ground.
  const MAX_SSE_3D = 200

  // OpenSky raster covers the same ground as the 3D mesh — when 3D is on,
  // dim it to reduce double-rendering and let the mesh dominate visually.
  const RASTER_OPACITY_WITH_3D = 0.35
  const OPENSKY_RASTER_LAYER_ID = 'opensky-latest-layer'

  // ---- Memory governor -------------------------------------------------
  // Each LOD GLB carries ~76 ODM texture chunks; decoded RGBA (4 B/px ×1.33
  // mipmaps — exactly what loaders.gl getMemoryUsageGLTF() reports into
  // tileset.gpuMemoryUsageInBytes) is ~1.7 GB per lod1 mission, ~424 MB lod2,
  // ~106 MB lod3. At pitch 45° over a contiguous 18-mission cluster the
  // traverser legitimately selects 9-13 GB worth of tiles → tab OOM. Selected
  // tiles are never evicted (TilesetCache only frees unselected), and the
  // library's own memoryAdjustedScreenSpaceError inflates only ×1.02 per tile
  // *add* — far too slow against the initial request volley. So we run our own
  // proportional controller on the live `tileset.memoryAdjustedScreenSpaceError`
  // field (the one the traverser actually reads — see PK/opensky-system.md):
  // SSE target = MAX_SSE × usage/budget, raised instantly under pressure,
  // relaxed gradually (damps lod2↔lod3 oscillation around the budget line).
  // Budget is DECODED bytes. deviceMemory is Chrome-only and capped at 8;
  // browsers without it get the conservative tier.
  const MEMORY_BUDGET_MB =
    typeof navigator !== 'undefined' && (navigator as any).deviceMemory >= 8 ? 2048 : 1024
  const SSE_INFLATION_CAP = 16 // never coarsen beyond ×16 (drops far missions entirely)

  let tilesetRef: any = null

  const _governMemory = () => {
    if (!tilesetRef) return
    const ratio = tilesetRef.gpuMemoryUsageInBytes / (1024 * 1024) / MEMORY_BUDGET_MB
    const target = MAX_SSE_3D * Math.min(Math.max(ratio, 1), SSE_INFLATION_CAP)
    const current = tilesetRef.memoryAdjustedScreenSpaceError || MAX_SSE_3D
    if (target > current) {
      // over budget: clamp selection NOW, before the next batch decodes
      tilesetRef.memoryAdjustedScreenSpaceError = target
    } else if (ratio < 0.5) {
      // clearly under budget (e.g. user left the heavy area and eviction ran):
      // snap straight back — a residual inflated SSE here can exceed the root
      // tileset's gate at far zooms and blank the whole layer (verified at z15)
      tilesetRef.memoryAdjustedScreenSpaceError = target
    } else {
      // hovering near the budget line: relax slowly to damp lod2↔lod3 churn
      tilesetRef.memoryAdjustedScreenSpaceError = current + (target - current) * 0.15
    }
  }

  // deck.gl spreads `loader.preload()`'s return value into `new Tileset3D(json, …)`,
  // which is the only point we can inject options BEFORE the first selectTiles
  // runs. Without this, the constructor uses the loaders.gl default (SSE=8),
  // schedules a doUpdate on next tick that selects lod0 for every visible
  // mission, and starts fetching 50–80 MB GLBs per mission *before* any
  // onTilesetLoad mutation can take effect. At z22 with 5 missions that
  // becomes 350+ MB and freezes the tab.
  const TunedTiles3DLoader = {
    ...Tiles3DLoader,
    async preload() {
      return {
        maximumScreenSpaceError: MAX_SSE_3D,
        // Decoded-bytes budget (see governor above). Doubles as the cache
        // eviction threshold: unselected tiles are freed once usage exceeds it.
        maximumMemoryUsage: MEMORY_BUDGET_MB,
        memoryCacheOverflow: 256,
        // Default is 64 → the entire first selection fires as one volley and
        // is fully decoded before any feedback can coarsen it. 6 in flight
        // lets the governor re-clamp selection between batches; queued
        // requests for de-selected tiles are simply never issued.
        maxRequests: 6,
      }
    },
  }

  const _buildLayer = () =>
    new Tile3DLayer({
      id: 'opensky-3d-tiles',
      data: TILESET_URL,
      loader: TunedTiles3DLoader as any,
      loadOptions: {
        '3d-tiles': {
          loadGLTF: true,
          decodeQuantizedPositions: true,
          // NOTE: Z-up axis hint is set in tileset.json `asset.gltfUpAxis`,
          // NOT here. loaders.gl reads it from the tileset, not loadOptions.
        },
        gltf: {
          loadBuffers: true,
          loadImages: true,
        },
        // Local draco worker — avoid CDN fetch from unpkg.com (CSP-blocked).
        // File copied from @loaders.gl/draco/dist/draco-worker.js into public/.
        draco: {
          workerUrl: '/draco/loaders-gl-draco-worker.js',
        },
      },
      pickable: false,
      onTilesetLoad: (tileset: any) => {
        tiles3dLoading.value = false
        tilesetRef = tileset
        // Debug handle (memory governor / LOD selection inspection):
        //   __opensky3d.gpuMemoryUsageInBytes, .memoryAdjustedScreenSpaceError,
        //   .selectedTiles.map(t => t.contentUrl)
        if (typeof window !== 'undefined') (window as any).__opensky3d = tileset
      },
      onTileLoad: () => {
        _governMemory()
        // Selective repaint only when a tile finishes loading.
        // NEVER call triggerRepaint() on every frame — that creates a 60fps
        // loop that burns ~100% CPU (lesson from previous Three.js impl).
        mapStore.mapInstance?.triggerRepaint()
      },
      onTileUnload: () => {
        _governMemory()
      },
      onTileError: (tile: any, message: string) => {
        console.error('[Tile3DLayer]', message, tile?.url || tile?.contentUrl)
      },
    })

  const toggle = () => {
    const map = mapStore.mapInstance
    if (!map) return

    tiles3dEnabled.value = !tiles3dEnabled.value

    if (tiles3dEnabled.value) {
      pitchBefore = map.getPitch()
      maxPitchBefore = map.getMaxPitch()
      tiles3dLoading.value = true

      // Dim the OpenSky orthomosaic underneath — it covers the same ground as
      // the 3D mesh, so full-opacity raster + mesh just doubles GPU work and
      // mutes the 3D look. Restored verbatim on toggle off.
      if (map.getLayer(OPENSKY_RASTER_LAYER_ID)) {
        rasterOpacityBefore = (map.getPaintProperty(OPENSKY_RASTER_LAYER_ID, 'raster-opacity') ?? 1) as number
        map.setPaintProperty(OPENSKY_RASTER_LAYER_ID, 'raster-opacity', RASTER_OPACITY_WITH_3D)
      }

      if (!overlay) {
        overlay = new MapboxOverlay({
          // interleaved: true → deck.gl shares MapLibre's depth buffer, so
          // mesh respects OSM occlusion AND lets the rendered geometry
          // appear at low/medium zooms with any pitch (with interleaved=false
          // mesh became invisible at pitch >40° at almost ALL zooms).
          interleaved: true,
          layers: [_buildLayer()],
        })
        map.addControl(overlay as any)
      } else {
        overlay.setProps({ layers: [_buildLayer()] })
      }

      // Re-run the governor on every settle — tile load/unload events alone
      // are not enough: with an inflated SSE and an empty selection no loads
      // ever fire, so nothing would relax the SSE back down.
      map.on('moveend', _governMemory)

      // Cap pitch while 3D is active (see MAX_PITCH_3D note above).
      map.setMaxPitch(MAX_PITCH_3D)
      if (map.getPitch() < 30) {
        map.easeTo({ pitch: MAX_PITCH_3D, duration: 800 })
      } else if (map.getPitch() > MAX_PITCH_3D) {
        map.easeTo({ pitch: MAX_PITCH_3D, duration: 400 })
      }
    } else {
      overlay?.setProps({ layers: [] })
      tiles3dLoading.value = false
      tilesetRef = null
      map.off('moveend', _governMemory)

      // Restore raster opacity that was active before 3D was enabled.
      if (rasterOpacityBefore !== null && map.getLayer(OPENSKY_RASTER_LAYER_ID)) {
        map.setPaintProperty(OPENSKY_RASTER_LAYER_ID, 'raster-opacity', rasterOpacityBefore)
      }
      rasterOpacityBefore = null

      // Restore maxPitch and pitch from before 3D was enabled.
      if (maxPitchBefore !== null) {
        map.setMaxPitch(maxPitchBefore)
        maxPitchBefore = null
      }
      const restorePitch = pitchBefore ?? 0
      pitchBefore = null
      if (map.getPitch() !== restorePitch) {
        map.easeTo({ pitch: restorePitch, duration: 800 })
      }
    }
  }

  const dispose = () => {
    const map = mapStore.mapInstance
    if (map) {
      map.off('moveend', _governMemory)
    }
    if (map && overlay) {
      try {
        map.removeControl(overlay as any)
      } catch {
        // Already removed
      }
      overlay = null
    }
    tilesetRef = null
    tiles3dEnabled.value = false
    tiles3dLoading.value = false
  }

  return {
    tiles3dEnabled: readonly(tiles3dEnabled),
    tiles3dLoading: readonly(tiles3dLoading),
    toggle,
    dispose,
  }
}
