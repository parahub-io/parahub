<template>
  <div>
    <Head>
      <Title>{{ prop?.name || '...' }} - Parahub</Title>
    </Head>

    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">

      <!-- Back + loading -->
      <NuxtLink :to="localePath('/iot')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ $t('property.title') }}
      </NuxtLink>

      <div v-if="loading" class="text-center py-12 text-neutral-500">
        <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2" />
      </div>

      <div v-else-if="!prop" class="text-center py-12 text-neutral-500">
        Property not found
      </div>

      <template v-else>
        <!-- ═══ Property Header ═══ -->
        <div class="flex items-start justify-between mb-8">
          <div>
            <div class="flex items-center gap-3 mb-1">
              <component :is="typeIcon" class="w-6 h-6 text-primary" />
              <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ prop.name }}</h1>
              <span class="badge-sm bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
                {{ $t(`property.types.${prop.property_type}`) }}
              </span>
            </div>
            <p v-if="prop.address" class="text-neutral-500 dark:text-neutral-400 ml-9">{{ prop.address }}</p>
          </div>
          <div class="flex gap-2">
            <button @click="showEditForm = !showEditForm" class="btn-secondary btn-sm gap-1">
              <Pencil class="w-4 h-4" />
              {{ $t('property.edit') }}
            </button>
            <button @click="confirmDelete" class="btn-secondary btn-sm gap-1 text-red-500 hover:text-red-600">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Edit form -->
        <IoTPropertyForm v-if="showEditForm" :prop="prop" @submit="onPropertyUpdated" @cancel="showEditForm = false" class="mb-8" />

        <div class="space-y-8">

          <!-- ═══ Smart Home Section ═══ -->
          <section v-if="haHomes.length > 0 || haEntities.length > 0 || showHAForm">
            <button @click="haExpanded = !haExpanded" class="section-header w-full">
              <div class="flex items-center gap-2">
                <Home class="w-5 h-5 text-sky-500" />
                <span>{{ $t('ha.title') }}</span>
                <span class="text-xs text-neutral-400">({{ totalEntityCount }})</span>
              </div>
              <ChevronDown class="w-4 h-4 text-neutral-400 transition-transform" :class="{ 'rotate-180': haExpanded }" />
            </button>

            <div v-show="haExpanded" class="mt-4 space-y-4">
              <!-- HA Home cards -->
              <div v-if="haHomes.length > 0" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <IoTHAHomeCard
                  v-for="home in haHomes" :key="home.id"
                  :home="home"
                  :syncing="syncingHomeId === home.id"
                  @discover="openDiscover(home)"
                  @sync="syncHome(home)"
                  @test="testHome(home)"
                  @edit="editingHome = home"
                  @delete="confirmDeleteHome(home)"
                />
              </div>

              <!-- Edit HA form -->
              <IoTHAHomeForm v-if="editingHome" :home="editingHome" @submit="editingHome = null" @cancel="editingHome = null" />

              <!-- Entities grouped by domain -->
              <template v-for="(entities, domain) in entitiesByDomain" :key="domain">
                <div class="space-y-2">
                  <h4 class="text-sm font-medium text-neutral-600 dark:text-neutral-400 capitalize">{{ domain }} ({{ entities.length }})</h4>
                  <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    <IoTHAEntityCard
                      v-for="entity in entities" :key="entity.id"
                      :entity="entity"
                      @delete="confirmDeleteEntity(entity)"
                    />
                  </div>
                </div>
              </template>

              <!-- Add HA button -->
              <button v-if="!showHAForm" @click="showHAForm = true" class="btn-secondary btn-sm gap-1">
                <Plus class="w-4 h-4" />
                {{ $t('ha.add_home') }}
              </button>
              <IoTHAHomeForm v-if="showHAForm" :property-id="propertyId" @submit="onHAAdded" @cancel="showHAForm = false" />
            </div>
          </section>

          <!-- HA empty — just show add button -->
          <section v-else-if="!showHAForm">
            <button @click="showHAForm = true" class="w-full text-left bg-neutral-50 dark:bg-neutral-800/50 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600 p-4 hover:border-sky-400 transition-colors">
              <div class="flex items-center gap-3">
                <Home class="w-5 h-5 text-sky-500 opacity-50" />
                <div>
                  <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ $t('ha.title') }}</span>
                  <p class="text-sm text-neutral-400">{{ $t('ha.no_homes_hint') }}</p>
                </div>
              </div>
            </button>
            <IoTHAHomeForm v-if="showHAForm" @submit="onHAAdded" @cancel="showHAForm = false" class="mt-4" />
          </section>

          <!-- ═══ Devices Section ═══ -->
          <section v-if="sensorDevices.length > 0 || showDeviceForm">
            <button @click="devicesExpanded = !devicesExpanded" class="section-header w-full">
              <div class="flex items-center gap-2">
                <Cpu class="w-5 h-5 text-blue-500" />
                <span>{{ $t('iot.title') }}</span>
                <span class="text-xs text-neutral-400">({{ sensorDevices.length }})</span>
              </div>
              <ChevronDown class="w-4 h-4 text-neutral-400 transition-transform" :class="{ 'rotate-180': devicesExpanded }" />
            </button>

            <div v-show="devicesExpanded" class="mt-4 space-y-4">
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <IoTDeviceCard
                  v-for="device in sensorDevices" :key="device.id"
                  :device="device"
                  @delete="handleDeleteDevice"
                  @refresh="loadPropertyData"
                />
              </div>
              <button v-if="!showDeviceForm" @click="showDeviceForm = true" class="btn-secondary btn-sm gap-1">
                <Plus class="w-4 h-4" />
                {{ $t('iot.add_device') }}
              </button>
            </div>
          </section>

          <!-- ═══ Network Section (Mesh) ═══ -->
          <section v-if="meshDevices.length > 0">
            <button @click="networkExpanded = !networkExpanded" class="section-header w-full">
              <div class="flex items-center gap-2">
                <Radio class="w-5 h-5 text-emerald-500" />
                <span>{{ $t('iot.filter_mesh', 'Network') }}</span>
                <span class="text-xs text-neutral-400">({{ meshDevices.length }})</span>
              </div>
              <ChevronDown class="w-4 h-4 text-neutral-400 transition-transform" :class="{ 'rotate-180': networkExpanded }" />
            </button>

            <div v-show="networkExpanded" class="mt-4 space-y-4">
              <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <IoTDeviceCard
                  v-for="device in meshDevices" :key="device.id"
                  :device="device"
                  @delete="handleDeleteDevice"
                  @refresh="loadPropertyData"
                />
              </div>

              <NuxtLink :to="localePath('/mesh')" class="inline-flex items-center gap-2 text-sm text-emerald-600 hover:text-emerald-500">
                <Radio class="w-4 h-4" />
                {{ $t('home.features.mesh.title', 'Mesh firmware downloads') }}
              </NuxtLink>
            </div>
          </section>

          <!-- ═══ Energy Section ═══ -->
          <section v-if="prop.energy_producer_count > 0 || prop.energy_consumer_count > 0">
            <button @click="energyExpanded = !energyExpanded" class="section-header w-full">
              <div class="flex items-center gap-2">
                <Zap class="w-5 h-5 text-yellow-500" />
                <span>{{ $t('nav.energy', 'Energy') }}</span>
              </div>
              <ChevronDown class="w-4 h-4 text-neutral-400 transition-transform" :class="{ 'rotate-180': energyExpanded }" />
            </button>

            <div v-show="energyExpanded" class="mt-4">
              <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
                <div class="flex items-center gap-3">
                  <Zap class="w-5 h-5" :class="prop.energy_producer_count > 0 ? 'text-green-500' : 'text-sky-500'" />
                  <div>
                    <span v-if="prop.energy_producer_count > 0" class="font-medium text-neutral-900 dark:text-neutral-100">
                      Energy Producer
                    </span>
                    <span v-else class="font-medium text-neutral-900 dark:text-neutral-100">
                      Energy Consumer
                    </span>
                  </div>
                </div>
                <NuxtLink :to="localePath('/energy')" class="inline-flex items-center gap-1 text-sm text-primary hover:underline mt-2">
                  {{ $t('iot.view_energy_cell', 'View energy cell details') }}
                  <ChevronRight class="w-3 h-3" />
                </NuxtLink>
              </div>
            </div>
          </section>

          <!-- Energy empty state — link to join -->
          <section v-else>
            <NuxtLink :to="localePath('/energy')" class="block bg-neutral-50 dark:bg-neutral-800/50 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600 p-4 hover:border-yellow-400 transition-colors">
              <div class="flex items-center gap-3">
                <Zap class="w-5 h-5 text-yellow-500 opacity-50" />
                <div>
                  <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ $t('nav.energy', 'Energy') }}</span>
                  <p class="text-sm text-neutral-400">{{ $t('iot.join_energy_hint', 'Join a P2P energy cell to share solar energy with neighbors') }}</p>
                </div>
              </div>
            </NuxtLink>
          </section>

        </div>
      </template>
    </div>

    <!-- Discover dialog -->
    <IoTHADiscoverDialog
      v-if="discoverHome"
      :show="!!discoverHome"
      :home="discoverHome"
      @close="discoverHome = null"
      @imported="onEntitiesImported"
    />

    <!-- Add device modal -->
    <IoTDeviceForm
      v-if="showDeviceForm"
      :is-open="showDeviceForm"
      :property-id="prop?.id"
      @close="showDeviceForm = false"
      @created="onDeviceCreated"
    />

    <UiConfirmModal
      v-model="showDeletePropertyConfirm"
      :title="$t('common.delete')"
      :message="$t('property.confirm_delete', { name: prop?.name })"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('common.delete')"
      @confirm="doDeleteProperty"
    />

    <UiConfirmModal
      v-model="showDeleteHomeConfirm"
      :title="$t('common.delete')"
      :message="$t('ha.confirm_delete_home', { name: pendingDeleteHome?.name })"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('common.delete')"
      @confirm="doDeleteHome"
    />

    <UiConfirmModal
      v-model="showDeleteEntityConfirm"
      :title="$t('common.delete')"
      :message="$t('ha.confirm_delete_entity', { name: pendingDeleteEntity?.friendly_name })"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('common.delete')"
      @confirm="doDeleteEntity"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  ArrowLeft, Loader2, Pencil, Trash2, Plus, ChevronDown, ChevronRight,
  Home, Cpu, Radio, Zap, House as HouseIcon, Building, MapPin, Server,
} from 'lucide-vue-next'
import type { HAHome, HAEntity } from '~/stores/ha'

