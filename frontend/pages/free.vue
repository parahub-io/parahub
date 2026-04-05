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

    <div class="max-w-2xl mx-auto px-4 py-10 space-y-8">
      <!-- Current Plan -->
      <div class="card p-6">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.free_plan_free') }}</h2>
            <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.free_speed_free') }}</p>
          </div>
          <div class="text-right">
            <p class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('mesh.subscribe_your_ip') }}</p>
            <p v-if="clientIP" class="text-lg font-mono font-bold text-neutral-900 dark:text-neutral-100">{{ clientIP }}</p>
            <p v-else class="text-neutral-400">...</p>
          </div>
        </div>
      </div>

      <!-- Upgrade Section -->
      <div class="text-center space-y-3">
        <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.free_upgrade_title') }}</h2>
        <p class="text-neutral-600 dark:text-neutral-400">{{ $t('mesh.free_upgrade_desc') }}</p>
        <p class="text-lg text-neutral-700 dark:text-neutral-300">
          {{ $t('mesh.subscribe_price', { amount: formatNumber(priceSats), days: durationDays }) }}
        </p>
      </div>

      <!-- State: Initial -->
      <div v-if="state === 'initial'" class="text-center space-y-4">
        <button
          @click="subscribe"
          :disabled="!clientIP || subscribing"
          class="btn-primary gap-2 px-8 py-4 rounded-xl text-lg font-bold"
        >
          <Zap class="w-5 h-5" />
          {{ subscribing ? '...' : $t('mesh.subscribe_pay') }}
        </button>
        <p v-if="error" class="text-error text-sm">{{ error }}</p>
      </div>

      <!-- State: Invoice / QR -->
      <div v-if="state === 'invoice'" class="text-center space-y-6">
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.subscribe_scan_qr') }}</p>

        <div class="flex justify-center">
          <canvas ref="qrCanvas" class="rounded-xl border-2 border-neutral-300 dark:border-neutral-600" role="img" :aria-label="$t('mesh.invoice_qr_aria_label')"></canvas>
        </div>

        <!-- Copyable invoice -->
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
            {{ copied ? '\u2713' : 'Copy' }}
          </button>
        </div>

        <div class="flex items-center justify-center gap-2 text-warning dark:text-warning">
          <Loader2 class="w-5 h-5 animate-spin" />
          <span class="text-sm">{{ $t('mesh.subscribe_waiting') }}</span>
        </div>

        <p class="text-xs text-neutral-400">{{ $t('mesh.subscribe_tv_hint') }}</p>
      </div>

      <!-- State: Active -->
      <div v-if="state === 'active'" class="text-center space-y-4">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-success-100 dark:bg-success-900/30 rounded-full mb-2">
          <Check class="w-8 h-8 text-success" />
        </div>
        <h2 class="text-2xl font-bold text-success">{{ $t('mesh.subscribe_active') }}</h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.free_speed_paid') }}</p>
        <p v-if="expiresAt" class="text-neutral-600 dark:text-neutral-400">
          {{ $t('mesh.subscribe_expires', { date: formatDate(expiresAt) }) }}
        </p>
      </div>

      <!-- State: Expired -->
      <div v-if="state === 'expired'" class="text-center space-y-4">
        <p class="text-neutral-500">{{ $t('mesh.subscribe_expired') }}</p>
        <button
          @click="reset"
          class="btn-primary gap-2 px-6 py-3 rounded-xl font-bold"
        >
          <RefreshCw class="w-5 h-5" />
          {{ $t('mesh.subscribe_renew') }}
        </button>
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
const localePath = useLocalePath()
import { Wifi, Zap, Check, RefreshCw, Loader2 } from 'lucide-vue-next'
import QRCode from 'qrcode'

definePageMeta({
  auth: false,
})
useHead({ title: 'Free WiFi' })

const { $fetch } = useNuxtApp()
const { locale } = useI18n()

const state = ref<'initial' | 'invoice' | 'active' | 'expired'>('initial')
const clientIP = ref('')
const invoice = ref('')
const paymentHash = ref('')
const priceSats = ref(50000)
const durationDays = ref(30)
const expiresAt = ref<string | null>(null)
const error = ref('')
const subscribing = ref(false)
const copied = ref(false)
const qrCanvas = ref<HTMLCanvasElement | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  try {
    const data = await $fetch<{ ip: string }>('/api/v1/iot/mesh/my-ip')
    clientIP.value = data.ip
  } catch {
    // IP detection failed
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

function formatNumber(n: number): string {
  return n.toLocaleString()
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

async function subscribe() {
  error.value = ''
  subscribing.value = true

  try {
    const data = await $fetch<{
      invoice: string
      payment_hash: string
      amount_sats: number
      expires_minutes: number
    }>('/api/v1/iot/mesh/subscribe', {
      method: 'POST',
      body: {},
    })

    invoice.value = data.invoice
    paymentHash.value = data.payment_hash
    priceSats.value = data.amount_sats
    state.value = 'invoice'

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
    error.value = e?.data?.detail || e?.message || 'Failed to create invoice'
  } finally {
    subscribing.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const data = await $fetch<{
        status: string
        expires_at: string | null
      }>(`/api/v1/iot/mesh/subscribe/status/${paymentHash.value}`)

      if (data.status === 'active') {
        state.value = 'active'
        expiresAt.value = data.expires_at
        if (pollTimer) clearInterval(pollTimer)
      } else if (data.status === 'expired') {
        state.value = 'expired'
        if (pollTimer) clearInterval(pollTimer)
      }
    } catch { /* keep polling */ }
  }, 3000)
}

function reset() {
  state.value = 'initial'
  invoice.value = ''
  paymentHash.value = ''
  expiresAt.value = null
  error.value = ''
}
</script>
