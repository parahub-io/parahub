<template>
  <AccordionSection
    section-id="civic"
    :title="$t('civic.residency.title')"
    :icon="Landmark"
    :open-sections="openSections"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-6">
      <!-- Residency picker (private, poll scoping only) -->
      <CivicResidencyPicker />

      <!-- Civic data / consent (GDPR Art. 9) -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-6">
        <h3 class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          {{ $t('civic.privacy.title') }}
        </h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">
          <template v-if="consentAt">{{ $t('civic.privacy.consentGiven', { date: formatDate(consentAt) }) }}</template>
          <template v-else>{{ $t('civic.privacy.consentNone') }}</template>
        </p>
        <UiButton
          v-if="consentAt"
          variant="outline-error" size="sm" :icon="Trash2"
          @click="showEraseModal = true"
        >
          {{ $t('civic.privacy.erase') }}
        </UiButton>
        <p v-if="erasedMessage" class="text-sm text-success mt-2">{{ erasedMessage }}</p>
      </div>
    </div>

    <UiConfirmModal
      v-model="showEraseModal"
      :title="$t('civic.privacy.eraseTitle')"
      :message="$t('civic.privacy.eraseMessage')"
      :confirm-label="$t('civic.privacy.eraseConfirm')"
      variant="error"
      :icon="Trash2"
      :loading="erasing"
      @confirm="eraseCivicData"
    />
  </AccordionSection>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Landmark, Trash2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import AccordionSection from './AccordionSection.vue'
import CivicResidencyPicker from '~/components/civic/CivicResidencyPicker.vue'

defineProps<{
  openSections: string[]
  animationEnabled?: boolean
}>()

const emit = defineEmits<{ toggle: [sectionId: string] }>()

const { t: $t, locale } = useI18n()
const authStore = useAuthStore()

const consentAt = ref<string | null>(null)
const showEraseModal = ref(false)
const erasing = ref(false)
const erasedMessage = ref('')

async function loadConsent() {
  try {
    await authStore.ensureToken()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    consentAt.value = res.consent ? (res.consent_at || new Date().toISOString()) : null
  } catch { /* not authenticated */ }
}

async function eraseCivicData() {
  erasing.value = true
  try {
    await authStore.ensureToken()
    const res: any = await $fetch('/api/v1/governance/civic/consent/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { granted: false },
    })
    consentAt.value = null
    erasedMessage.value = $t('civic.privacy.erased', { n: res.erased_polls ?? 0 })
    showEraseModal.value = false
  } catch { /* keep modal open on failure */ }
  erasing.value = false
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(loadConsent)
</script>
