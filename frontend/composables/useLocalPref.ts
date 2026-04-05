import { ref, watch } from 'vue'
import type { Ref } from 'vue'

// Shared ref cache: all callers with the same key get the same reactive ref
const _cache = new Map<string, Ref<any>>()

/**
 * Reactive localStorage preference (SSR-safe).
 * Drop-in replacement for useCookie() for client-only UI preferences.
 * Returns a shared singleton ref per key — changes are reactive across all callers.
 */
export function useLocalPref<T>(key: string, defaultValue: T): Ref<T> {
  if (_cache.has(key)) return _cache.get(key) as Ref<T>

  const val = ref(defaultValue) as Ref<T>
  if (import.meta.client) {
    const stored = localStorage.getItem(key)
    if (stored !== null) {
      try { val.value = JSON.parse(stored) } catch { /* use default */ }
    } else {
      // One-time migration: cookie → localStorage
      const cookie = document.cookie.split(';').find(c => c.trim().startsWith(key + '='))
      if (cookie) {
        const raw = decodeURIComponent(cookie.split('=')[1]).replace(/^"|"$/g, '')
        try {
          const parsed = JSON.parse(raw)
          val.value = parsed
          localStorage.setItem(key, JSON.stringify(parsed))
        } catch {
          // Plain string value (not JSON)
          val.value = raw as T
          localStorage.setItem(key, JSON.stringify(raw))
        }
        document.cookie = `${key}=; max-age=0; path=/`
      }
    }
    watch(val, (v) => localStorage.setItem(key, JSON.stringify(v)))
  }
  _cache.set(key, val)
  return val
}
