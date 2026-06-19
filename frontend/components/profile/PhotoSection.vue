<template>
  <AccordionSection
    section-id="about"
    :title="$t('profile.about_you_title', 'About You')"
    :icon="UserCircle"
    :open-sections="openSections"
    :status="status"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-6">
      <!-- ID Photo Section -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('profile.photos.id_photo_label') }}
        </label>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.photos.id_photo_hint') }}
        </p>

        <div class="flex items-start gap-4">
          <!-- ID Photo Preview -->
          <div class="relative">
            <div
              v-if="idPhotoUrl"
              class="w-24 h-32 rounded-lg overflow-hidden border-2"
              :class="idPhotoVerified
                ? 'border-green-500'
                : 'border-amber-500'"
            >
              <img :src="idPhotoUrl" alt="ID Photo" class="w-full h-full object-cover" />
              <!-- Verification badge -->
              <div
                class="absolute top-1 right-1 rounded-full p-1"
                :class="idPhotoVerified
                  ? 'bg-green-500'
                  : 'bg-amber-500'"
              >
                <Check v-if="idPhotoVerified" class="w-3 h-3 text-white" />
                <AlertTriangle v-else class="w-3 h-3 text-white" />
              </div>
            </div>
            <div
              v-else
              class="w-24 h-32 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center border-2 border-dashed border-neutral-300 dark:border-neutral-600"
            >
              <User class="w-8 h-8 text-neutral-400" />
            </div>
            <!-- Upload overlay -->
            <label
              v-if="idPhotoUrl"
              class="absolute inset-0 rounded-lg bg-black/50 opacity-0 hover:opacity-100 flex items-center justify-center cursor-pointer transition-opacity"
            >
              <Upload class="w-6 h-6 text-white" />
              <input
                type="file"
                accept="image/*"
                class="hidden"
                @change="uploadIdPhoto"
                :disabled="idPhotoUploading"
              />
            </label>
          </div>

          <!-- ID Photo Actions -->
          <div class="flex-1">
            <!-- Verification Status -->
            <div v-if="idPhotoUrl" class="mb-3">
              <div
                class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm"
                :class="idPhotoVerified
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                  : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'"
              >
                <Check v-if="idPhotoVerified" class="w-4 h-4" />
                <AlertTriangle v-else class="w-4 h-4" />
                {{ idPhotoVerified
                  ? $t('profile.photos.verified')
                  : $t('profile.photos.not_verified') }}
              </div>
            </div>

            <!-- Verification Issues -->
            <div v-if="verificationIssues.length > 0" class="mb-3 text-sm text-amber-600 dark:text-amber-400">
              <ul class="list-disc list-inside">
                <li v-for="issue in verificationIssues" :key="issue">{{ issue }}</li>
              </ul>
            </div>

            <!-- Tips -->
            <div class="mb-3 text-xs text-neutral-500 dark:text-neutral-400 space-y-1">
              <p class="font-medium">{{ $t('profile.photos.id_tips_title') }}</p>
              <ul class="list-disc list-inside">
                <li>{{ $t('profile.photos.id_tip_1') }}</li>
                <li>{{ $t('profile.photos.id_tip_2') }}</li>
                <li>{{ $t('profile.photos.id_tip_3') }}</li>
              </ul>
            </div>

            <div class="flex gap-2">
              <label
                class="px-4 py-2 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg cursor-pointer transition-colors text-sm font-medium text-neutral-700 dark:text-neutral-300"
              >
                <span v-if="!idPhotoUploading">{{ idPhotoUrl ? $t('profile.photos.replace') : $t('profile.photos.upload') }}</span>
                <span v-else class="flex items-center gap-2">
                  <Loader2 class="w-4 h-4 animate-spin" />
                  {{ $t('profile.photos.uploading') }}
                </span>
                <input
                  type="file"
                  accept="image/*"
                  class="hidden"
                  @change="uploadIdPhoto"
                  :disabled="idPhotoUploading"
                />
              </label>
              <button
                v-if="idPhotoUrl"
                @click="deleteIdPhoto"
                :disabled="idPhotoDeleting"
                class="px-4 py-2 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 rounded-lg transition-colors text-sm font-medium text-red-700 dark:text-red-400"
              >
                <span v-if="!idPhotoDeleting">{{ $t('profile.photos.delete') }}</span>
                <span v-else>...</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Verification Photo Section -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <div class="flex items-center gap-2 mb-1">
          <ShieldCheck class="w-4 h-4 text-blue-500" />
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('profile.verification_photo.title') }}
          </label>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.verification_photo.hint') }}
        </p>

        <!-- Status -->
        <div v-if="vpStatus.has_photo" class="mb-3 flex flex-wrap items-center gap-2">
          <div
            class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm"
            :class="vpStatus.reconfirmation_needed
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
              : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'"
          >
            <AlertTriangle v-if="vpStatus.reconfirmation_needed" class="w-4 h-4" />
            <Check v-else class="w-4 h-4" />
            {{ vpStatus.reconfirmation_needed
              ? $t('profile.verification_photo.reconfirmation_warning', { count: vpStatus.reconfirmation_count })
              : $t('profile.verification_photo.status_ready') }}
          </div>
          <span
            v-if="vpStatus.face_fingerprint"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300"
            :title="$t('profile.verification_photo.fingerprint_hint', 'Biometric signature of your face — approximately stable across photos of you (most hex chars stay the same), distinct from other people')"
          >
            <Fingerprint class="w-3 h-3" />
            {{ vpStatus.face_fingerprint }}
          </span>
        </div>

        <!-- GDPR Consent checkbox -->
        <div v-if="!vpStatus.has_photo || !vpStatus.biometric_consent" class="mb-3">
          <label class="flex items-start gap-3 cursor-pointer">
            <input
              v-model="vpConsent"
              type="checkbox"
              class="mt-1 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
            />
            <span class="text-xs text-neutral-600 dark:text-neutral-400">
              {{ $t('profile.verification_photo.consent_label') }}
            </span>
          </label>
        </div>

        <!-- Upload / Replace buttons -->
        <div class="flex gap-2">
          <label
            class="px-4 py-2 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg cursor-pointer transition-colors text-sm font-medium text-neutral-700 dark:text-neutral-300"
            :class="{ 'opacity-50 pointer-events-none': vpUploading }"
          >
            <span v-if="!vpUploading">{{ vpStatus.has_photo ? $t('profile.photos.replace') : $t('profile.photos.upload') }}</span>
            <span v-else class="flex items-center gap-2">
              <Loader2 class="w-4 h-4 animate-spin" />
              {{ $t('profile.photos.uploading') }}
            </span>
            <input
              type="file"
              accept="image/*"
              class="hidden"
              @change="uploadVerificationPhoto"
              :disabled="vpUploading"
            />
          </label>
          <button
            v-if="vpStatus.has_photo"
            @click="deleteVerificationPhoto"
            :disabled="vpDeleting"
            class="px-4 py-2 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 rounded-lg transition-colors text-sm font-medium text-red-700 dark:text-red-400"
          >
            <span v-if="!vpDeleting">{{ $t('profile.photos.delete') }}</span>
            <span v-else>...</span>
          </button>
        </div>
      </div>

      <!-- Para-ID Badge Section -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          Para-ID
        </label>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.para_id_hint') }}
        </p>
        <div class="flex gap-2">
          <button
            @click="downloadBadge('single')"
            :disabled="badgeLoading"
            class="px-4 py-2 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-50 flex items-center gap-2"
          >
            <Loader2 v-if="badgeLoading" class="w-4 h-4 animate-spin" />
            <Download v-else class="w-4 h-4" />
            {{ $t('profile.badge_single') }}
          </button>
          <button
            @click="downloadBadge('batch')"
            :disabled="badgeLoading"
            class="px-4 py-2 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors text-sm font-medium text-neutral-700 dark:text-neutral-300 disabled:opacity-50 flex items-center gap-2"
          >
            <Loader2 v-if="badgeLoading" class="w-4 h-4 animate-spin" />
            <Grid3X3 v-else class="w-4 h-4" />
            {{ $t('profile.badge_batch') }}
          </button>
        </div>
      </div>

      <!-- Describe Yourself in 4 Words -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <div class="flex items-center gap-2 mb-1">
          <Brain class="w-4 h-4 text-purple-500" />
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('personality.psychhash_title') }}
          </label>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
          {{ $t('personality.psychhash_description') }}
        </p>

        <!-- 4 Word Inputs -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div v-for="i in 4" :key="i" class="relative">
            <input
              v-model="psychHash4[i - 1]"
              @input="autoSavePsychHash"
              type="text"
              :placeholder="$t('personality.word_number_placeholder', { number: i }, `Word #${i}`)"
              maxlength="50"
              class="w-full px-3 py-2.5 pr-7 text-sm bg-white dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
            <button
              v-if="psychHash4[i - 1]?.trim().length > 0"
              @click="clearWord(i - 1)"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Save indicator -->
        <div v-if="savingPsychHash" class="flex items-center gap-2 text-sm text-purple-600 dark:text-purple-400 mt-2">
          <Loader2 class="w-3.5 h-3.5 animate-spin" />
          {{ $t('personality.saving', 'Saving...') }}
        </div>

        <!-- How to get your words -->
        <details class="text-sm mt-3">
          <summary class="cursor-pointer text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 select-none">
            {{ $t('personality.how_to_get_psychhash_title') }}
          </summary>
          <div class="mt-3 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-lg p-3">
            <ol class="text-sm text-neutral-700 dark:text-neutral-300 space-y-1.5 list-decimal ml-4">
              <li>{{ $t('personality.instruction_step1') }}</li>
              <li>{{ $t('personality.instruction_step2') }}</li>
              <li>{{ $t('personality.instruction_step3') }}</li>
            </ol>
            <button
              @click="copyForm5"
              class="mt-3 btn-secondary btn-sm inline-flex items-center gap-2"
            >
              <Copy class="w-4 h-4" />
              {{ $t('personality.copy_inner_map', 'Copy Form Text') }}
            </button>
          </div>
        </details>
      </div>
    </div>
  </AccordionSection>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { UserCircle, Upload, User, Check, AlertTriangle, Loader2, Download, Grid3X3, Brain, X, Copy, ShieldCheck, Fingerprint } from 'lucide-vue-next'
