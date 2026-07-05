<template>
  <div>
    <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('civic.residency.hint') }}</p>

    <UiAlert v-if="cooldownUntil" variant="warning" class="mb-3">
      {{ $t('civic.residency.cooldown', { date: formatDate(cooldownUntil) }) }}
    </UiAlert>

    <CivicTerritorySelect v-if="ready" v-model="selectedId" :initial-chain="initialChain" />

    <div class="flex items-center gap-3 mt-4">
      <UiButton variant="primary" size="sm" :loading="saving" :disabled="!selectedId" @click="save">
        {{ $t('civic.residency.save') }}
      </UiButton>
      <span v-if="saved" class="text-sm text-success">{{ $t('civic.residency.saved') }}</span>
      <span v-if="error" class="text-sm text-error">{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import CivicTerritorySelect from './CivicTerritorySelect.vue'

const emit = defineEmits<{ saved: [] }>()

const { t: $t, locale } = useI18n()
const authStore = useAuthStore()

const selectedId = ref('')
const initialChain = ref<any[]>([])
const ready = ref(false)
const saving = ref(false)
const saved = ref(false)
const error = ref('')
const cooldownUntil = ref<string | null>(null)

async function loadCurrent() {
  try {
    await authStore.ensureToken()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    cooldownUntil.value = res.cooldown_until
    initialChain.value = res.chain || []
  } catch { /* unauthenticated or no residency yet */ }
  ready.value = true
}

async function save() {
  if (!selectedId.value || saving.value) return
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    await authStore.ensureToken()
    const res: any = await $fetch('/api/v1/governance/civic/residency/', {
      method: 'PUT',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { territory_id: selectedId.value },
    })
    cooldownUntil.value = res.cooldown_until
    saved.value = true
    emit('saved')
  } catch (e: any) {
    error.value = e?.response?._data?.detail || e?.data?.detail || String(e?.message || e)
  } finally {
    saving.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(loadCurrent)
</script>
