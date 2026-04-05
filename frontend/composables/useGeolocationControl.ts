/**
 * Custom MapLibre geolocation control with long-press stop, click recenter,
 * watchPosition with pulsing marker.
 *
 * Extracted from MapView.vue lines 2067-2264.
 */

export function createGeolocationControl(
  mapStore: ReturnType<typeof useMapStore>,
  animationEnabled: { value: boolean }
) {
  return class GeolocationControl {
    _map: any
    _container: any
    _button: any
    _isTracking: boolean = false
    _watchId: number | null = null
    _userMarker: any = null
    _isFirstPosition: boolean = true

    onAdd(map: any) {
      this._map = map
      this._container = document.createElement('div')
      this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group'

      this._button = document.createElement('button')
      this._button.className = 'maplibregl-ctrl-geolocate'
      this._button.type = 'button'
      this._button.title = 'Track my location'
      this._button.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>
      `

      // Setup click and long press handlers
      let pressTimer: any = null
      let longPressTriggered = false

      const startPress = () => {
        longPressTriggered = false
        pressTimer = setTimeout(() => {
          // Long press detected - stop tracking
          longPressTriggered = true
          if (this._isTracking) {
            this._stopTracking()
          }
        }, 500)
      }

      const cancelPress = () => {
        clearTimeout(pressTimer)
      }

      // Mouse events
      this._button.addEventListener('mousedown', startPress)
      this._button.addEventListener('mouseup', cancelPress)
      this._button.addEventListener('mouseleave', cancelPress)

      // Touch events for mobile
      this._button.addEventListener('touchstart', startPress)
      this._button.addEventListener('touchend', cancelPress)
      this._button.addEventListener('touchcancel', cancelPress)

      this._button.addEventListener('click', (e: Event) => {
        if (longPressTriggered) {
          e.preventDefault()
          return
        }
        this._toggleTracking()
      })

      this._container.appendChild(this._button)
      return this._container
    }

    onRemove() {
      if (this._watchId !== null) {
        navigator.geolocation.clearWatch(this._watchId)
        this._watchId = null
      }
      if (this._userMarker) {
        this._userMarker.remove()
        this._userMarker = null
      }
      this._container.parentNode?.removeChild(this._container)
      this._map = undefined
    }

    _toggleTracking() {
      if (this._isTracking) {
        // If already tracking, recenter on current position instead of stopping
        this._recenterOnUser()
      } else {
        this._startTracking()
      }
    }

    _recenterOnUser() {
      const userLocation = mapStore.userLocation
      if (!userLocation || !this._map) return

      if (animationEnabled.value) {
        this._map.flyTo({
          center: userLocation,
          zoom: Math.max(this._map.getZoom(), 15),
          essential: true,
          speed: 4.5
        })
      } else {
        this._map.jumpTo({
          center: userLocation,
          zoom: Math.max(this._map.getZoom(), 15)
        })
      }
    }

    async _startTracking() {
      if (!navigator.geolocation) return

      this._isTracking = true
      this._isFirstPosition = true
      this._button.classList.add('maplibregl-ctrl-geolocate-active')
      this._button.title = 'Click to recenter, long press to stop'

      this._watchId = navigator.geolocation.watchPosition(
        async (position) => {
          const lng = position.coords.longitude
          const lat = position.coords.latitude

          // Create or update user marker
          if (!this._userMarker) {
            const el = document.createElement('div')
            el.className = 'user-location-marker'
            el.innerHTML = `
              <div class="user-marker-dot"></div>
              <div class="user-marker-pulse"></div>
            `

            const maplibreModule = await import('maplibre-gl')
            const maplibregl = maplibreModule.default || maplibreModule

            this._userMarker = new maplibregl.Marker({
              element: el,
              anchor: 'center'
            })
              .setLngLat([lng, lat])
              .addTo(this._map)
          } else {
            this._userMarker.setLngLat([lng, lat])
          }

          // Update map store
          mapStore.updateUserLocation([lng, lat])

          // Center map on user location ONLY on first position
          if (this._isFirstPosition && this._map) {
            if (animationEnabled.value) {
              this._map.flyTo({
                center: [lng, lat],
                zoom: Math.max(this._map.getZoom(), 15),
                essential: true,
                speed: 4.5
              })
            } else {
              this._map.jumpTo({
                center: [lng, lat],
                zoom: Math.max(this._map.getZoom(), 15)
              })
            }
            this._isFirstPosition = false
          }
        },
        (error) => {
          console.error('[GeolocationControl] Error:', error)
          this._button.classList.add('maplibregl-ctrl-geolocate-error')
          setTimeout(() => {
            this._button.classList.remove('maplibregl-ctrl-geolocate-error')
          }, 3000)
          this._stopTracking()
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 5000
        }
      )
    }

    _stopTracking() {
      if (this._watchId !== null) {
        navigator.geolocation.clearWatch(this._watchId)
        this._watchId = null
      }
      if (this._userMarker) {
        this._userMarker.remove()
        this._userMarker = null
      }
      this._isTracking = false
      this._button.classList.remove('maplibregl-ctrl-geolocate-active')
      this._button.title = 'Track my location'
    }
  }
}
