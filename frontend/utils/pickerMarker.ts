/**
 * Design-system marker elements for location-picker minimaps (PK/design-system.md
 * § Minimap rule 5): the picker places the very marker the entity wears on /map,
 * drawn with the same shared canvas painters — never a stock MapLibre teardrop.
 */
import {
  DEVICE_HEX_SIZE, PLACE_SQUARE_SIZE, hexagonPath, roundedSquarePath,
  strokeMarkerOutline, glyphColorFor, drawLucideGlyph,
} from '~/composables/useMapToggleableLayer'
import { drawWifiGlyph } from '~/composables/useMapMeshLayer'

export type PickerGlyph = string[] | 'wifi' | null

function paintGlyph(ctx: CanvasRenderingContext2D, s: number, glyph: PickerGlyph, fill: string) {
  if (glyph === 'wifi') drawWifiGlyph(ctx, s)
  else if (glyph) drawLucideGlyph(ctx, s, glyph, 24, glyphColorFor(fill))
}

function markerCanvas(sizePx: number): [HTMLCanvasElement, CanvasRenderingContext2D, number] {
  const canvas = document.createElement('canvas')
  const s = sizePx * 2
  canvas.width = s
  canvas.height = s
  canvas.style.width = `${sizePx}px`
  canvas.style.height = `${sizePx}px`
  canvas.style.display = 'block'
  return [canvas, canvas.getContext('2d')!, s]
}

/** Flat-top device hexagon (fill = status, glyph = device type) as a Marker element. */
export function createDeviceHexElement(fill: string, glyph: PickerGlyph, sizePx = DEVICE_HEX_SIZE): HTMLElement {
  const [canvas, ctx, s] = markerCanvas(sizePx)
  hexagonPath(ctx, s)
  ctx.fillStyle = fill
  ctx.fill()
  strokeMarkerOutline(ctx)
  paintGlyph(ctx, s, glyph, fill)
  return canvas
}

/** Rounded square (static place: property, condo, hub) as a Marker element. */
export function createPlaceSquareElement(fill: string, glyph: PickerGlyph, sizePx = PLACE_SQUARE_SIZE): HTMLElement {
  const [canvas, ctx, s] = markerCanvas(sizePx)
  roundedSquarePath(ctx, s, 4)
  ctx.fillStyle = fill
  ctx.fill()
  strokeMarkerOutline(ctx)
  paintGlyph(ctx, s, glyph, fill)
  return canvas
}
