/**
 * Avatar panel state + map presence handlers.
 *
 * Extracted from MapView.vue: activeAvatarPanel, selectedOtherAvatar,
 * panelContentType, panelAvatarData, wrappedSetState/setSpeechBubble,
 * initializeMapPresence, handleAvatarClick, handleAvatarTypeChange.
 */

import { ref, computed } from 'vue'

export function useMapAvatarPanel(opts: {
  browseVisible: { value: boolean }
  browseWasOpen: { value: boolean }
  setSelectedFeature: (f: any) => void
  setClickedFeatures: (f: any[]) => void
  setClickCoordinates: (c: any) => void
}) {
  const authStore = useAuthStore()
  const mapStore = useMapStore()

  const mapPresenceEnabled = useLocalPref('map_presence_enabled', false)
  const currentAvatarType = useLocalPref('map_presence_avatar_type', 'p1')
  const currentSpeechBubble = ref('')
  const currentAvatarState = ref<'idle' | 'walking' | 'jumping' | 'sitting' | 'emoting'>('idle')
  const activeAvatarPanel = ref<'own' | 'other' | null>(null)
  const selectedOtherAvatar = ref<any>(null)

  const {
    connect: connectMapPresence,
    disconnect: disconnectMapPresence,
    updatePosition,
    setState,
    setSpeechBubble,
    nearbyAvatars,
    isConnected: isMapPresenceConnected,
  } = useMapPresence()

  // Wrapped setState to also update local state
  const wrappedSetState = (state: 'idle' | 'walking' | 'jumping' | 'sitting' | 'emoting') => {
    currentAvatarState.value = state
    setState(state)
  }
  const wrappedSetSpeechBubble = (text: string) => {
    currentSpeechBubble.value = text
    setSpeechBubble(text)
  }

  // Unified panel computed
  const panelContentType = computed(() => {
    if (activeAvatarPanel.value === 'own') return 'own_avatar'
    if (activeAvatarPanel.value === 'other') return 'other_avatar'
    return 'osm'
  })

  const panelAvatarData = computed(() => {
    if (activeAvatarPanel.value === 'own') {
      const profile = authStore.activeProfile
      return {
        isConnected: isMapPresenceConnected.value,
        setState: wrappedSetState,
        setSpeechBubble: wrappedSetSpeechBubble,
        currentAvatarType: currentAvatarType.value,
        currentAvatarState: currentAvatarState.value,
        profile_id: profile?.id,
        profile_name: profile?.display_name || profile?.local_name || '',
        profile_hna: profile?.hna || `${profile?.local_name}@parahub.io`,
      }
    }
    if (activeAvatarPanel.value === 'other') return selectedOtherAvatar.value
    return null
  })

  async function initializeMapPresence(map: any) {
    const connected = await connectMapPresence()
    if (!connected) return

    const waitForConnection = () => {
      return new Promise<void>((resolve) => {
        if (isMapPresenceConnected.value) { resolve(); return }
        const checkInterval = setInterval(() => {
          if (isMapPresenceConnected.value) { clearInterval(checkInterval); resolve() }
        }, 50)
        setTimeout(() => { clearInterval(checkInterval); resolve() }, 3000)
      })
    }

    await waitForConnection()
    const center = map.getCenter()
    const zoom = map.getZoom()
    updatePosition(center.lat, center.lng, zoom, currentAvatarType.value as any, 'idle', true)

    map.on('moveend', () => {
      const center = map.getCenter()
      const zoom = map.getZoom()
      updatePosition(center.lat, center.lng, zoom, currentAvatarType.value as any, currentAvatarState.value as any)
    })
  }

  function handleAvatarClick(avatar: any, isOwnArg?: boolean) {
    opts.setSelectedFeature(null)
    opts.setClickedFeatures([])
    opts.setClickCoordinates(null)
    if (opts.browseVisible.value) {
      opts.browseWasOpen.value = true
      opts.browseVisible.value = false
    }
    const isOwn = isOwnArg ?? (avatar.profile_id === authStore.activeProfile?.id)
    if (isOwn) {
      if (activeAvatarPanel.value === 'own') {
        activeAvatarPanel.value = null
      } else {
        activeAvatarPanel.value = 'own'
        selectedOtherAvatar.value = null
      }
    } else {
      activeAvatarPanel.value = 'other'
      selectedOtherAvatar.value = avatar
    }
  }

  function handleAvatarTypeChange(type: string) {
    currentAvatarType.value = type
    if (mapStore.mapInstance && isMapPresenceConnected.value) {
      const center = mapStore.mapInstance.getCenter()
      const zoom = mapStore.mapInstance.getZoom()
      updatePosition(center.lat, center.lng, zoom, type as any, 'idle')
    }
  }

  function clearAvatarPanel() {
    activeAvatarPanel.value = null
    selectedOtherAvatar.value = null
  }

  return {
    mapPresenceEnabled,
    currentAvatarType,
    currentSpeechBubble,
    currentAvatarState,
    activeAvatarPanel,
    selectedOtherAvatar,
    nearbyAvatars,
    isMapPresenceConnected,
    panelContentType,
    panelAvatarData,
    wrappedSetState,
    wrappedSetSpeechBubble,
    initializeMapPresence,
    handleAvatarClick,
    handleAvatarTypeChange,
    clearAvatarPanel,
    disconnectMapPresence,
  }
}
