<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('iot.title') }}
        </h2>
        <p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {{ $t('iot.subtitle') }}
        </p>
      </div>

      <div class="mt-4 sm:mt-0 flex space-x-3">
        <!-- Filter -->
        <select
          v-model="selectedType"
          class="block w-full sm:w-auto pl-3 pr-10 py-2 text-base border-neutral-300 dark:border-neutral-600 focus:outline-none focus:ring-primary focus:border-primary sm:text-sm rounded-md dark:bg-neutral-700 dark:text-neutral-100">
          <option value="">{{ $t('iot.filter_all') }}</option>
          <option value="TRACKER">{{ $t('iot.filter_trackers') }}</option>
          <option value="SENSOR">{{ $t('iot.filter_sensors') }}</option>
          <option value="ACTUATOR">{{ $t('iot.filter_actuators') }}</option>
          <option value="GATEWAY">{{ $t('iot.filter_gateways') }}</option>
          <option value="MESH_ROUTER">{{ $t('iot.filter_mesh') }}</option>
          <option v-if="isStaff" value="SERVER">{{ $t('iot.filter_server') }}</option>
          <option v-if="isStaff" value="HIVE">{{ $t('iot.filter_hive') }}</option>
        </select>

        <!-- Add device button -->
        <button
          ref="addDeviceBtn"
          @click="openAddForm"
          class="btn-primary btn-sm gap-2">
          <Plus class="w-4 h-4" />
          {{ $t('iot.add_device') }}
        </button>
      </div>
    </div>

    <!-- Compact summary stats -->
    <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm text-neutral-500 dark:text-neutral-400">
      <span><strong class="text-neutral-900 dark:text-neutral-100">{{ filteredDevices.length }}</strong> {{ $t('iot.stat_total').toLowerCase() }}</span>
      <span class="text-green-600 dark:text-green-400"><strong>{{ getActiveDevices().length }}</strong> {{ $t('iot.stat_online').toLowerCase() }}</span>
      <span v-if="meshCount > 0"><strong class="text-neutral-900 dark:text-neutral-100">{{ meshCount }}</strong> {{ $t('iot.stat_mesh').toLowerCase() }}</span>
      <span v-if="trackerCount > 0"><strong class="text-neutral-900 dark:text-neutral-100">{{ trackerCount }}</strong> {{ $t('iot.stat_trackers').toLowerCase() }}</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center items-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
      <span class="ml-3 text-neutral-600 dark:text-neutral-400">{{ $t('iot.loading') }}</span>
    </div>

    <!-- Error state -->
    <UiAlert v-else-if="error" variant="error" :title="$t('iot.error_loading')">
      <p>{{ error }}</p>
      <button
        @click="loadDevices()"
        class="mt-3 btn-error btn-sm">
        {{ $t('iot.try_again') }}
      </button>
    </UiAlert>

    <!-- Empty state -->
    <div v-else-if="filteredDevices.length === 0 && !((showHive || showServer) && isStaff)" class="text-center py-12">
      <Icon name="heroicons:cpu-chip" class="mx-auto h-12 w-12 text-neutral-400" />
      <h3 class="mt-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
        {{ selectedType ? $t('iot.no_devices_type') : $t('iot.no_devices') }}
      </h3>
      <p class="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {{ selectedType ? $t('iot.no_devices_filter_hint') : $t('iot.no_devices_hint') }}
      </p>
      <div class="mt-6">
        <button
          @click="openAddForm"
          class="btn-primary btn-sm gap-2">
          <Plus class="w-4 h-4" />
          {{ $t('iot.add_device') }}
        </button>
      </div>
    </div>

    <!-- Device grid -->
    <div v-else class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <!-- Server card (admin only) -->
      <IoTServerCard v-if="showServer && isStaff" />

      <!-- Hive card (admin only) -->
      <IoTHiveCard v-if="showHive && isStaff" />

      <IoTDeviceCard
        v-for="device in filteredDevices"
        :key="device.id"
        :device="device"
        @delete="handleDeleteDevice"
        @refresh="loadDevices"
      />
    </div>

    <!-- Add device modal -->
    <IoTDeviceForm
      :is-open="showAddForm"
      :triggering-element="addDeviceBtn"
      @close="closeAddForm"
      @created="handleDeviceCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import type { IoTDevice } from '~/stores/iot'

const iotStore = useIoTStore()
const {
  devices,
  loading,
  error,
  loadDevices,
  deleteDevice,
  filterDevicesByType,
  getActiveDevices
} = useIoT()

const { announceFormSuccess } = useA11y()

// Local state
const showAddForm = ref(false)
const selectedType = ref('')
const addDeviceBtn = ref<HTMLElement | null>(null)

// Modal control functions
const openAddForm = () => {
  showAddForm.value = true
}

const closeAddForm = () => {
  showAddForm.value = false
}

// Computed
const filteredDevices = computed(() => {
  return filterDevicesByType(selectedType.value)
})

const meshCount = computed(() => filterDevicesByType('MESH_ROUTER').length)
const trackerCount = computed(() => filterDevicesByType('TRACKER').length)
const showServer = computed(() => selectedType.value === '' || selectedType.value === 'SERVER')
const showHive = computed(() => selectedType.value === '' || selectedType.value === 'HIVE')
const isStaff = computed(() => useAuthStore().user?.is_staff ?? false)

// Load devices on mount - wait for auth to be ready
onMounted(async () => {
  const authStore = useAuthStore()

  // Wait for auth to be loaded
  if (!authStore.token) {
    const stopWatching = watch(
      () => authStore.token,
      async (newToken) => {
        if (newToken) {
          await loadDevices()
          iotStore.subscribeToPositionUpdates()
          stopWatching()
        }
      },
      { immediate: true }
    )
  } else {
    await loadDevices()
    iotStore.subscribeToPositionUpdates()
  }
})

onUnmounted(() => {
  iotStore.unsubscribeFromPositionUpdates()
})

// Handle device deletion (confirmation handled by DeviceCard modal)
const handleDeleteDevice = async (deviceId: string) => {
  await deleteDevice(deviceId)
}

// Handle new device created
const handleDeviceCreated = (device: IoTDevice) => {
  showAddForm.value = false
  announceFormSuccess(`Device "${device.name}" created successfully`)
}
</script>
