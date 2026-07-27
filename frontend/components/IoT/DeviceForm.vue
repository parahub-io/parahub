<template>
    <div v-if="props.isOpen" class="relative z-50" role="dialog" aria-modal="true" aria-labelledby="device-form-title" @keydown.escape="closeModal">
      <div class="fixed inset-0 bg-neutral-600 bg-opacity-50" @click="closeModal" />

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4 text-center">
            <div class="relative w-full max-w-lg transform overflow-hidden rounded-md bg-neutral-100 dark:bg-neutral-800 dark:border-neutral-700 p-5 text-left align-middle shadow-lg">
              <!-- Modal header -->
              <div class="flex items-center justify-between mb-6">
                <h3 id="device-form-title" class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100">
                  {{ $t('iot.add_device') }}
                </h3>
                <button
                  @click="closeModal"
                  aria-label="Close dialog"
                  class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 rounded-full p-1 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                >
                  <Icon name="heroicons:x-mark" class="w-6 h-6" aria-hidden="true" />
                </button>
              </div>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Device name -->
        <div>
          <label for="deviceName" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('iot.device_form.name_label') }} <span class="text-red-500">*</span>
          </label>
          <input
            id="deviceName"
            v-model="form.name"
            type="text"
            required
            :placeholder="$t('iot.device_form.name_placeholder')"
            :aria-invalid="!!nameError"
            :aria-describedby="nameError ? 'name-error' : undefined"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-700 dark:text-neutral-100"
            :class="{ 'border-red-500 focus:ring-error': nameError }"
          />
          <p v-if="nameError" id="name-error" class="mt-1 text-sm text-red-600 dark:text-red-400">
            {{ nameError }}
          </p>
        </div>

        <!-- Device type -->
        <div>
          <label for="deviceType" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('iot.device_form.type_label') }} <span class="text-red-500">*</span>
          </label>
          <select
            id="deviceType"
            v-model="form.device_type"
            required
            @change="onDeviceTypeChange"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-700 dark:text-neutral-100">
            <option value="">{{ $t('iot.device_form.type_select') }}</option>
            <option v-for="dt in DEVICE_TYPES" :key="dt" :value="dt">{{ $t(`iot.device_types.${dt}`) }}</option>
          </select>
        </div>

        <!-- Device identifier for trackers: must match what the tracker sends -->
        <div v-if="form.device_type === 'TRACKER'">
          <label for="deviceIdentifier" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('iot.device_form.identifier_label') }}
          </label>
          <input
            id="deviceIdentifier"
            v-model="form.device_id"
            type="text"
            maxlength="64"
            placeholder="123456"
            aria-describedby="identifier-help"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-700 dark:text-neutral-100 font-mono"
          />
          <p id="identifier-help" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('iot.device_form.identifier_help') }}
          </p>
        </div>

        <!-- IMEI for trackers -->
        <div v-if="form.device_type === 'TRACKER'">
          <label for="deviceIMEI" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('iot.device_form.imei_label') }}
          </label>
          <input
            id="deviceIMEI"
            v-model="form.imei"
            type="text"
            placeholder="123456789012345"
            maxlength="15"
            pattern="[0-9]{15}"
            :aria-invalid="!!imeiError"
            :aria-describedby="imeiError ? 'imei-error' : 'imei-help'"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-700 dark:text-neutral-100 font-mono"
            :class="{ 'border-red-500 focus:ring-error': imeiError }"
          />
          <p v-if="imeiError" id="imei-error" class="mt-1 text-sm text-red-600 dark:text-red-400">
            {{ imeiError }}
          </p>
          <p v-else id="imei-help" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('iot.device_form.imei_help') }}
          </p>
        </div>

        <!-- Tracker configuration info -->
        <UiAlert v-if="form.device_type === 'TRACKER'" variant="info" :title="$t('iot.device_form.tracker_info_title')">
          <p class="mb-2">{{ $t('iot.device_form.tracker_phone_hint', { url: osmandUrl }) }}</p>
          <p>{{ $t('iot.device_form.tracker_hw_hint', { host: trackerHost }) }}</p>
        </UiAlert>

        <!-- Error message -->
        <UiAlert v-if="submitError" variant="error" :title="$t('iot.device_form.error_title')">
          {{ submitError }}
        </UiAlert>

        <!-- Form buttons -->
        <div class="flex justify-end space-x-3 pt-4">
          <button
            type="button"
            @click="$emit('close')"
            :disabled="creating"
            class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded-md hover:bg-neutral-50 dark:hover:bg-neutral-600 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50">
            {{ $t('iot.cancel') }}
          </button>

          <button
            type="submit"
            :disabled="creating || !isFormValid"
            class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed">
            <Icon v-if="creating" name="heroicons:arrow-path" class="w-4 h-4 mr-2" aria-hidden="true" />
            <Icon v-else name="heroicons:plus" class="w-4 h-4 mr-2" aria-hidden="true" />
            {{ creating ? $t('iot.device_form.creating') : $t('iot.device_form.create') }}
          </button>
        </div>
      </form>
            </div>
        </div>
      </div>
    </div>