definePageMeta({
  middleware: 'auth',
  keepalive: true,
})

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const propertyStore = usePropertyStore()
const iotStore = useIoTStore()
const haStore = useHAStore()

const propertyId = computed(() => route.params.id as string)

// State
const loading = ref(true)
const showDeletePropertyConfirm = ref(false)
const showDeleteHomeConfirm = ref(false)
const showDeleteEntityConfirm = ref(false)
const pendingDeleteHome = ref<HAHome | null>(null)
const pendingDeleteEntity = ref<HAEntity | null>(null)
const showEditForm = ref(false)
const showHAForm = ref(false)
const showDeviceForm = ref(false)
const editingHome = ref<HAHome | null>(null)
const discoverHome = ref<HAHome | null>(null)
const syncingHomeId = ref<string | null>(null)
const homeEntities = ref<Record<string, HAEntity[]>>({})

// Section expand state (all expanded by default)
const haExpanded = ref(true)
const devicesExpanded = ref(true)
const networkExpanded = ref(true)
const energyExpanded = ref(true)

// Property
const prop = computed(() => propertyStore.getById(propertyId.value))

const typeIcon = computed(() => {
  const icons: Record<string, any> = {
    house: HouseIcon, apartment: Building, office: Server,
    dacha: HouseIcon, garage: HouseIcon, land: MapPin, other: Cpu,
  }
  return icons[prop.value?.property_type || ''] || Cpu
})

