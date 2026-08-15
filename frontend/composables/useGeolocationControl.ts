/**
 * Custom MapLibre geolocation control with long-press stop, click recenter,
 * watchPosition with a course-aware self marker.
 *
 * Marker = avatar-class circle per the map-marker grammar (hexes are devices,
 * squares are places — people are circles): indigo dot with the 1px dark rest
 * stroke, an indigo course pointer at the rim while moving (GPS heading, same
 * cue as moving tracker hexes), and an accuracy disc that reflects the real
 * fix radius instead of a decorative pulse.
 */

// Same 3 km/h moving cut as tracker hexes (PK/design-system.md § Map Markers)
const MOVING_SPEED_MS = 3 / 3.6
// The accuracy disc renders only when the fix is coarse enough to matter on
// screen: worse than 30 m AND wider than the dot at the current zoom.
const ACCURACY_MIN_M = 30
const ACCURACY_MIN_PX = 16

export function createGeolocationControl(
  mapStore: ReturnType<typeof useMapStore>,
  animationEnabled: { value: boolean },
  t: (key: string) => string
) {
  return class GeolocationControl {
    _map: any
    _container: any
    _button: any
    _isTracking: boolean = false
    _watchId: number | null = null
    _userMarker: any = null
    _isFirstPosition: boolean = true
    _accuracyEl: HTMLElement | null = null
    _lastFix: { lng: number; lat: number; accuracy: number } | null = null
    _onZoom: (() => void) | null = null

    onAdd(map: any) {
      this._map = map
      this._container = document.createElement('div')
      this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group'

      this._button = document.createElement('button')
      this._button.className = 'maplibregl-ctrl-geolocate'
      this._button.type = 'button'
      this._button.title = t('map.geolocate.find')
      // lucide `locate-fixed` — standard "my location" crosshair glyph
      this._button.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="2" x2="5" y1="12" y2="12"></line>
          <line x1="19" x2="22" y1="12" y2="12"></line>
          <line x1="12" x2="12" y1="2" y2="5"></line>
          <line x1="12" x2="12" y1="19" y2="22"></line>
          <circle cx="12" cy="12" r="7"></circle>
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
      this._removeMarker()
      this._container.parentNode?.removeChild(this._container)
      this._map = undefined
    }

    _removeMarker() {
      if (this._onZoom && this._map) {
        this._map.off('zoom', this._onZoom)
      }
      this._onZoom = null
      this._accuracyEl = null
      this._lastFix = null
      if (this._userMarker) {
        this._userMarker.remove()
        this._userMarker = null
      }
    }

    /** Size the accuracy disc to the fix radius in screen pixels at the
     *  current zoom; hide it while the fix is good (or the disc would sit
     *  under the dot). */
    _resizeAccuracy() {
      if (!this._accuracyEl || !this._lastFix || !this._map) return
      const { lng, lat, accuracy } = this._lastFix
      let radiusPx = 0
      if (accuracy > ACCURACY_MIN_M) {
        const metersPerDegLng = 111320 * Math.cos(lat * Math.PI / 180)
        if (metersPerDegLng > 1) {
          const p1 = this._map.project([lng, lat])
          const p2 = this._map.project([lng + accuracy / metersPerDegLng, lat])
          radiusPx = Math.hypot(p2.x - p1.x, p2.y - p1.y)
        }
      }
      if (radiusPx > ACCURACY_MIN_PX) {
        this._accuracyEl.style.width = `${radiusPx * 2}px`
        this._accuracyEl.style.height = `${radiusPx * 2}px`
        this._accuracyEl.style.display = ''
      } else {
        this._accuracyEl.style.display = 'none'
      }
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
      this._button.title = t('map.geolocate.active')

      this._watchId = navigator.geolocation.watchPosition(
        async (position) => {
          const lng = position.coords.longitude
          const lat = position.coords.latitude

          // Create or update user marker
          if (!this._userMarker) {
            const el = document.createElement('div')
            el.className = 'user-location-marker'
            el.innerHTML = `
              <div class="user-marker-accuracy"></div>
              <div class="user-marker-heading"></div>
              <div class="user-marker-dot"></div>
            `
            this._accuracyEl = el.querySelector('.user-marker-accuracy')

            const maplibreModule = await import('maplibre-gl')
            const maplibregl = maplibreModule.default || maplibreModule

            this._userMarker = new maplibregl.Marker({
              element: el,
              anchor: 'center',
              // Course pointer rotates against map north; the marker itself
              // stays a screen-space billboard
              rotationAlignment: 'map',
              pitchAlignment: 'viewport'
            })
              .setLngLat([lng, lat])
              .addTo(this._map)

            this._onZoom = () => this._resizeAccuracy()
            this._map.on('zoom', this._onZoom)
          } else {
            this._userMarker.setLngLat([lng, lat])
          }

          // Course pointer: GPS heading is only meaningful while moving
          const speed = position.coords.speed
          const heading = position.coords.heading
          const moving = speed != null && speed >= MOVING_SPEED_MS
            && heading != null && Number.isFinite(heading)
          this._userMarker.getElement().classList.toggle('user-marker-moving', moving)
          if (moving && heading != null) {
            this._userMarker.setRotation(heading)
          }

          this._lastFix = { lng, lat, accuracy: position.coords.accuracy }
          this._resizeAccuracy()

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
      this._removeMarker()
      this._isTracking = false
      this._button.classList.remove('maplibregl-ctrl-geolocate-active')
      this._button.title = t('map.geolocate.find')
    }
  }
}
