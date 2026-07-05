<template>
  <div class="bg-neutral-50 dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 pb-4">
    <div class="max-w-[42rem] w-full mx-auto">
      <!-- Balance card -->
      <div v-if="!showNoSeedWarning && !showWalletIntro && sdkState !== 'error'" class="w-full bg-secondary-700 dark:bg-secondary-800 rounded-2xl p-4 mb-2 transition-colors duration-300" :class="{ '!bg-secondary-500 dark:!bg-secondary-600': balanceFlash }">
        <div class="flex items-center justify-between mb-2">
          <h1 class="text-sm font-medium text-white/70">{{ $t('wallet.title') }}</h1>
          <div class="flex items-center gap-2">
            <button
              v-if="lightningAddress"
              type="button"
              class="text-xs text-white/60 hover:text-white bg-white/10 hover:bg-white/20 px-2.5 py-1 rounded-full transition-colors font-mono truncate max-w-[200px]"
              @click="copyLnAddress"
              :title="$t('wallet.copyLnAddress')"
            >
              {{ lnAddressCopied ? $t('common.copied') : lightningAddress.lightningAddress }}
            </button>
            <button
              type="button"
              class="p-1.5 rounded-full text-white/60 hover:text-white hover:bg-white/10 transition-colors"
              @click="balanceHidden = !balanceHidden"
              :title="balanceHidden ? $t('wallet.showBalance') : $t('wallet.hideBalance')"
            >
              <EyeOff v-if="balanceHidden" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
            <button
              type="button"
              class="p-1.5 rounded-full transition-colors"
              :class="balanceFlash ? 'text-success-400 bg-success-400/20' : 'text-white/60 hover:text-white hover:bg-white/10'"
              @click="refreshBalance"
              :disabled="loadingBalance"
            >
              <Check v-if="balanceFlash" class="w-4 h-4" />
              <RefreshCw v-else class="w-4 h-4" :class="{ 'animate-spin': loadingBalance }" />
            </button>
          </div>
        </div>

        <!-- Balance display -->
        <div class="text-center py-2">
          <!-- Hidden balance (shown immediately — no scary 0 since it's masked) -->
          <template v-if="balanceHidden">
            <p class="text-3xl font-bold text-white tracking-tight">••••••</p>
            <p class="text-sm text-white/60 mt-1">••••••</p>
          </template>
          <!-- Skeleton until the real balance lands: never flash a premature 0 -->
          <template v-else-if="!balanceLoaded">
            <div class="h-8 w-40 mx-auto bg-white/20 rounded animate-pulse mb-2"></div>
            <div class="h-4 w-24 mx-auto bg-white/10 rounded animate-pulse"></div>
          </template>
          <!-- Visible balance -->
          <template v-else>
            <div
              class="cursor-pointer select-none"
              @click="balanceFiat !== null && userCurrency !== 'BTC' && (showSatsFirst = !showSatsFirst)"
            >
              <template v-if="balanceFiat !== null && userCurrency !== 'BTC'">
                <p class="text-3xl font-bold text-white tracking-tight tabular-nums">
                  {{ showSatsFirst ? `${formatSats(balanceSats)} sats` : formatFiat(balanceFiat) }}
                </p>
                <p class="text-sm text-white/60 tabular-nums mt-1">
                  {{ showSatsFirst ? formatFiat(balanceFiat) : `${formatSats(balanceSats)} sats` }}
                </p>
              </template>
              <p v-else class="text-3xl font-bold text-white tabular-nums">
                {{ formatSats(balanceSats) }} sats
              </p>
            </div>
          </template>
        </div>
      </div>

      <!-- Quick action buttons -->
      <div v-if="sdkState === 'ready'" class="flex gap-3 mb-2">
        <UiButton variant="primary" class="flex-1 !py-3 !text-base !font-semibold !rounded-xl" :icon="ArrowUpFromLine" @click="showSendModal = true">
          {{ $t('wallet.send') }}
        </UiButton>
        <UiButton variant="primary" class="flex-1 !py-3 !text-base !font-semibold !rounded-xl" :icon="Download" @click="showReceiveModal = true">
          {{ $t('wallet.receive') }}
        </UiButton>
      </div>
      <!-- Skeleton quick actions -->
      <div v-else-if="sdkState === 'initializing' && !showNoSeedWarning && !showWalletIntro" class="flex gap-3 mb-2">
        <div class="flex-1 h-12 bg-neutral-200 dark:bg-neutral-700 rounded-xl animate-pulse"></div>
        <div class="flex-1 h-12 bg-neutral-200 dark:bg-neutral-700 rounded-xl animate-pulse"></div>
      </div>

      <!-- Page title when balance card is hidden due to SDK error -->
      <div v-if="sdkState === 'error' && !showNoSeedWarning && !showWalletIntro" class="pt-4 pb-2">
        <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('wallet.title') }}</h1>
      </div>

      <!-- Content tabs (History / Debts / Tickets) -->
      <div v-if="!showNoSeedWarning && !showWalletIntro" class="mb-2">
        <UiTabs v-model="activeTab" :tabs="tabs" full-width />
      </div>

      <!-- ===== HISTORY TAB ===== -->
      <WalletHistory v-if="activeTab === 'history' && sdkState === 'ready'" ref="historyRef" />

      <!-- History: SDK error -->
      <div v-if="activeTab === 'history' && sdkState === 'error' && !showNoSeedWarning && !showWalletIntro" class="space-y-6">
        <UiAlert variant="error" :title="sdkError === 'walletOpenInAnotherTab' ? $t('wallet.walletOpenInAnotherTab') : $t('wallet.initError')">
          <p v-if="sdkError && sdkError !== 'walletOpenInAnotherTab' && sdkError !== 'noSeed'" class="font-mono text-xs">
            {{ sdkError }}
          </p>
          <div v-if="sdkError === 'walletOpenInAnotherTab'" class="flex flex-wrap gap-2 mt-3">
            <UiButton variant="primary" size="sm" :icon="LogIn" @click="takeOverLock">
              {{ $t('wallet.openHere') }}
            </UiButton>
            <UiButton variant="outline" size="sm" :icon="RefreshCw" @click="reloadWallet">
              {{ $t('common.retry') }}
            </UiButton>
          </div>
        </UiAlert>
      </div>

      <!-- History skeleton when SDK initializing -->
      <div v-if="activeTab === 'history' && sdkState === 'initializing'" class="bg-white dark:bg-neutral-800 rounded-xl p-6">
        <div class="space-y-4">
          <div v-for="i in 3" :key="i" class="flex items-center gap-3">
            <div class="w-8 h-8 bg-neutral-200 dark:bg-neutral-700 rounded-full animate-pulse"></div>
            <div class="flex-1 space-y-2">
              <div class="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse"></div>
              <div class="h-3 w-20 bg-neutral-100 dark:bg-neutral-700/50 rounded animate-pulse"></div>
            </div>
            <div class="h-4 w-16 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse"></div>
          </div>
        </div>
      </div>

      <!-- ===== DEBTS TAB ===== -->
      <WalletDebtsTab v-if="activeTab === 'debts'" ref="debtsTabRef" />

      <!-- ===== TICKETS TAB ===== -->
      <div v-if="activeTab === 'tickets'" class="space-y-3">
        <div v-if="loadingMyTickets" class="text-center py-8">
          <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto" role="status">
            <span class="sr-only">Loading...</span>
          </div>
        </div>
        <div v-else-if="myTickets.length === 0" class="bg-white dark:bg-neutral-800 rounded-xl p-6 text-center">
          <Ticket class="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
          <p class="text-neutral-500">{{ $t('tickets.no_tickets') }}</p>
        </div>
        <template v-else>
          <TicketsTicketCard
            v-for="ticket in myTickets"
            :key="ticket.id"
            :ticket="ticket"
            @show-qr="walletQrTicket = ticket"
          />
          <div
            v-for="ticket in unsignedActiveTickets"
            :key="`sign-${ticket.id}`"
            class="flex items-center gap-2 px-4 py-2 bg-neutral-50 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700"
          >
            <span class="text-sm text-neutral-600 dark:text-neutral-400 flex-1 truncate">
              {{ ticket.ticket_type_name }}
            </span>
            <UiButton
              variant="outline"
              size="sm"
              :loading="signingTicketId === ticket.id"
              @click="signMyTicket(ticket)"
            >
              <ShieldCheck class="w-3.5 h-3.5 mr-1" />
              {{ $t('tickets.pgp_sign') }}
            </UiButton>
          </div>
        </template>
        <TicketsTicketQRModal :ticket="walletQrTicket" @close="walletQrTicket = null" />
      </div>


      <!-- ===== WALLET INTRO (no seed, first visit) ===== -->
      <div v-if="showWalletIntro" class="space-y-4">
        <div class="bg-white dark:bg-neutral-800 rounded-xl p-6 text-center">
          <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-primary/20 flex items-center justify-center">
            <Zap class="w-8 h-8 text-primary" />
          </div>
          <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            {{ $t('wallet.introTitle') }}
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400 mb-6">
            {{ $t('wallet.introDescription') }}
          </p>

          <div class="space-y-3 text-left mb-6">
            <div class="flex items-start gap-3">
              <Send class="w-5 h-5 text-primary mt-0.5 shrink-0" />
              <p class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('wallet.introFeature1') }}</p>
            </div>
            <div class="flex items-start gap-3">
              <Shield class="w-5 h-5 text-primary mt-0.5 shrink-0" />
              <p class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('wallet.introFeature2') }}</p>
            </div>
            <div class="flex items-start gap-3">
              <Ticket class="w-5 h-5 text-primary mt-0.5 shrink-0" />
              <p class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('wallet.introFeature3') }}</p>
            </div>
          </div>

          <div class="space-y-3">
            <UiButton
              variant="primary"
              :icon="Zap"
              :to="localePath('/seed-setup') + '?next=' + encodeURIComponent(localePath('/wallet'))"
              class="w-full"
            >
              {{ $t('wallet.setupWallet') }}
            </UiButton>

            <UiButton
              variant="secondary"
              :icon="Download"
              :to="localePath('/seed-restore') + '?next=' + encodeURIComponent(localePath('/wallet'))"
              class="w-full"
            >
              {{ $t('seed.restoreFromSeed') }}
            </UiButton>
          </div>
        </div>

        <!-- Tickets shortcut -->
        <div class="text-center">
          <button
            type="button"
            class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary transition-colors"
            @click="activeTab = 'tickets'; showWalletIntro = false"
          >
            {{ $t('wallet.viewTicketsWithoutWallet') }}
          </button>
        </div>
      </div>

      <!-- ===== NO SEED WARNING (has PGP key, different device) ===== -->
      <div v-if="showNoSeedWarning" class="space-y-6">
        <div class="bg-white dark:bg-neutral-800 rounded-xl p-6 space-y-4">
          <p class="text-neutral-600 dark:text-neutral-400">
            {{ $t('wallet.noLocalSeed') }}
          </p>

          <div class="space-y-3">
            <UiButton
              variant="primary"
              :icon="Download"
              :to="localePath('/seed-restore') + '?next=' + encodeURIComponent(localePath('/wallet'))"
              class="w-full"
            >
              {{ $t('seed.restoreFromSeed') }}
            </UiButton>

            <UiButton
              variant="warning"
              :icon="Plus"
              :to="localePath('/seed-setup') + '?next=' + encodeURIComponent(localePath('/wallet'))"
              class="w-full"
            >
              {{ $t('wallet.generateNewSeed') }}
            </UiButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Modals -->
    <WalletSendModal v-model="showSendModal" @success="onSendSuccess" />
    <WalletReceiveModal v-model="showReceiveModal" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, onUnmounted, markRaw, watch } from 'vue'
