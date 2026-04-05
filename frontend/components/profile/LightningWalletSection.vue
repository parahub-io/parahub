<template>
  <AccordionSection
    section-id="lightning"
    :title="$t('profile.lightning.title')"
    :icon="Zap"
    :open-sections="openSections"
    :status="status"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <!-- Help text (only when not yet configured) -->
    <UiAlert v-if="!lnAddress && !hasWalletConfig" variant="info" :title="$t('profile.lightning.help_title')" class="mb-4">
      {{ $t('profile.lightning.help_text') }}
    </UiAlert>

    <div class="space-y-6">
      <!-- LN Address -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('ads.profile.your_ln_address') }}
        </label>
        <div class="flex gap-2">
          <input
            v-model="lnAddress"
            type="text"
            :placeholder="$t('ads.profile.ln_address_placeholder')"
            class="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 dark:placeholder-neutral-500"
          />
          <UiButton variant="primary" :loading="saving" :disabled="saving" @click="saveLnAddress">
            {{ $t('ads.profile.save') }}
          </UiButton>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('ads.profile.ln_address_help') }}
        </p>
      </div>

      <!-- Non-custodial notice -->
      <p class="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
        <ShieldCheck class="w-4 h-4 flex-shrink-0" />
        {{ $t('ads.profile.wallet_info') }}
      </p>

      <!-- Provider Status -->
      <div v-if="hasWalletConfig" class="flex items-center gap-2">
        <Zap class="w-4 h-4 text-success" />
        <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ walletProviderLabel }}</span>
        <UiBadge variant="success" type="soft" size="sm">{{ $t('ads.profile.provider_connected') }}</UiBadge>
      </div>

      <!-- Advanced Wallet Configuration -->
      <details class="border border-neutral-300 dark:border-neutral-600 rounded-lg">
        <summary class="cursor-pointer px-4 py-3 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700 rounded-lg transition-colors">
          {{ hasWalletConfig
            ? `${walletProviderLabel} (${$t('ads.profile.configured')})`
            : $t('ads.profile.advanced_config')
          }}
        </summary>

        <div class="px-4 pb-4 pt-2 space-y-4">
          <!-- Provider Selection -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('ads.profile.wallet_provider') }}
            </label>
            <select
              v-model="walletConfig.provider"
              class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
            >
              <option value="">{{ $t('ads.profile.select_provider') }}</option>
              <option value="lnbits">LNbits</option>
              <option value="alby">Getalby</option>
            </select>
          </div>

          <!-- LNbits Config -->
          <div v-if="walletConfig.provider === 'lnbits'" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.profile.api_url') }}
              </label>
              <input
                v-model="walletConfig.api_url"
                type="url"
                placeholder="https://legend.lnbits.com"
                class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.profile.invoice_key') }}
              </label>
              <input
                v-model="walletConfig.invoice_key"
                type="password"
                :placeholder="$t('ads.profile.invoice_key_placeholder')"
                class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('ads.profile.invoice_key_help') }}
              </p>
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.profile.admin_key') }}
              </label>
              <input
                v-model="walletConfig.admin_key"
                type="password"
                :placeholder="$t('ads.profile.admin_key_placeholder')"
                class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('ads.profile.admin_key_help') }}
              </p>
            </div>
          </div>

          <!-- Alby Config -->
          <div v-if="walletConfig.provider === 'alby'" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.profile.access_token') }}
              </label>
              <input
                v-model="walletConfig.access_token"
                type="password"
                :placeholder="$t('ads.profile.access_token_placeholder')"
                class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('ads.profile.access_token_help') }}
              </p>
            </div>
          </div>

          <!-- Save Wallet Config -->
          <div v-if="walletConfig.provider" class="flex gap-2">
            <UiButton variant="outline" size="sm" :loading="testingConnection" :disabled="testingConnection" @click="testWalletConnection">
              {{ testingConnection ? $t('ads.profile.testing') : $t('ads.profile.test_connection') }}
            </UiButton>
            <UiButton variant="primary" size="sm" :loading="savingConfig" :disabled="savingConfig" @click="saveWalletConfig">
              {{ $t('ads.profile.save_config') }}
            </UiButton>
          </div>

          <!-- Connection Status -->
          <UiAlert v-if="connectionStatus" :variant="connectionStatus.success ? 'success' : 'error'">
            {{ connectionStatus.message }}
          </UiAlert>
        </div>
      </details>

      <!-- Screen reader announcements -->
      <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
        <span v-if="saving">{{ $t('ads.profile.saving_address') }}</span>
        <span v-else-if="savingConfig">{{ $t('ads.profile.saving_config') }}</span>
        <span v-else-if="testingConnection">{{ $t('ads.profile.testing') }}</span>
      </div>
    </div>
  </AccordionSection>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Zap, ShieldCheck } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useNotification } from '~/composables/useNotification'
import AccordionSection from './AccordionSection.vue'

