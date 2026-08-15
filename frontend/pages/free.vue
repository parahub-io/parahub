<template>
  <div class="min-h-screen bg-white dark:bg-neutral-900">
    <!-- Hero -->
    <div class="bg-primary py-12">
      <div class="max-w-2xl mx-auto px-4 text-center">
        <Wifi class="w-12 h-12 mx-auto mb-3 text-neutral-900" />
        <h1 class="text-3xl font-bold text-neutral-900 mb-2">{{ $t('mesh.free_title') }}</h1>
        <p class="text-neutral-800">{{ $t('mesh.free_subtitle') }}</p>
      </div>
    </div>

    <div class="max-w-2xl mx-auto px-4 py-10 space-y-6">
      <!-- Network status -->
      <UiAlert v-if="network === 'guest'" variant="info" :icon="Wifi">
        <i18n-t keypath="mesh.network_guest" tag="span">
          <template #node>
            <NuxtLink
              v-if="nodeId"
              :to="localePath({ path: '/map', query: { device: `mesh:${nodeId}` } })"
              class="font-medium underline"
            >{{ nodeHostname || 'Parahub' }}</NuxtLink>
            <template v-else>{{ nodeHostname || 'Parahub' }}</template>
          </template>
        </i18n-t>
      </UiAlert>
      <UiAlert v-else-if="network === 'private'" variant="success" :icon="Wifi">
        {{ $t('mesh.network_private') }}
      </UiAlert>
      <UiAlert v-else-if="networkChecked" variant="info" :icon="WifiOff">
        {{ $t('mesh.network_off') }}
      </UiAlert>

      <!-- Intro -->
      <div class="text-center space-y-2">
        <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.pass_title') }}</h2>
        <p class="text-neutral-600 dark:text-neutral-400">
          {{ $t('mesh.pass_intro', { n: passInfo?.max_devices ?? 5 }) }}
        </p>
        <p class="text-lg text-neutral-700 dark:text-neutral-300">
          {{ $t('mesh.subscribe_price', { amount: formatNumber(passInfo?.price_sats ?? 5000), days: passInfo?.duration_days ?? 30 }) }}
        </p>
      </div>

      <!-- Not logged in -->
      <div v-if="!authStore.isAuthenticated" class="py-12 text-center space-y-4">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-secondary-100 dark:bg-secondary-900/30">
          <KeyRound class="w-8 h-8 text-secondary" />
        </div>
        <p class="text-neutral-600 dark:text-neutral-400 max-w-md mx-auto">{{ $t('mesh.pass_login_hint') }}</p>
        <UiButton variant="primary" :to="localePath(`/login?redirect=${encodeURIComponent(route.fullPath)}`)">
          {{ $t('mesh.pass_login_cta') }}
        </UiButton>
      </div>

      <template v-else>
        <!-- Loading pass (or auth still hydrating) -->
        <div v-if="passLoading || !passAttempted" class="py-12 text-center" role="status">
          <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 mx-auto"></div>
          <span class="sr-only">Loading</span>
        </div>

        <template v-else-if="passInfo">
          <!-- Active pass -->
          <div v-if="passInfo.active" class="card p-6 space-y-4">
            <div class="flex items-center gap-3">
              <div class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-success-100 dark:bg-success-900/30 shrink-0">
                <Check class="w-5 h-5 text-success" />
              </div>
              <div>
                <h3 class="font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.free_speed_paid') }}</h3>
                <p class="text-sm text-neutral-500 dark:text-neutral-400">
                  {{ $t('mesh.pass_active_until', { date: formatDate(passInfo.expires_at!) }) }}
                </p>
                <p v-if="passInfo.from_hosting" class="text-sm text-neutral-500 dark:text-neutral-400">
                  {{ $t('mesh.pass_from_hosting') }}
                </p>
              </div>
            </div>

            <!-- Bind this device. `thisDeviceBound` is a localStorage heuristic
                 (per browser, and per-connection MAC randomization can defeat
                 the MAC binding), so the action stays available as a demoted
                 "re-activate" instead of disappearing. -->
            <div class="space-y-2">
              <UiAlert
                v-if="thisDeviceBound && network === 'guest' && !bindResult && !bindError"
                variant="success"
                :icon="Zap"
              >
                {{ $t('mesh.device_active_here') }}
              </UiAlert>
              <UiButton
                :variant="thisDeviceBound ? 'outline' : 'primary'"
                size="lg"
                class="w-full"
                :icon="Zap"
                :loading="binding"
                :disabled="network !== 'guest'"
                @click="bindDevice"
              >
                {{ thisDeviceBound ? $t('mesh.bind_again') : $t('mesh.bind_button') }}
              </UiButton>
              <p v-if="network === 'private'" class="text-sm text-center text-neutral-500 dark:text-neutral-400">
                {{ $t('mesh.bind_err_private') }}
              </p>
              <p v-else-if="networkChecked && network !== 'guest'" class="text-sm text-center text-neutral-500 dark:text-neutral-400">
                {{ $t('mesh.bind_err_not_on_mesh') }}
              </p>
              <UiAlert v-if="bindResult === 'activated'" variant="success" :icon="Zap">
                {{ $t('mesh.bind_success') }}
              </UiAlert>
              <UiAlert v-else-if="bindResult === 'pending'" variant="info" :icon="Clock">
                {{ $t('mesh.bind_pending') }}
              </UiAlert>
              <UiAlert v-else-if="bindError" variant="warning" :icon="AlertTriangle">
                {{ bindError }}
              </UiAlert>
            </div>
          </div>

          <!-- No active pass: pay -->
          <div v-else class="card p-6 space-y-4">
            <h3 class="font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.pass_inactive') }}</h3>

            <template v-if="payState === 'idle'">
              <UiButton
                v-if="passInfo.payments_available"
                variant="primary"
                size="lg"
                class="w-full"
                :icon="Zap"
                :loading="paying"
                @click="buyPass"
              >
                {{ $t('mesh.subscribe_pay') }}
              </UiButton>
              <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ $t('mesh.pass_payments_unavailable') }}
              </p>
              <p v-if="payError" class="text-error text-sm">{{ payError }}</p>
            </template>

            <template v-else-if="payState === 'invoice'">
              <p class="text-sm text-center text-neutral-500 dark:text-neutral-400">{{ $t('mesh.subscribe_scan_qr') }}</p>
              <div class="flex justify-center">
                <canvas ref="qrCanvas" class="rounded-xl border-2 border-neutral-300 dark:border-neutral-600" role="img" :aria-label="$t('mesh.invoice_qr_aria_label')"></canvas>
              </div>
              <div class="relative">
                <input
                  :value="invoice"
                  readonly
                  class="w-full px-4 py-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg text-xs font-mono text-neutral-600 dark:text-neutral-400 pr-20"
                  @click="copyInvoice"
                />
                <button
                  @click="copyInvoice"
                  class="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-neutral-200 dark:bg-neutral-700 rounded text-xs hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors"
                >
                  {{ copied ? '✓' : 'Copy' }}
                </button>
              </div>
              <div class="flex items-center justify-center gap-2 text-warning">
                <Loader2 class="w-5 h-5 animate-spin" />
                <span class="text-sm">{{ $t('mesh.subscribe_waiting') }}</span>
              </div>
            </template>
          </div>

          <!-- Devices -->
          <div v-if="passInfo.devices.length" class="space-y-2">
            <h3 class="font-bold text-neutral-900 dark:text-neutral-100">
              {{ $t('mesh.devices_title') }}
              <span class="text-sm font-normal text-neutral-500 dark:text-neutral-400">{{ passInfo.devices.length }}/{{ passInfo.max_devices }}</span>
            </h3>
            <div class="border border-neutral-300 dark:border-neutral-600 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
              <div
                v-for="d in passInfo.devices"
                :key="d.id"
                class="flex items-center justify-between gap-3 px-4 py-3"
              >
                <div class="min-w-0">
                  <p class="font-medium text-neutral-900 dark:text-neutral-100 truncate">
                    {{ d.label || d.mac }}
                    <UiBadge v-if="d.id === thisDeviceId" variant="secondary" type="soft" size="sm">{{ $t('mesh.device_this') }}</UiBadge>
                  </p>
                  <p class="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                    {{ d.mac }}<span v-if="d.last_ipv4"> · {{ d.last_ipv4 }}</span>
                  </p>
                </div>
                <UiButton
                  :variant="removePending === d.id ? 'error' : 'ghost'"
                  size="sm"
                  :icon="Trash2"
                  :loading="removing === d.id"
                  @click="removeDevice(d)"
                >
                  {{ removePending === d.id ? $t('mesh.device_remove_confirm') : $t('mesh.device_remove') }}
                </UiButton>
              </div>
            </div>
          </div>
          <p v-else-if="passInfo.active" class="text-sm text-center text-neutral-500 dark:text-neutral-400">
            {{ $t('mesh.devices_empty') }}
          </p>
        </template>

        <!-- Pass failed to load (expired session, backend hiccup) -->
        <div v-else class="py-12 text-center space-y-3">
          <p class="text-neutral-500 dark:text-neutral-400">{{ $t('mesh.pass_load_error') }}</p>
          <UiButton variant="outline" :icon="RefreshCw" @click="loadPass">{{ $t('mesh.pass_retry') }}</UiButton>
        </div>
      </template>

      <!-- What the network sees: guests get this notice without having to log in -->
      <div class="card p-5 space-y-2">
        <div class="flex items-center gap-2">
          <ShieldCheck class="w-5 h-5 text-secondary shrink-0" />
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.free_privacy_title') }}</h3>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('mesh.free_privacy_text') }}</p>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <NuxtLink :to="localePath('/about/privacy')" class="text-secondary hover:underline">{{ $t('mesh.free_privacy_link') }}</NuxtLink>
          <NuxtLink :to="localePath('/mesh/peering')" class="text-secondary hover:underline">{{ $t('mesh.free_peering_link') }}</NuxtLink>
        </div>
      </div>

      <!-- Footer -->
      <div class="text-center pt-4 border-t border-neutral-200 dark:border-neutral-700 space-y-2">
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.free_powered_by') }}</p>
        <NuxtLink :to="localePath('/mesh')" class="text-sm text-secondary dark:text-secondary hover:underline">
          {{ $t('mesh.free_learn_more') }} →
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Wifi, WifiOff, Zap, Check, Clock, KeyRound, Loader2, RefreshCw, Trash2, AlertTriangle, ShieldCheck } from 'lucide-vue-next'
import QRCode from 'qrcode'

