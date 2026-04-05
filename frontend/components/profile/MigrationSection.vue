<template>
  <AccordionSection
    section-id="migration"
    :title="$t('federation.profile.title')"
    :icon="ArrowRightLeft"
    :open-sections="openSections"
    :animation-enabled="animationEnabled"
    :status="sectionStatus"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-4">
      <!-- Active migration -->
      <div v-if="activeMigration" class="space-y-4">
        <div class="p-4 bg-neutral-50 dark:bg-neutral-700/50 rounded-lg border border-neutral-200 dark:border-neutral-600">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100">{{ activeMigration.from_hna }}</span>
              <ArrowRight class="w-4 h-4 text-neutral-500" />
              <span class="font-mono text-sm text-neutral-900 dark:text-neutral-100">{{ activeMigration.to_hna || '?' }}</span>
            </div>
            <span class="px-2 py-0.5 rounded text-xs font-medium"
              :class="{
                'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400': activeMigration.status === 'initiated',
                'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400': activeMigration.status === 'exported',
                'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400': activeMigration.status === 'signed',
                'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400': activeMigration.status === 'completed',
              }">
              {{ $t(`federation.migrations.${activeMigration.status}`) }}
            </span>
          </div>

          <!-- Signatures -->
          <div class="grid grid-cols-2 gap-2 text-xs mb-3">
            <div class="flex items-center gap-1">
              <component :is="activeMigration.has_from_signature ? CheckCircle : Circle" class="w-3.5 h-3.5" :class="activeMigration.has_from_signature ? 'text-emerald-500' : 'text-neutral-400'" />
              <span class="text-neutral-600 dark:text-neutral-400">{{ $t('federation.migrations.from_user') }}</span>
            </div>
            <div class="flex items-center gap-1">
              <component :is="activeMigration.has_to_signature ? CheckCircle : Circle" class="w-3.5 h-3.5" :class="activeMigration.has_to_signature ? 'text-emerald-500' : 'text-neutral-400'" />
              <span class="text-neutral-600 dark:text-neutral-400">{{ $t('federation.migrations.to_user') }}</span>
            </div>
            <div class="flex items-center gap-1">
              <component :is="activeMigration.has_from_node_signature ? CheckCircle : Circle" class="w-3.5 h-3.5" :class="activeMigration.has_from_node_signature ? 'text-emerald-500' : 'text-neutral-400'" />
              <span class="text-neutral-600 dark:text-neutral-400">{{ $t('federation.migrations.from_node') }}</span>
            </div>
            <div class="flex items-center gap-1">
              <component :is="activeMigration.has_to_node_signature ? CheckCircle : Circle" class="w-3.5 h-3.5" :class="activeMigration.has_to_node_signature ? 'text-emerald-500' : 'text-neutral-400'" />
              <span class="text-neutral-600 dark:text-neutral-400">{{ $t('federation.migrations.to_node_sig') }}</span>
            </div>
          </div>

          <!-- Action buttons based on status -->
          <div class="flex flex-wrap gap-2">
            <!-- Sign (if initiated, not yet signed) -->
            <button
              v-if="activeMigration.status === 'initiated' && !activeMigration.has_from_signature"
              @click="signMigration"
              :disabled="signing || !hasPGP"
              class="btn-primary btn-sm gap-1"
            >
              <Key class="w-4 h-4" />
              {{ signing ? '...' : $t('federation.migrations.sign') }}
            </button>

            <!-- Export data -->
            <button
              v-if="activeMigration.status === 'initiated' || activeMigration.status === 'exported'"
              @click="exportData"
              :disabled="exporting"
              class="btn-outline btn-sm gap-1"
            >
              <Download class="w-4 h-4" />
              {{ exporting ? '...' : $t('federation.migrations.export_data') }}
            </button>

            <!-- Complete -->
            <button
              v-if="activeMigration.has_from_signature && activeMigration.status !== 'completed'"
              @click="completeMigration"
              :disabled="completing"
              class="btn-primary btn-sm gap-1"
            >
              <Check class="w-4 h-4" />
              {{ completing ? '...' : $t('federation.migrations.complete') }}
            </button>

            <!-- Cancel -->
            <UiButton
              v-if="activeMigration.status !== 'completed'"
              variant="outline-error"
              size="sm"
              @click="showCancelConfirm = true"
            >
              {{ $t('federation.migrations.cancel') }}
            </UiButton>
          </div>

          <div v-if="activeMigration.export_hash" class="mt-2 text-xs text-neutral-500 font-mono">
            SHA256: {{ activeMigration.export_hash.substring(0, 32) }}...
          </div>
        </div>
      </div>

      <!-- No active migration — show initiate form -->
      <div v-else class="space-y-4">
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ $t('federation.profile.start_description') }}
        </p>

        <UiAlert variant="warning">
          {{ $t('federation.profile.warning') }}
        </UiAlert>

        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('federation.migrations.to_node') }}
            </label>
            <input
              v-model="toNode"
              type="text"
              :placeholder="$t('federation.migrations.to_node_placeholder')"
              class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm"
            >
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('federation.migrations.to_hna') }}
            </label>
            <input
              v-model="toHna"
              type="text"
              :placeholder="$t('federation.migrations.to_hna_placeholder')"
              class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm"
            >
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('federation.migrations.reason') }}
            </label>
            <input
              v-model="reason"
              type="text"
              class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm"
            >
          </div>
          <button
            @click="initiateMigration"
            :disabled="!toNode || initiating"
            class="btn-primary btn-sm gap-1"
          >
            <ArrowRightLeft class="w-4 h-4" />
            {{ initiating ? '...' : $t('federation.migrations.initiate') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Cancel confirmation -->
    <UiConfirmModal
      v-model="showCancelConfirm"
      :title="$t('federation.migrations.cancel')"
      :message="$t('federation.migrations.confirm_cancel')"
      :confirm-label="$t('federation.migrations.cancel')"
      variant="error"
      :icon="AlertTriangle"
      @confirm="cancelMigration"
    />
  </AccordionSection>
</template>

<script setup lang="ts">
import { ArrowRightLeft, ArrowRight, CheckCircle, Circle, Key, Download, Check, AlertTriangle } from 'lucide-vue-next'
import AccordionSection from './AccordionSection.vue'

const props = defineProps<{
  openSections: string[]
  animationEnabled?: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
}>()

const { t: $t } = useI18n()
const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()

// PGP
const { keyPair: pgpKeyPair, signCanonicalPayload } = usePGP()
const hasPGP = computed(() => !!pgpKeyPair.value)

// State
const activeMigration = ref<any>(null)
const toNode = ref('')
const toHna = ref('')
const reason = ref('')
const initiating = ref(false)
const signing = ref(false)
const exporting = ref(false)
const completing = ref(false)
const showCancelConfirm = ref(false)

const sectionStatus = computed(() => {
  if (activeMigration.value) {
    if (activeMigration.value.status === 'completed') return { complete: true }
    return { complete: false, icon: 'alert' as const }
  }
  return { complete: false, icon: 'minus' as const }
})

const fetchMigrations = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const res = await $fetch('/api/v1/federation/migrations/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    }) as any[]

    // Find active (non-completed, non-cancelled)
    activeMigration.value = res.find(
      (m: any) => !['completed', 'cancelled'].includes(m.status)
    ) || null
  } catch (e) {
    // No migrations or not available
  }
}

const initiateMigration = async () => {
  initiating.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch('/api/v1/federation/migration/initiate/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { to_node: toNode.value, to_hna: toHna.value, reason: reason.value },
    })
    activeMigration.value = res
    toNode.value = ''
    toHna.value = ''
    reason.value = ''
    showSuccess($t('federation.migrations.initiated'))
  } catch (e: any) {
    showError(e.data?.detail || 'Failed to initiate migration')
  } finally {
    initiating.value = false
  }
}

