<template>
  <div>
    <Head>
      <Title>{{ $t('iot.hub_title') }} - Parahub</Title>
      <Meta name="description" content="Manage your devices, homes, and smart home integrations" />
    </Head>

    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <PageHeader
        :title="$t('iot.hub_title')"
        :create-label="createLabel"
        @create="onCreate"
      />

      <UiTabs v-model="activeTab" :tabs="tabs" class="mb-6" />

      <!-- ═══ Trackers tab: GPS trackers ═══ -->
      <div v-if="activeTab === 'trackers'" class="space-y-4">
        <div v-if="trackerDevices.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <IoTDeviceCard
            v-for="device in trackerDevices" :key="device.id"
            :device="device"
            :property-id="device.property_id"
            :property-name="propertyName(device.property_id)"
            @delete="handleDeleteDevice"
            @refresh="loadAll"
          />
        </div>

        <div v-else-if="!iotStore.loading"
             class="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <p>{{ $t('iot.no_devices_type') }}</p>
          <p class="text-sm mt-1">{{ $t('iot.no_devices_hint') }}</p>
        </div>
      </div>

      <!-- ═══ Network tab: mesh routers + gateways ═══ -->
      <div v-else-if="activeTab === 'network'" class="space-y-4">
        <div v-if="networkDevices.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <IoTDeviceCard
            v-for="device in networkDevices" :key="device.id"
            :device="device"
            :property-id="device.property_id"
            :property-name="propertyName(device.property_id)"
            @delete="handleDeleteDevice"
            @refresh="loadAll"
          />
        </div>

        <div v-else-if="!iotStore.loading"
             class="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <img src="/images/para/building.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <p>{{ $t('iot.no_devices_type') }}</p>
          <p class="text-sm mt-1">{{ $t('iot.no_devices_hint') }}</p>
        </div>

        <!-- Claim a pre-provisioned router by its sticker MAC -->
        <button
          type="button"
          class="w-full text-left flex items-center gap-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-primary transition-colors group"
          @click="showClaimModal = true"
        >
          <KeyRound class="w-5 h-5 text-primary flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('iot.claim_entry_title') }}</span>
            <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
              {{ $t('iot.claim_entry_desc') }}
            </p>
          </div>
          <ChevronRight class="w-4 h-4 text-neutral-400 group-hover:text-secondary transition-colors flex-shrink-0" />
        </button>

        <!-- Mesh firmware — provision a new mesh router -->
        <NuxtLink
          :to="localePath('/mesh')"
          class="flex items-center gap-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-primary transition-colors group"
        >
          <Radio class="w-5 h-5 text-primary flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('home.features.mesh.title', 'Mesh Network Firmware') }}</span>
            <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
              {{ $t('home.features.mesh.description', 'OpenWrt firmware with batman-adv mesh, auto-configured WiFi and guest network') }}
            </p>
          </div>
          <ChevronRight class="w-4 h-4 text-neutral-400 group-hover:text-secondary transition-colors flex-shrink-0" />
        </NuxtLink>
      </div>

      <!-- ═══ Sensors tab: sensor/actuator devices + environmental stations ═══ -->
      <div v-else-if="activeTab === 'sensors'" class="space-y-4">
        <div v-if="sensorDevices.length > 0 || envStore.stations.length > 0"
             class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <IoTDeviceCard
            v-for="device in sensorDevices" :key="device.id"
            :device="device"
            :property-id="device.property_id"
            :property-name="propertyName(device.property_id)"
            @delete="handleDeleteDevice"
            @refresh="loadAll"
          />
          <IoTEnvStationCard
            v-for="st in envStore.stations" :key="st.id"
            :station="st"
            @changed="envStore.fetchStations()"
            @deleted="envStore.fetchStations()"
          />
        </div>
        <div v-else-if="!iotStore.loading && !envStore.loading"
             class="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <p>{{ $t('map.env.no_stations') }}</p>
          <p class="text-sm mt-1">{{ $t('map.env.no_stations_hint') }}</p>
        </div>
      </div>

      <!-- ═══ Objects tab: properties ═══ -->
      <div v-else-if="activeTab === 'objects'" class="space-y-4">
        <!-- Add form -->
        <IoTPropertyForm v-if="showPropertyForm" @submit="showPropertyForm = false" @cancel="showPropertyForm = false" />

        <!-- Property cards — click to navigate to detail -->
        <div v-if="propertyStore.properties.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <IoTPropertyCard
            v-for="prop in propertyStore.properties" :key="prop.id"
            :property="prop"
          />
        </div>

        <!-- Empty state -->
        <div v-if="!propertyStore.loading && propertyStore.properties.length === 0 && !showPropertyForm"
             class="text-center py-12 text-neutral-500 dark:text-neutral-400">
          <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <p>{{ $t('property.no_properties') }}</p>
          <p class="text-sm mt-1">{{ $t('property.no_properties_hint') }}</p>
        </div>
      </div>

      <!-- ═══ Infrastructure tab (admin only) ═══ -->
      <div v-else-if="activeTab === 'infra' && isStaff" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <IoTHiveCard />
        <IoTServerCard />
      </div>
    </div>

    <!-- Add device modal (device created here is unassigned; assign via property detail) -->
    <IoTDeviceForm
      v-if="showDeviceForm"
      :is-open="showDeviceForm"
      :default-type="deviceFormType"
      @close="showDeviceForm = false"
      @created="onDeviceCreated"
    />

    <!-- Add environmental station modal -->
    <IoTEnvStationForm
      v-if="showStationForm"
      @close="showStationForm = false"
      @created="onStationCreated"
    />

    <!-- Claim router modal (unclaimed pool, MAC from the sticker) -->
    <IoTClaimDeviceModal
      v-if="showClaimModal"
      @close="showClaimModal = false"
      @claimed="showClaimModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onDeactivated } from 'vue'