const props = defineProps<{
  openSections: string[]
  status?: { complete: boolean; icon?: string }
  animationEnabled: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
  'wallet-configured': [configured: boolean]
}>()

const authStore = useAuthStore()
const { t } = useI18n()
const { showSuccess, showError } = useNotification()

const lnAddress = ref('')
const hasWalletConfig = ref(false)
const walletProvider = ref('')
const walletConfig = ref({
  provider: '',
  api_url: '',
  invoice_key: '',
  admin_key: '',
  access_token: '',
})
const saving = ref(false)
const savingConfig = ref(false)
const testingConnection = ref(false)
const connectionStatus = ref<{ success: boolean; message: string } | null>(null)

const PROVIDER_LABELS: Record<string, string> = { lnbits: 'LNbits', alby: 'Getalby' }
const walletProviderLabel = computed(() => PROVIDER_LABELS[walletProvider.value] || walletProvider.value)

const loadAdsProfile = async () => {
  try {
    await authStore.ensureToken()
    const profile = await $fetch('/api/v1/ads/profile/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (profile) {
      lnAddress.value = profile.ln_address || ''
      hasWalletConfig.value = !!profile.has_wallet_config
      walletProvider.value = profile.wallet_provider || ''

      // Emit wallet configured status
      emit('wallet-configured', !!profile.ln_address)

      // Load wallet config if available (keys are encrypted, show placeholder)
      if (profile.has_wallet_config) {
        walletConfig.value = {
          provider: profile.wallet_provider || '',
          api_url: profile.ln_wallet_config?.api_url || '',
          invoice_key: '',
          admin_key: '',
          access_token: '',
        }
      }
    }
  } catch (error) {
    console.error('Failed to load ads profile:', error)
  }
}

const saveLnAddress = async () => {
  saving.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: { ln_address: lnAddress.value }
    })

    emit('wallet-configured', !!lnAddress.value)
    showSuccess(t('ads.profile.ln_address_saved'))
  } catch (error) {
    console.error('Failed to save LN address:', error)
    showError(t('ads.profile.ln_address_error'))
  } finally {
    saving.value = false
  }
}

const testWalletConnection = async () => {
  testingConnection.value = true
  connectionStatus.value = null

  try {
    // Validate config locally first
    if (walletConfig.value.provider === 'lnbits') {
      if (!walletConfig.value.api_url || !walletConfig.value.invoice_key) {
        throw new Error(t('ads.profile.lnbits_fields_required'))
      }
    } else if (walletConfig.value.provider === 'alby') {
      if (!walletConfig.value.access_token) {
        throw new Error(t('ads.profile.alby_token_required'))
      }
    }

    // Build config for test
    const config: any = { provider: walletConfig.value.provider }
    if (walletConfig.value.provider === 'lnbits') {
      config.api_url = walletConfig.value.api_url
      config.invoice_key = walletConfig.value.invoice_key
      if (walletConfig.value.admin_key) config.admin_key = walletConfig.value.admin_key
    } else if (walletConfig.value.provider === 'alby') {
      config.access_token = walletConfig.value.access_token
    }

    await authStore.ensureToken()
    const result = await $fetch<any>('/api/v1/ads/wallet-test/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    })

    if (result.success) {
      const balanceInfo = result.balance_sats != null
        ? ` (${t('ads.profile.balance')}: ${result.balance_sats} sats)`
        : ''
      connectionStatus.value = {
        success: true,
        message: t('ads.profile.wallet_connected') + balanceInfo
      }
    } else {
      connectionStatus.value = {
        success: false,
        message: result.error || t('ads.profile.wallet_test_error')
      }
    }
  } catch (error: any) {
    const msg = error?.data?.error || error?.message || t('ads.profile.wallet_test_error')
    connectionStatus.value = {
      success: false,
      message: msg
    }
  } finally {
    testingConnection.value = false
  }
}

const saveWalletConfig = async () => {
  savingConfig.value = true
  try {
    await authStore.ensureToken()

    const config: any = {
      provider: walletConfig.value.provider
    }

    if (walletConfig.value.provider === 'lnbits') {
      config.api_url = walletConfig.value.api_url
      config.invoice_key = walletConfig.value.invoice_key
      if (walletConfig.value.admin_key) {
        config.admin_key = walletConfig.value.admin_key
      }
    } else if (walletConfig.value.provider === 'alby') {
      config.access_token = walletConfig.value.access_token
    }

    await $fetch('/api/v1/ads/profile/', {
      method: 'PUT',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        ln_wallet_config: config
      })
    })

    connectionStatus.value = {
      success: true,
      message: t('ads.profile.wallet_config_saved')
    }
    showSuccess(t('ads.profile.save_config_success'))
  } catch (error) {
    console.error('Failed to save wallet config:', error)
    connectionStatus.value = {
      success: false,
      message: t('ads.profile.wallet_config_error')
    }
    showError(t('ads.profile.save_config_error'))
  } finally {
    savingConfig.value = false
  }
}

onMounted(async () => {
  await loadAdsProfile()
})
</script>