// Devices for this property
const propertyDevices = computed(() =>
  iotStore.devices.filter(d => d.property_id === propertyId.value)
)

const sensorDevices = computed(() =>
  propertyDevices.value.filter(d =>
    d.device_type !== 'MESH_ROUTER' && d.device_type !== 'TRACKER'
  )
)

const meshDevices = computed(() =>
  propertyDevices.value.filter(d => d.device_type === 'MESH_ROUTER')
)

// HA for this property
const haHomes = computed(() => haStore.homes)

const haEntities = computed(() => {
  const all: HAEntity[] = []
  for (const entities of Object.values(homeEntities.value)) {
    all.push(...entities)
  }
  return all
})

const totalEntityCount = computed(() => haEntities.value.length)

const entitiesByDomain = computed(() => {
  const grouped: Record<string, HAEntity[]> = {}
  for (const entity of haEntities.value) {
    if (!grouped[entity.domain]) grouped[entity.domain] = []
    grouped[entity.domain].push(entity)
  }
  // Sort domains
  return Object.fromEntries(
    Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b))
  )
})

// Actions
async function loadPropertyData() {
  loading.value = true
  try {
    await Promise.all([
      propertyStore.fetchProperties(),
      iotStore.fetchDevices({ propertyId: propertyId.value }),
      haStore.fetchHomes({ propertyId: propertyId.value }),
    ])
    // Load entities for each HA home
    for (const home of haStore.homes) {
      try {
        const entities = await haStore.listEntities(home.id)
        homeEntities.value[home.id] = entities
      } catch {}
    }
  } finally {
    loading.value = false
  }
}

