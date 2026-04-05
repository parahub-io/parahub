/**
 * useMap3DTiles — MapLibre Custom Layer for OGC 3D Tiles
 *
 * Uses 3d-tiles-renderer (NASA) with Three.js to render 3D mesh LODs
 * as a MapLibre GL custom layer. Shared WebGL context.
 */

const TILESET_URL = '/api/v1/geo/opensky/3dtiles/tileset.json'
const LAYER_ID = 'opensky-3d-tiles'

export function useMap3DTiles() {
  const mapStore = useMapStore()
  const tiles3dEnabled = ref(false)

  let tilesRenderer: any = null
  let threeRenderer: any = null
  let scene: any = null
  let camera: any = null
  let layerAdded = false
  let pitchBefore: number | null = null

  const toggle = () => {
    tiles3dEnabled.value = !tiles3dEnabled.value
    const map = mapStore.mapInstance
    if (!map) return

    if (tiles3dEnabled.value) {
      pitchBefore = map.getPitch()
      _addLayer(map)
      // Tilt map for 3D effect
      if (map.getPitch() < 30) {
        map.easeTo({ pitch: 60, duration: 800 })
      }
    } else {
      _removeLayer(map)
      // Restore pitch from before 3D was enabled
      const restorePitch = pitchBefore ?? 0
      pitchBefore = null
      if (map.getPitch() !== restorePitch) {
        map.easeTo({ pitch: restorePitch, duration: 800 })
      }
    }
  }

  const _addLayer = async (map: any) => {
    if (layerAdded) return

    const THREE = await import('three')
    const { TilesRenderer } = await import('3d-tiles-renderer')
    const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
    const { DRACOLoader } = await import('three/examples/jsm/loaders/DRACOLoader.js')

    tilesRenderer = new TilesRenderer(TILESET_URL)

    // Configure Draco decoder (already in public/draco/)
    const dracoLoader = new DRACOLoader()
    dracoLoader.setDecoderPath('/draco/')
    const gltfLoader = new GLTFLoader()
    gltfLoader.setDRACOLoader(dracoLoader)
    tilesRenderer.manager.addHandler(/\.glb$/, gltfLoader)

    map.addLayer({
      id: LAYER_ID,
      type: 'custom' as any,
      renderingMode: '3d',

      onAdd(_map: any, gl: WebGL2RenderingContext) {
        camera = new THREE.Camera()
        scene = new THREE.Scene()

        threeRenderer = new THREE.WebGLRenderer({
          canvas: _map.getCanvas(),
          context: gl,
          antialias: true,
        })
        threeRenderer.autoClear = false

        // Lighting
        scene.add(new THREE.AmbientLight(0xffffff, 0.6))
        const sun = new THREE.DirectionalLight(0xffffff, 0.8)
        sun.position.set(100, 200, 100)
        scene.add(sun)

        scene.add(tilesRenderer.group)
      },

      render(_gl: WebGL2RenderingContext, matrix: number[]) {
        if (!tilesRenderer || !camera || !threeRenderer) return

        // MapLibre passes the mercator MVP matrix as a 16-element array
        camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix)

        tilesRenderer.setCamera(camera)
        tilesRenderer.setResolutionFromRenderer(camera, threeRenderer)
        tilesRenderer.update()

        threeRenderer.resetState()
        threeRenderer.render(scene, camera)
        map.triggerRepaint()
      },

      onRemove() {
        if (tilesRenderer) {
          tilesRenderer.dispose()
          tilesRenderer = null
        }
        if (threeRenderer) {
          threeRenderer.dispose()
          threeRenderer = null
        }
        scene = null
        camera = null
      },
    })

    layerAdded = true
  }

  const _removeLayer = (map: any) => {
    if (!layerAdded) return
    try {
      if (map.getLayer(LAYER_ID)) {
        map.removeLayer(LAYER_ID)
      }
    } catch {
      // Layer might already be removed
    }
    layerAdded = false
  }

  const dispose = () => {
    const map = mapStore.mapInstance
    if (map) _removeLayer(map)
    tiles3dEnabled.value = false
  }

  return {
    tiles3dEnabled: readonly(tiles3dEnabled),
    toggle,
    dispose,
  }
}