import {
  RefreshCw, Download, ArrowUpFromLine,
  History, Check, Plus, Eye, EyeOff,
  Ticket, ShieldCheck, HandCoins, Zap, Shield, Send, LogIn
} from 'lucide-vue-next'
import { useLightning } from '~/composables/useLightning'
import { useBtcPrice } from '~/composables/useBtcPrice'
import { useAuthStore } from '~/stores/auth'
import { useLocalPref } from '~/composables/useLocalPref'

definePageMeta({
  middleware: 'auth',
  key: 'wallet'
})

const { t, locale } = useI18n()
const router = useRouter()

useSeoMeta({
  title: t('wallet.title') + ' - Parahub',
  ogTitle: t('wallet.title') + ' - Parahub',
})
const localePath = useLocalePath()
const authStore = useAuthStore()

const {
  sdkState,
  sdkError,
  balanceSats,
  balanceLoaded,
  lightningAddress,
  initSdk,
  takeOverLock,
  syncAndRefresh: doRefreshBalance,
  getSparkAddress,
  paymentEventVersion,
  registerLnAddress,
  checkLnAddressAvailable,
  getLnAddress,
  formatSats,
  hasSeed
} = useLightning()

const {
  userCurrency,
  fetchBtcPrice,
  satsToFiat,
  formatFiat
} = useBtcPrice()

