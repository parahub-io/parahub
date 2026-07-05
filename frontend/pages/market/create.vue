<template>
  <div class="pb-6">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-center gap-3 mb-2">
          <UiButton variant="ghost" :icon="X" icon-only :aria-label="$t('common.close')" @click="navigateTo(localePath(isEditMode ? `/market/${editItemId}` : '/market'))" />
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ isEditMode ? $t('market.edit_modal.title') : $t('market.create_modal.title') }}
          </h1>
        </div>
      </div>

      <!-- Loading edit data -->
      <div v-if="loadingEdit" class="py-12 text-center" role="status" aria-live="polite">
        <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Published: nudge to declare a want (barter demand generation) -->
      <div v-else-if="justCreated" class="space-y-6">
        <div class="flex items-center gap-2 text-green-600 dark:text-green-400">
          <CheckCircle2 class="w-5 h-5 shrink-0" />
          <span class="text-sm font-medium">{{ $t('barter.create_nudge.published') }}</span>
        </div>

        <div class="card p-5 space-y-4 border-2 border-primary/30">
          <div class="flex items-start gap-3">
            <RefreshCw class="w-6 h-6 text-secondary shrink-0 mt-0.5" />
            <div>
              <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {{ $t('barter.create_nudge.heading') }}
              </h2>
              <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                {{ $t('barter.create_nudge.explainer') }}
              </p>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('barter.create_nudge.category_label') }}
            </label>
            <CategorySelect
              v-model="wantCategoryId"
              :placeholder="$t('market.create_modal.category_placeholder')"
              mode="create"
              domain="market"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('barter.create_nudge.title_label') }}
            </label>
            <input
              v-model="wantTitle"
              type="text"
              maxlength="255"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              :placeholder="$t('barter.create_nudge.title_placeholder')"
              @keydown.enter.prevent="addWant"
            >
          </div>

          <div class="flex flex-col sm:flex-row gap-3 pt-1">
            <UiButton
              :loading="creatingWant"
              :disabled="creatingWant || !wantCategoryId || !wantTitle.trim()"
              class="flex-1"
              @click="addWant"
            >
              {{ $t('barter.create_nudge.add') }}
            </UiButton>
            <UiButton variant="outline" class="flex-1" :disabled="creatingWant" @click="skipWant">
              {{ $t('barter.create_nudge.skip') }}
            </UiButton>
          </div>
        </div>
      </div>

      <!-- Form -->
      <form v-else @submit.prevent="submitForm" class="space-y-6">
        <!-- Type selection -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
            {{ $t('market.create_modal.type_label') || 'Type' }} <span class="text-red-500">*</span>
          </label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label class="relative">
              <input
                v-model="newItem.type"
                type="radio"
                value="CREDIT"
                class="peer sr-only"
              >
              <div class="px-4 py-3 border-2 rounded-lg cursor-pointer peer-checked:border-primary peer-checked:bg-primary peer-checked:bg-opacity-10 border-neutral-300 dark:border-neutral-600">
                <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.create_modal.type_offer') }}</div>
                <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('market.create_modal.type_offer_desc') }}</div>
              </div>
            </label>

            <label class="relative">
              <input
                v-model="newItem.type"
                type="radio"
                value="DEBIT"
                class="peer sr-only"
              >
              <div class="px-4 py-3 border-2 rounded-lg cursor-pointer peer-checked:border-primary peer-checked:bg-primary peer-checked:bg-opacity-10 border-neutral-300 dark:border-neutral-600">
                <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.create_modal.type_request') }}</div>
                <div class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('market.create_modal.type_request_desc') }}</div>
              </div>
            </label>
          </div>
        </div>

        <!-- Voice dictation button (create mode only) -->
        <div v-if="!isEditMode" class="flex flex-col items-center gap-2">
          <button
            type="button"
            :disabled="voiceProcessing"
            class="flex items-center gap-2 px-4 py-2.5 rounded-lg border-2 transition-all duration-200"
            :class="voiceRecording
              ? 'border-red-500 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 animate-pulse'
              : voiceProcessing
                ? 'border-neutral-300 dark:border-neutral-600 bg-neutral-100 dark:bg-neutral-800 text-neutral-400 cursor-wait'
                : 'border-primary/50 bg-primary-100 dark:bg-primary-900/30 text-neutral-700 dark:text-neutral-200 hover:border-primary hover:bg-primary-100 dark:hover:bg-primary-900/40'"
            @click="toggleVoiceRecording"
          >
            <component :is="voiceRecording ? MicOff : voiceProcessing ? Loader2 : Mic"
              :class="['w-5 h-5', voiceProcessing ? 'animate-spin' : '']" />
            <span class="text-sm font-medium">
              {{ voiceRecording
                ? $t('market.create_modal.voice_recording')
                : voiceProcessing
                  ? $t('market.create_modal.voice_processing')
                  : $t('market.create_modal.voice_dictate') }}
            </span>
          </button>
          <!-- Voice error/feedback message -->
          <p v-if="voiceMessage" class="text-sm text-neutral-600 dark:text-neutral-400 text-center max-w-md">
            {{ voiceMessage }}
          </p>
        </div>

        <!-- Post as establishment (create + edit) -->
        <EstablishmentSelector v-model="newItem.establishment_id" />

        <!-- Images (AI-powered analysis, create mode only) -->
        <MarketCreateImageUpload
          v-if="!isEditMode"
          v-model="newItem.images"
          :is-authenticated="authStore.isAuthenticated"
          :visible="!!newItem.type"
          :item-type="newItem.type"
          @location-detected="onLocationDetected"
          @ai-result="onAIResult"
        />

        <!-- Media (edit mode: photos + video in one orderable strip, saved immediately) -->
        <MarketMediaManager
          v-else-if="loadedEditId"
          :item-id="editItemId"
          :initial-photos="editImages"
        />

        <!-- Category -->
        <div ref="categoryField">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('market.create_modal.category_label') }} <span class="text-red-500">*</span>
          </label>
          <CategorySelect
            v-model="newItem.category_id"
            :placeholder="$t('market.create_modal.category_placeholder')"
            :required="true"
            mode="create"
            domain="market"
            @change="onCategorySelect"
          />
        </div>

        <!-- Title -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('market.create_modal.title_label') }} <span class="text-red-500">*</span>
          </label>
          <input
            ref="titleField"
            v-model="newItem.title"
            type="text"
            required
            maxlength="255"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('market.create_modal.title_placeholder')"
          >
        </div>

        <!-- Description -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('market.create_modal.description_label') }}
          </label>
          <textarea
            ref="descriptionField"
            v-model="newItem.description"
            rows="4"
            maxlength="5000"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :placeholder="$t('market.create_modal.description_placeholder')"
          ></textarea>
        </div>

        <!-- Pricing Options -->
        <MarketCreatePricingOptions
          ref="pricingComponent"
          v-model="newItem.pricing_options"
          :can-rent="canRentInCategory"
          :currency="userCurrency"
        />

        <!-- Location -->
        <MarketCreateLocationSection
          v-model="newItem.location"
        />

        <!-- Made by hand (own production) — offers only; you can't "make" a request -->
        <div v-if="newItem.type === 'CREDIT'">
          <label class="flex items-start gap-3 cursor-pointer p-3 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <input
              type="checkbox"
              v-model="newItem.self_made"
              class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary shrink-0"
            >
            <div>
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.create_modal.self_made_label') }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('market.create_modal.self_made_desc') }}</div>
            </div>
          </label>
        </div>

        <!-- International listing toggle -->
        <div>
          <label class="flex items-start gap-3 cursor-pointer p-3 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <input
              type="checkbox"
              v-model="newItem.is_international"
              class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary shrink-0"
            >
            <div>
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.create_modal.international_label') }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('market.create_modal.international_desc') }}</div>
            </div>
          </label>
        </div>

        <!-- Audience scope: public by default, or registered-only (hidden from anonymous + search) -->
        <div>
          <label class="flex items-start gap-3 cursor-pointer p-3 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <input
              type="checkbox"
              v-model="registeredOnly"
              class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary shrink-0"
            >
            <div>
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('market.create_modal.visibility_label') }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('market.create_modal.visibility_desc') }}</div>
            </div>
          </label>
        </div>

        <!-- Submit buttons -->
        <div class="space-y-3 pt-6 border-t border-neutral-200 dark:border-neutral-700">
          <UiButton type="submit" :loading="creating" :disabled="creating" class="w-full">
            {{ isEditMode
              ? (creating ? $t('market.edit_modal.saving') : $t('market.edit_modal.save'))
              : (creating ? $t('market.create_modal.submitting') : $t('market.create_modal.submit'))
            }}
          </UiButton>
          <UiButton type="button" variant="outline" class="w-full" @click="navigateTo(localePath(isEditMode ? `/market/${editItemId}` : '/market'))">
            {{ $t('market.create_modal.cancel') }}
          </UiButton>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useMapStore } from '~/stores/map'
