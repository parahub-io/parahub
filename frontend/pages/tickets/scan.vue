<template>
  <div class="min-h-screen bg-neutral-950 text-white flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-neutral-800">
      <h1 class="text-lg font-semibold">{{ $t('tickets.scan_title') }}</h1>
      <UiButton variant="ghost" size="sm" :to="localePath('/')">
        <X class="w-5 h-5" />
      </UiButton>
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
          :class="result?.valid ? 'bg-emerald-500/20' : 'bg-red-500/20'"
        >
          <CheckCircle2 v-if="result?.valid" class="w-14 h-14 text-emerald-400" />
          <XCircle v-else class="w-14 h-14 text-red-400" />
        </div>

        <div>
          <h2 class="text-2xl font-bold" :class="result?.valid ? 'text-emerald-400' : 'text-red-400'">
            {{ result?.valid ? $t('tickets.scan_result_valid') : $t('tickets.scan_result_invalid') }}
          </h2>
          <p class="mt-1 text-neutral-400">{{ result?.message }}</p>
        </div>

        <div v-if="result?.ticket_type_name" class="bg-neutral-900 rounded-xl p-4 space-y-2">
          <div class="text-sm text-neutral-500">{{ result.ticket_type_name }}</div>
          <div v-if="result.buyer_name" class="text-lg font-medium">{{ result.buyer_name }}</div>
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
import { X, CheckCircle2, XCircle, ScanLine, CameraOff } from 'lucide-vue-next'

definePageMeta({ layout: 'blank', middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

useHead({ title: computed(() => t('tickets.scan_page_title')) })

type ScanState = 'scanning' | 'validating' | 'result' | 'denied'

const state = ref<ScanState>('scanning')
const videoEl = ref<HTMLVideoElement | null>(null)
const result = ref<{ valid: boolean; message: string; buyer_name?: string; ticket_type_name?: string } | null>(null)

let stream: MediaStream | null = null
let canvas: HTMLCanvasElement | null = null
let ctx: CanvasRenderingContext2D | null = null
let scanInterval: ReturnType<typeof setInterval> | null = null

// Dynamic import of jsQR
let jsQR: any = null

async function startCamera() {
  try {
    const { default: jsQRLib } = await import('jsqr')
    jsQR = jsQRLib

    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 640 } },
    })
    if (videoEl.value) {
      videoEl.value.srcObject = stream
    }

    canvas = document.createElement('canvas')
    ctx = canvas.getContext('2d')

    // Start scanning loop
    scanInterval = setInterval(scanFrame, 250)
  } catch {
    state.value = 'denied'
  }
}

function scanFrame() {
  if (!videoEl.value || !canvas || !ctx || !jsQR) return
  if (videoEl.value.readyState !== videoEl.value.HAVE_ENOUGH_DATA) return

  canvas.width = videoEl.value.videoWidth
  canvas.height = videoEl.value.videoHeight
  ctx.drawImage(videoEl.value, 0, 0, canvas.width, canvas.height)
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const code = jsQR(imageData.data, imageData.width, imageData.height)

  if (code?.data && code.data.length === 64 && /^[0-9a-f]{64}$/.test(code.data)) {
    stopCamera()
    validateTicket(code.data)
  }
}

function stopCamera() {
  if (scanInterval) {
    clearInterval(scanInterval)
    scanInterval = null
  }
  if (stream) {
    stream.getTracks().forEach(t => t.stop())
    stream = null
  }
}

async function validateTicket(qrToken: string) {
  state.value = 'validating'
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
  } catch (e: any) {
    result.value = {
      valid: false,
      message: e?.data?.message || e?.data?.detail || t('tickets.error_validate'),
    }
    state.value = 'result'
  }
}

function resetScan() {
  result.value = null
  state.value = 'scanning'
  startCamera()
}

onMounted(() => {
  startCamera()
})

onUnmounted(() => {
  stopCamera()
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