import type { IoTDevice } from '~/stores/iot'
import {
  House as HouseIcon, ChevronRight, Navigation, Router as RouterIcon, Gauge,
  KeyRound, Radio, Server, WifiOff,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  order: 4,
  keepalive: true,
})

const iotStore = useIoTStore()
const propertyStore = usePropertyStore()
const envStore = useEnvStore()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const authStore = useAuthStore()
const { getDeviceStatus } = useIoT()

const showPropertyForm = ref(false)
const showDeviceForm = ref(false)
const showStationForm = ref(false)
const showClaimModal = ref(false)
const deviceFormType = ref('')  // preset the device-form type per originating tab

const isStaff = computed(() => authStore.user?.is_staff)

const activeTab = useTabSync(['trackers', 'network', 'sensors', 'objects', 'infra'])

// Device inventory split into coherent domains: mobility (trackers), connectivity
// (mesh routers + gateways), and sensing (sensor/actuator devices + env stations).
const trackerDevices = computed(() => iotStore.devices.filter(d => d.device_type === 'TRACKER'))
const networkDevices = computed(() => iotStore.devices.filter(d => d.device_type === 'MESH_ROUTER' || d.device_type === 'GATEWAY'))
const sensorDevices = computed(() => iotStore.devices.filter(d => d.device_type === 'SENSOR' || d.device_type === 'ACTUATOR'))

// Wall-clock tick so offline counts stay honest while the page sits open —
// a device/station crosses its staleness threshold on elapsed time alone,
// without a refetch. Managed via activated/deactivated (page is keepalive).
const STALE_STATION_MS = 30 * 60 * 1000  // mirrors useEnvFreshness STALE_AFTER
const nowTick = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null
onActivated(() => {
  nowTick.value = Date.now()
  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 60_000)
})
onDeactivated(() => {
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
})

