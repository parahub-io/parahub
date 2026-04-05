/**
 * Utility to determine if an establishment is currently open
 * based on OSM-style opening_hours JSON (e.g. {'mon-fri': '08:00-22:00', 'sat': 'closed'}).
 */

const DAY_INDEX: Record<string, number> = {
  sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6
}

function expandDayRange(key: string): number[] {
  const parts = key.toLowerCase().split(',').map(s => s.trim())
  const days: number[] = []
  for (const part of parts) {
    if (part.includes('-')) {
      const [startStr, endStr] = part.split('-').map(s => s.trim())
      const start = DAY_INDEX[startStr]
      const end = DAY_INDEX[endStr]
      if (start === undefined || end === undefined) continue
      let i = start
      while (true) {
        days.push(i)
        if (i === end) break
        i = (i + 1) % 7
      }
    } else {
      const idx = DAY_INDEX[part]
      if (idx !== undefined) days.push(idx)
    }
  }
  return days
}

/**
 * Check if an establishment is currently open.
 * @returns true = open, false = closed, null = can't determine (no hours or today not listed)
 */
export function checkIsOpen(openingHours: Record<string, string> | null | undefined): boolean | null {
  if (!openingHours || Object.keys(openingHours).length === 0) return null

  const now = new Date()
  const todayIdx = now.getDay() // 0=Sun
  const currentMinutes = now.getHours() * 60 + now.getMinutes()

  for (const [key, val] of Object.entries(openingHours)) {
    const dayIndices = expandDayRange(key)
    if (!dayIndices.includes(todayIdx)) continue
    if (val.toLowerCase() === 'closed') return false

    const ranges = val.split(',').map(s => s.trim())
    for (const range of ranges) {
      const match = range.match(/^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/)
      if (!match) continue
      const openMin = parseInt(match[1]) * 60 + parseInt(match[2])
      const closeMin = parseInt(match[3]) * 60 + parseInt(match[4])
      if (closeMin > openMin) {
        if (currentMinutes >= openMin && currentMinutes < closeMin) return true
      } else {
        // Wraps past midnight (e.g. 12:00-01:00)
        if (currentMinutes >= openMin || currentMinutes < closeMin) return true
      }
    }
    return false
  }
  return null // Today not listed in hours
}

/**
 * Reactive composable for a single establishment's opening hours.
 */
export function useOpeningHours(openingHours: Ref<Record<string, string> | null | undefined> | ComputedRef<Record<string, string> | null | undefined>) {
  const isOpen = computed(() => checkIsOpen(unref(openingHours)))
  return { isOpen }
}
