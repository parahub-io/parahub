/**
 * Transit Vehicles Composable — WebSocket connection for real-time GTFS-RT vehicles.
 *
 * Public WS (no auth required). Bbox-based subscription — subscribe with map bounds,
 * server does GEOSEARCH on each daemon tick (~30s) and pushes vehicles in viewport.
 *
 * Usage:
 *   const { connect, disconnect, subscribeBbox, updateBbox, toGeoJSON, updateCounter } = useTransitVehicles()
 *   connect()
 *   subscribeBbox([west, south, east, north])
 */

import { ref } from 'vue'

interface VehicleData {
  v: string   // vehicle_id
  lat: number
  lon: number
  b: number | null   // bearing (null when the feed omits a real heading)
  s: number   // speed km/h
  r: string   // route_source_id
  rc: string  // route_color hex (no #), '' when the feed defines none
  rn: string  // route_name
  rt: number  // route_type (GTFS: 0=tram, 1=metro, 2=rail, 3=bus, 4=ferry, 7=funicular, 11=trolleybus)
  st: string  // status
  t: number   // timestamp (epoch)
  tid: string // trip_id
  sid: string // stop_source_id
  d: number   // direction_id
  hs: string  // headsign
  z: number   // zombie flag (1 = stationary)
  eta: number // ETA to next stop (seconds)
  ps: string  // place_slug
  rs: string  // route_slug
}

type Bbox = [number, number, number, number] // [west, south, east, north]

// Singleton state — shared across components (MapView is singleton anyway)
const vehicles = new Map<string, VehicleData>()
const isConnected = ref(false)
const updateCounter = ref(0)
const listeners = new Set<() => void>()

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let currentBbox: Bbox | null = null

function connect() {
  if (ws) return
  if (typeof window === 'undefined') return

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  ws = new WebSocket(`${protocol}//${host}/ws/v1/transit/`)

  ws.onopen = () => {
    isConnected.value = true
    reconnectAttempts = 0
    // Re-subscribe if we had a bbox
    if (currentBbox) {
      subscribeBbox(currentBbox)
    }
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'transit_update' && data.vehicles) {
        // Full replace — server sends vehicles in bbox
        vehicles.clear()
        for (const v of data.vehicles) {
          vehicles.set(v.v, v)
        }
        updateCounter.value++
        listeners.forEach(fn => fn())
      }
    } catch {}
  }

  ws.onclose = (event) => {
    isConnected.value = false
    ws = null
    if (event.code !== 1000) {
      const delay = Math.min(3000 * Math.pow(2, reconnectAttempts), 60000)
      reconnectAttempts++
      reconnectTimer = setTimeout(connect, delay)
    }
  }

  ws.onerror = () => {}
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close(1000)
    ws = null
    isConnected.value = false
  }
  vehicles.clear()
  currentBbox = null
  updateCounter.value++
}

function subscribeBbox(bbox: Bbox) {
  currentBbox = bbox
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'subscribe_vehicles', bbox }))
  }
}

function updateBbox(bbox: Bbox) {
  currentBbox = bbox
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'update_bbox', bbox }))
  }
}

function toGeoJSON(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = []
  for (const v of vehicles.values()) {
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
      properties: {
        vehicle_id: v.v,
        // bearing stays numeric for icon-rotate; has_bearing gates the chevron so
        // vehicles without a real heading don't all point north (b === null/absent).
        bearing: typeof v.b === 'number' ? v.b : 0,
        has_bearing: typeof v.b === 'number' ? 1 : 0,
        speed: v.s || 0,
        route_id: v.r || '',
        route_color: v.rc || '3b82f6',
        route_color_set: v.rc ? 1 : 0,
        route_name: v.rn || '',
        route_type: v.rt ?? 3,
        status: v.st || '',
        timestamp: v.t || 0,
        headsign: v.hs || '',
        direction_id: v.d,
        eta: v.eta || 0,
        zombie: v.z || 0,
        place_slug: v.ps || '',
        route_slug: v.rs || '',
      },
    })
  }
  return { type: 'FeatureCollection', features }
}

function onUpdate(fn: () => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

export function useTransitVehicles() {
  return {
    isConnected,
    updateCounter,
    connect,
    disconnect,
    subscribeBbox,
    updateBbox,
    toGeoJSON,
    onUpdate,
  }
}