definePageMeta({
  auth: false,
})
useHead({ title: 'Free WiFi' })

const localePath = useLocalePath()
const route = useRoute()
const { t, locale } = useI18n()
const authStore = useAuthStore()

interface MeshDevice {
  id: string
  mac: string
  label: string
  last_ipv4: string | null
  last_seen_at: string | null
  created_at: string
}

interface MeshPassInfo {
  active: boolean
  expires_at: string | null
  max_devices: number
  devices: MeshDevice[]
  price_sats: number
  duration_days: number
  payments_available: boolean
  from_hosting: boolean
}

const network = ref<'guest' | 'private' | null>(null)
const networkChecked = ref(false)
const nodeHostname = ref<string | null>(null)
const nodeId = ref<string | null>(null)

const passInfo = ref<MeshPassInfo | null>(null)
const passLoading = ref(false)
const passAttempted = ref(false)

const binding = ref(false)
const bindResult = ref<'activated' | 'pending' | null>(null)
const bindError = ref('')
const thisDeviceId = ref<string | null>(null)
const thisDeviceBound = computed(() =>
  !!thisDeviceId.value && !!passInfo.value?.devices.some(d => d.id === thisDeviceId.value))

const payState = ref<'idle' | 'invoice'>('idle')
const paying = ref(false)
const payError = ref('')
const invoice = ref('')
const paymentHash = ref('')
const copied = ref(false)
const qrCanvas = ref<HTMLCanvasElement | null>(null)