import { X, Mic, MicOff, Loader2, CheckCircle2, RefreshCw } from 'lucide-vue-next'
import CategorySelect from '~/components/CategorySelect.vue'

const route = useRoute()
const authStore = useAuthStore()
const localePath = useLocalePath()
const mapStore = useMapStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()

// Edit mode
const editItemId = computed(() => String(route.query.edit || ''))
const isEditMode = computed(() => !!editItemId.value)
const loadingEdit = ref(false)
const editVersion = ref(0)

// Reactive state
const creating = ref(false)
const aiAnalysisLogId = ref(null)

// Voice dictation state
const voiceRecording = ref(false)
const voiceProcessing = ref(false)
const voiceMessage = ref('')
let mediaRecorder = null
let audioChunks = []

// Field refs for flash animation
const titleField = ref(null)
const descriptionField = ref(null)
const pricingComponent = ref(null)
const categoryField = ref(null)

// Currency preference (localStorage, shared with useBtcPrice)
const userCurrency = useLocalPref('preferred_currency', 'EUR')

// Form data
const defaultItem = () => ({
  type: 'CREDIT',
  category_id: '',
  title: '',
  description: '',
  pricing_options: [{ type: 'sale', amount: null, currency: userCurrency.value, unit: '', note: '' }],
  accepted_payment_methods: ['parahub_ln', 'bank_transfer', 'cash'],
  tags: '',
  location: {
    latitude: null,
    longitude: null
  },
  images: [],
  is_international: false,
  self_made: false,
  visibility: 'PUBLIC',
  establishment_id: null
})

