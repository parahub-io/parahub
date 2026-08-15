<template>
  <AccordionSection
    section-id="about"
    :title="$t('profile.about_you_title', 'Identity & Trust')"
    :icon="UserCircle"
    :open-sections="openSections"
    :status="status"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-6">
      <!-- Verification Photo Section — the key to the Web of Trust, so it comes first -->
      <div>
        <div class="flex flex-wrap items-center gap-2 mb-1">
          <ShieldCheck class="w-4 h-4 text-blue-500" />
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('profile.verification_photo.title') }}
          </label>
          <UiBadge v-if="wotStatus" :variant="wotStatus.is_verified ? 'success' : 'neutral'" size="sm">
            {{ wotStatus.is_verified
              ? $t('profile.verification_photo.wot_verified')
              : $t('profile.verification_photo.wot_progress', { count: wotStatus.verification_count }) }}
          </UiBadge>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.verification_photo.hint') }}
          <NuxtLink :to="localePath('/docs/wot')" class="text-link whitespace-nowrap">{{ $t('profile.verification_photo.learn_more') }}</NuxtLink>
        </p>

        <div class="flex items-start gap-4">
          <!-- Stored photo preview: the WoT photo is otherwise invisible to its owner,
               so a replacement of the Para-ID photo can look like it changed this one -->
          <div
            v-if="vpStatus.has_photo"
            class="w-24 h-32 rounded-lg overflow-hidden border-2 border-blue-500 flex-shrink-0"
          >
            <img
              v-if="vpPhotoSrc"
              :src="vpPhotoSrc"
              :alt="$t('profile.verification_photo.title')"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full flex items-center justify-center bg-neutral-100 dark:bg-neutral-800">
              <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
            </div>
          </div>
          <div
            v-else
            class="w-24 h-32 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center border-2 border-dashed border-neutral-300 dark:border-neutral-600 flex-shrink-0"
          >
            <ShieldCheck class="w-8 h-8 text-neutral-400" />
          </div>

          <div class="flex-1 min-w-0">
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

            <!-- What actually clears the pending round — otherwise the warning above
                 reads as something the owner is powerless to resolve -->
            <p
              v-if="vpStatus.has_photo && vpStatus.reconfirmation_needed"
              class="mb-3 text-xs text-neutral-600 dark:text-neutral-400"
            >
              {{ $t('profile.verification_photo.reconfirmation_hint') }}
            </p>

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
                class="btn-outline btn-sm cursor-pointer"
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
                class="btn-outline-error btn-sm"
              >
                <span v-if="!vpDeleting">{{ $t('profile.photos.delete') }}</span>
                <span v-else>...</span>
              </button>
            </div>

            <!-- Who opened the photo (GDPR Art.15(1)(c) recipients). Rows outlive
                 the photo, so the log stays up after an erasure — that is the
                 case where "who saw it" is hardest to answer any other way. -->
            <PhotoAccessLog
              v-if="vpStatus.has_photo || vpAccesses.length"
              :title="$t('profile.verification_photo.access_log_title')"
              :accesses="vpAccesses"
            />
          </div>
        </div>
      </div>

      <!-- Derived photos: built from the verification photo on explicit request.
           The Para-ID photo is an exact face crop (no AI redraw — it is printed on
           an identity card); the avatar is the brand watercolor restyle. -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
        <div class="flex items-center gap-2 mb-1">
          <Sparkles class="w-4 h-4 text-secondary dark:text-secondary-400" />
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ $t('profile.photos.derived_title') }}
          </label>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
          {{ $t('profile.photos.derived_hint') }}
        </p>

        <div class="space-y-6">
          <!-- Para-ID row: photo (input) + live card preview + actions -->
          <div class="flex flex-wrap items-start gap-4">
            <!-- Card photo (input) -->
            <div class="relative flex-shrink-0">
              <div
                v-if="idPhotoUrl"
                class="w-24 h-32 rounded-lg overflow-hidden border-2"
                :class="idPhotoVerified
                  ? 'border-green-500'
                  : 'border-amber-500'"
              >
                <img v-if="idPhotoSrc" :src="idPhotoSrc" :alt="$t('profile.photos.id_photo_label')" class="w-full h-full object-cover" />
                <div v-else class="w-full h-full flex items-center justify-center bg-neutral-100 dark:bg-neutral-800">
                  <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
                </div>
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

            <!-- Live card preview, rendered server-side from the same generator as the PDF -->
            <div class="w-20 flex-shrink-0 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 bg-white" style="aspect-ratio: 54 / 86">
              <img
                v-if="badgePreviewSrc"
                :src="badgePreviewSrc"
                alt="Para-ID"
                class="w-full h-full object-contain"
              />
              <div v-else class="w-full h-full flex items-center justify-center">
                <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
              </div>
            </div>

            <!-- Photo + card actions -->
            <div class="flex-1 min-w-[14rem]">
              <div class="flex flex-wrap items-center gap-2 mb-1">
                <IdCard class="w-4 h-4 text-secondary dark:text-secondary-400" />
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {{ $t('profile.para_id_title', 'Para-ID — printable card') }}
                </label>
                <div
                  v-if="idPhotoUrl"
                  class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs"
                  :class="idPhotoVerified
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                    : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'"
                >
                  <Check v-if="idPhotoVerified" class="w-3.5 h-3.5" />
                  <AlertTriangle v-else class="w-3.5 h-3.5" />
                  {{ idPhotoVerified
                    ? $t('profile.photos.verified')
                    : $t('profile.photos.not_verified') }}
                </div>
              </div>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
                {{ $t('profile.para_id_hint') }}
              </p>

              <!-- Where this photo shows up. Stays in the open: the card is the
                   obvious destination, the public profile is not, and a reader
                   who just learned the source photo is private would otherwise
                   assume its crop is private too. -->
              <p class="flex items-start gap-1.5 text-xs text-neutral-600 dark:text-neutral-300 mb-2">
                <Eye class="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-neutral-400" />
                <span>{{ $t('profile.photos.id_photo_visibility') }}</span>
              </p>

              <!-- Verification Issues -->
              <div v-if="verificationIssues.length > 0" class="mb-2 text-sm text-amber-600 dark:text-amber-400">
                <ul class="list-disc list-inside">
                  <li v-for="issue in verificationIssues" :key="issue">{{ issue }}</li>
                </ul>
              </div>

              <!-- Tips (collapsed) -->
              <details class="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
                <summary class="cursor-pointer select-none hover:text-neutral-700 dark:hover:text-neutral-300">
                  {{ $t('profile.photos.id_tips_title') }}
                </summary>
                <p class="mt-1">{{ $t('profile.photos.id_photo_hint') }}</p>
                <ul class="list-disc list-inside mt-1 space-y-1">
                  <li>{{ $t('profile.photos.id_tip_1') }}</li>
                  <li>{{ $t('profile.photos.id_tip_2') }}</li>
                  <li>{{ $t('profile.photos.id_tip_3') }}</li>
                </ul>
              </details>

              <div class="flex flex-wrap gap-2">
                <button
                  v-if="vpStatus.has_photo"
                  @click="deriveIdPhoto"
                  :disabled="idPhotoDeriving"
                  class="btn-secondary btn-sm"
                >
                  <span v-if="!idPhotoDeriving" class="flex items-center gap-2">
                    <Crop class="w-4 h-4" />
                    {{ $t('profile.photos.derive_id') }}
                  </span>
                  <span v-else class="flex items-center gap-2">
                    <Loader2 class="w-4 h-4 animate-spin" />
                    {{ $t('profile.photos.uploading') }}
                  </span>
                </button>
                <label
                  class="btn-outline btn-sm cursor-pointer"
                  :class="{ 'opacity-50 pointer-events-none': idPhotoUploading }"
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
                  class="btn-outline-error btn-sm"
                >
                  <span v-if="!idPhotoDeleting">{{ $t('profile.photos.delete') }}</span>
                  <span v-else>...</span>
                </button>
              </div>

              <!-- Card downloads -->
              <div class="flex flex-wrap gap-2 mt-3">
                <UiButton
                  variant="outline"
                  size="sm"
                  :icon="Download"
                  :loading="badgeLoading"
                  @click="downloadBadge('single')"
                >
                  {{ $t('profile.badge_single') }}
                </UiButton>
                <UiButton
                  variant="outline"
                  size="sm"
                  :icon="Grid3X3"
                  :loading="badgeLoading"
                  @click="downloadBadge('batch')"
                >
                  {{ $t('profile.badge_batch') }}
                </UiButton>
              </div>

              <!-- The Para-ID photo gets no view notification (a portrait meant
                   to be shown), so this log is the whole of the owner's view -->
              <PhotoAccessLog
                v-if="idPhotoUrl || idAccesses.length"
                :title="$t('profile.photos.access_log_id_title')"
                :accesses="idAccesses"
              />
            </div>
          </div>

          <!-- Avatar row: current avatar (+ watercolor preview while deciding) + actions -->
          <div class="flex items-start gap-4">
            <div
              v-if="avatarUrl"
              class="w-24 h-24 rounded-full overflow-hidden border-2 border-neutral-200 dark:border-neutral-700 flex-shrink-0"
            >
              <img :src="avatarUrl" alt="" class="w-full h-full object-cover" />
            </div>
            <div
              v-else
              class="w-24 h-24 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center border-2 border-dashed border-neutral-300 dark:border-neutral-600 flex-shrink-0"
            >
              <User class="w-8 h-8 text-neutral-400" />
            </div>
            <div
              v-if="stylizedPreview"
              class="w-24 h-24 rounded-full overflow-hidden border-2 border-primary flex-shrink-0"
            >
              <img :src="stylizedPreview" alt="" class="w-full h-full object-cover" />
            </div>

            <div class="flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2 mb-1">
                <CircleUserRound class="w-4 h-4 text-secondary dark:text-secondary-400" />
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {{ $t('profile.photos.avatar_label') }}
                </label>
              </div>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
                {{ stylizedPreview ? $t('profile.photos.stylize_preview_hint') : $t('profile.photos.avatar_derived_hint') }}
              </p>

              <div class="flex flex-wrap gap-2">
                <template v-if="stylizedPreview">
                  <button
                    @click="applyStylized"
                    :disabled="stylizedApplying"
                    class="btn-primary btn-sm"
                  >
                    <span class="flex items-center gap-2">
                      <Loader2 v-if="stylizedApplying" class="w-4 h-4 animate-spin" />
                      {{ $t('profile.photos.stylize_apply') }}
                    </span>
                  </button>
                  <button
                    @click="stylizedPreview = null"
                    :disabled="stylizedApplying"
                    class="btn-outline btn-sm"
                  >
                    {{ $t('profile.photos.stylize_discard') }}
                  </button>
                </template>
                <button
                  v-else-if="vpStatus.has_photo"
                  @click="stylizeFromVerification"
                  :disabled="avatarStylizing"
                  class="btn-secondary btn-sm"
                >
                  <span v-if="!avatarStylizing" class="flex items-center gap-2">
                    <Sparkles class="w-4 h-4" />
                    {{ $t('profile.photos.stylize') }}
                  </span>
                  <span v-else class="flex items-center gap-2">
                    <Loader2 class="w-4 h-4 animate-spin" />
                    {{ $t('profile.photos.stylizing') }}
                  </span>
                </button>
              </div>

              <StylizePromptDisclosure />
            </div>
          </div>
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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { UserCircle, Upload, User, Check, AlertTriangle, Loader2, Download, Grid3X3, Brain, X, Copy, ShieldCheck, Fingerprint, Eye, IdCard, Sparkles, Crop, CircleUserRound } from 'lucide-vue-next'
import { useNotification } from '~/composables/useNotification'
import { dataUrlToBlob } from '~/utils/dataUrl'
import { saveFile } from '~/utils/download'
import { useAuthStore } from '~/stores/auth'
import AccordionSection from './AccordionSection.vue'
import PhotoAccessLog from './PhotoAccessLog.vue'
import StylizePromptDisclosure from './StylizePromptDisclosure.vue'