import { useNotification } from '~/composables/useNotification'
import { useAuthStore } from '~/stores/auth'
import AccordionSection from './AccordionSection.vue'

const props = defineProps<{
  openSections: string[]
  status: { complete: boolean; icon?: string }
  animationEnabled: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
  'hash-loaded': [completed: boolean]
}>()

const { t, locale } = useI18n()
const { showSuccess, showError } = useNotification()
const authStore = useAuthStore()

// === ID Photo state ===
const idPhotoUrl = computed(() => authStore.user?.profile?.id_photo_url || null)
const idPhotoVerified = computed(() => authStore.user?.profile?.id_photo_verified || false)
const verificationIssues = ref<string[]>([])

const idPhotoUploading = ref(false)
const idPhotoDeleting = ref(false)
const badgeLoading = ref(false)

// === Verification Photo state ===
const vpStatus = ref<{
  has_photo: boolean
  biometric_consent?: boolean
  reconfirmation_needed?: boolean
  reconfirmation_count?: number
  face_fingerprint?: string | null
}>({ has_photo: false })
const vpConsent = ref(false)
const vpUploading = ref(false)
const vpDeleting = ref(false)

// === Psycho-hash state ===
const psychHash4 = ref<string[]>(['', '', '', ''])
const savingPsychHash = ref(false)
const psychHashSaveTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
const form5Text = ref('')

