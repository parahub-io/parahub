/**
 * ?device=<kind>:<id> deep links for MapView's entity panels.
 *
 * Serialisation: `deviceParam` reflects the currently open entity panel
 * (vehicle / IoT device / env station / condo / hub / gov+church POI) and is
 * folded into the /map query by useMapUrlSync's buildMapQuery, so the open
 * panel survives F5 and travels in shared links. Kinds:
 *   tracker | mesh | energy | env  — IoT devices (id = device/cell ULID)
 *   condo | hub | gov | church     — static place panels (id = entity ULID)
 *   veh                            — live transit vehicle (id = {ds}:{vid} uid)
 *
 * Restore: parseInitialQuery / reapplyQueryNavigation stash the raw param on
 * window._pendingDeviceRestore; restorePendingDevice() (called from map load
 * and onActivated) resolves it against the relevant layer's item list —
 * force-enabling toggled-off layers first (deep-link intent is "show me this",
 * same rule as the layer fitBounds helpers) — then opens the panel through the
 * shared clearEntityPanels flow and flies to the device with panel padding.
 *
 * Vehicles are realtime-only: restore enables the transit layer, waits for the
 * WS feed to deliver the uid (bbox-scoped, so the link's lat/lng viewport must
 * cover the vehicle), opens the panel and turns on follow mode — the camera
 * glides to each new WS position (1s, matching the icon animator) until the
 * user drags the map or closes the panel. The same follow toggle is exposed in
 * the vehicle panel for manually clicked vehicles.
 */
import { computed, ref, watch, onScopeDispose } from 'vue'
import type { Ref } from 'vue'
import { ensemblePlacement } from '~/composables/useMapDeviceEnsembles'

const VEHICLE_WAIT_MS = 90000
const LIST_WAIT_MS = 12000