const removePending = ref<string | null>(null)
const removing = ref<string | null>(null)
let removeResetTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  thisDeviceId.value = localStorage.getItem('mesh_device_id')
  try {
    const data = await $fetch<{ on_mesh: boolean; network: string | null; node_hostname: string | null; node_id: string | null }>('/api/v1/iot/mesh/network')
    network.value = (data.network as 'guest' | 'private' | null) ?? null
    nodeHostname.value = data.node_hostname
    nodeId.value = data.node_id
  } catch { /* network detection failed — treat as off-mesh */ }
  networkChecked.value = true

  // Auth hydrates asynchronously after mount — load once it's ready, and
  // whenever it flips (login on this page redirects back here).
  if (authStore.isAuthenticated) await loadPass()
})

watch(() => authStore.isAuthenticated, (isAuth) => {
  if (isAuth) loadPass()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (removeResetTimer) clearTimeout(removeResetTimer)
})

async function authHeaders() {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function loadPass() {
  passLoading.value = true
  try {
    passInfo.value = await $fetch<MeshPassInfo>('/api/v1/iot/mesh/pass', {
      credentials: 'include',
      headers: await authHeaders(),
    })
  } catch { /* keep previous state */ } finally {
    passAttempted.value = true
    passLoading.value = false
  }
}

function formatNumber(n: number): string {
  // Explicit locale: the bare call takes Node's default on SSR, so pt/ru readers
  // got "5,000" — a decimal comma in those locales, i.e. five.
  return n.toLocaleString(locale.value)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, {
    year: 'numeric', month: 'long', day: 'numeric',
  })
}