const signMigration = async () => {
  if (!activeMigration.value || !hasPGP.value) return
  signing.value = true
  try {
    const payload = {
      type: 'profile_migration',
      migration_id: activeMigration.value.id,
      from_hna: activeMigration.value.from_hna,
      to_hna: activeMigration.value.to_hna,
    }
    const signature = await signCanonicalPayload(payload)

    await authStore.ensureToken()
    const res = await $fetch(`/api/v1/federation/migration/${activeMigration.value.id}/sign/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { signature },
    })
    activeMigration.value = res
    showSuccess($t('federation.migrations.signed'))
  } catch (e: any) {
    showError(e.data?.detail || 'Failed to sign migration')
  } finally {
    signing.value = false
  }
}

const exportData = async () => {
  if (!activeMigration.value) return
  exporting.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch(`/api/v1/federation/migration/${activeMigration.value.id}/export/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      responseType: 'blob',
    })

    // Download the file
    const url = window.URL.createObjectURL(response as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `migration_${activeMigration.value.from_hna}_${activeMigration.value.id.substring(0, 8)}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)

    // Refresh migration status
    await fetchMigrations()
    showSuccess($t('federation.migrations.exported'))
  } catch (e: any) {
    showError(e.data?.detail || 'Failed to export data')
  } finally {
    exporting.value = false
  }
}

const completeMigration = async () => {
  if (!activeMigration.value) return
  completing.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch(`/api/v1/federation/migration/${activeMigration.value.id}/complete/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    activeMigration.value = res
    showSuccess($t('federation.migrations.completed'))
  } catch (e: any) {
    showError(e.data?.detail || 'Failed to complete migration')
  } finally {
    completing.value = false
  }
}

const cancelMigration = async () => {
  if (!activeMigration.value) return
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/federation/migration/${activeMigration.value.id}/cancel/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    activeMigration.value = null
    showSuccess($t('federation.migrations.cancelled'))
  } catch (e: any) {
    showError(e.data?.detail || 'Failed to cancel migration')
  }
}

onMounted(fetchMigrations)
</script>
