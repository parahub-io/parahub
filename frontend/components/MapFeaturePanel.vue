<template>
  <transition :name="animationsEnabled ? 'slide' : ''" :duration="animationsEnabled ? 300 : 0">
    <div
      v-if="feature || contentType === 'own_avatar' || contentType === 'other_avatar' || contentType === 'vehicle' || contentType === 'iot_device' || contentType === 'condominium' || contentType === 'hub' || contentType === 'establishment'"
      class="fixed bottom-0 left-0 right-0 w-full md:absolute md:top-0 md:bottom-0 md:right-auto md:left-0 md:h-full md:w-96 bg-white dark:bg-neutral-900 shadow-2xl z-50 flex flex-col rounded-t-2xl md:rounded-none"
      :style="isMobile ? sheetStyle : {}"
    >
      <!-- Mobile drag handle -->
      <div
        class="md:hidden flex justify-center pt-3 pb-2 touch-none cursor-grab"
        v-bind="dragHandleAttrs"
      >
        <div class="w-12 h-1 bg-neutral-300 dark:bg-neutral-600 rounded-full"></div>
      </div>

      <!-- Header: yellow (list/OSM view) -->
      <div v-if="!osmHasSelectedEstablishment" class="bg-primary dark:bg-primary-700 text-neutral-900 px-4 pt-4 pb-2 rounded-t-2xl md:rounded-none flex-shrink-0">
        <div class="flex items-center justify-between">
          <!-- Back to browse button -->
          <button
            v-if="showBackToBrowse"
            @click="emit('back')"
            class="mr-2 p-2 hover:bg-primary-400 dark:hover:bg-primary-600 rounded-full transition flex items-center gap-1 text-sm"
          >
            <ArrowLeft :size="16" />
            <span class="hidden sm:inline">{{ t('map.panel.back_to_browse') }}</span>
          </button>
          <div class="flex-1">
            <h2 class="text-lg font-semibold">
              {{ panelTitle }}
            </h2>
            <p class="text-sm text-neutral-700 dark:text-neutral-800">{{ panelSubtitle }}</p>
          </div>
          <button
            @click="emit('close')"
            class="ml-2 p-2 hover:bg-primary-400 dark:hover:bg-primary-600 rounded-full transition"
            aria-label="Close panel"
          >
            <X :size="20" />
          </button>
        </div>
      </div>

      <!-- Header: establishment detail (nav bar outside scrollable area) -->
      <div v-else class="p-4 border-b border-neutral-200 dark:border-neutral-700 flex items-center justify-between flex-shrink-0">
        <button
          @click="osmPanelRef?.backToList()"
          class="flex items-center gap-2 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 text-sm font-medium transition"
        >
          <ChevronRight :size="16" class="rotate-180" />
          {{ $t('map.panel.back_to_list') }}
        </button>
        <button
          @click="emit('close')"
          class="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-full transition"
          aria-label="Close panel"
        >
          <X :size="20" class="text-neutral-600 dark:text-neutral-400" />
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto overflow-x-hidden pb-4 pt-0 space-y-0">

        <!-- Avatar panels -->
        <MapPanelAvatar
          v-if="contentType === 'own_avatar' || contentType === 'other_avatar'"
          ref="avatarPanelRef"
          :content-type="contentType"
          :avatar-data="avatarData"
          @close="emit('close')"
          @avatar-type-change="emit('avatar-type-change', $event)"
        />

        <!-- Transit Vehicle -->
        <MapPanelVehicle
          v-else-if="contentType === 'vehicle'"
          :vehicle-data="vehicleData"
        />

        <!-- IoT Device -->
        <MapPanelIotDevice
          v-else-if="contentType === 'iot_device'"
          :iot-device-data="iotDeviceData"
          :is-following="iotFollowing"
          @show-trail="emit('show-trail', $event)"
          @clear-trail="emit('clear-trail')"
          @trail-cursor="emit('trail-cursor', $event)"
          @recenter="emit('recenter-iot')"
        />

        <!-- Condominium -->
        <MapPanelCondominium
          v-else-if="contentType === 'condominium'"
          :condominium-data="condominiumData"
          @close="emit('close')"
        />

        <!-- Hub -->
        <MapPanelHub
          v-else-if="contentType === 'hub'"
          :hub-data="hubData"
          @close="emit('close')"
        />

        <!-- Internal POI (government, churches) -->
        <MapPanelEstablishmentPoi
          v-else-if="contentType === 'establishment'"
          :establishment-data="establishmentData"
          @close="emit('close')"
        />

        <!-- OSM features (buildings, roads, POIs, etc.) -->
        <MapPanelOsm
          v-else
          ref="osmPanelRef"
          :feature="feature"
          :click-coordinates="clickCoordinates"
          @close="emit('close')"
          @search-location="emit('search-location', $event)"
          @establishment-selected="emit('establishment-selected', $event)"
          @osm-resolved="emit('osm-resolved', $event)"
          @update:title="osmTitle = $event"
          @update:subtitle="osmSubtitle = $event"
          @update:has-selected-establishment="osmHasSelectedEstablishment = $event"
        />

      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, type PropType } from 'vue'
import { X, ChevronRight, ArrowLeft } from 'lucide-vue-next'
import { useBottomSheet } from '~/composables/useBottomSheet'
import type { AvatarType } from '~/composables/useMapPresence'
import MapPanelAvatar from '~/components/MapPanelAvatar.vue'
import MapPanelVehicle from '~/components/MapPanelVehicle.vue'
import MapPanelIotDevice from '~/components/MapPanelIotDevice.vue'
import MapPanelCondominium from '~/components/MapPanelCondominium.vue'
import MapPanelHub from '~/components/MapPanelHub.vue'
import MapPanelEstablishmentPoi from '~/components/MapPanelEstablishmentPoi.vue'
import MapPanelOsm from '~/components/MapPanelOsm.vue'