function onPropertyUpdated() {
  showEditForm.value = false
  propertyStore.fetchProperties()
}

function confirmDelete() {
  showDeletePropertyConfirm.value = true
}

async function doDeleteProperty() {
  if (!prop.value) return
  showDeletePropertyConfirm.value = false
  await propertyStore.deleteProperty(prop.value.id)
  router.push(localePath('/iot'))
}

// HA actions
function openDiscover(home: HAHome) { discoverHome.value = home }

async function syncHome(home: HAHome) {
  syncingHomeId.value = home.id
  try {
    await haStore.syncHome(home.id)
    await haStore.fetchHomes({ propertyId: propertyId.value })
  } catch {} finally { syncingHomeId.value = null }
}

async function testHome(home: HAHome) {
  try {
    const result = await haStore.testConnection(home.id)
    if (result.ok) await haStore.fetchHomes({ propertyId: propertyId.value })
  } catch {}
}

function confirmDeleteHome(home: HAHome) {
  pendingDeleteHome.value = home
  showDeleteHomeConfirm.value = true
}

function doDeleteHome() {
  if (!pendingDeleteHome.value) return
  showDeleteHomeConfirm.value = false
  haStore.deleteHome(pendingDeleteHome.value.id)
  pendingDeleteHome.value = null
}

function confirmDeleteEntity(entity: HAEntity) {
  pendingDeleteEntity.value = entity
  showDeleteEntityConfirm.value = true
}

function doDeleteEntity() {
  if (!pendingDeleteEntity.value) return
  showDeleteEntityConfirm.value = false
  haStore.deleteEntity(pendingDeleteEntity.value.id, pendingDeleteEntity.value.home_id)
  pendingDeleteEntity.value = null
}

async function onHAAdded() {
  showHAForm.value = false
  await loadPropertyData()
}

async function onEntitiesImported() {
  await loadPropertyData()
}

// Device actions
function handleDeleteDevice(deviceId: string) {
  iotStore.deleteDevice(deviceId)
}

function onDeviceCreated() {
  showDeviceForm.value = false
  loadPropertyData()
}

onMounted(loadPropertyData)
</script>

<style scoped>
.section-header {
  @apply flex items-center justify-between py-3 px-1 text-lg font-semibold text-neutral-900 dark:text-neutral-100;
  @apply border-b border-neutral-200 dark:border-neutral-700 cursor-pointer;
  @apply hover:text-secondary transition-colors;
}
</style>
