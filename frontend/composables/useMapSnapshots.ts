/**
 * Shared MapLibre instance for generating static map snapshots.
 * Instead of creating N separate MapLibre WebGL contexts (one per tracker card),
 * we create a single hidden instance and sequentially capture canvas screenshots.
 *
 * Usage:
 *   const { capture } = useMapSnapshots()
 *   const dataUrl = await capture(lat, lon, 15)
 */

let mapInstance: any = null
let mapReady = false
let initPromise: Promise<void> | null = null
let captureQueue: Promise<void> = Promise.resolve()
const MAX_CACHE_SIZE = 50
const cache = new Map<string, string>()

function cacheKey(lat: number, lon: number, zoom: number, theme: string): string {
  return `${lat.toFixed(5)},${lon.toFixed(5)},${zoom},${theme}`
}

async function ensureMap(styleUrl: string, initialCenter?: [number, number]): Promise<any> {
  if (mapInstance && mapReady) return mapInstance
  if (initPromise) {
    await initPromise
    return mapInstance
  }

  initPromise = new Promise<void>(async (resolve) => {
    const mod = await import('maplibre-gl')
    const maplibregl = mod.default || mod
    await import('maplibre-gl/dist/maplibre-gl.css')

    // Hidden off-screen container
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:400px;height:248px;visibility:hidden;'
    document.body.appendChild(container)

    mapInstance = new maplibregl.Map({
      container,
      style: styleUrl,
      center: initialCenter || [0, 0],
      zoom: 15,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    })

    mapInstance.once('load', () => {
      mapReady = true
      resolve()
    })
  })

  await initPromise
  return mapInstance
}

export function useMapSnapshots() {
  const colorMode = useColorMode()

  const getStyleUrl = () =>
    colorMode.value === 'dark'
      ? '/map-styles/dark-liberty-parahub.json'
      : '/map-styles/liberty-parahub.json'

  /**
   * Capture a snapshot for given coordinates.
   * Queued so only one capture runs at a time (shared map instance).
   */
  async function capture(lat: number, lon: number, zoom: number = 15): Promise<string> {
    const theme = colorMode.value === 'dark' ? 'dark' : 'light'
    const key = cacheKey(lat, lon, zoom, theme)
    const cached = cache.get(key)
    if (cached) return cached

    return new Promise<string>((resolve) => {
      captureQueue = captureQueue.then(async () => {
        // Re-check after waiting in queue
        const cached2 = cache.get(key)
        if (cached2) { resolve(cached2); return }

        // Pass first capture's coords as initial center to avoid loading [0,0] tiles
        const map = await ensureMap(getStyleUrl(), [lon, lat])
        map.jumpTo({ center: [lon, lat], zoom })

        // After jumpTo, MapLibre needs a render frame to request new tiles.
        // Wait for that, then wait for idle (all tiles loaded).
        await new Promise<void>((done) => {
          const timeout = setTimeout(done, 5000)
          // Let MapLibre start a render cycle to discover which tiles it needs
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              const onIdle = () => { clearTimeout(timeout); done() }
              if (map.areTilesLoaded()) onIdle()
              else map.once('idle', onIdle)
            })
          })
        })

        const dataUrl = map.getCanvas().toDataURL('image/webp', 0.85)
        cache.set(key, dataUrl)
        // LRU eviction: Map iteration order = insertion order
        if (cache.size > MAX_CACHE_SIZE) {
          const oldest = cache.keys().next().value
          if (oldest !== undefined) cache.delete(oldest)
        }
        resolve(dataUrl)
      })
    })
  }

  /**
   * Invalidate cached snapshot (e.g. when tracker moves).
   */
  function invalidate(lat: number, lon: number, zoom: number = 15) {
    for (const theme of ['light', 'dark']) {
      cache.delete(cacheKey(lat, lon, zoom, theme))
    }
  }

  // Theme change: clear all snapshots, update map style
  watch(() => colorMode.value, () => {
    cache.clear()
    if (mapInstance && mapReady) {
      mapInstance.setStyle(getStyleUrl())
    }
  })

  return { capture, invalidate }
}