const newItem = ref(defaultItem())

// Audience scope as a simple "registered-only" toggle over the visibility enum
// (PUBLIC default ⇄ REGISTERED). A future CIRCLE tier would turn this into a select.
const registeredOnly = computed({
  get: () => newItem.value.visibility === 'REGISTERED',
  set: (v) => { newItem.value.visibility = v ? 'REGISTERED' : 'PUBLIC' },
})

// ULID of the item whose data is currently loaded into the form (edit mode), null in create mode
const loadedEditId = ref(null)

// Existing photos of the item being edited ([{ id, url, order, caption }]) — seeds
// MarketMediaManager, which then owns photos+video live (uploads/deletes/reorder
// hit the API immediately).
const editImages = ref([])

// Selected category object for sale_only check
const selectedCategoryObject = ref(null)

// Barter demand-generation nudge: after publishing an OFFER, capture what the
// user wants in return (a DEBIT item) inline, without a second full form.
// justCreated holds the just-published offer ({id, slug, establishment_id}) and
// flips the page into the success/nudge step; null = normal create form.
const justCreated = ref(null)
const wantCategoryId = ref('')
const wantTitle = ref('')
const creatingWant = ref(false)

// The page instance survives navigation (app-wide KeepAlive in app.vue) — without an explicit
// reset, the next visit shows the previous item's fields
const resetForm = () => {
  newItem.value = defaultItem()
  selectedCategoryObject.value = null
  aiAnalysisLogId.value = null
  voiceMessage.value = ''
  editVersion.value = 0
  loadedEditId.value = null
  editImages.value = []
  wantCategoryId.value = ''
  wantTitle.value = ''
}

