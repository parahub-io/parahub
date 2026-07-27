/**
 * Shared deck.gl overlay for live-transit rendering (comet trails + vehicles).
 *
 * One MapboxOverlay on deck's OWN canvas (interleaved: false). An interleaved
 * overlay shares MapLibre's GL pass, so per-frame transit animation would
 * force a full repaint of the entire vector basemap every frame (~8k draw
 * calls/s in a dense city) even when the viewport is idle. On the overlaid
 * canvas the animation touches only deck's small layers and MapLibre stays
 * idle between real camera/data changes.
 *
 * Consumers own named layer groups (useTransitTrails / useTransitVehiclesDeck)
 * and replace them independently; the overlay always composes groups in
 * GROUP_ORDER (later = drawn on top), so trails stay under the vehicle icons.
 */

const GROUP_ORDER = ['trails', 'vehicles'] as const
export type TransitDeckGroup = (typeof GROUP_ORDER)[number]

export interface TransitDeckOverlay {
  /** Load the deck chunk and attach the overlay control to the map (idempotent). */
  ensure(map: any): Promise<void>
  /** Replace one group's layers and re-flush the composed layer list. */
  setGroup(name: TransitDeckGroup, layers: any[]): void
  /** Merge top-level Deck props (onHover, onClick, ...) into the overlay. */
  setDeckProps(props: Record<string, any>): void
  /** Pick the topmost object at a screen point (null when nothing / not ready). */
  pick(opts: { x: number; y: number; radius?: number }): any | null
  ready(): boolean
}

export function createTransitDeckOverlay(): TransitDeckOverlay {
  let overlay: any = null
  let ensuring: Promise<void> | null = null
  const groups: Record<TransitDeckGroup, any[]> = { trails: [], vehicles: [] }
  let deckProps: Record<string, any> = {}

  function flush() {
    if (!overlay) return
    overlay.setProps({ ...deckProps, layers: GROUP_ORDER.flatMap((g) => groups[g]) })
  }

  return {
    async ensure(map: any) {
      if (overlay) return
      if (!ensuring) {
        ensuring = import('@deck.gl/mapbox').then((m) => {
          if (overlay) return
          overlay = new (m as any).MapboxOverlay({ interleaved: false, layers: [] })
          map.addControl(overlay)
          flush()
          // Debug handle (same pattern as window.__transitTrails)
          if (typeof window !== 'undefined') {
            ;(window as any).__transitDeck = {
              overlay: () => overlay,
              groups: () => ({ trails: groups.trails.length, vehicles: groups.vehicles.length }),
            }
          }
        }).catch((e) => {
          ensuring = null  // allow a retry on the next start
          throw e
        })
      }
      await ensuring
    },
    setGroup(name, layers) {
      groups[name] = layers
      flush()
    },
    setDeckProps(props) {
      deckProps = { ...deckProps, ...props }
      flush()
    },
    pick(opts) {
      try {
        return overlay?.pickObject(opts) ?? null
      } catch {
        return null  // deck not fully initialized yet
      }
    },
    ready: () => overlay != null,
  }
}
