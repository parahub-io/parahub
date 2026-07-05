<template>
  <div>
    <Head>
      <Title>{{ $t('property.title') }} - Parahub</Title>
      <Meta name="description" content="Manage your homes, devices, and smart home integrations" />
    </Head>

    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <PageHeader
        :title="$t('property.title')"
        :create-label="!showPropertyForm ? $t('property.add_property') : undefined"
        @create="showPropertyForm = true"
      />
      <div class="space-y-8">

        <!-- ═══ Properties Section ═══ -->
        <div class="space-y-4">

          <!-- Add form -->
          <IoTPropertyForm v-if="showPropertyForm" @submit="showPropertyForm = false" @cancel="showPropertyForm = false" />

          <!-- Property cards — click to navigate to detail -->
          <div v-if="propertyStore.properties.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NuxtLink
              v-for="prop in propertyStore.properties" :key="prop.id"
              :to="localePath(`/iot/${prop.id}`)"
              class="block bg-neutral-100 dark:bg-neutral-800 rounded-lg p-5 border border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors group"
            >
              <div class="flex items-start justify-between mb-3">
                <div class="flex items-center gap-2">
                  <component :is="typeIcon(prop.property_type)" class="w-5 h-5 text-primary" />
                  <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ prop.name }}</h3>
                </div>
                <ChevronRight class="w-4 h-4 text-neutral-400 group-hover:text-secondary transition-colors" />
              </div>
              <p v-if="prop.address" class="text-sm text-neutral-500 dark:text-neutral-400 mb-3 line-clamp-1">{{ prop.address }}</p>
              <!-- Counts -->
              <div class="flex flex-wrap gap-3 text-xs text-neutral-500 dark:text-neutral-400">
                <span v-if="prop.device_count" class="flex items-center gap-1">
                  <Cpu class="w-3.5 h-3.5" /> {{ prop.device_count }} {{ $t('property.devices') }}
                </span>
                <span v-if="prop.ha_entity_count" class="flex items-center gap-1">
                  <Home class="w-3.5 h-3.5" /> {{ prop.ha_entity_count }} entities
                </span>
                <span v-if="prop.mesh_count" class="flex items-center gap-1">
                  <Radio class="w-3.5 h-3.5" /> {{ prop.mesh_count }} mesh
                </span>
                <span v-if="prop.energy_producer_count" class="flex items-center gap-1">
                  <Zap class="w-3.5 h-3.5 text-green-500" /> producer
                </span>
                <span v-if="prop.energy_consumer_count" class="flex items-center gap-1">
                  <Zap class="w-3.5 h-3.5 text-sky-500" /> consumer
                </span>
              </div>
            </NuxtLink>
          </div>

          <!-- Empty state -->
          <div v-if="!propertyStore.loading && propertyStore.properties.length === 0 && !showPropertyForm"
               class="text-center py-8 text-neutral-500 dark:text-neutral-400">
            <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
            <p>{{ $t('property.no_properties') }}</p>
            <p class="text-sm mt-1">{{ $t('property.no_properties_hint') }}</p>
          </div>
        </div>

        <!-- ═══ Unassigned Devices ═══ -->
        <div v-if="unassignedDevices.length > 0" class="space-y-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <LinkIcon class="w-5 h-5 text-neutral-400" />
            {{ $t('iot.unassigned_devices', 'Unassigned devices') }}
          </h2>
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <IoTDeviceCard
              v-for="device in unassignedDevices" :key="device.id"
              :device="device"
              @delete="handleDeleteDevice"
              @refresh="loadAll"
            />
          </div>
        </div>

        <!-- ═══ Tracking Section ═══ -->
        <div v-if="trackerDevices.length > 0 || !iotStore.loading" class="space-y-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <MapPin class="w-5 h-5 text-primary" />
            {{ $t('iot.filter_trackers', 'GPS Trackers') }}
          </h2>

          <div v-if="trackerDevices.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <IoTDeviceCard
              v-for="device in trackerDevices" :key="device.id"
              :device="device"
              @delete="handleDeleteDevice"
              @refresh="loadAll"
            />
          </div>

          <!-- Traccar link -->
          <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
            <div class="flex items-center justify-between gap-4">
              <div>
                <h3 class="font-medium text-neutral-900 dark:text-neutral-100">GPS Monitoring (Traccar)</h3>
                <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {{ $t('iot.traccar_hint', 'Real-time GPS tracker monitoring with auto sign-in') }}
                </p>
              </div>
              <button @click="openTraccar" class="btn-primary btn-sm flex-shrink-0 gap-1">
                <ExternalLink class="w-4 h-4" />
                Traccar
              </button>
            </div>
          </div>
        </div>

        <!-- ═══ Mesh Network Section ═══ -->
        <div v-if="meshDevices.length > 0 || !iotStore.loading" class="space-y-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Radio class="w-5 h-5 text-emerald-500" />
            {{ $t('iot.filter_mesh', 'Mesh Routers') }}
          </h2>

          <!-- Mesh devices not assigned to property -->
          <div v-if="unassignedMeshDevices.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <IoTDeviceCard
              v-for="device in unassignedMeshDevices" :key="device.id"
              :device="device"
              @delete="handleDeleteDevice"
              @refresh="loadAll"
            />
          </div>

          <!-- Firmware link -->
          <NuxtLink :to="localePath('/mesh')" class="block bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 hover:border-emerald-500 transition-colors">
            <div class="flex items-center gap-3">
              <Radio class="w-5 h-5 text-emerald-500 flex-shrink-0" />
              <div>
                <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('home.features.mesh.title', 'Mesh Network Firmware') }}</span>
                <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {{ $t('home.features.mesh.description', 'OpenWrt firmware with batman-adv mesh, auto-configured WiFi and guest network') }}
                </p>
              </div>
            </div>
          </NuxtLink>
        </div>

        <!-- ═══ Server Section (admin only) ═══ -->
        <div v-if="isStaff" class="space-y-4">
          <h2 class="text-sm font-medium text-neutral-500 dark:text-neutral-400 flex items-center gap-2">
            <Server class="w-4 h-4" />
            Infrastructure
          </h2>
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <IoTHiveCard />
            <IoTServerCard />
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  House as HouseIcon, Plus, ChevronRight, Cpu, Home, Radio, Zap,
  MapPin, ExternalLink, Link as LinkIcon, Server,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  order: 4,
  keepalive: true,
})