const props = defineProps<{
  openSections: string[]
  status: { complete: boolean; icon?: string }
  animationEnabled: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
  'hash-loaded': [completed: boolean]
  'vp-status': [hasPhoto: boolean]
}>()

const { t, locale } = useI18n()
const localePath = useLocalePath()
const { showSuccess, showError } = useNotification()
const authStore = useAuthStore()
const pgp = usePGP()

// === ID Photo state ===
// id_photo_url is now a gated endpoint (private media) — presence = "has photo",
// but the actual <img> needs an authed blob fetch (idPhotoSrc).
const idPhotoUrl = computed(() => authStore.user?.profile?.id_photo_url || null)
const idPhotoVerified = computed(() => authStore.user?.profile?.id_photo_verified || false)
const idPhotoSrc = ref<string | null>(null)
// The gated endpoint URL is constant across replacements, so a re-upload leaves
// idPhotoUrl untouched and the preview would keep the old blob — bump this instead.
const idPhotoVersion = ref(0)
const verificationIssues = ref<string[]>([])

const loadIdPhotoPreview = async (url: string) => {
  if (!import.meta.client) return
  try {
    await authStore.ensureToken()
    const res = await fetch(url, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (res.ok) {
      if (idPhotoSrc.value) URL.revokeObjectURL(idPhotoSrc.value)
      idPhotoSrc.value = URL.createObjectURL(await res.blob())
    }
  } catch (err) {
    console.error('Failed to load ID photo preview:', err)
  }
}

watch([idPhotoUrl, idPhotoVersion], ([url]) => {
  if (url) {
    loadIdPhotoPreview(url)
  } else if (idPhotoSrc.value) {
    URL.revokeObjectURL(idPhotoSrc.value)
    idPhotoSrc.value = null
  }
}, { immediate: true })

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
// Private media behind an authed endpoint — fetched as a blob, like the ID photo
const vpPhotoSrc = ref<string | null>(null)

// === WoT status (verification progress chip) ===
const wotStatus = ref<{ is_verified: boolean; verification_count: number } | null>(null)

async function loadWotStatus() {
  try {
    await authStore.ensureToken()
    wotStatus.value = await $fetch('/api/v1/wot/my-status/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
  } catch (error) {
    console.error('Error loading WoT status:', error)
  }
}

// Rendered by PhotoAccessLog.vue (same shape for both private photos)
interface PhotoAccess {
  viewer_id: string
  viewer_hna: string
  viewer_display_name: string
  viewed_at: string   // last view of that day
  views: number       // opens by this viewer that day
}
const vpAccesses = ref<PhotoAccess[]>([])
const idAccesses = ref<PhotoAccess[]>([])

// === Psycho-hash state ===
const psychHash4 = ref<string[]>(['', '', '', ''])
const savingPsychHash = ref(false)
const psychHashSaveTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
const form5Text = ref('')

// === Para-ID preview state ===
const badgePreviewSrc = ref<string | null>(null)

async function loadBadgePreview() {
  try {
    await authStore.ensureToken()
    const res = await fetch('/api/v1/profiles/me/badge/?format=png', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (res.ok) {
      if (badgePreviewSrc.value) URL.revokeObjectURL(badgePreviewSrc.value)
      badgePreviewSrc.value = URL.createObjectURL(await res.blob())
    }
  } catch (err) {
    console.error('Failed to load badge preview:', err)
  }
}

// Render the preview when the section is first opened (PNG rendering costs a
// server-side subprocess — don't pay it for a closed accordion), and refresh
// it after the ID photo changes since the photo is printed on the badge
const aboutSectionOpen = computed(() => props.openSections.includes('about'))
watch([aboutSectionOpen, idPhotoUrl, idPhotoVersion], ([open]) => {
  if (open && import.meta.client) loadBadgePreview()
}, { immediate: true })

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

    await saveFile(await response.blob(), filename)
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
    idPhotoVersion.value++

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

// Derive the Para-ID photo from the verification photo: deterministic 3:4
// face crop server-side, then the same advisory AI validation as an upload
const idPhotoDeriving = ref(false)

async function deriveIdPhoto() {
  idPhotoDeriving.value = true
  verificationIssues.value = []

  try {
    await authStore.ensureToken()

    const response = await $fetch<{
      url: string
      verified: boolean
      verification_issues: string[] | null
    }>('/api/v1/profiles/me/id-photo/derive/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    verificationIssues.value = response.verification_issues || []

    if (authStore.user?.profile) {
      authStore.user.profile.id_photo_url = response.url
      authStore.user.profile.id_photo_verified = response.verified
    }
    idPhotoVersion.value++

    showSuccess(t('profile.photos.derive_id_done'))
  } catch (error: any) {
    console.error('ID photo derive error:', error)
    showError(error.data?.error || t('profile.photos.upload_failed'))
  } finally {
    idPhotoDeriving.value = false
  }
}

// Watercolor avatar from the verification photo: backend returns a preview,
// nothing is applied until the user confirms (same pattern as the header modal)
const avatarUrl = computed(() => authStore.user?.profile?.avatar_url || null)
const avatarStylizing = ref(false)
const stylizedPreview = ref<string | null>(null)
const stylizedApplying = ref(false)

async function stylizeFromVerification() {
  avatarStylizing.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch<{ preview: string }>('/api/v1/profiles/me/avatar/stylize/?source=verification', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    stylizedPreview.value = response.preview
  } catch (error: any) {
    console.error('Avatar stylize error:', error)
    if (error?.status === 429) {
      showError(t('profile.photos.stylize_quota'))
    } else {
      showError(error.data?.error || t('profile.photos.stylize_failed'))
    }
  } finally {
    avatarStylizing.value = false
  }
}

async function applyStylized() {
  if (!stylizedPreview.value) return
  stylizedApplying.value = true
  try {
    await authStore.ensureToken()
    const blob = dataUrlToBlob(stylizedPreview.value)
    const formData = new FormData()
    formData.append('image', new File([blob], 'stylized.jpg', { type: 'image/jpeg' }))
    const response = await $fetch<{ url: string }>('/api/v1/profiles/me/avatar/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (authStore.user?.profile) {
      authStore.user.profile.avatar_url = response.url
    }
    stylizedPreview.value = null
    showSuccess(t('profile.photos.avatar_uploaded'))
  } catch (error: any) {
    console.error('Stylized avatar apply error:', error)
    showError(error.data?.error || t('profile.photos.upload_failed'))
  } finally {
    stylizedApplying.value = false
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
function clearVpPhoto() {
  if (vpPhotoSrc.value) {
    URL.revokeObjectURL(vpPhotoSrc.value)
    vpPhotoSrc.value = null
  }
}

async function loadVpPhoto() {
  if (!import.meta.client) return
  try {
    await authStore.ensureToken()
    const res = await fetch('/api/v1/profiles/me/verification-photo/file/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (!res.ok) return
    const blob = await res.blob()
    clearVpPhoto()
    vpPhotoSrc.value = URL.createObjectURL(blob)
  } catch (err) {
    console.error('Failed to load verification photo preview:', err)
  }
}

async function loadVpAccesses() {
  try {
    await authStore.ensureToken()
    const res = await $fetch<{ accesses: PhotoAccess[] }>('/api/v1/profiles/me/verification-photo/access-log/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    vpAccesses.value = res.accesses || []
  } catch (error) {
    console.error('Error loading verification photo access log:', error)
  }
}

async function loadIdAccesses() {
  try {
    await authStore.ensureToken()
    const res = await $fetch<{ accesses: PhotoAccess[] }>('/api/v1/profiles/me/id-photo/access-log/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    idAccesses.value = res.accesses || []
  } catch (error) {
    console.error('Error loading ID photo access log:', error)
  }
}

async function loadVpStatus() {
  try {
    await authStore.ensureToken()
    vpStatus.value = await $fetch('/api/v1/profiles/me/verification-photo/status/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (vpStatus.value.biometric_consent) vpConsent.value = true
    emit('vp-status', !!vpStatus.value.has_photo)
    if (vpStatus.value.has_photo) await loadVpPhoto()
    else clearVpPhoto()
  } catch (error) {
    console.error('Error loading verification photo status:', error)
  }
}

/**
 * Sign the exact bytes being uploaded with the profile's PGP key.
 *
 * A valid signature tells the backend the member replaced their own photo, which
 * is the question a re-confirmation round is asked to answer — signed swaps skip
 * the round entirely. Unsigned is a normal outcome, not a failure: a member may
 * have no key yet, and the upload still goes through (the round then applies).
 */
async function signPhotoUpload(file: File): Promise<{ statement: string; signature: string }> {
  const empty = { statement: '', signature: '' }
  try {
    await pgp.loadKeys()
    if (!pgp.hasKeys.value) return empty

    const profile = authStore.user?.profile
    if (!profile?.id || !profile?.hna) return empty

    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
    const sha256 = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('')

    const statement = JSON.stringify({
      action: 'verification_photo_upload',
      profile_id: profile.id,
      profile_hna: profile.hna,
      sha256,
      timestamp: new Date().toISOString()
    }, null, 2)

    return { statement, signature: await pgp.signMessage(statement) }
  } catch (e) {
    console.error('Failed to sign verification photo upload:', e)
    return empty
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

    const signed = await signPhotoUpload(file)
    formData.append('photo_statement', signed.statement)
    formData.append('photo_signature', signed.signature)

    const response = await $fetch<{
      success: boolean
      face_detected: boolean
      reconfirmation_needed: boolean
      reconfirmation_count: number
      owner_signed: boolean
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
      // A different-enough face opens a re-confirmation round; verifications
      // themselves stay active, so refresh both the photo status and the chip
      await Promise.all([loadVpStatus(), loadWotStatus()])
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
    emit('vp-status', false)
    clearVpPhoto()
    loadWotStatus()
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

// Both access logs load unconditionally — their rows outlive the photo they
// describe, and a deleted photo is exactly when the trail matters most.
onMounted(async () => {
  await Promise.all([
    loadPsychProfile(), loadInnerRealityMap(), loadVpStatus(), loadWotStatus(),
    loadVpAccesses(), loadIdAccesses(),
  ])
})

onBeforeUnmount(() => {
  if (badgePreviewSrc.value) URL.revokeObjectURL(badgePreviewSrc.value)
})
</script>
