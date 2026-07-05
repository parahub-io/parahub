<template>
  <div class="min-h-screen bg-neutral-950 text-white flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-neutral-800">
      <h1 class="text-lg font-semibold">{{ $t('tickets.scan_title') }}</h1>
      <div class="flex items-center gap-2">
        <span
          v-if="queueCount > 0"
          class="inline-flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 rounded-full px-2 py-1"
        >
          <WifiOff class="w-3.5 h-3.5" />
          {{ $t('tickets.offline_queued', { n: queueCount }) }}
        </span>
        <UiButton variant="ghost" size="sm" :to="localePath('/tickets/operator')">
          <ChartColumn class="w-4 h-4 mr-1.5" />
          {{ $t('tickets.operator_title') }}
        </UiButton>
        <UiButton variant="ghost" size="sm" :to="localePath('/')">
          <X class="w-5 h-5" />
        </UiButton>
      </div>
    </div>

    <!-- Sync banner -->
    <div
      v-if="syncBanner"
      class="px-4 py-2 text-sm text-center"
      :class="syncBanner.rejected ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300'"
    >
      {{ $t('tickets.offline_synced', { n: syncBanner.synced, m: syncBanner.rejected }) }}
    </div>

    <!-- Camera / Result -->
    <div class="flex-1 flex flex-col items-center justify-center p-4">
      <!-- Scanning state -->
      <div v-if="state === 'scanning'" class="w-full max-w-sm space-y-4">
        <div class="relative aspect-square rounded-2xl overflow-hidden bg-neutral-900 border-2 border-neutral-700">
          <video ref="videoEl" class="w-full h-full object-cover" autoplay playsinline muted />
          <!-- Scanning overlay -->
          <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div class="w-48 h-48 border-2 border-primary rounded-xl scan-animation" />
          </div>
        </div>
        <p class="text-center text-neutral-400 text-sm">{{ $t('tickets.scan_prompt') }}</p>
      </div>

      <!-- Result state -->
      <div v-else-if="state === 'result'" class="w-full max-w-sm space-y-6 text-center">
        <div
          class="w-24 h-24 mx-auto rounded-full flex items-center justify-center"
          :class="result?.offline ? 'bg-amber-500/20' : (result?.valid ? 'bg-emerald-500/20' : 'bg-red-500/20')"
        >
          <WifiOff v-if="result?.offline" class="w-14 h-14 text-amber-400" />
          <CheckCircle2 v-else-if="result?.valid" class="w-14 h-14 text-emerald-400" />
          <XCircle v-else class="w-14 h-14 text-red-400" />
        </div>

        <div>
          <h2
            class="text-2xl font-bold"
            :class="result?.offline ? 'text-amber-400' : (result?.valid ? 'text-emerald-400' : 'text-red-400')"
          >
            <template v-if="result?.offline">{{ $t('tickets.scan_result_offline') }}</template>
            <template v-else>{{ result?.valid ? $t('tickets.scan_result_valid') : $t('tickets.scan_result_invalid') }}</template>
          </h2>
          <p class="mt-1 text-neutral-400">{{ result?.message }}</p>
        </div>

        <div v-if="result?.ticket_type_name" class="bg-neutral-900 rounded-xl p-4 space-y-2">
          <div class="text-sm text-neutral-500">{{ result.ticket_type_name }}</div>
          <div v-if="result.buyer_name" class="text-lg font-medium">{{ result.buyer_name }}</div>
          <div
            v-if="result.concession_category"
            class="inline-flex items-center gap-1 text-sm text-amber-300 bg-amber-500/10 rounded-full px-3 py-1"
          >
            <BadgeCheck class="w-4 h-4" />
            {{ $t(`tickets.concession_${result.concession_category.toLowerCase()}`) }}
            — {{ $t('tickets.concession_check_doc') }}
          </div>
          <div v-if="result.validation_count && result.validation_count > 1" class="text-sm text-neutral-400">
            {{ $t('tickets.scan_count', { n: result.validation_count }) }}
          </div>
        </div>

        <UiButton variant="outline" class="w-full" @click="resetScan">
          <ScanLine class="w-4 h-4 mr-2" />
          {{ $t('tickets.scan_again') }}
        </UiButton>
      </div>

      <!-- Permission denied -->
      <div v-else-if="state === 'denied'" class="text-center space-y-4">
        <CameraOff class="w-16 h-16 text-neutral-600 mx-auto" />
        <p class="text-neutral-400">{{ $t('tickets.camera_denied') }}</p>
      </div>

      <!-- Loading -->
      <div v-else-if="state === 'validating'" class="text-center space-y-4">
        <div class="w-12 h-12 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin mx-auto" />
        <p class="text-neutral-400">{{ $t('tickets.payment_confirm') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { X, CheckCircle2, XCircle, ScanLine, CameraOff, WifiOff, BadgeCheck, ChartColumn } from 'lucide-vue-next'

definePageMeta({ layout: 'blank', middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

useHead({ title: computed(() => t('tickets.scan_page_title')) })

type ScanState = 'scanning' | 'validating' | 'result' | 'denied'

interface ScanResult {
  valid: boolean
  message: string
  buyer_name?: string
  ticket_type_name?: string
  validation_count?: number | null
  concession_category?: string | null
  offline?: boolean
}

const state = ref<ScanState>('scanning')
const videoEl = ref<HTMLVideoElement | null>(null)
const result = ref<ScanResult | null>(null)
const queueCount = ref(0)
const syncBanner = ref<{ synced: number; rejected: number } | null>(null)

// qr-scanner instance (same lib as WalletSendModal — worker-based decode)
let qrScanner: any = null

// ── Offline support ──────────────────────────────────────────────────
// QR format `PHT1.<b64url payload>.<b64url sig>` is server-signed (Ed25519),
// so the scanner can verify authenticity without network. Offline verdicts
// are advisory; scans are queued and replayed via /validate/sync/.

const QR_PREFIX = 'PHT1'
const LS_PUBKEY = 'parahub_qr_pubkey'
const LS_TYPES = 'parahub_validable_types'
const LS_QUEUE = 'parahub_scan_queue'

function b64urlDecode(s: string): Uint8Array {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (s.length % 4)) % 4)
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0))
}