const iotStore = useIoTStore()
const propertyStore = usePropertyStore()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const authStore = useAuthStore()

const showPropertyForm = ref(false)

const isStaff = computed(() => authStore.user?.is_staff)

// All devices loaded globally
const allDevices = computed(() => iotStore.devices)

// Tracker devices (always shown in Tracking section, regardless of property)
const trackerDevices = computed(() =>
  allDevices.value.filter(d => d.device_type === 'TRACKER')
)

// Mesh devices without property (shown in Mesh section)
const meshDevices = computed(() =>
  allDevices.value.filter(d => d.device_type === 'MESH_ROUTER')
)
const unassignedMeshDevices = computed(() =>
  meshDevices.value.filter(d => !d.property_id)
)

// Non-tracker, non-mesh devices without property
const unassignedDevices = computed(() =>
  allDevices.value.filter(d =>
    !d.property_id &&
    d.device_type !== 'TRACKER' &&
    d.device_type !== 'MESH_ROUTER'
  )
)

function typeIcon(type: string) {
  const icons: Record<string, any> = {
    house: HouseIcon, apartment: Home, office: Server,
    dacha: HouseIcon, garage: HouseIcon, land: MapPin, other: Cpu,
  }
  return icons[type] || Cpu
}

async function loadAll() {
  await Promise.all([
    propertyStore.fetchProperties(),
    iotStore.fetchDevices(),
  ])
}

function handleDeleteDevice(deviceId: string) {
  iotStore.deleteDevice(deviceId)
}

const openTraccar = () => {
  window.open('https://parahub.io/api/v1/iot/traccar/sso-redirect', '_blank', 'noopener,noreferrer')
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
