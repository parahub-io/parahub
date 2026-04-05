/**
 * Shared helper functions for transit pages (stop, route, index).
 */
export function useTransitHelpers() {
  /** Default route color by GTFS route_type when GTFS feed has no color */
  function defaultColorForType(type?: number): string {
    const map: Record<number, string> = {
      0: '00A550',   // Tram — green
      1: '0033A0',   // Metro — dark blue
      2: '6D6E71',   // Rail — gray
      3: 'EFF216',   // Bus — yellow
      4: '0077C8',   // Ferry — ocean blue
      7: '8B4513',   // Funicular — brown
      11: '00A550',  // Trolleybus — green
    }
    return map[type ?? 3] || 'EFF216'
  }

  function resolveColor(r: { route_color?: string; route_type?: number }): string {
    return r.route_color || defaultColorForType(r.route_type)
  }

  function routeBadgeStyle(r: { route_color?: string; route_type?: number }): string {
    const hex = resolveColor(r)
    const bg = `#${hex}`
    const color = textColorFor(hex)
    return `background-color: ${bg}; color: ${color}`
  }

  function textColorFor(hex?: string): string {
    if (!hex) return '#ffffff'
    const r = parseInt(hex.substring(0, 2), 16)
    const g = parseInt(hex.substring(2, 4), 16)
    const b = parseInt(hex.substring(4, 6), 16)
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance > 0.5 ? '#000000' : '#ffffff'
  }

  function routeTypeFallback(type: number): string {
    const map: Record<number, string> = { 0: 'Tram', 1: 'Metro', 2: 'Rail', 3: 'Bus', 4: 'Ferry', 7: 'Funicular', 11: 'Trolleybus', 200: 'Coach', 1100: 'Air', 1501: 'Minibus' }
    return map[type] || 'Bus'
  }

  function routeTypeIcon(type: number): string {
    const exact: Record<number, string> = {
      0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
      7: 'train', 11: 'trolleybus', 1100: 'airplane', 1501: 'bus-taxi',
    }
    if (exact[type]) return `/img/transit/${exact[type]}.svg`
    if (type >= 200 && type <= 299) return '/img/transit/2bus.svg'
    if (type >= 900 && type <= 999) return '/img/transit/tram.svg'
    if (type >= 100 && type <= 199) return '/img/transit/train.svg'
    if (type >= 400 && type <= 499) return '/img/transit/metro.svg'
    if (type >= 700 && type <= 799) return '/img/transit/bus.svg'
    if (type >= 1500 && type <= 1599) return '/img/transit/bus-taxi.svg'
    return '/img/transit/bus.svg'
  }

  function formatTime(timeStr: string): string {
    if (!timeStr) return ''
    return timeStr.substring(0, 5)
  }

  return { routeBadgeStyle, resolveColor, defaultColorForType, textColorFor, routeTypeFallback, routeTypeIcon, formatTime }
}