const reloadWallet = () => { if (import.meta.client) window.location.reload() }

// ===== MODALS =====
const showSendModal = ref(false)
const showReceiveModal = ref(false)

// ===== TABS (3 content tabs) =====
const route = useRoute()
const tabs = computed(() => [
  { id: 'history', label: t('wallet.history'), icon: markRaw(History) },
  { id: 'debts', label: t('wallet.debts'), icon: markRaw(HandCoins) },
  { id: 'tickets', label: t('tickets.my_tickets'), icon: markRaw(Ticket) },
])
const validTabs = ['history', 'debts', 'tickets']
const routeTab = route.params.tab as string | undefined
// Legacy URL support: /wallet/send → open send modal, /wallet/receive → open receive modal
const legacySendReceive = routeTab === 'send' || routeTab === 'receive'
const initialTab = routeTab && validTabs.includes(routeTab) ? routeTab : 'history'
const activeTab = ref(initialTab)

watch(activeTab, (newTab) => {
  if (newTab === 'history') {
    router.replace(localePath('/wallet'))
  } else {
    router.replace(localePath(`/wallet/${newTab}`))
  }
  if (newTab === 'tickets') loadMyTickets()
})

// ===== BALANCE =====
const balanceHidden = useLocalPref('parahub_balance_hidden', false)
const loadingBalance = ref(false)
const showSatsFirst = ref(false)
const balanceFlash = ref(false)