// Para-ID Badge download
async function downloadBadge(format: 'single' | 'batch') {
  badgeLoading.value = true
  try {
    await authStore.ensureToken()
    const response = await fetch(`/api/v1/profiles/me/badge/?format=${format}`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (!response.ok) throw new Error('Failed to generate badge')

    const contentDisposition = response.headers.get('Content-Disposition')
    let filename = format === 'batch' ? 'para-id-batch.pdf' : 'para-id.pdf'
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="(.+)"/)
      if (match) filename = match[1]
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    showSuccess(t('profile.badge_downloaded'))
  } catch (error) {
    console.error('Failed to download badge:', error)
    showError(t('profile.badge_download_failed'))
  } finally {
    badgeLoading.value = false
  }
}

// ID Photo upload
async function uploadIdPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  const file = input.files[0]
  if (file.size > 10 * 1024 * 1024) {
    showError(t('profile.photos.error_file_too_large'))
    return
  }

  idPhotoUploading.value = true
  verificationIssues.value = []

  try {
    await authStore.ensureToken()

    const formData = new FormData()
    formData.append('image', file)

    const response = await $fetch<{
      url: string
      verified: boolean
      verification_issues: string[] | null
    }>('/api/v1/profiles/me/id-photo/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    verificationIssues.value = response.verification_issues || []

    // Update store (computed will reflect the change)
    if (authStore.user?.profile) {
      authStore.user.profile.id_photo_url = response.url
      authStore.user.profile.id_photo_verified = response.verified
    }

    if (response.verified) {
      showSuccess(t('profile.photos.id_photo_verified_success'))
    } else {
      showSuccess(t('profile.photos.id_photo_uploaded'))
    }
  } catch (error: any) {
    console.error('ID photo upload error:', error)
    showError(error.data?.error || t('profile.photos.upload_failed'))
  } finally {
    idPhotoUploading.value = false
    input.value = '' // Reset input
  }
}