export function useMapDeviceDeepLink(opts: {
  getMap: () => any
  animationEnabled: Ref<boolean>
  panels: {
    selectedVehicle: Ref<any>
    selectedIoTDevice: Ref<any>
    selectedEnvStation: Ref<any>
    selectedCondominium: Ref<any>
    selectedHub: Ref<any>
    selectedEstablishment: Ref<any>
    clearEntityPanels: () => void
  }
  iot: {
    trackerPositionsList: Ref<any[]>
    energyCellsList: Ref<any[]>
    envStationsList: Ref<any[]>
    energyCellsEnabled: Ref<boolean>
    envStationsEnabled: Ref<boolean>
    toggleEnergyCells: () => void
    toggleEnvStations: () => void
    showIoTLockOn: (lat: number, lon: number, offsetPx?: [number, number] | null) => void
    getPanelPadding: () => any
  }
  layers: {
    mesh: { ensureLoaded: (map: any) => Promise<any[]> }
    condo: { ensureLoaded: (map: any) => Promise<any[]> }
    hub: { ensureLoaded: (map: any) => Promise<any[]> }
    gov: { ensureLoaded: (map: any) => Promise<any[]> }
    church: { ensureLoaded: (map: any) => Promise<any[]> }
  }
  transit: {
    transitEnabled: Ref<boolean>
    enableLayerVisibility: (map: any) => void
  }
}) {
  const { getMap, animationEnabled, panels, iot, layers, transit } = opts
  const authStore = useAuthStore()
  const vehiclesWs = useTransitVehicles()
  const { t } = useI18n()

  // ======== map → URL ========

  const deviceParam = computed<string | null>(() => {
    if (panels.selectedVehicle.value?.uid) return `veh:${panels.selectedVehicle.value.uid}`
    const dev = panels.selectedIoTDevice.value
    if (dev?.device_id) {
      const kind = dev.deviceType === 'tracker' ? 'tracker'
        : dev.deviceType === 'mesh_router' ? 'mesh' : 'energy'
      return `${kind}:${dev.device_id}`
    }
    if (panels.selectedEnvStation.value?.id) return `env:${panels.selectedEnvStation.value.id}`
    if (panels.selectedCondominium.value?.id) return `condo:${panels.selectedCondominium.value.id}`
    if (panels.selectedHub.value?.id) return `hub:${panels.selectedHub.value.id}`
    const est = panels.selectedEstablishment.value
    if (est?.id) return `${est.kind === 'church' ? 'church' : 'gov'}:${est.id}`
    return null
  })

  // ======== URL → panel ========

  const flyToDevice = (lng: number, lat: number, targetZoom: number) => {
    const map = getMap()
    if (!map) return
    const zoom = Math.max(map.getZoom(), targetZoom)
    const padding = iot.getPanelPadding()
    if (animationEnabled.value !== false) {
      map.flyTo({ center: [lng, lat], zoom, essential: true, speed: 4.5, padding })
    } else {
      map.jumpTo({ center: [lng, lat], zoom, padding })
    }
  }

  /** Poll a list-backed lookup until it yields (layer data loads async on mount). */
  const waitForItem = async (get: () => any, timeoutMs = LIST_WAIT_MS): Promise<any | null> => {
    const started = Date.now()
    for (;;) {
      const item = get()
      if (item) return item
      if (Date.now() - started > timeoutMs) return null
      await new Promise((r) => setTimeout(r, 400))
    }
  }

  /**
   * Ensemble render placement of a static device: geo anchor + constant
   * screen-px fan-out (useMapDeviceEnsembles). The lock-on marker must mirror
   * both, or it lands on the device's raw coords while the icon renders fanned
   * out. Placements exist by the time the item shows up in its layer list —
   * every layer publishes its segment synchronously with setting the list.
   */
  const placementLockOn = (segment: string, id: string): { anchor: [number, number] | null; offset: [number, number] | null } => {
    const pl = ensemblePlacement(segment, id)
    if (!pl) return { anchor: null, offset: null }
    return { anchor: pl.anchor, offset: pl.offset[0] || pl.offset[1] ? pl.offset : null }
  }

  const restoreStationary = async (kind: string, id: string) => {
    const map = getMap()
    if (!map) return
    let item: any = null
    let open: ((item: any) => {
      lngLat: { lng: number; lat: number }
      zoom: number
      lockOn?: boolean
      lockOnAnchor?: [number, number] | null
      lockOnOffset?: [number, number] | null
    }) | null = null

    if (kind === 'tracker') {
      if (!authStore.isAuthenticated) return
      item = await waitForItem(() => iot.trackerPositionsList.value.find((t: any) => t.device_id === id))
      open = (t) => {
        panels.selectedIoTDevice.value = {
          deviceType: 'tracker', device_id: t.device_id, name: t.name || '',
          status: t.traccar_status || 'unknown',
          speed: t.speed ? `${Math.round(t.speed)} km/h` : '',
          firmware_role: '', hardware_profile: '', price: '',
          lngLat: { lng: t.longitude, lat: t.latitude }, last_update: t.last_update || null,
        }
        return { lngLat: { lng: t.longitude, lat: t.latitude }, zoom: 17, lockOn: true }
      }
    } else if (kind === 'mesh') {
      const list = await layers.mesh.ensureLoaded(map)
      item = list.find((p: any) => p.device_id === id)
      open = (p) => {
        const lk = placementLockOn('mesh', p.device_id)
        panels.selectedIoTDevice.value = {
          deviceType: 'mesh_router', device_id: p.device_id, name: p.name || '',
          status: p.status || 'offline', speed: '', firmware_role: '',
          hardware_profile: p.hardware_profile || 'unknown', price: '',
          owner_name: p.owner_name || '', owner_cri: p.owner_cri || '',
          lngLat: { lng: p.longitude, lat: p.latitude }, lockOnOffset: lk.offset, last_update: null,
        }
        return { lngLat: { lng: p.longitude, lat: p.latitude }, zoom: 17, lockOn: true, lockOnAnchor: lk.anchor, lockOnOffset: lk.offset }
      }
    } else if (kind === 'energy') {
      if (!iot.energyCellsEnabled.value) iot.toggleEnergyCells()
      item = await waitForItem(() => iot.energyCellsList.value.find((c: any) => c.id === id))
      open = (c) => {
        const lk = placementLockOn('energy', c.id)
        panels.selectedIoTDevice.value = {
          deviceType: 'energy_cell', device_id: c.id, name: c.name || '',
          status: c.status || 'unknown', speed: '', firmware_role: '',
          hardware_profile: '', price: c.current_price_eur || '',
          lngLat: { lng: c.longitude, lat: c.latitude }, lockOnOffset: lk.offset, last_update: null,
        }
        return { lngLat: { lng: c.longitude, lat: c.latitude }, zoom: 17, lockOn: true, lockOnAnchor: lk.anchor, lockOnOffset: lk.offset }
      }
    } else if (kind === 'env') {
      if (!iot.envStationsEnabled.value) iot.toggleEnvStations()
      item = await waitForItem(() => iot.envStationsList.value.find((s: any) => s.id === id))
      open = (s) => {
        const lk = placementLockOn('env', s.id)
        panels.selectedEnvStation.value = {
          id: s.id, name: s.name || '', source: s.source || '',
          latest: s.latest || {}, last_reading_at: s.last_reading_at || null,
          public_url: s.public_url || '',
          owner_name: s.owner_name || '', owner_cri: s.owner_cri || '',
          lngLat: { lng: s.longitude, lat: s.latitude }, lockOnOffset: lk.offset,
        }
        return { lngLat: { lng: s.longitude, lat: s.latitude }, zoom: 15, lockOn: true, lockOnAnchor: lk.anchor, lockOnOffset: lk.offset }
      }
    } else if (kind === 'condo') {
      const list = await layers.condo.ensureLoaded(map)
      item = list.find((c: any) => c.id === id)
      open = (c) => {
        panels.selectedCondominium.value = {
          id: c.id, name: c.name || '', slug: c.slug || '',
          full_address: c.full_address || '', fraction_count: c.fraction_count || 0,
          member_count: c.member_count || 0,
          lngLat: { lng: c.longitude, lat: c.latitude },
        }
        return { lngLat: { lng: c.longitude, lat: c.latitude }, zoom: 17 }
      }
    } else if (kind === 'hub') {
      const list = await layers.hub.ensureLoaded(map)
      item = list.find((h: any) => h.id === id)
      open = (h) => {
        panels.selectedHub.value = {
          id: h.id, name: h.name || '', slug: h.slug || '',
          hub_capacity: h.hub_capacity || 0,
          hub_accepted_sizes: (h.hub_accepted_sizes || []).join(', '),
          hub_storage_fee_daily: h.hub_storage_fee_daily || '0',
          opening_hours: h.opening_hours || '', phone: h.phone || '',
          lngLat: { lng: h.lon, lat: h.lat },
        }
        return { lngLat: { lng: h.lon, lat: h.lat }, zoom: 17 }
      }
    } else if (kind === 'gov' || kind === 'church') {
      const layer = kind === 'church' ? layers.church : layers.gov
      const list = await layer.ensureLoaded(map)
      item = list.find((p: any) => p.id === id)
      open = (p) => {
        panels.selectedEstablishment.value = {
          id: p.id, name: p.name || '', slug: p.slug || '', kind,
          category_label: kind === 'church' ? t('map.layers.churches') : t('map.layers.government'),
          municipality: p.municipality || '',
          lngLat: { lng: p.longitude, lat: p.latitude },
        }
        return { lngLat: { lng: p.longitude, lat: p.latitude }, zoom: 16 }
      }
    }

    if (!item || !open) return
    panels.clearEntityPanels()
    const target = open(item)
    if (target.lockOn) {
      const a = target.lockOnAnchor || [target.lngLat.lng, target.lngLat.lat]
      iot.showIoTLockOn(a[1], a[0], target.lockOnOffset || null)
    }
    flyToDevice(target.lngLat.lng, target.lngLat.lat, target.zoom)
  }

  // ======== Vehicles: restore + follow ========

  const vehicleFollowing = ref(false)

  let vehicleWaitUnsub: (() => void) | null = null
  const cancelVehicleWait = () => {
    if (vehicleWaitUnsub) { vehicleWaitUnsub(); vehicleWaitUnsub = null }
  }

  const findVehicle = (uid: string): any | null => {
    const fc = vehiclesWs.toGeoJSON()
    return (fc.features as any[]).find((f: any) => f.properties.uid === uid) || null
  }

  const followEase = (lng: number, lat: number) => {
    const map = getMap()
    if (!map) return
    map.easeTo({ center: [lng, lat], duration: 1000, padding: iot.getPanelPadding() })
  }

  const openVehicle = (f: any) => {
    const [lng, lat] = f.geometry.coordinates
    panels.clearEntityPanels()
    panels.selectedVehicle.value = { ...f.properties, lngLat: { lng, lat } }
    vehicleFollowing.value = true
    followEase(lng, lat)
  }

  const restoreVehicle = (uid: string) => {
    const map = getMap()
    if (!map) return
    transit.transitEnabled.value = true
    transit.enableLayerVisibility(map)
    cancelVehicleWait()
    const found = findVehicle(uid)
    if (found) { openVehicle(found); return }
    // The feed ticks ~30s; keep listening until the uid shows up in the
    // subscribed bbox or the wait times out (vehicle gone off-shift / far away).
    const started = Date.now()
    vehicleWaitUnsub = vehiclesWs.onUpdate(() => {
      const f = findVehicle(uid)
      if (f) {
        cancelVehicleWait()
        // A panel the user opened meanwhile wins over the stale deep link
        if (!panels.selectedVehicle.value) openVehicle(f)
      } else if (Date.now() - started > VEHICLE_WAIT_MS) {
        cancelVehicleWait()
        console.warn(`[MapDeepLink] vehicle ${uid} not seen in feed, giving up`)
      }
    })
  }

  // Live panel refresh + follow while a vehicle panel is open. Keyed on uid so
  // our own selectedVehicle updates don't re-trigger the watcher.
  let liveUnsub: (() => void) | null = null
  watch(() => panels.selectedVehicle.value?.uid, (uid) => {
    if (liveUnsub) { liveUnsub(); liveUnsub = null }
    if (!uid) { vehicleFollowing.value = false; return }
    liveUnsub = vehiclesWs.onUpdate(() => {
      const f = findVehicle(uid)
      if (!f) return
      const [lng, lat] = f.geometry.coordinates
      panels.selectedVehicle.value = { ...f.properties, lngLat: { lng, lat } }
      if (vehicleFollowing.value) followEase(lng, lat)
    })
  })

  const toggleVehicleFollow = () => {
    vehicleFollowing.value = !vehicleFollowing.value
    if (vehicleFollowing.value && panels.selectedVehicle.value?.lngLat) {
      const { lng, lat } = panels.selectedVehicle.value.lngLat
      followEase(lng, lat)
    }
  }

  const disableVehicleFollow = () => { vehicleFollowing.value = false }

  onScopeDispose(() => {
    cancelVehicleWait()
    if (liveUnsub) { liveUnsub(); liveUnsub = null }
  })

  // ======== pending consumer ========

  const restorePendingDevice = () => {
    if (typeof window === 'undefined') return
    const raw = (window as any)._pendingDeviceRestore
    if (!raw || !getMap()) return
    delete (window as any)._pendingDeviceRestore
    const sep = String(raw).indexOf(':')
    if (sep <= 0) return
    const kind = String(raw).slice(0, sep)
    const id = String(raw).slice(sep + 1)
    if (!id) return
    if (kind === 'veh') restoreVehicle(id)
    else void restoreStationary(kind, id)
  }

  return {
    deviceParam,
    restorePendingDevice,
    vehicleFollowing,
    toggleVehicleFollow,
    disableVehicleFollow,
  }
}
