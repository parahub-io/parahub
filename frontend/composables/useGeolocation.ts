import { ref, onMounted, onUnmounted } from 'vue'

export interface GeolocationPosition {
  lat: number
  lng: number
  accuracy: number
  timestamp: number
}

export const useGeolocation = () => {
  const location = ref<GeolocationPosition | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  const permissionDenied = ref(false)

  let watchId: number | null = null

  const updateLocation = (position: GeolocationPosition) => {
    location.value = position

    // Update map store if available
    const mapStore = useMapStore()
    if (mapStore) {
      mapStore.updateUserLocation([position.lng, position.lat])
    }
  }

  const handleSuccess = (pos: GeolocationPosition) => {
    loading.value = false
    error.value = null
    permissionDenied.value = false

    updateLocation({
      lat: pos.coords.latitude,
      lng: pos.coords.longitude,
      accuracy: pos.coords.accuracy,
      timestamp: pos.timestamp
    })
  }

  const handleError = (err: GeolocationPositionError) => {
    loading.value = false

    switch (err.code) {
      case err.PERMISSION_DENIED:
        error.value = 'Location permission denied'
        permissionDenied.value = true
        break
      case err.POSITION_UNAVAILABLE:
        error.value = 'Location unavailable'
        break
      case err.TIMEOUT:
        error.value = 'Location request timeout'
        break
      default:
        error.value = 'Unknown geolocation error'
    }
  }

  const startWatching = () => {
    if (!process.client) return
    if (!navigator.geolocation) {
      error.value = 'Geolocation not supported'
      return
    }

    loading.value = true

    // Watch position with high accuracy
    watchId = navigator.geolocation.watchPosition(
      handleSuccess,
      handleError,
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 5000
      }
    )
  }

  const stopWatching = () => {
    if (watchId !== null) {
      navigator.geolocation.clearWatch(watchId)
      watchId = null
    }
  }

  const requestOnce = () => {
    if (!process.client) return
    if (!navigator.geolocation) {
      error.value = 'Geolocation not supported'
      return
    }

    loading.value = true

    navigator.geolocation.getCurrentPosition(
      handleSuccess,
      handleError,
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 5000
      }
    )
  }

  onMounted(() => {
    startWatching()
  })

  onUnmounted(() => {
    stopWatching()
  })

  return {
    location,
    error,
    loading,
    permissionDenied,
    startWatching,
    stopWatching,
    requestOnce
  }
}
