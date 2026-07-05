<template>
  <div v-if="visible">
    <div class="flex items-center justify-between mb-2">
      <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {{ $t('market.create_modal.images_label') }}
      </label>
      <!-- AI Quota Badge -->
      <div
        v-if="isAuthenticated && !loadingQuota"
        class="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium"
        :class="{
          'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200': aiQuota.remaining > 10,
          'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200': aiQuota.remaining > 0 && aiQuota.remaining <= 10,
          'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200': aiQuota.remaining === 0
        }"
      >
        <Sparkles class="w-3 h-3" />
        <span>{{ $t('market.ai_quota_label', { remaining: aiQuota.remaining, limit: aiQuota.limit }) }}</span>
      </div>
    </div>
    <div class="space-y-3">
      <!-- AI Analysis Loading State -->
      <div v-if="aiAnalyzing" class="p-4 border-2 border-primary rounded-lg bg-primary bg-opacity-5" role="status" aria-live="polite">
        <div class="flex items-center gap-3">
          <div class="animate-spin rounded-full h-5 w-5 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
          <div>
            <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.notifications.ai_analyzing') }}</div>
            <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('market.notifications.ai_please_wait') }}</div>
          </div>
        </div>
      </div>

      <!-- Image preview grid -->
      <div v-if="modelValue.length > 0" class="grid grid-cols-5 gap-2">
        <div
          v-for="(img, index) in modelValue"
          :key="index"
          class="relative aspect-square rounded-lg overflow-hidden border-2 border-neutral-300 dark:border-neutral-600"
        >
          <img :src="img.preview" :alt="index === 0 ? $t('market.create_modal.image_main') : `Image #${index + 1}`" class="w-full h-full object-cover" />
          <button
            type="button"
            @click="removeImage(index)"
            class="btn-error absolute top-1 right-1 !p-1 !rounded-full"
            :aria-label="$t('common.remove')"
          >
            <X class="w-3 h-3" aria-hidden="true" />
          </button>
          <div class="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs text-center py-1">
            {{ index === 0 ? $t('market.create_modal.image_main') : `#${index + 1}` }}
          </div>
        </div>
      </div>

      <!-- Upload buttons -->
      <div v-if="modelValue.length < 5">
        <!-- Hidden file inputs -->
        <input
          ref="imageInput"
          type="file"
          accept="image/*"
          multiple
          @change="handleImageSelect"
          class="hidden"
          :aria-label="$t('market.create_modal.images_label')"
        >
        <input
          ref="cameraInput"
          type="file"
          accept="image/*"
          capture="environment"
          @change="handleImageSelect"
          class="hidden"
          :aria-label="$t('market.create_modal.take_photo')"
        >

        <!-- Desktop: Single button -->
        <button
          type="button"
          @click="imageInput?.click()"
          :disabled="aiAnalyzing"
          class="btn-outline hidden md:block w-full border-dashed border-2 hover:border-primary hover:bg-primary/5"
        >
          {{ modelValue.length === 0 ? $t('market.create_modal.add_first_photo_ai') : $t('market.create_modal.add_photo', { current: modelValue.length }) }}
        </button>

        <!-- Mobile: Two buttons (Camera + Gallery). type="button" is REQUIRED — UiButton
             renders a bare <button> which, with no type, defaults to submit and would
             post the surrounding create form once required fields are filled. -->
        <div class="md:hidden grid grid-cols-2 gap-2">
          <UiButton type="button" variant="outline" :icon="Camera" :disabled="aiAnalyzing" class="border-dashed border-2 hover:border-primary hover:bg-primary/5" @click="cameraInput?.click()">
            {{ $t('market.create_modal.take_photo') }}
          </UiButton>
          <UiButton type="button" variant="outline" :icon="ImageIcon" :disabled="aiAnalyzing" class="border-dashed border-2 hover:border-primary hover:bg-primary/5" @click="imageInput?.click()">
            {{ $t('market.create_modal.from_gallery') }}
          </UiButton>
        </div>
      </div>
      <p class="text-xs text-neutral-500 dark:text-neutral-400">
        {{ modelValue.length === 0 ? $t('market.create_modal.images_help_ai') : $t('market.create_modal.images_help') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useWebSocket } from '~/composables/useWebSocket'
import { X, Camera, ImageIcon, Sparkles } from 'lucide-vue-next'
import exifr from 'exifr'
import imageCompression from 'browser-image-compression'

const props = defineProps({
  modelValue: {
    type: Array,
    required: true
  },
  isAuthenticated: {
    type: Boolean,
    default: false
  },
  visible: {
    type: Boolean,
    default: true
  },
  // 'CREDIT' (user sells) or 'DEBIT' (user is looking to buy) — flips the AI's
  // framing from a seller's listing to a "wanted"/buy-request listing.
  itemType: {
    type: String,
    default: 'CREDIT'
  }
})

const emit = defineEmits(['update:modelValue', 'location-detected', 'ai-result'])

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()

// Refs
const imageInput = ref(null)
const cameraInput = ref(null)
const aiAnalyzing = ref(false)
const loadingQuota = ref(false)

// AI Quota state
const aiQuota = ref({
  remaining: 30,
  limit: 30,
  used: 0,
  reset_at: null
})

// WebSocket for AI analysis progress updates
const { connect: connectWS, disconnect: disconnectWS } = useWebSocket({
  path: '/ws/v1/realtime/',
  onMessage: (data) => {
    if (data.type === 'ai.analysis_progress') {
      emit('ai-result', {
        title: data.title,
        description: data.description,
        suggested_price: data.suggested_price,
        source: 'websocket'
      })
    }
  },
  onOpen: () => {},
  autoReconnect: true
})

// Fetch AI quota
const fetchAIQuota = async () => {
  try {
    loadingQuota.value = true
    await authStore.ensureToken()

    if (!authStore.token) {
      return
    }

    const quota = await $fetch('/api/v1/ai/usage-quota/', {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    aiQuota.value = quota
  } catch (error) {
    console.error('Failed to fetch AI quota:', error)
  } finally {
    loadingQuota.value = false
  }
}

// Image handling
const handleImageSelect = async (event) => {
  const files = Array.from(event.target.files)
  const remainingSlots = 5 - props.modelValue.length
  const isFirstImage = props.modelValue.length === 0

  if (files.length > remainingSlots) {
    toastStore.error($t('market.notifications.max_photos', { count: remainingSlots }))
    return
  }

  const validFiles = []
  const compressedFiles = []
  const newImages = [...props.modelValue]

  // Compression options with EXIF preservation
  const compressionOptions = {
    maxSizeMB: 1,
    maxWidthOrHeight: 1920,
    useWebWorker: true,
    preserveExif: true,
    fileType: 'image/jpeg'
  }

  for (const file of files) {
    if (!file.type.startsWith('image/')) {
      toastStore.error($t('market.notifications.not_image', { filename: file.name }))
      continue
    }

    if (file.size > 15 * 1024 * 1024) {
      toastStore.error($t('market.notifications.file_too_large', { filename: file.name }))
      continue
    }

    validFiles.push(file)

    try {
      const compressedFile = await imageCompression(file, compressionOptions)
      compressedFiles.push(compressedFile)

      const preview = await readFileAsDataURL(compressedFile)
      newImages.push({ file: compressedFile, preview })
    } catch (compressionError) {
      console.error('Image compression failed, using original:', compressionError)
      compressedFiles.push(file)

      const preview = await readFileAsDataURL(file)
      newImages.push({ file, preview })
    }
  }

  emit('update:modelValue', newImages)

  // Extract EXIF GPS from first image
  if (isFirstImage && validFiles.length > 0) {
    await extractGPSFromImage(validFiles[0])
    // AI analysis on compressed file
    if (compressedFiles.length > 0 && aiQuota.value.remaining > 0) {
      await analyzeImageWithAI(compressedFiles[0])
    } else if (aiQuota.value.remaining === 0) {
      toastStore.info($t('market.notifications.ai_quota_exhausted'))
    }
  }
}

// Helper: read file as data URL (promisified)
const readFileAsDataURL = (file) => {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => resolve(e.target.result)
    reader.readAsDataURL(file)
  })
}

// Extract GPS coordinates from image EXIF
const extractGPSFromImage = async (file) => {
  try {
    const exifData = await exifr.parse(file, { gps: true })

    if (exifData && exifData.latitude && exifData.longitude) {
      emit('location-detected', {
        latitude: Math.round(exifData.latitude * 100000) / 100000,
        longitude: Math.round(exifData.longitude * 100000) / 100000
      })
      // GPS silently applied — no toast
    }
  } catch (error) {
    console.error('Failed to extract GPS from image:', error)
  }
}

// AI Image Analysis
const analyzeImageWithAI = async (file) => {
  try {
    aiAnalyzing.value = true
    await authStore.ensureToken()

    if (!authStore.token) {
      throw new Error('No authentication token available')
    }

    const formData = new FormData()
    formData.append('image', file)
    // Tell the AI whether this is a sell offer (CREDIT) or a buy request (DEBIT)
    formData.append('item_type', props.itemType || 'CREDIT')

    const result = await $fetch('/api/v1/ai/analyze-image/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    // Refresh quota after successful analysis
    await fetchAIQuota()

    // Emit full AI result to parent (for category + fallback fields)
    emit('ai-result', {
      title: result.title,
      description: result.description,
      category_id: result.category_id,
      category_name: result.category_name,
      suggested_price: result.suggested_price
        ? { amount: result.suggested_price.amount, currency: result.suggested_price.currency, type: result.suggested_price.type }
        : null,
      log_id: result.log_id,
      source: 'http'
    })

    // No toasts — parent handles field flash animations
  } catch (error) {
    console.error('AI analysis failed:', error)

    const data = error.response?._data || error.response?.data || error.data
    const status = error.response?.status || error.status
    const errorMsg = data?.error || error.message || ''

    if (status === 429) {
      await fetchAIQuota()
      const quotaInfo = data?.quota
      toastStore.error($t('market.notifications.ai_quota_exceeded', {
        limit: quotaInfo?.limit || 30
      }))
      return
    }

    const statusKey = `market.notifications.ai_error_${status}`
    const statusText = $t(statusKey) !== statusKey
      ? $t(statusKey)
      : $t('market.notifications.ai_error_unknown') + (status ? ` ${status}` : '')

    const fullMessage = errorMsg
      ? `${statusText}. ${errorMsg}`
      : statusText

    toastStore.error(`AI Analysis failed: ${fullMessage}`)
  } finally {
    aiAnalyzing.value = false
  }
}

// Remove image
const removeImage = (index) => {
  const newImages = [...props.modelValue]
  newImages.splice(index, 1)
  emit('update:modelValue', newImages)
}

onMounted(() => {
  if (props.isAuthenticated) {
    fetchAIQuota()
  }
  connectWS()
})

onUnmounted(() => {
  disconnectWS()
})
</script>