</template>

<script setup lang="ts">
import type { IoTDevice, IoTDeviceInput } from '~/stores/iot'

interface Props {
  isOpen: boolean
  triggeringElement?: HTMLElement | null
  propertyId?: string | null
  defaultType?: string  // preselect the device type (e.g. TRACKER from the Trackers tab)
}

const props = withDefaults(defineProps<Props>(), {
  isOpen: false,
  triggeringElement: null,
  propertyId: null,
  defaultType: '',
})

interface Emits {
  (e: 'close'): void
  (e: 'created', device: IoTDevice): void
}

const emit = defineEmits<Emits>()

// Close modal function
function closeModal() {
  emit('close')
}

const { createDevice, validateDeviceName, validateIMEI } = useIoT()
const config = useRuntimeConfig()

const DEVICE_TYPES = ['TRACKER', 'SENSOR', 'ACTUATOR', 'GATEWAY', 'MESH_ROUTER'] as const

// Form state
const form = reactive<IoTDeviceInput>({
  name: '',
  device_type: props.defaultType || '',
  imei: undefined,
  device_id: undefined,
})

const creating = ref(false)
const submitError = ref('')

// Traccar ingest endpoints: phone app speaks OsmAnd (5055), hardware
// trackers use their protocol's port (hint lists them)
const trackerHost = config.public.traccarPublicHost || ''
const osmandUrl = `http://${trackerHost}:5055`

// Validation (pristine empty field shows no error — submit is gated anyway)
const nameError = computed(() => form.name ? validateDeviceName(form.name) : null)
const imeiError = computed(() => {
  if (form.device_type === 'TRACKER' && form.imei) {
    return validateIMEI(form.imei)
  }
  return null
})

const isFormValid = computed(() => {
  return form.name.trim().length >= 2 && 
         form.device_type !== '' && 
         !nameError.value && 
         !imeiError.value
})

// Handle device type change
const onDeviceTypeChange = () => {
  // Clear tracker-only fields when changing away from tracker
  if (form.device_type !== 'TRACKER') {
    form.imei = undefined
    form.device_id = undefined
  }
  submitError.value = ''
}

// Handle form submission
const handleSubmit = async () => {
  if (!isFormValid.value) return
  
  creating.value = true
  submitError.value = ''
  
  try {
    // Prepare form data
    const deviceData: IoTDeviceInput = {
      name: form.name.trim(),
      device_type: form.device_type,
    }

    // Add IMEI / Traccar identifier for trackers if provided
    if (form.device_type === 'TRACKER' && form.imei?.trim()) {
      deviceData.imei = form.imei.trim()
    }
    if (form.device_type === 'TRACKER' && form.device_id?.trim()) {
      deviceData.device_id = form.device_id.trim()
    }

    // Link to property if provided
    if (props.propertyId) {
      deviceData.property_id = props.propertyId
    }
    
    // Create device
    const device = await createDevice(deviceData)
    
    // Success will be handled by parent component with proper ARIA live region
    // Removed alert() for better accessibility
    
    // Emit success
    emit('created', device)
    
  } catch (error: any) {
    console.error('Error creating device:', error)
    const { t } = useNuxtApp().$i18n
    submitError.value = error.message || t('device.create.error')
  } finally {
    creating.value = false
  }
}

// Focus return on unmount
onUnmounted(() => {
  // Return focus to triggering element if available
  if (props.triggeringElement) {
    nextTick(() => {
      props.triggeringElement?.focus()
    })
  }
})
</script>