// ID Photo delete
async function deleteIdPhoto() {
  idPhotoDeleting.value = true

  try {
    await authStore.ensureToken()

    await $fetch('/api/v1/profiles/me/id-photo/', {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    verificationIssues.value = []

    // Update store (computed will reflect the change)
    if (authStore.user?.profile) {
      authStore.user.profile.id_photo_url = null
      authStore.user.profile.id_photo_verified = false
    }
    showSuccess(t('profile.photos.id_photo_deleted'))
  } catch (error: any) {
    console.error('ID photo delete error:', error)
    showError(error.data?.error || t('profile.photos.delete_failed'))
  } finally {
    idPhotoDeleting.value = false
  }
}

// === Verification Photo logic ===
async function loadVpStatus() {
  try {
    await authStore.ensureToken()
    vpStatus.value = await $fetch('/api/v1/profiles/me/verification-photo/status/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (vpStatus.value.biometric_consent) vpConsent.value = true
  } catch (error) {
    console.error('Error loading verification photo status:', error)
  }
}

async function uploadVerificationPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  if (!vpConsent.value && !vpStatus.value.biometric_consent) {
    showError(t('profile.verification_photo.consent_required'))
    input.value = ''
    return
  }

  const file = input.files[0]
  if (file.size > 10 * 1024 * 1024) {
    showError(t('profile.photos.error_file_too_large'))
    input.value = ''
    return
  }

  vpUploading.value = true
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('image', file)
    formData.append('biometric_consent', 'true')

    const response = await $fetch<{
      success: boolean
      face_detected: boolean
      reconfirmation_needed: boolean
      quality_warnings?: string[]
    }>('/api/v1/profiles/me/verification-photo/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    if (response.success) {
      showSuccess(t('profile.verification_photo.uploaded'))
      for (const w of response.quality_warnings || []) showError(w)
      await loadVpStatus()
    }
  } catch (error: any) {
    console.error('Verification photo upload error:', error)
    showError(error.data?.error || t('profile.photos.upload_failed'))
  } finally {
    vpUploading.value = false
    input.value = ''
  }
}

async function deleteVerificationPhoto() {
  vpDeleting.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/verification-photo/', {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    vpStatus.value = { has_photo: false }
    vpConsent.value = false
    showSuccess(t('profile.photos.id_photo_deleted'))
  } catch (error: any) {
    console.error('Verification photo delete error:', error)
    showError(error.data?.error || t('profile.photos.delete_failed'))
  } finally {
    vpDeleting.value = false
  }
}

// === Psycho-hash logic ===

const autoSavePsychHash = () => {
  if (psychHashSaveTimeout.value) clearTimeout(psychHashSaveTimeout.value)

  psychHashSaveTimeout.value = setTimeout(async () => {
    savingPsychHash.value = true
    try {
      await authStore.ensureToken()

      await $fetch('/api/v1/profiles/me/psych/', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`
        },
        body: {
          psych_hash_4: psychHash4.value.map(w => w.trim())
        }
      })

      // Emit completion status
      const filled = psychHash4.value.filter(w => w.trim().length > 0).length
      emit('hash-loaded', filled === 4)
    } catch (error) {
      console.error('Error auto-saving psycho-hash:', error)
    } finally {
      savingPsychHash.value = false
    }
  }, 1000)
}

const clearWord = (index: number) => {
  psychHash4.value[index] = ''
  autoSavePsychHash()
}

const loadPsychProfile = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const response: any = await $fetch('/api/v1/profiles/me/psych/', {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (response.psych_hash_4 && response.psych_hash_4.length === 4) {
      psychHash4.value = response.psych_hash_4
    }

    const filled = psychHash4.value.filter(w => w.trim().length > 0).length
    emit('hash-loaded', filled === 4)
  } catch (error) {
    console.error('Error loading psych profile:', error)
  }
}

const loadInnerRealityMap = async () => {
  try {
    const currentLocale = locale.value || 'en'
    const response = await fetch(`/locales/inner-reality-map.${currentLocale}.txt`)
    if (response.ok) {
      form5Text.value = await response.text()
    }
  } catch (error) {
    console.error('Error loading Inner Reality Map:', error)
  }
}

const copyForm5 = () => {
  navigator.clipboard.writeText(form5Text.value).then(() => {
    showSuccess(t('personality.copy_form_text_alert'))
  }).catch(() => {
    showError(t('personality.copy_failed'))
  })
}

watch(locale, () => {
  loadInnerRealityMap()
})

onMounted(async () => {
  await Promise.all([loadPsychProfile(), loadInnerRealityMap(), loadVpStatus()])
})
</script>