const balanceFiat = computed(() => {
  if (userCurrency.value === 'BTC') return null
  if (balanceSats.value === 0) return 0
  return satsToFiat(balanceSats.value)
})

const refreshBalance = async () => {
  loadingBalance.value = true
  try {
    await doRefreshBalance()
    balanceFlash.value = true
    setTimeout(() => { balanceFlash.value = false }, 800)
  } finally {
    loadingBalance.value = false
  }
}

// ===== SEND SUCCESS HANDLER =====
const historyRef = ref<InstanceType<typeof WalletHistory> | null>(null)

const onSendSuccess = () => {
  balanceFlash.value = true
  setTimeout(() => { balanceFlash.value = false }, 800)
  historyRef.value?.loadHistory()
  doRefreshBalance()
}

// ===== DEBTS =====
const debtsTabRef = ref<any>(null)

// ===== TICKETS =====
const myTickets = ref<any[]>([])
const loadingMyTickets = ref(false)
const walletQrTicket = ref<any>(null)
const signingTicketId = ref<string | null>(null)

const unsignedActiveTickets = computed(() =>
  myTickets.value.filter(t => t.status === 'ACTIVE' && !t.pgp_signature)
)

const loadMyTickets = async () => {
  loadingMyTickets.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch<any[]>('/api/v1/tickets/my/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    myTickets.value = data || []
  } catch (e) {
    console.error('Failed to load tickets:', e)
  } finally {
    loadingMyTickets.value = false
  }
}