// Pre-select offer/request from ?type= (e.g. the barter tab's "Add a request" → DEBIT).
// No-op in edit mode (type comes from the loaded item) or for any other value.
const applyQueryType = () => {
  if (isEditMode.value) return
  const t = String(route.query.type || '').toUpperCase()
  if (t === 'CREDIT' || t === 'DEBIT') {
    newItem.value.type = t
  }
}

const canRentInCategory = computed(() => {
  return !selectedCategoryObject.value?.sale_only
})

// Category selection handler
const onCategorySelect = (category) => {
  selectedCategoryObject.value = category

  if (category?.sale_only) {
    newItem.value.pricing_options.forEach(opt => {
      if (opt.type === 'rent') {
        opt.type = 'sale'
      }
    })
  }
}

// Flash animation for auto-filled fields
const flashField = (fieldName) => {
  let element = null

  if (fieldName === 'title' && titleField.value) {
    element = titleField.value
  } else if (fieldName === 'description' && descriptionField.value) {
    element = descriptionField.value
  } else if (fieldName === 'pricing' && pricingComponent.value?.pricingContainer) {
    element = pricingComponent.value.pricingContainer
  } else if (fieldName === 'category' && categoryField.value) {
    element = categoryField.value
  }

  if (element) {
    element.classList.add('field-flash')
    setTimeout(() => {
      element.classList.remove('field-flash')
    }, 400)
  }
}

// --- Voice dictation ---
const toggleVoiceRecording = async () => {
  if (voiceRecording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

const startRecording = async () => {
  voiceMessage.value = ''
  audioChunks = []

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true }
    })

    // Pick supported mime type
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'

    mediaRecorder = new MediaRecorder(stream, { mimeType })

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.onstop = async () => {
      // Stop all tracks
      stream.getTracks().forEach(t => t.stop())

      const blob = new Blob(audioChunks, { type: mimeType })
      if (blob.size < 1000) {
        voiceMessage.value = $t('market.create_modal.voice_error_short')
        return
      }
      await sendVoiceAudio(blob)
    }

    mediaRecorder.start()
    voiceRecording.value = true
  } catch (err) {
    console.error('Mic access error:', err)
    voiceMessage.value = $t('market.create_modal.voice_error_mic')
  }
}

const stopRecording = () => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  voiceRecording.value = false
}

const sendVoiceAudio = async (blob) => {
  voiceProcessing.value = true
  voiceMessage.value = ''

  try {
    await authStore.ensureToken()

    const formData = new FormData()
    formData.append('audio', blob, 'recording.webm')

    const result = await $fetch('/api/v1/ai/voice-to-listing/', {
      method: 'POST',
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      credentials: 'include',
      body: formData
    })

    // Check for error message from AI
    if (result.error_message && result.confidence < 0.3) {
      voiceMessage.value = result.error_message
      return
    }

    // Show transcript as feedback
    if (result.transcript) {
      voiceMessage.value = `"${result.transcript}"`
    }

    // Fill form fields with flash animations
    if (result.item_type) {
      newItem.value.type = result.item_type
    }

    if (result.title) {
      newItem.value.title = result.title
      flashField('title')
    }

    if (result.description) {
      setTimeout(() => {
        newItem.value.description = result.description
        flashField('description')
      }, 150)
    }

    if (result.category_id) {
      setTimeout(() => {
        newItem.value.category_id = result.category_id
        flashField('category')
      }, 300)
    }

    if (result.pricing_options?.length > 0) {
      setTimeout(() => {
        newItem.value.pricing_options = result.pricing_options.map(po => ({
          type: po.type || 'sale',
          amount: po.amount,
          currency: po.currency || userCurrency.value,
          unit: po.unit || '',
          note: po.note || ''
        }))
        flashField('pricing')
      }, 450)
    }

    if (result.is_international) {
      newItem.value.is_international = true
    }

    // Show low-confidence warning
    if (result.error_message) {
      voiceMessage.value = result.error_message
    }

  } catch (err) {
    console.error('Voice-to-listing error:', err)
    const errData = err.data || err.response?._data
    voiceMessage.value = errData?.error || $t('market.create_modal.voice_error_generic')
  } finally {
    voiceProcessing.value = false
  }
}