// Offline = not reporting (down or never seen); excludes "recent" transient blips.
function offlineDeviceCount(list: IoTDevice[]) {
  void nowTick.value
  return list.filter((d) => {
    const s = getDeviceStatus(d).status
    return s === 'offline' || s === 'never'
  }).length
}
// Stale = no reading within STALE_STATION_MS (matches the station card's live badge).
const stationsOffline = computed(() => {
  const cutoff = nowTick.value - STALE_STATION_MS
  return envStore.stations.filter((st) => {
    const ts = st.last_reading_at ? new Date(st.last_reading_at).getTime() : 0
    return !ts || ts < cutoff
  }).length
})

const trackersOffline = computed(() => offlineDeviceCount(trackerDevices.value))
const networkOffline = computed(() => offlineDeviceCount(networkDevices.value))
const sensorsOffline = computed(() => offlineDeviceCount(sensorDevices.value) + stationsOffline.value)

const tabs = computed(() => {
  const list = [
    {
      id: 'trackers', label: $t('iot.tab_trackers'), icon: Navigation,
      badge: trackerDevices.value.length || undefined,
      alertBadge: trackersOffline.value || undefined,
      alertIcon: WifiOff,
      alertLabel: $t('iot.n_offline', { n: trackersOffline.value }),
    },
    {
      id: 'network', label: $t('iot.tab_network'), icon: RouterIcon,
      badge: networkDevices.value.length || undefined,
      alertBadge: networkOffline.value || undefined,
      alertIcon: WifiOff,
      alertLabel: $t('iot.n_offline', { n: networkOffline.value }),
    },
    {
      id: 'sensors', label: $t('iot.tab_sensors'), icon: Gauge,
      badge: (sensorDevices.value.length + envStore.stations.length) || undefined,
      alertBadge: sensorsOffline.value || undefined,
      alertIcon: WifiOff,
      alertLabel: $t('iot.n_offline', { n: sensorsOffline.value }),
    },
    { id: 'objects', label: $t('iot.tab_objects'), icon: HouseIcon, badge: propertyStore.properties.length || undefined },
  ]
  if (isStaff.value) list.push({ id: 'infra', label: 'Infrastructure', icon: Server, badge: undefined })
  return list
})

const createLabel = computed(() => {
  if (activeTab.value === 'trackers' || activeTab.value === 'network') return $t('iot.add_device')
  if (activeTab.value === 'sensors') return $t('map.env.add_station')
  if (activeTab.value === 'objects' && !showPropertyForm.value) return $t('property.add_property')
  return undefined
})

function onCreate() {
  if (activeTab.value === 'trackers') { deviceFormType.value = 'TRACKER'; showDeviceForm.value = true }
  else if (activeTab.value === 'network') { deviceFormType.value = ''; showDeviceForm.value = true }
  else if (activeTab.value === 'sensors') showStationForm.value = true
  else if (activeTab.value === 'objects') showPropertyForm.value = true
}

function propertyName(propertyId?: string | null) {
  if (!propertyId) return undefined
  return propertyStore.properties.find(p => p.id === propertyId)?.name
}

async function loadAll() {
  await Promise.all([
    propertyStore.fetchProperties(),
    iotStore.fetchDevices(),
    envStore.fetchStations(),
  ])
}

function handleDeleteDevice(deviceId: string) {
  iotStore.deleteDevice(deviceId)
}

function onDeviceCreated() {
  showDeviceForm.value = false
  iotStore.fetchDevices()
}

function onStationCreated() {
  showStationForm.value = false
  envStore.fetchStations()
}

// Client-side fetch behind Suspense (token-authed → no SSR): on client-side
// navigation the previous page stays visible until devices/properties are in
// the stores, instead of flashing an empty shell (was onMounted(loadAll)).
const bootstrap = useAsyncData('iot-bootstrap', async () => {
  await loadAll()
  return true
}, { server: false })

await bootstrap
</script>
