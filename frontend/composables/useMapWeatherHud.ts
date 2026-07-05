/**
 * Weather HUD orchestration over useMapWeather: visibility (hidden while any
 * panel is open), moveend-driven refresh, and the periodic re-poll timer.
 *
 * Weather changes ~every 15 min, so a timer — not a WS stream — is the right
 * cadence. refresh() no-ops unless the cell's reading has aged past FRESH_MS,
 * and the backend's 30-min grid cache absorbs repeat calls. The timer is
 * paused while the map is deactivated (KeepAlive) or the tab is hidden, per
 * the map-composable timer rule.
 */
import { computed } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { debounce } from '~/utils/debounce'

const WEATHER_REFRESH_MS = 15 * 60 * 1000

export function useMapWeatherHud(opts: {
  isActive: Ref<boolean>
  blocked: ComputedRef<boolean>
}) {
  const hud = useMapWeather()
  const weatherData = hud.weather
  const weatherHudVisible = computed(() => !!weatherData.value?.available && !opts.blocked.value)

  let map: any = null
  let timer: ReturnType<typeof setInterval> | null = null

  function startTimer() {
    stopTimer()
    timer = setInterval(() => {
      if (!map || !opts.isActive.value || document.visibilityState !== 'visible') return
      const c = map.getCenter()
      hud.refresh(c.lat, c.lng)
    }, WEATHER_REFRESH_MS)
  }

  function stopTimer() {
    if (timer) { clearInterval(timer); timer = null }
  }

  /** Hook the moveend-driven refresh onto the map and take an initial reading. */
  function attach(m: any) {
    map = m
    const refreshDebounced = debounce(() => {
      if (!map || !opts.isActive.value) return
      const c = map.getCenter()
      hud.refresh(c.lat, c.lng)
    }, 600)
    map.on('moveend', refreshDebounced)
    const c0 = map.getCenter()
    hud.refresh(c0.lat, c0.lng)
  }

  /** Refresh for wherever the kept-alive map now sits and restart the timer. */
  function resume() {
    if (map) {
      const c = map.getCenter()
      hud.refresh(c.lat, c.lng)
    }
    startTimer()
  }

  return { weatherData, weatherHudVisible, attach, resume, stopTimer }
}
