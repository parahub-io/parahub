/**
 * Freshness state for an env-station reading: live/stale flag plus localized
 * absolute and relative timestamps, self-ticking every 30 s so the relative
 * time stays honest while the page stays open. Shared by the map panel and
 * the /iot station card. Stale mirrors the map feed's STALE_AFTER_SECONDS
 * (30 min).
 */
import { ref, computed, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useEnvFreshness(lastReadingAt: Ref<string | null | undefined>) {
  const { t, locale } = useI18n()

  const nowTick = ref(Date.now())
  let tickTimer: ReturnType<typeof setInterval> | null = null
  if (import.meta.client) {
    tickTimer = setInterval(() => { nowTick.value = Date.now() }, 30_000)
  }
  onUnmounted(() => {
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
  })

  const readingMs = computed(() => {
    const ts = lastReadingAt.value
    return ts ? new Date(ts).getTime() : 0
  })

  const isStale = computed(() => {
    if (!readingMs.value) return true
    return nowTick.value - readingMs.value > 30 * 60 * 1000
  })

  const absoluteTime = computed(() => {
    if (!readingMs.value) return ''
    try {
      return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' })
        .format(new Date(readingMs.value))
    } catch {
      return new Date(readingMs.value).toLocaleString()
    }
  })

  const relativeTime = computed(() => {
    if (!readingMs.value) return ''
    const secs = Math.round((nowTick.value - readingMs.value) / 1000)
    if (secs < 60) return t('map.env.just_now')
    if (secs < 3600) return t('map.env.min_ago', { n: Math.floor(secs / 60) })
    if (secs < 86400) return t('map.env.hours_ago', { n: Math.floor(secs / 3600) })
    return t('map.env.days_ago', { n: Math.floor(secs / 86400) })
  })

  return { isStale, absoluteTime, relativeTime }
}