// Handle location detected from image EXIF
const onLocationDetected = (coords) => {
  newItem.value.location.latitude = coords.latitude
  newItem.value.location.longitude = coords.longitude
}

// Handle AI analysis result
const onAIResult = (result) => {
  if (result.source === 'websocket') {
    // WebSocket progress: fill title, description, price with delays
    const title = result.title?.substring(0, 50) || ''
    const price = result.suggested_price

    if (title) {
      newItem.value.title = result.title
      flashField('title')
    }

    if (price && price.amount) {
      setTimeout(() => {
        newItem.value.pricing_options = [price]
        flashField('pricing')
      }, 150)
    }

    if (result.description) {
      setTimeout(() => {
        newItem.value.description = result.description
        flashField('description')
      }, 300)
    }
  } else {
    // HTTP response: category + fallback fields
    if (result.category_id) {
      newItem.value.category_id = result.category_id
      flashField('category')
    }

    // Fallback: fill fields if WebSocket didn't
    if (!newItem.value.title && result.title) {
      newItem.value.title = result.title
      flashField('title')
    }

    if (result.description) {
      newItem.value.description = result.description
      flashField('description')
    }

    const pricingIsEmpty = newItem.value.pricing_options.every(opt => !opt.amount)
    if (pricingIsEmpty && result.suggested_price && result.suggested_price.amount) {
      newItem.value.pricing_options = [result.suggested_price]
      flashField('pricing')
    }

    aiAnalysisLogId.value = result.log_id
  }
}

// Load existing item data for edit mode
const loadEditData = async () => {
  if (!editItemId.value) return

  loadingEdit.value = true
  try {
    await authStore.ensureToken()
    const item = await $fetch(`/api/v1/items/${editItemId.value}/`)

    // Pre-fill form
    newItem.value.type = item.item_type || 'CREDIT'
    newItem.value.title = item.title || ''
    newItem.value.description = item.description || ''
    newItem.value.category_id = item.category_id || ''
    newItem.value.is_international = item.is_international || false
    newItem.value.self_made = item.self_made || false
    newItem.value.visibility = item.visibility || 'PUBLIC'
    newItem.value.establishment_id = item.establishment_id || null

    // Location (API returns fuzzed {latitude, longitude})
    if (item.location) {
      newItem.value.location.latitude = item.location.latitude
      newItem.value.location.longitude = item.location.longitude
    }

    // Pricing options
    if (item.pricing_options?.length > 0) {
      newItem.value.pricing_options = item.pricing_options.map(opt => ({
        type: opt.type || 'sale',
        amount: opt.amount || null,
        currency: opt.currency || userCurrency.value,
        unit: opt.unit || '',
        note: opt.note || ''
      }))
    } else {
      newItem.value.pricing_options = [{ type: 'sale', amount: null, currency: userCurrency.value, unit: '', note: '' }]
    }

    // Existing photos for the edit-mode image manager (sorted by display order)
    editImages.value = (item.images || [])
      .map(img => ({ id: img.id, url: img.url, order: img.order, caption: img.caption || '' }))
      .sort((a, b) => a.order - b.order)

    editVersion.value = item.version || 0
    loadedEditId.value = editItemId.value
  } catch (error) {
    console.error('Failed to load item for editing:', error)
    toastStore.error($t('market.notifications.load_error'))
    navigateTo(localePath('/market'))
  } finally {
    loadingEdit.value = false
  }
}