const { t } = useI18n()

const animationsEnabled = useLocalPref('animation_enabled', true)

// Mobile detection
const isMobile = ref(false)
let _resizeHandler: (() => void) | null = null
if (import.meta.client) {
  isMobile.value = window.innerWidth < 768
  _resizeHandler = () => { isMobile.value = window.innerWidth < 768 }
  window.addEventListener('resize', _resizeHandler)
}

const props = defineProps({
  feature: { type: Object, default: null },
  allFeatures: { type: Array, default: () => [] },
  clickCoordinates: { type: Object, default: null },
  contentType: {
    type: String as PropType<'osm' | 'own_avatar' | 'other_avatar' | 'vehicle' | 'iot_device' | 'condominium' | 'hub' | 'establishment'>,
    default: 'osm'
  },
  avatarData: { type: Object, default: null },
  vehicleData: { type: Object, default: null },
  iotDeviceData: { type: Object, default: null },
  iotFollowing: { type: Boolean, default: false },
  condominiumData: { type: Object, default: null },
  hubData: { type: Object, default: null },
  establishmentData: { type: Object, default: null },
  showBackToBrowse: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'back', 'feature-selected', 'search-location', 'establishment-selected', 'avatar-type-change', 'show-trail', 'clear-trail', 'trail-cursor', 'recenter-iot', 'osm-resolved'])

// Bottom sheet drag
const { sheetStyle, dragHandleAttrs, snapTo } = useBottomSheet({
  initialSnap: 'half',
  onDismiss: () => emit('close')
})

// Sub-panel refs
const avatarPanelRef = ref<InstanceType<typeof MapPanelAvatar> | null>(null)
const osmPanelRef = ref<InstanceType<typeof MapPanelOsm> | null>(null)

// OSM sub-panel state (received via emits)
const osmTitle = ref('')
const osmSubtitle = ref('')
const osmHasSelectedEstablishment = ref(false)

// ======== Panel title/subtitle ========

const panelTitle = computed(() => {
  if (props.contentType === 'own_avatar') {
    return props.avatarData?.profile_name || props.avatarData?.profile_hna?.split('@')[0] || t('map.presence.your_avatar')
  }
  if (props.contentType === 'other_avatar') {
    return props.avatarData?.profile_name || props.avatarData?.profile_hna?.split('@')[0] || 'User'
  }
  if (props.contentType === 'vehicle') {
    return props.vehicleData?.route_name || props.vehicleData?.route_id || t('map.transit.vehicle')
  }
  if (props.contentType === 'iot_device') {
    return props.iotDeviceData?.name || t('map.iot.device')
  }
  if (props.contentType === 'condominium') {
    return props.condominiumData?.name || t('map.condo.title')
  }
  if (props.contentType === 'hub') {
    return props.hubData?.name || t('map.hub.title')
  }
  if (props.contentType === 'establishment') {
    return props.establishmentData?.name || ''
  }
  // OSM — title comes from sub-panel
  return osmTitle.value
})

const panelSubtitle = computed(() => {
  if (props.contentType === 'own_avatar') return props.avatarData?.profile_hna || ''
  if (props.contentType === 'other_avatar') return props.avatarData?.profile_hna || ''
  if (props.contentType === 'vehicle') {
    const v = props.vehicleData
    if (!v) return ''
    const statusLabels: Record<string, string> = { 'IN_TRANSIT_TO': t('map.transit.in_transit'), 'STOPPED_AT': t('map.transit.stopped'), 'INCOMING_AT': t('map.transit.arriving') }
    return statusLabels[v.status] || ''
  }
  if (props.contentType === 'iot_device') {
    const d = props.iotDeviceData
    if (!d) return ''
    return d.deviceType === 'tracker' ? t('map.iot.type_tracker') : d.deviceType === 'mesh_router' ? t('map.iot.type_mesh_router') : t('map.iot.type_energy_cell')
  }
  if (props.contentType === 'condominium') return t('map.condo.subtitle')
  if (props.contentType === 'hub') return t('map.hub.subtitle')
  if (props.contentType === 'establishment') return props.establishmentData?.category_label || ''
  // OSM
  return osmSubtitle.value
})

// Expose focus method for parent (delegates to avatar sub-panel)
const focusSpeechInput = () => {
  avatarPanelRef.value?.focusSpeechInput()
}
defineExpose({ focusSpeechInput })

onUnmounted(() => {
  if (_resizeHandler) {
    window.removeEventListener('resize', _resizeHandler)
    _resizeHandler = null
  }
})
</script>

<style scoped>
/* Mobile: slide from bottom */
@media (max-width: 767px) {
  .slide-enter-active,
  .slide-leave-active {
    transition: transform 0.3s ease;
  }

  .slide-enter-from {
    transform: translateY(100%);
  }

  .slide-leave-to {
    transform: translateY(100%);
  }
}

/* Desktop: slide from left */
@media (min-width: 768px) {
  .slide-enter-active,
  .slide-leave-active {
    transition: transform 0.3s ease;
  }

  .slide-enter-from {
    transform: translateX(-100%);
  }

  .slide-leave-to {
    transform: translateX(-100%);
  }
}
</style>
