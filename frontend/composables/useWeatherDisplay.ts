import { computed, type Ref } from 'vue'
import {
  Sun, Moon, CloudSun, CloudMoon, Cloud, Cloudy,
  CloudFog, CloudDrizzle, CloudRain, CloudSnow, CloudLightning,
} from 'lucide-vue-next'
import type { WeatherData } from '~/composables/useMapWeather'

// WMO weather code → icon + i18n label bucket. Shared by every weather surface
// (the floating map HUD, transit-stop chip, …) so the icon/condition mapping
// lives in exactly one place.
function classify(code: number, isDay: boolean) {
  if (code === 0 || code === 1) return { icon: isDay ? Sun : Moon, key: 'clear' }
  if (code === 2) return { icon: isDay ? CloudSun : CloudMoon, key: 'partly_cloudy' }
  if (code === 3) return { icon: Cloudy, key: 'overcast' }
  if (code === 45 || code === 48) return { icon: CloudFog, key: 'fog' }
  if (code >= 51 && code <= 57) return { icon: CloudDrizzle, key: 'drizzle' }
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return { icon: CloudRain, key: 'rain' }
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return { icon: CloudSnow, key: 'snow' }
  if (code >= 95) return { icon: CloudLightning, key: 'thunderstorm' }
  return { icon: Cloud, key: 'cloudy' }
}

const COMPASS = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw']

/**
 * Derive the display bits for a weather reading: condition icon + i18n word,
 * temperature label, the wind arrow's rotation (points where the wind blows TO),
 * the wind-speed label, and a one-line tooltip with the details the compact chip
 * drops. Strings come from the shared `map.weather.*` namespace (loaded globally,
 * so every page — map or transit — resolves them).
 */
export function useWeatherDisplay(data: Ref<WeatherData | null>) {
  const { t } = useI18n()

  const cls = computed(() => classify(data.value?.weather_code ?? -1, data.value?.is_day ?? true))
  const stateIcon = computed(() => cls.value.icon)
  const stateKey = computed(() => `map.weather.${cls.value.key}`)
  const conditionLabel = computed(() => t(stateKey.value))

  const tempLabel = computed(() =>
    data.value?.temperature != null ? `${Math.round(data.value.temperature)}°` : '–')

  const windUnit = computed(() => data.value?.units?.wind_speed || 'km/h')

  // Open-Meteo gives the direction the wind comes FROM; rotate +180° so the arrow
  // points where it's actually blowing TO. ArrowUp points north at 0°; CSS rotate
  // is clockwise = compass-aligned. (from 0/N → 180° → points S, etc.)
  const windStyle = computed(() => {
    const from = data.value?.wind_direction ?? 0
    return { transform: `rotate(${(from + 180) % 360}deg)` }
  })

  const windLabel = computed(() =>
    data.value?.wind_speed != null ? `${Math.round(data.value.wind_speed)} ${windUnit.value}` : '')

  // Tooltip carries everything a compact chip drops: condition word, feels-like,
  // which way the wind comes from, and gusts.
  const detailTitle = computed(() => {
    const d = data.value
    if (!d) return ''
    const parts: string[] = [t(stateKey.value)]
    if (d.apparent_temperature != null) {
      parts.push(`${t('map.weather.feels_like')} ${Math.round(d.apparent_temperature)}°`)
    }
    if (d.wind_direction != null) {
      const dir = t(`map.weather.compass.${COMPASS[Math.round(d.wind_direction / 45) % 8]}`)
      parts.push(t('map.weather.wind_from', { dir }))
    }
    if (d.wind_gusts != null) {
      parts.push(`${t('map.weather.gusts')} ${Math.round(d.wind_gusts)} ${windUnit.value}`)
    }
    return parts.join(' · ')
  })

  return { stateIcon, stateKey, conditionLabel, tempLabel, windUnit, windStyle, windLabel, detailTitle }
}
