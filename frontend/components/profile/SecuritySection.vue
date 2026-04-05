<template>
  <AccordionSection
    section-id="security"
    :title="$t('profile.security.title')"
    :icon="Shield"
    :open-sections="openSections"
    :status="status"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-4">
      <!-- Has keys state -->
      <div v-if="pgpHasKeys && pgpKeyPair">
        <!-- Active key card -->
        <div class="card p-4 mb-4">
          <div class="flex items-start justify-between gap-2 mb-2">
            <div class="flex items-center gap-2 flex-1 min-w-0">
              <CheckCircle class="w-4 h-4 text-success flex-shrink-0" />
              <span class="font-mono text-xs break-all text-neutral-700 dark:text-neutral-300">
                {{ pgpKeyPair.fingerprint }}
              </span>
            </div>
            <UiBadge variant="success" type="soft" size="sm">
              {{ $t('profile.security.active') }}
            </UiBadge>
          </div>

          <div class="text-xs text-neutral-500 dark:text-neutral-400">
            <div v-if="activeKeyFromHistory">
              <strong>{{ $t('profile.security.created') }}:</strong> {{ formatDate(activeKeyFromHistory.valid_from) }}
              <span v-if="activeKeyFromHistory.created_from_ip"> • {{ $t('profile.security.from') }}: {{ activeKeyFromHistory.created_from_ip }}</span>
            </div>
            <div v-else-if="profile?.pgp_fingerprint">
              <strong>{{ $t('profile.security.active_since') }}:</strong> {{ formatDate(profile.updated_at || new Date().toISOString()) }}
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-3 flex-wrap">
          <UiButton variant="outline" size="sm" @click="copyPublicKey">
            {{ $t('profile.security.copy_public_key') }}
          </UiButton>
          <UiButton variant="outline-warning" size="sm" @click="handleExportPrivateKey">
            {{ $t('profile.security.export_private_key') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" @click="showPGPHistory = !showPGPHistory">
            {{ showPGPHistory ? $t('profile.security.hide_history') : $t('profile.security.view_history') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :to="localePath('/pgp-test')">
            {{ $t('profile.security.test_pgp') }} →
          </UiButton>
        </div>

        <!-- Key History (collapsible) -->
        <PGPHistoryList
          :show="showPGPHistory"
          :history="pgpHistory"
          :loading="pgpHistoryLoading"
          container-class="mt-4"
          @export="exportPublicKeyFromHistory"
        />
      </div>

      <!-- No keys state -->
      <div v-else class="space-y-4">
        <UiAlert variant="info" :title="$t('profile.security.pgp_setup_title')">
          {{ $t('profile.security.pgp_setup_text') }}
        </UiAlert>

        <!-- Action buttons -->
        <div class="flex gap-3 flex-wrap">
          <UiButton variant="primary" size="sm" :to="localePath('/seed-restore')">
            {{ $t('seed.restoreFromSeed') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :to="localePath('/seed-setup')">
            {{ $t('profile.security.generate_new_seed') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" @click="showPGPHistory = !showPGPHistory">
            {{ showPGPHistory ? $t('profile.security.hide_history') : $t('profile.security.view_history') }}
          </UiButton>
        </div>

        <!-- Key History (also show when no active keys) -->
        <PGPHistoryList
          :show="showPGPHistory"
          :history="pgpHistory"
          :loading="pgpHistoryLoading"
          container-class="mb-4 border border-neutral-300 dark:border-neutral-600 rounded-lg p-4"
          @export="exportPublicKeyFromHistory"
        />
      </div>

      <!-- Seed Phrase Backup -->
      <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4 mt-4">
        <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3 flex items-center gap-2">
          <KeyRound class="w-4 h-4" />
          {{ $t('profile.security.seed_backup_title') }}
        </h3>

        <!-- Seed warning -->
        <UiAlert v-if="!hasSeedPhrase" variant="warning" :title="$t('seed.noSeedTitle', 'Seed phrase missing')" class="mb-3">
          {{ $t('profile.security.backup_warning_text') }}
          {{ $t('seed.noSeedText', 'No saved seed phrase on this device. Restore or create a new one.') }}
        </UiAlert>
        <UiAlert v-else variant="warning" :title="$t('profile.security.backup_warning_title')" class="mb-3">
          {{ $t('profile.security.backup_warning_text') }}
        </UiAlert>

        <!-- Seed actions -->
        <div class="flex flex-wrap gap-3">
          <template v-if="hasSeedPhrase">
            <UiButton variant="outline" size="sm" :icon="showSeed ? EyeOff : Eye" @click="toggleSeedPhrase">
              {{ showSeed ? $t('profile.security.hide_seed') : $t('profile.security.show_seed') }}
            </UiButton>
          </template>
          <template v-else>
            <UiButton variant="primary" size="sm" :icon="Download" :to="localePath('/seed-restore')">
              {{ $t('seed.restoreFromSeed') }}
            </UiButton>
            <UiButton variant="outline" size="sm" :icon="Plus" :to="localePath('/seed-setup')">
              {{ $t('profile.security.generate_new_seed') }}
            </UiButton>
          </template>
        </div>

        <!-- Seed phrase display -->
        <div
          v-if="showSeed && seedWords.length > 0"
          class="bg-white dark:bg-neutral-800 rounded-xl p-6 border border-neutral-200 dark:border-neutral-700 mt-3"
        >
          <div class="grid grid-cols-3 gap-3 mb-4">
            <div
              v-for="(word, index) in seedWords"
              :key="index"
              class="bg-neutral-100 dark:bg-neutral-700 rounded-lg p-2 text-center"
            >
              <span class="text-xs text-neutral-500">{{ index + 1 }}</span>
              <p class="font-mono text-sm">{{ word }}</p>
            </div>
          </div>

          <!-- Copy button -->
          <button
            type="button"
            class="w-full flex items-center justify-center space-x-2 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
            @click="copySeedPhrase"
          >
            <Copy class="w-4 h-4" />
            <span>{{ seedCopied ? $t('common.copied') : $t('profile.security.copy_seed') }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Export Private Key Warning Modal -->
    <Teleport to="body">
      <div v-if="showExportPrivateKeyWarning" class="fixed inset-0 z-50 overflow-y-auto">
        <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
          <div @click="showExportPrivateKeyWarning = false" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

          <div class="relative inline-block w-full max-w-md px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
            <div class="sm:flex sm:items-start">
              <div class="w-full">
                <div class="flex items-center gap-3 mb-4">
                  <div class="w-12 h-12 bg-orange-100 dark:bg-orange-900/30 rounded-full flex items-center justify-center flex-shrink-0">
                    <AlertTriangle class="w-6 h-6 text-orange-600 dark:text-orange-400" />
                  </div>
                  <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100">
                    {{ $t('profile.security.export_private_key') }}?
                  </h3>
                </div>

                <UiAlert variant="warning" :title="$t('profile.security.critical_warning')" class="mb-4">
                  <ul class="space-y-2 mt-2">
                    <li class="flex items-start gap-2">
                      <span class="font-bold mt-0.5">•</span>
                      <span v-html="$t('profile.security.warning_full_control')"></span>
                    </li>
                    <li class="flex items-start gap-2">
                      <span class="font-bold mt-0.5">•</span>
                      <span v-html="$t('profile.security.warning_never_share')"></span>
                    </li>
                    <li class="flex items-start gap-2">
                      <span class="font-bold mt-0.5">•</span>
                      <span v-html="$t('profile.security.warning_secure_storage')"></span>
                    </li>
                    <li class="flex items-start gap-2">
                      <span class="font-bold mt-0.5">•</span>
                      <span v-html="$t('profile.security.warning_impersonation')"></span>
                    </li>
                  </ul>
                </UiAlert>

                <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
                  {{ $t('profile.security.export_confirm_text') }}
                </p>

                <div class="flex justify-end gap-3">
                  <button
                    @click="showExportPrivateKeyWarning = false"
                    class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
                  >
                    {{ $t('common.cancel') }}
                  </button>
                  <button
                    @click="confirmExportPrivateKey"
                    class="px-4 py-2 bg-orange-600 text-white font-medium rounded-lg hover:bg-orange-700"
                  >
                    {{ $t('profile.security.export_confirm_button') }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </AccordionSection>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Shield, CheckCircle, AlertTriangle, Eye, EyeOff, Download, Plus, Copy, KeyRound } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { usePGP } from '~/composables/usePGP'
import { useSeed } from '~/composables/useSeed'
import { useNotification } from '~/composables/useNotification'
import AccordionSection from './AccordionSection.vue'
import PGPHistoryList from './PGPHistoryList.vue'

const props = defineProps<{
  openSections: string[]
  status: { complete: boolean; icon?: string }
  animationEnabled: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
}>()

const authStore = useAuthStore()
const localePath = useLocalePath()
const { t, locale } = useI18n()
const { showSuccess, showError } = useNotification()
const { loadSeed, hasSeed } = useSeed()

const profile = computed(() => authStore.profile)

// PGP Key Management
const {
  keyPair: pgpKeyPair,
  loading: pgpLoading,
  hasKeys: pgpHasKeys,
  loadKeys: pgpLoadKeys,
  exportPublicKey: pgpExportPublicKey,
  exportPrivateKey: pgpExportPrivateKey
} = usePGP()

const showExportPrivateKeyWarning = ref(false)
const pgpUploading = ref(false)
const showPGPHistory = ref(false)
const pgpHistory = ref([])
const pgpHistoryLoading = ref(false)

// Seed phrase state
const hasSeedPhrase = ref(false)
const seedWords = ref<string[]>([])
const showSeed = ref(false)
const seedCopied = ref(false)

// Get active key from history for display
const activeKeyFromHistory = computed(() => {
  return pgpHistory.value.find(k => k.is_active)
})

const copyPublicKey = async () => {
  try {
    await navigator.clipboard.writeText(pgpKeyPair.value.publicKey)
    showSuccess(t('profile.security.public_key_copied'))
  } catch (e) {
    showError(t('profile.security.copy_failed'))
  }
}

const handleExportPrivateKey = () => {
  showExportPrivateKeyWarning.value = true
}

const confirmExportPrivateKey = async () => {
  try {
    const privateKey = pgpExportPrivateKey()
    if (!privateKey || !pgpKeyPair.value) {
      throw new Error('No private key available')
    }

    const fingerprint = pgpKeyPair.value.fingerprint
    const filename = `parahub_private_key_${fingerprint}.asc`

    const blob = new Blob([privateKey], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    showExportPrivateKeyWarning.value = false
    showSuccess(t('profile.security.private_key_exported'))
  } catch (e) {
    showError(t('profile.security.export_failed'))
  }
}

const uploadPublicKey = async () => {
  pgpUploading.value = true
  try {
    const publicKey = pgpExportPublicKey()
    if (!publicKey) {
      throw new Error('No public key available')
    }

    await $fetch('/api/v1/profiles/me/keys/', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`,
        'Content-Type': 'application/json'
      },
      body: { public_key: publicKey }
    })

    showSuccess(t('profile.security.public_key_uploaded'))

    await authStore.fetchProfile()
    await loadPGPHistory()
  } catch (e) {
    console.error('Failed to upload public key:', e)
    showError(t('profile.security.upload_failed'))
  } finally {
    pgpUploading.value = false
  }
}

const loadPGPHistory = async () => {
  pgpHistoryLoading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/profiles/me/keys/history/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    pgpHistory.value = response || []
  } catch (e) {
    console.error('Failed to load PGP history:', e)
    showError(t('profile.security.history_load_failed'))
  } finally {
    pgpHistoryLoading.value = false
  }
}

watch(showPGPHistory, async (isOpen) => {
  if (isOpen) {
    await loadPGPHistory()
  }
})

const exportPublicKeyFromHistory = async (key: any) => {
  try {
    const publicKey = key.public_key
    if (!publicKey) {
      showError(t('profile.security.public_key_not_available'))
      return
    }

    const filename = `parahub_public_key_${key.fingerprint}.asc`
    const blob = new Blob([publicKey], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    showSuccess(t('profile.security.public_key_exported'))
  } catch (e) {
    showError(t('profile.security.export_failed'))
  }
}

// Seed phrase methods
const toggleSeedPhrase = () => {
  showSeed.value = !showSeed.value
}

const copySeedPhrase = async () => {
  try {
    await navigator.clipboard.writeText(seedWords.value.join(' '))
    seedCopied.value = true
    setTimeout(() => { seedCopied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

// Format date helper
const formatDate = (dateString: string) => {
  const date = new Date(dateString)
  return new Intl.DateTimeFormat(locale.value, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

// Load PGP keys and seed on mount
onMounted(async () => {
  await pgpLoadKeys()

  if (pgpHasKeys.value) {
    await loadPGPHistory()
  }

  // Load seed phrase
  hasSeedPhrase.value = hasSeed()
  if (hasSeedPhrase.value) {
    const words = loadSeed()
    if (words) {
      seedWords.value = words
    }
  }
})
</script>
