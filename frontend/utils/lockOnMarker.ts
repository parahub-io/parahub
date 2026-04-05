/**
 * Lock-on bracket marker — reusable factory for the animated targeting brackets
 * shown on hover/click over map features (search results, IoT devices, routing waypoints).
 *
 * Usage:
 *   import { createLockOnElement } from '~/utils/lockOnMarker'
 *   const el = createLockOnElement()
 *   new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([lon, lat]).addTo(map)
 *
 * CSS is in MapRoutingPanel.vue (unscoped, global).
 */

export function createLockOnElement(options?: { iconUrl?: string, clickable?: boolean, noDot?: boolean }): HTMLDivElement {
  const el = document.createElement('div')
  el.className = 'geocode-preview-marker'
  if (options?.clickable) {
    el.style.pointerEvents = 'auto'
    el.style.cursor = 'pointer'
  }
  // Flat-top hexagon (honeycomb cell) — regular hex inscribed in 100×100 viewBox
  const hex = '<svg viewBox="0 0 100 100" style="width:100%;height:100%"><polygon points="27,9 73,9 97,50 73,91 27,91 3,50" fill="none" stroke="currentColor" stroke-width="5"/></svg>'
  const center = options?.iconUrl
    ? `<img src="${options.iconUrl}" alt="" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:18px;height:18px;object-fit:contain;z-index:4;filter:drop-shadow(0 1px 3px rgba(0,0,0,0.4))">`
    : options?.noDot ? '' : '<div class="geocode-preview-dot"></div>'
  el.innerHTML = `<div class="geocode-preview-container">
    <div class="geocode-preview-bracket geocode-preview-b1">${hex}</div>
    ${center}
  </div>`
  return el
}

/**
 * Flash crosshair lines from a point to near-edges of the map container.
 * Fires at the end of lock-in animation (~450ms), fades out in 200ms.
 */
export function flashCrosshair(mapContainer: HTMLElement, screenX: number, screenY: number) {
  const EDGE_PAD = 0     // lines go to screen edge
  const GAP = 100        // px gap from target center (lines start here)
  const W = mapContainer.clientWidth
  const H = mapContainer.clientHeight

  const lines: HTMLDivElement[] = []

  const makeLine = (css: string) => {
    const el = document.createElement('div')
    el.className = 'lockon-crosshair'
    el.style.cssText = css
    mapContainer.appendChild(el)
    lines.push(el)
  }

  // Top line: from GAP above center up to EDGE_PAD from top
  const topStart = screenY - GAP
  if (topStart > EDGE_PAD + 20) {
    makeLine(`left:${screenX}px;top:${EDGE_PAD}px;width:1px;height:${topStart - EDGE_PAD}px`)
  }
  // Bottom line: from GAP below center down to EDGE_PAD from bottom
  const botStart = screenY + GAP
  if (botStart < H - EDGE_PAD - 20) {
    makeLine(`left:${screenX}px;top:${botStart}px;width:1px;height:${H - EDGE_PAD - botStart}px`)
  }
  // Left line: from GAP left of center to EDGE_PAD from left
  const leftStart = screenX - GAP
  if (leftStart > EDGE_PAD + 20) {
    makeLine(`left:${EDGE_PAD}px;top:${screenY}px;width:${leftStart - EDGE_PAD}px;height:1px`)
  }
  // Right line: from GAP right of center to EDGE_PAD from right
  const rightStart = screenX + GAP
  if (rightStart < W - EDGE_PAD - 20) {
    makeLine(`left:${rightStart}px;top:${screenY}px;width:${W - EDGE_PAD - rightStart}px;height:1px`)
  }

  // Trigger fade-out after a brief flash
  requestAnimationFrame(() => {
    lines.forEach(el => el.classList.add('lockon-crosshair-fade'))
  })

  // Remove from DOM after fade completes
  setTimeout(() => {
    lines.forEach(el => el.remove())
  }, 1200)
}
