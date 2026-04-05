<template>
    <div v-if="props.isOpen" class="relative z-50" role="dialog" aria-modal="true" aria-labelledby="device-form-title" @keydown.escape="closeModal">
      <div class="fixed inset-0 bg-neutral-600 bg-opacity-50" @click="closeModal" />

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4 text-center">
            <div class="relative w-full max-w-lg transform overflow-hidden rounded-md bg-neutral-100 dark:bg-neutral-800 dark:border-neutral-700 p-5 text-left align-middle shadow-lg">
              <!-- Modal header -->
              <div class="flex items-center justify-between mb-6">
                <h3 id="device-form-title" class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100">
                  Add IoT device
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
            Device name <span class="text-red-500">*</span>
          </label>
          <input
            id="deviceName"
            v-model="form.name"
            type="text"
            required
            placeholder="My GPS tracker"
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
            Device type <span class="text-red-500">*</span>
          </label>
          <select
            id="deviceType"
            v-model="form.device_type"
            required
            @change="onDeviceTypeChange"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-700 dark:text-neutral-100">
            <option value="">Select type...</option>
            <option value="TRACKER">GPS Tracker</option>
            <option value="SENSOR">Sensor</option>
            <option value="ACTUATOR">Actuator</option>
            <option value="GATEWAY">Gateway</option>
            <option value="MESH_ROUTER">Mesh Router</option>
          </select>
        </div>

        <!-- IMEI for trackers -->
        <div v-if="form.device_type === 'TRACKER'">
          <label for="deviceIMEI" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            IMEI (optional)
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
            15-digit IMEI number (digits only)
          </p>
        </div>

        <!-- Tracker configuration info -->
        <UiAlert v-if="form.device_type === 'TRACKER'" variant="info" title="GPS tracker configuration">
          <p class="mb-2">After creation, the device will be automatically registered in Traccar. Configure your tracker:</p>
          <ul class="space-y-1 font-mono text-xs">
            <li><strong>Server:</strong> {{ trackerConfig.server }}</li>
            <li><strong>Port:</strong> {{ trackerConfig.port }}</li>
            <li><strong>ID:</strong> will be generated automatically</li>
          </ul>
        </UiAlert>

        <!-- Error message -->
        <UiAlert v-if="submitError" variant="error" title="Error creating device">
          {{ submitError }}
        </UiAlert>

        <!-- Form buttons -->
        <div class="flex justify-end space-x-3 pt-4">
          <button
            type="button"
            @click="$emit('close')"
            :disabled="creating"
            class="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded-md hover:bg-neutral-50 dark:hover:bg-neutral-600 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50">
            Cancel
          </button>
          
          <button
            type="submit"
            :disabled="creating || !isFormValid"
            class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed">
            <Icon v-if="creating" name="heroicons:arrow-path" class="w-4 h-4 mr-2" aria-hidden="true" />
            <Icon v-else name="heroicons:plus" class="w-4 h-4 mr-2" aria-hidden="true" />
            {{ creating ? 'Creating...' : 'Create device' }}
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
}

const props = withDefaults(defineProps<Props>(), {
  isOpen: false,
  triggeringElement: null,
  propertyId: null,
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

// Form state
const form = reactive<IoTDeviceInput>({
  name: '',
  device_type: '',
  imei: undefined
})

const creating = ref(false)
const submitError = ref('')

// Tracker configuration
const trackerConfig = {
  server: config.public.traccarPublicHost || '',
  port: 5013
}

// Validation
const nameError = computed(() => validateDeviceName(form.name))
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
  // Clear IMEI when changing away from tracker
  if (form.device_type !== 'TRACKER') {
    form.imei = undefined
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

    // Add IMEI for trackers if provided
    if (form.device_type === 'TRACKER' && form.imei?.trim()) {
      deviceData.imei = form.imei.trim()
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