const signMyTicket = async (ticket: any) => {
  signingTicketId.value = ticket.id
  try {
    const { signMessage } = usePGP()
    const signature = await signMessage(ticket.qr_token)
    await authStore.ensureToken()
    const updated = await $fetch<any>(`/api/v1/tickets/${ticket.id}/sign/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { pgp_signature: signature },
    })
    const idx = myTickets.value.findIndex(t => t.id === ticket.id)
    if (idx !== -1) myTickets.value[idx] = updated
  } catch (e: any) {
    console.error('PGP sign failed:', e)
  } finally {
    signingTicketId.value = null
  }
}

// ===== LIGHTNING ADDRESS =====
const lnAddressCopied = ref(false)

const syncLnAddressToProfile = async (address: string) => {
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {},
      body: { ln_address: address }
    })
  } catch {}
}

const syncSparkAddressToProfile = async () => {
  try {
    const result = await getSparkAddress()
    if (!result.paymentRequest) return
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {},
      body: { spark_address: result.paymentRequest }
    })
  } catch {}
}

const autoRegisterLnAddress = async () => {
  const username = authStore.user?.username || authStore.profile?.local_name
  if (!username) return

  const maxAttempts = 10
  for (let i = 0; i < maxAttempts; i++) {
    const candidate = i === 0 ? username : `${username}${i}`
    try {
      const available = await checkLnAddressAvailable(candidate)
      if (!available) continue

      const info = await registerLnAddress(candidate)
      try {
        await authStore.ensureToken()
        const headers = authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {}
        await $fetch('/api/v1/profiles/me/preferences/', {
          method: 'PATCH',
          credentials: 'include',
          headers,
          body: { ln_address: info.lightningAddress }
        })
      } catch {}
      return
    } catch {}
  }
}

const copyLnAddress = async () => {
  if (!lightningAddress.value) return
  try {
    await navigator.clipboard.writeText(lightningAddress.value.lightningAddress)
    lnAddressCopied.value = true
    setTimeout(() => { lnAddressCopied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

// ===== NO SEED / WALLET INTRO =====
const showNoSeedWarning = ref(false)
const showWalletIntro = ref(false)

// ===== LIFECYCLE =====
onMounted(async () => {
  // Tickets tab doesn't require SDK
  if (activeTab.value === 'tickets') loadMyTickets()

  // Legacy URL support: open modal for /wallet/send or /wallet/receive
  if (legacySendReceive) {
    router.replace(localePath('/wallet'))
    if (routeTab === 'send') showSendModal.value = true
    if (routeTab === 'receive') showReceiveModal.value = true
  }

  if (!hasSeed()) {
    if (authStore.profile?.pgp_fingerprint) {
      showNoSeedWarning.value = true
      return
    }
    if (activeTab.value === 'tickets' || activeTab.value === 'debts') return
    showWalletIntro.value = true
    return
  }

  await initSdk()

  if (sdkError.value === 'noSeed') {
    if (authStore.profile?.pgp_fingerprint) {
      showNoSeedWarning.value = true
    } else {
      showWalletIntro.value = true
    }
    return
  }

  try { await getLnAddress() } catch {}

  if (!lightningAddress.value) {
    await autoRegisterLnAddress()
  } else {
    syncLnAddressToProfile(lightningAddress.value.lightningAddress)
  }

  syncSparkAddressToProfile()
  fetchBtcPrice()

  if (activeTab.value === 'tickets') loadMyTickets()

  // Open legacy modals after SDK ready
  if (legacySendReceive && sdkState.value === 'ready') {
    if (routeTab === 'send') showSendModal.value = true
    if (routeTab === 'receive') showReceiveModal.value = true
  }
})

// KeepAlive: re-check seed when returning from seed-restore/seed-setup
onActivated(async () => {
  if ((showNoSeedWarning.value || showWalletIntro.value) && hasSeed()) {
    showNoSeedWarning.value = false
    showWalletIntro.value = false
    await initSdk()
    if (sdkState.value === 'ready') {
      try { await getLnAddress() } catch {}
      if (!lightningAddress.value) {
        await autoRegisterLnAddress()
      } else {
        syncLnAddressToProfile(lightningAddress.value.lightningAddress)
      }
      syncSparkAddressToProfile()
      fetchBtcPrice()
    }
  }
})
</script>