// Submit dispatcher
const submitForm = () => {
  if (isEditMode.value) {
    updateItem()
  } else {
    createItem()
  }
}

// Update existing item
const updateItem = async () => {
  creating.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      toastStore.error($t('market.notifications.login_required'))
      return
    }

    // Clean pricing_options
    const cleanPricingOptions = newItem.value.pricing_options
      .filter(opt => {
        if (opt.type === 'free') return true
        if (!opt.amount || opt.amount <= 0) return false
        return true
      })
      .map(opt => {
        const cleaned = { type: opt.type }
        if (opt.type !== 'free') {
          cleaned.amount = opt.amount
          cleaned.currency = opt.currency
        }
        if (opt.unit) cleaned.unit = opt.unit
        if (opt.note) cleaned.note = opt.note
        return cleaned
      })

    const payload = {
      title: newItem.value.title,
      description: newItem.value.description,
      category_id: newItem.value.category_id || undefined,
      pricing_options: cleanPricingOptions,
      self_made: newItem.value.self_made,
      visibility: newItem.value.visibility,
      // '' detaches (post personally); a ULID attaches the establishment
      establishment_id: newItem.value.establishment_id || '',
      expected_version: editVersion.value
    }

    if (newItem.value.location.latitude && newItem.value.location.longitude) {
      payload.location = newItem.value.location
    }

    await $fetch(`/api/v1/items/${editItemId.value}/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include',
      body: payload
    })

    toastStore.success($t('market.notifications.updated'))
    useState('marketDirty', () => false).value = true

    // Seed the detail page's useAsyncData cache with the fresh item BEFORE we
    // navigate. market/[id].vue is kept-alive and reads `useAsyncData(`item-${id}`)`;
    // on (re)mount that serves the pre-edit payload, and the page's onActivated
    // refresh deliberately skips the first activation — so the just-saved edit would
    // render stale until a hard reload (the bug). useNuxtData shares the ref by key,
    // so this also updates a live kept-alive instance. Seed both the ULID and slug
    // keys since the page may have been opened by either. Same endpoint as the page,
    // so no shape mismatch and no blank flash.
    try {
      const fresh = await $fetch(`/api/v1/items/${editItemId.value}/`)
      for (const key of [fresh?.id, fresh?.slug].filter(Boolean)) {
        useNuxtData(`item-${key}`).data.value = fresh
      }
    } catch (e) {
      console.error('Failed to refresh item cache after edit:', e)
    }

    await navigateTo(localePath(`/market/${editItemId.value}`))
  } catch (error) {
    console.error('Failed to update item:', error)
    const data = error.data || error.response?._data
    toastStore.error(`${$t('market.notifications.update_error')} ${data?.error || error.message || ''}`)
  } finally {
    creating.value = false
  }
}

// Create item
const createItem = async () => {
  creating.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      toastStore.error($t('market.notifications.login_required'))
      return
    }

    // Clean pricing_options
    const cleanPricingOptions = newItem.value.pricing_options
      .filter(opt => {
        if (opt.type === 'free') return true
        if (!opt.amount || opt.amount <= 0) return false
        return true
      })
      .map(opt => {
        const cleaned = { type: opt.type }
        if (opt.type !== 'free') {
          cleaned.amount = opt.amount
          cleaned.currency = opt.currency
        }
        if (opt.unit) {
          cleaned.unit = opt.unit
        }
        if (opt.note) {
          cleaned.note = opt.note
        }
        return cleaned
      })

    const itemData = {
      item_type: newItem.value.type,
      category_id: newItem.value.category_id,
      title: newItem.value.title,
      description: newItem.value.description,
      pricing_options: cleanPricingOptions,
      accepted_payment_methods: newItem.value.accepted_payment_methods,
      location: newItem.value.location.latitude && newItem.value.location.longitude
        ? newItem.value.location
        : null,
      is_international: newItem.value.is_international,
      self_made: newItem.value.self_made,
      visibility: newItem.value.visibility,
      ai_analysis_log_id: aiAnalysisLogId.value,
      establishment_id: newItem.value.establishment_id || undefined
    }

    const itemResponse = await $fetch('/api/v1/items/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include',
      body: itemData
    })

    // Upload images if any
    if (newItem.value.images.length > 0) {
      const itemId = itemResponse.id

      for (let i = 0; i < newItem.value.images.length; i++) {
        const formData = new FormData()
        formData.append('image', newItem.value.images[i].file)
        formData.append('order', i)
        formData.append('caption', '')

        try {
          await $fetch(`/api/v1/items/${itemId}/images/`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${authStore.accessToken}`
            },
            credentials: 'include',
            body: formData
          })
        } catch (imgError) {
          console.error(`Failed to upload image ${i}:`, imgError)
        }
      }
    }

    useState('marketDirty', () => false).value = true

    // Capture the published offer before resetForm() wipes the draft
    const created = {
      id: itemResponse.id,
      slug: itemResponse.slug,
      establishment_id: newItem.value.establishment_id || null,
    }
    const wasOffer = newItem.value.type === 'CREDIT'
    resetForm()
    toastStore.success($t('market.notifications.created'))

    if (wasOffer) {
      // Demand-generation nudge: turn a one-sided offer into a two-sided barter
      // intent by capturing what the user wants in return (see addWant/skipWant)
      justCreated.value = created
    } else {
      // A request is already the demand side — no nudge needed
      await navigateTo(localePath(`/market/${created.slug || created.id}`))
    }
  } catch (error) {
    console.error('Failed to create item:', error)

    const data = error.data || error.response?._data || error.response?.data
    const status = error.status || error.response?.status

    const formatDetails = (details) => {
      if (!details) return ''
      if (typeof details === 'string') return details
      if (Array.isArray(details)) {
        return details.map(err => {
          const field = err.loc ? err.loc.join('.') : 'field'
          return `${field}: ${err.msg || err.message || 'invalid'}`
        }).join(', ')
      }
      if (typeof details === 'object') {
        try {
          return JSON.stringify(details, null, 2)
        } catch (e) {
          return String(details)
        }
      }
      return String(details)
    }

    const detailsFormatted = data?.details ? formatDetails(data.details) : ''

    const errorMessages = {
      401: 'Please log in again.',
      404: data?.error || 'Category not found.',
      400: data?.error ? `${data.error}${detailsFormatted ? ` (${detailsFormatted})` : ''}` : 'Please check your input fields.',
      500: `Server error. ${data?.error || ''}${detailsFormatted ? ` Details: ${detailsFormatted}` : ''}`.trim()
    }

    toastStore.error(`${$t('market.notifications.create_error')} ${errorMessages[status] || error.message || ''}`)
  } finally {
    creating.value = false
  }
}

