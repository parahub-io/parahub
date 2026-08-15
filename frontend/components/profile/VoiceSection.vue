<template>
  <AccordionSection
    section-id="voice"
    :title="$t('voice_notes.consent.section_title')"
    :icon="Mic"
    :open-sections="openSections"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-6">
      <!-- What the feature is, before anything is asked of the reader -->
      <div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ $t('voice_notes.consent.intro') }}
        </p>
        <NuxtLink :to="localePath('/talk')" class="text-link text-sm inline-flex items-center gap-1 mt-2">
          <MessagesSquare :size="14" />
          {{ $t('voice_notes.consent.open_talk') }}
        </NuxtLink>
      </div>

      <!-- Not yet opted in: the full explanation, then an act -->
      <div v-if="!status.consent" class="border-t border-neutral-200 dark:border-neutral-700 pt-6">
        <h3 class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('voice_notes.consent.title') }}
        </h3>
        <ul class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1.5 mb-4 list-disc pl-5">
          <li>{{ $t('voice_notes.consent.point_provider') }}</li>
          <li>{{ $t('voice_notes.consent.point_voiceprint') }}</li>
          <li>{{ $t('voice_notes.consent.point_languages') }}</li>
          <li>{{ $t('voice_notes.consent.point_own_voice') }}</li>
          <li>{{ $t('voice_notes.consent.point_revocable') }}</li>
        </ul>

        <label class="flex items-start gap-2 mb-4 cursor-pointer">
          <input
            v-model="accepted"
            type="checkbox"
            class="mt-0.5 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-2 focus:ring-primary"
          >
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ $t('voice_notes.consent.checkbox') }}
          </span>
        </label>

        <UiButton
          variant="secondary"
          size="sm"
          :icon="Check"
          :disabled="!accepted"
          :loading="saving"
          @click="grant"
        >
          {{ $t('voice_notes.consent.grant') }}
        </UiButton>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-3">
          {{ $t('voice_notes.consent.optional_note') }}
        </p>
      </div>

      <!-- Opted in: what has been collected and what exists -->
      <div v-else class="border-t border-neutral-200 dark:border-neutral-700 pt-6 space-y-4">
        <p class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ $t('voice_notes.consent.granted_on', { date: formatDate(status.consent_granted_at) }) }}
        </p>

        <div v-if="!status.has_clone">
          <div class="flex items-center justify-between text-sm mb-1">
            <span class="text-neutral-700 dark:text-neutral-300">
              {{ $t('voice_notes.consent.collecting') }}
            </span>
            <span class="text-neutral-500 dark:text-neutral-400 tabular-nums">
              {{ Math.round(status.collected_seconds) }}s / {{ Math.round(status.next_threshold_seconds) }}s
            </span>
          </div>
          <div class="h-1.5 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
            <div class="h-full bg-primary transition-[width]" :style="{ width: progressWidth }" />
          </div>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {{ $t('voice_notes.consent.collecting_hint') }}
          </p>
        </div>

        <div v-else class="flex items-start gap-2">
          <AudioLines :size="18" class="text-success flex-shrink-0 mt-0.5" />
          <div>
            <p class="text-sm text-neutral-900 dark:text-neutral-100">
              {{ status.stage >= 2
                ? $t('voice_notes.consent.clone_refined')
                : $t('voice_notes.consent.clone_ready') }}
            </p>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">
              {{ $t('voice_notes.consent.clone_built_from', { seconds: Math.round(status.sample_seconds) }) }}
            </p>
          </div>
        </div>

        <UiButton variant="outline-error" size="sm" :icon="Trash2" @click="showDeleteModal = true">
          {{ $t('voice_notes.consent.delete') }}
        </UiButton>
      </div>
    </div>

    <UiConfirmModal
      v-model="showDeleteModal"
      :title="$t('voice_notes.consent.delete_title')"
      :message="$t('voice_notes.consent.delete_message')"
      :confirm-label="$t('voice_notes.consent.delete_confirm')"
      variant="error"
      :icon="Trash2"
      :loading="deleting"
      @confirm="deleteVoice"
    />
  </AccordionSection>
</template>

<script setup lang="ts">
import { AudioLines, Check, MessagesSquare, Mic, Trash2 } from 'lucide-vue-next'
import AccordionSection from './AccordionSection.vue'

defineProps<{
  openSections: string[]
  animationEnabled?: boolean
}>()

const emit = defineEmits<{ toggle: [sectionId: string] }>()

const { t: $t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { showError } = useNotification()

interface CloneStatus {
  consent: boolean
  consent_granted_at: string | null
  consent_text_version: string
  has_clone: boolean
  stage: number
  collected_seconds: number
  next_threshold_seconds: number
  sample_seconds: number
}

const status = ref<CloneStatus>({
  consent: false, consent_granted_at: null, consent_text_version: '1',
  has_clone: false, stage: 0, collected_seconds: 0,
  next_threshold_seconds: 60, sample_seconds: 0,
})
const accepted = ref(false)   // never pre-checked: the tick is the consent
const saving = ref(false)
const deleting = ref(false)
const showDeleteModal = ref(false)

const progressWidth = computed(() => {
  const target = status.value.next_threshold_seconds || 1
  return `${Math.min(100, Math.round((status.value.collected_seconds / target) * 100))}%`
})

async function authed<T>(url: string, options: any = {}): Promise<T> {
  await authStore.ensureToken()
  return await $fetch<T>(url, {
    credentials: 'include',
    headers: { Authorization: `Bearer ${authStore.token}` },
    ...options,
  })
}

async function load() {
  try {
    status.value = await authed<CloneStatus>('/api/v1/voice/clone')
  } catch { /* signed out or backend without the feature yet */ }
}

async function grant() {
  if (!accepted.value) return
  saving.value = true
  try {
    status.value = await authed<CloneStatus>('/api/v1/voice/clone', {
      method: 'POST',
      body: { accepted: true, consent_text_version: status.value.consent_text_version },
    })
  } catch (e) {
    showError($t('voice_notes.consent.grant_failed'))
  }
  saving.value = false
}

async function deleteVoice() {
  deleting.value = true
  try {
    status.value = await authed<CloneStatus>('/api/v1/voice/clone', { method: 'DELETE' })
    accepted.value = false
    showDeleteModal.value = false
  } catch (e) {
    showError($t('voice_notes.consent.delete_failed'))
  }
  deleting.value = false
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

onMounted(load)
</script>