async function copyInvoice() {
  try {
    await navigator.clipboard.writeText(invoice.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch { /* ignore */ }
}

async function bindDevice() {
  binding.value = true
  bindResult.value = null
  bindError.value = ''
  try {
    const data = await $fetch<{ status: string; device: MeshDevice; activated: boolean }>('/api/v1/iot/mesh/bind', {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
    })
    bindResult.value = data.activated ? 'activated' : 'pending'
    thisDeviceId.value = data.device.id
    localStorage.setItem('mesh_device_id', data.device.id)
    await loadPass()
  } catch (e: any) {
    const code = e?.data?.detail || ''
    const known = ['not_on_mesh', 'on_private_network', 'no_active_pass', 'client_not_found', 'device_bound_elsewhere', 'device_limit_reached', 'node_unreachable']
    if (code === 'device_bound_elsewhere') bindError.value = t('mesh.bind_err_taken')
    else if (code === 'device_limit_reached') bindError.value = t('mesh.bind_err_limit')
    else if (code === 'client_not_found') bindError.value = t('mesh.bind_err_not_found')
    else if (code === 'node_unreachable') bindError.value = t('mesh.bind_err_node')
    else if (code === 'on_private_network') bindError.value = t('mesh.bind_err_private')
    else if (known.includes(code)) bindError.value = t('mesh.bind_err_not_on_mesh')
    else bindError.value = t('mesh.bind_err_node')
  }
  binding.value = false
}

async function buyPass() {
  paying.value = true
  payError.value = ''
  try {
    const data = await $fetch<{ invoice: string; payment_hash: string }>('/api/v1/iot/mesh/pass/invoice', {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
    })
    invoice.value = data.invoice
    paymentHash.value = data.payment_hash
    payState.value = 'invoice'
    await nextTick()
    if (qrCanvas.value) {
      await QRCode.toCanvas(qrCanvas.value, data.invoice.toUpperCase(), {
        width: 280,
        margin: 2,
        color: { dark: '#000000', light: '#ffffff' },
      })
    }
    startPolling()
  } catch (e: any) {
    payError.value = e?.data?.detail || e?.message || 'Failed to create invoice'
  }
  paying.value = false
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const data = await $fetch<{ status: string }>(`/api/v1/iot/mesh/pass/invoice/${paymentHash.value}`, {
        credentials: 'include',
        headers: await authHeaders(),
      })
      if (data.status === 'paid') {
        if (pollTimer) clearInterval(pollTimer)
        payState.value = 'idle'
        await loadPass()
      } else if (data.status === 'expired') {
        if (pollTimer) clearInterval(pollTimer)
        payState.value = 'idle'
      }
    } catch { /* keep polling */ }
  }, 3000)
}

async function removeDevice(d: MeshDevice) {
  if (removePending.value !== d.id) {
    removePending.value = d.id
    if (removeResetTimer) clearTimeout(removeResetTimer)
    removeResetTimer = setTimeout(() => { removePending.value = null }, 3000)
    return
  }
  removePending.value = null
  removing.value = d.id
  try {
    await $fetch(`/api/v1/iot/mesh/devices/${d.id}`, {
      method: 'DELETE',
      credentials: 'include',
      headers: await authHeaders(),
    })
    if (thisDeviceId.value === d.id) {
      thisDeviceId.value = null
      localStorage.removeItem('mesh_device_id')
    }
    await loadPass()
  } catch { /* keep list */ }
  removing.value = null
}
</script>