// Create the matching request (DEBIT) from the post-publish nudge, then land on
// the barter tab so the user sees both sides of their new exchange intent.
const addWant = async () => {
  if (!wantCategoryId.value || !wantTitle.value.trim() || creatingWant.value) return
  creatingWant.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.accessToken) {
      toastStore.error($t('market.notifications.login_required'))
      return
    }

    await $fetch('/api/v1/items/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include',
      body: {
        item_type: 'DEBIT',
        category_id: wantCategoryId.value,
        title: wantTitle.value.trim(),
        description: '',
        pricing_options: [],
        accepted_payment_methods: [],
        is_international: false,
        self_made: false,
        visibility: 'PUBLIC',
        establishment_id: justCreated.value?.establishment_id || undefined
      }
    })

    useState('marketDirty', () => false).value = true
    justCreated.value = null
    wantCategoryId.value = ''
    wantTitle.value = ''
    toastStore.success($t('barter.create_nudge.added'))
    await navigateTo(localePath({ path: '/market/my', query: { tab: 'barter' } }))
  } catch (error) {
    const data = error.data || error.response?._data || error.response?.data
    toastStore.error(`${$t('market.notifications.create_error')} ${data?.error || error.message || ''}`)
  } finally {
    creatingWant.value = false
  }
}

