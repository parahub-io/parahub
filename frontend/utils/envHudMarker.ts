/**
 * Device HUD marker — instrument readout rendered as a DOM overlay centered
 * on a device's rendered map position (the true point plus any ensemble
 * offset; see useMapDeviceEnsembles.ts). The GL hexagon keeps hover / click /
 * lock-on; the HUD is pointer-events: none.
 *
 * Parts, all hanging off a 0×0 center-anchored marker root:
 *  - readout column: primary line + per-metric rows (mono uppercase, white
 *    halo), side/topSlot/nudge/rail placement from the ensemble layout;
 *  - compass bezel (wind data only): transparent ring around the hex itself,
 *    12 round-cap ticks with a long red north tick, and a rim-pointer dart at
 *    the wind's ORIGIN bearing (meteorological convention). The ring
 *    counter-rotates by the map bearing (`--map-bearing-neg` on the map
 *    container) so north stays geo-aligned; the pointer angle accumulates
 *    continuously so 350°→10° turns 20°, not −340°.
 *
 * Usage:
 *   const { el, update } = createDeviceHudElement()
 *   new maplibregl.Marker({ element: el, anchor: 'center', offset }).setLngLat(...).addTo(map)
 *   update(view)   // on every reading / layout change
 *
 * CSS is in MapView.vue (unscoped, global) — `.env-hud*`.
 */

const C = 28 // bezel center in the 56×56 viewBox
const RING_R = 15.5

function _bezelSvg(): string {
  let ticks = ''
  for (let a = 0; a < 360; a += 30) {
    const cardinal = a % 90 === 0
    const north = a === 0
    const outer = north ? 19.8 : cardinal ? 18.6 : 17.7
    const rad = (a * Math.PI) / 180
    const x1 = (C + RING_R * Math.sin(rad)).toFixed(2)
    const y1 = (C - RING_R * Math.cos(rad)).toFixed(2)
    const x2 = (C + outer * Math.sin(rad)).toFixed(2)
    const y2 = (C - outer * Math.cos(rad)).toFixed(2)
    ticks += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${north ? '#dc2626' : '#1f2937'}" stroke-width="${north ? 1.9 : cardinal ? 1.5 : 1.0}" opacity="${north ? 1 : cardinal ? 0.9 : 0.5}" stroke-linecap="round"/>`
  }
  // White halo under the ring keeps it legible on dark/satellite ground;
  // the rim-pointer dart's apex points inward at the station
  return `<svg class="env-hud-ring" viewBox="0 0 56 56">
    <circle cx="${C}" cy="${C}" r="${RING_R}" fill="none" stroke="rgba(255,255,255,0.95)" stroke-width="3.2"/>
    <circle cx="${C}" cy="${C}" r="${RING_R}" fill="none" stroke="#1f2937" stroke-width="1.1" opacity="0.85"/>
    ${ticks}
    <g class="env-hud-pointer">
      <polygon points="${C},${C - 13.6} ${C - 2.9},${C - 19.4} ${C},${C - 18} ${C + 2.9},${C - 19.4}" fill="#4E4EC8" stroke="#ffffff" stroke-width="0.9" stroke-linejoin="round"/>
    </g>
  </svg>`
}

export interface DeviceHudView {
  /** Headline value (temperature / AQI line / shared-wifi SSID) */
  primary: string
  /** Compact instrument rows: [label, value] */
  rows: Array<[string, string]>
  /** Wind origin bearing in degrees; null = no compass bezel */
  windDir: number | null
  stale: boolean
  /** Ensemble member (28 px hex → 56 px bezel + wider gaps) vs 22 px base */
  ensemble: boolean
  side: 'left' | 'right'
  topSlot: boolean
  nudge: 'up' | 'down' | null
  /** Right-rail override: absolute left px for the top slot's column */
  hudLeft: number | null
}

export function createDeviceHudElement(): {
  el: HTMLDivElement
  update: (view: DeviceHudView) => void
} {
  const el = document.createElement('div')
  el.className = 'env-hud'
  // All visual styling (incl. fade opacity) lives on the inner wrapper:
  // MapLibre manages inline styles on the marker root element itself.
  el.innerHTML = `<div class="env-hud-inner">
    ${_bezelSvg()}
    <div class="env-hud-col">
      <div class="env-hud-primary"></div>
      <div class="env-hud-rows"></div>
    </div>
  </div>`

  const ring = el.querySelector('.env-hud-ring') as SVGElement
  const pointer = el.querySelector('.env-hud-pointer') as SVGGElement
  const col = el.querySelector('.env-hud-col') as HTMLElement
  const primary = el.querySelector('.env-hud-primary') as HTMLElement
  const rows = el.querySelector('.env-hud-rows') as HTMLElement

  const update = (view: DeviceHudView) => {
    // classList (never className) — MapLibre owns its own classes on the root
    el.classList.toggle('env-hud-stale', view.stale)
    el.classList.toggle('env-hud-ens', view.ensemble)
    el.classList.toggle('env-hud-base', !view.ensemble)
    el.classList.toggle('env-hud-side-l', view.side === 'left')
    el.classList.toggle('env-hud-side-r', view.side !== 'left')
    el.classList.toggle('env-hud-ringed', view.windDir != null)
    el.classList.toggle('env-hud-topslot', view.topSlot)
    el.classList.toggle('env-hud-up', !view.topSlot && view.nudge === 'up')
    el.classList.toggle('env-hud-down', !view.topSlot && view.nudge === 'down')
    col.style.left = view.hudLeft != null ? `${view.hudLeft}px` : ''

    primary.textContent = view.primary
    primary.style.display = view.primary ? '' : 'none'
    rows.textContent = ''
    for (const [k, v] of view.rows) {
      const row = document.createElement('div')
      row.className = 'env-hud-row'
      const kEl = document.createElement('span')
      kEl.className = 'env-hud-k'
      kEl.textContent = k
      const vEl = document.createElement('span')
      vEl.className = 'env-hud-v'
      vEl.textContent = v
      row.append(kEl, vEl)
      rows.append(row)
    }

    if (view.windDir != null) {
      ring.style.display = ''
      // Accumulate a continuous angle so 350°→10° turns 20°, not −340°
      const target = ((Number(view.windDir) % 360) + 360) % 360
      const prev = parseFloat(pointer.dataset.angle || '')
      let angle = target
      if (!Number.isNaN(prev)) {
        const prevNorm = ((prev % 360) + 360) % 360
        let delta = target - prevNorm
        if (delta > 180) delta -= 360
        if (delta < -180) delta += 360
        angle = prev + delta
      }
      pointer.style.transform = `rotate(${angle}deg)`
      pointer.dataset.angle = String(angle)
    } else {
      ring.style.display = 'none'
    }
  }

  return { el, update }
}
