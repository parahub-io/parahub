<template>
  <div id="wallet-sync" class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4">
    <div class="flex items-center gap-4 sm:gap-5">
      <img
        src="/images/wallet/sync.webp"
        alt=""
        aria-hidden="true"
        class="w-20 sm:w-28 h-auto object-contain flex-shrink-0"
      />
      <div class="flex-1 min-w-0">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {{ $t('profile.preferences.wallet_sync_label') }}
        </h2>

        <div class="flex items-center gap-3 mt-3">
          <button
            :disabled="!walletSyncAvailable || walletSyncBusy"
            @click="toggleWalletSync"
            class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            :class="walletSyncOn ? 'bg-primary' : 'bg-neutral-300 dark:bg-neutral-600'"
            :aria-label="$t('profile.preferences.wallet_sync_label')"
            :aria-pressed="walletSyncOn"
          >
            <span
              class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
              :class="walletSyncOn ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
          <span class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ walletSyncOn ? $t('profile.preferences.wallet_sync_enabled') : $t('profile.preferences.wallet_sync_disabled') }}
          </span>
        </div>

        <p v-if="!walletSyncAvailable" class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.wallet_sync_needs_wallet') }}
        </p>
        <p v-else-if="walletSyncError === 'key-mismatch'" class="text-xs text-amber-600 dark:text-amber-400 mt-2">
          {{ $t('profile.preferences.wallet_sync_key_mismatch') }}
        </p>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
          {{ $t('profile.preferences.wallet_sync_hint') }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useNotification } from '~/composables/useNotification'

const { t } = useI18n()
const { showSuccess } = useNotification()

// Wallet cross-device sync — server-side account flag, encrypted client-side.
// Off by default; the toggle needs a wallet on this device to derive the key.
const walletSync = useWalletSync()
const walletSyncOn = computed(() => walletSync.enabled.value === true)
const walletSyncError = walletSync.lastError
const walletSyncAvailable = ref(false)
const walletSyncBusy = ref(false)

onMounted(async () => {
  walletSyncAvailable.value = walletSync.hasWallet()
  await walletSync.refreshStatus()
  // Already on: validate this device's key right here, so a seed mismatch is
  // reported on the settings page instead of as a silently empty cabinet.
  if (walletSync.enabled.value === true && walletSyncAvailable.value) {
    walletSync.pull(true)
  }
})

const toggleWalletSync = async () => {
  walletSyncBusy.value = true
  try {
    if (walletSyncOn.value) {
      const ok = await walletSync.disable()
      if (ok) showSuccess(t('profile.preferences.wallet_sync_disabled_toast'))
    } else {
      const ok = await walletSync.enable()
      if (ok) showSuccess(t('profile.preferences.wallet_sync_enabled_toast'))
    }
  } finally {
    walletSyncBusy.value = false
  }
}
</script>