// Skip the nudge: go to the offer that was just published
const skipWant = async () => {
  const dest = justCreated.value
  justCreated.value = null
  wantCategoryId.value = ''
  wantTitle.value = ''
  await navigateTo(localePath(`/market/${dest?.slug || dest?.id || ''}`))
}

// Set page meta
definePageMeta({
  middleware: ['auth'],
  ssr: false
})

// ESC handler
const handleEscape = (event) => {
  if (event.key === 'Escape') {
    navigateTo(localePath('/market'))
  }
}

// Watch for coordinate changes to update global map marker (without moving the main map)
watch(() => [newItem.value.location.latitude, newItem.value.location.longitude], ([lat, lon]) => {
  if (lat && lon) {
    mapStore.addMarker({
      id: 'item-location',
      coordinates: [lon, lat],
      type: 'item'
    })
  } else {
    mapStore.removeMarker('item-location')
  }
})

onMounted(async () => {
  if (isEditMode.value) {
    // Edit mode: load existing item data
    await loadEditData()
  } else {
    applyQueryType()
  }

  window.addEventListener('keydown', handleEscape)
})

// KeepAlive re-entry: onMounted/onUnmounted do not fire on a cached instance,
// so listeners/markers and form↔route sync must be handled here
let hasActivated = false
onActivated(() => {
  window.addEventListener('keydown', handleEscape)

  // A re-entry always starts on the form, never on a stale post-publish nudge
  // (addWant/skipWant navigate away, so this only matters on KeepAlive return)
  justCreated.value = null

  // Restore the map marker removed on deactivation
  const { latitude, longitude } = newItem.value.location
  if (latitude && longitude) {
    mapStore.addMarker({
      id: 'item-location',
      coordinates: [longitude, latitude],
      type: 'item'
    })
  }

  if (!hasActivated) {
    // First activation fires right after onMounted — already initialized there
    hasActivated = true
    return
  }

  if (isEditMode.value) {
    // Always refetch: the item (and its version) may have changed since last load
    loadEditData()
  } else if (loadedEditId.value) {
    // Last use was edit mode — don't leak that item's fields into the create form
    resetForm()
  }
  // Create-mode re-entry with no prior edit keeps the unsubmitted draft (deliberate)
  // An explicit ?type= (e.g. barter "Add a request" → DEBIT) still wins.
  applyQueryType()
})

onDeactivated(() => {
  window.removeEventListener('keydown', handleEscape)

  if (voiceRecording.value) {
    stopRecording()
  }

  mapStore.removeMarker('item-location')
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleEscape)

  // Stop recording if still active
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }

  mapStore.removeMarker('item-location')
})
</script>

<style scoped>
/* Flash animation for AI auto-filled fields */
@keyframes flash-border {
  0% {
    box-shadow: 0 0 0 0 rgba(255, 226, 22, 0);
    border-color: inherit;
  }
  50% {
    box-shadow: 0 0 12px 4px rgba(255, 226, 22, 0.7);
    border-color: #FFE216;
  }
  100% {
    box-shadow: 0 0 0 0 rgba(255, 226, 22, 0);
    border-color: inherit;
  }
}

.field-flash {
  animation: flash-border 0.4s ease-out;
}

.field-flash :deep(input),
.field-flash :deep(textarea),
.field-flash :deep(select),
.field-flash :deep([role="combobox"]),
.field-flash :deep(.category-select) {
  animation: flash-border 0.4s ease-out;
}
</style>