function readQueue(): { qr_token: string; scanned_at: string }[] {
  try { return JSON.parse(localStorage.getItem(LS_QUEUE) || '[]') } catch { return [] }
}

function writeQueue(items: { qr_token: string; scanned_at: string }[]) {
  localStorage.setItem(LS_QUEUE, JSON.stringify(items))
  queueCount.value = items.length
}

function enqueueScan(qrToken: string) {
  const queue = readQueue()
  queue.push({ qr_token: qrToken, scanned_at: new Date().toISOString() })
  writeQueue(queue)
}

async function refreshOfflineCache() {
  try {
    await authStore.ensureToken()
    const [pub, types] = await Promise.all([
      $fetch<{ key: string }>('/api/v1/tickets/qr-pubkey/'),
      $fetch<{ id: string; name: string }[]>('/api/v1/tickets/operator/validable-types/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      }),
    ])
    localStorage.setItem(LS_PUBKEY, pub.key)
    localStorage.setItem(LS_TYPES, JSON.stringify(types.map(x => x.id)))
  } catch {
    // offline at load — caches from a previous session keep working
  }
}

interface QrPayload { tid: string; qr: string; ty: string; nm: string; vm: number | null; cc: string | null }

async function verifySignedQr(data: string): Promise<QrPayload | null> {
  const pubB64 = localStorage.getItem(LS_PUBKEY)
  if (!pubB64) return null
  const [, payloadB64, sigB64] = data.split('.')
  try {
    const [ed, h] = await Promise.all([import('@noble/ed25519'), import('@noble/hashes/sha2.js')])
    if (!(ed as any).hashes.sha512) (ed as any).hashes.sha512 = (h as any).sha512
    const raw = b64urlDecode(payloadB64)
    const ok = await ed.verifyAsync(b64urlDecode(sigB64), raw, b64urlDecode(pubB64))
    if (!ok) return null
    return JSON.parse(new TextDecoder().decode(raw))
  } catch {
    return null
  }
}

async function syncQueue() {
  const queue = readQueue()
  if (!queue.length) return
  try {
    await authStore.ensureToken()
    const results = await $fetch<{ qr_token: string; valid: boolean; message: string }[]>(
      '/api/v1/tickets/validate/sync/',
      {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: { items: queue },
      },
    )
    writeQueue([])
    const rejected = results.filter(r => !r.valid).length
    syncBanner.value = { synced: results.length - rejected, rejected }
    setTimeout(() => { syncBanner.value = null }, 8000)
  } catch {
    // still offline — keep the queue
  }
}

// ── Camera loop ──────────────────────────────────────────────────────

async function startCamera() {
  try {
    const QrScanner = (await import('qr-scanner')).default
    await nextTick() // the <video> re-renders when state flips back to 'scanning'
    if (!videoEl.value) return
    qrScanner = new QrScanner(
      videoEl.value,
      (res: any) => onDecoded(res.data ?? ''),
      {
        preferredCamera: 'environment',
        returnDetailedScanResult: true,
        maxScansPerSecond: 4,
        highlightScanRegion: false, // the template draws its own overlay
      },
    )
    await qrScanner.start()
  } catch {
    state.value = 'denied'
  }
}

function onDecoded(data: string) {
  if (state.value !== 'scanning' || !data) return
  const isLegacy = data.length === 64 && /^[0-9a-f]{64}$/.test(data)
  const isSigned = data.startsWith(QR_PREFIX + '.') && data.split('.').length === 3
  if (isLegacy || isSigned) {
    stopCamera()
    validateTicket(data, isSigned)
  }
}

function stopCamera() {
  if (qrScanner) {
    qrScanner.destroy()
    qrScanner = null
  }
}

async function validateTicket(data: string, isSigned: boolean) {
  state.value = 'validating'

  let qrToken = data
  let payload: QrPayload | null = null
  if (isSigned) {
    payload = await verifySignedQr(data)
    if (payload?.qr) qrToken = payload.qr
  }
  if (isSigned && !payload) {
    // Signature invalid or pubkey missing — never accept
    result.value = { valid: false, message: t('tickets.offline_bad_signature') }
    state.value = 'result'
    return
  }

  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/tickets/validate/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { qr_token: qrToken },
    })
    result.value = res
    state.value = 'result'
    syncQueue()
  } catch (e: any) {
    const serverResponded = !!(e?.status || e?.response?.status || e?.statusCode)
    if (serverResponded) {
      result.value = {
        valid: false,
        message: e?.data?.message || e?.data?.detail || t('tickets.error_validate'),
      }
    } else if (payload) {
      // Offline + authentic signature: advisory accept, queue for sync
      enqueueScan(qrToken)
      const myTypes: string[] = JSON.parse(localStorage.getItem(LS_TYPES) || '[]')
      const foreign = myTypes.length > 0 && !myTypes.includes(payload.ty)
      result.value = {
        valid: true,
        offline: true,
        ticket_type_name: payload.nm,
        concession_category: payload.cc,
        message: foreign ? t('tickets.offline_foreign_type') : t('tickets.offline_advisory'),
      }
    } else {
      // Offline + legacy unverifiable QR: queue, but warn
      enqueueScan(qrToken)
      result.value = { valid: false, offline: true, message: t('tickets.offline_unverified') }
    }
    state.value = 'result'
  }
}

function resetScan() {
  result.value = null
  state.value = 'scanning'
  startCamera()
}

function onOnline() {
  syncQueue()
  refreshOfflineCache()
}

onMounted(() => {
  queueCount.value = readQueue().length
  refreshOfflineCache()
  syncQueue()
  window.addEventListener('online', onOnline)
  startCamera()
})

onUnmounted(() => {
  stopCamera()
  window.removeEventListener('online', onOnline)
})
</script>

<style scoped>
.scan-animation {
  animation: scan-pulse 2s ease-in-out infinite;
}
@keyframes scan-pulse {
  0%, 100% { opacity: 0.5; transform: scale(0.95); }
  50% { opacity: 1; transform: scale(1.05); }
}
</style>
