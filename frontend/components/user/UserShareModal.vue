<template>
  <Modal
    v-model="visible"
    :title="t('user_profile.share_profile')"
    :icon="Share2"
    icon-class="text-indigo-600"
    size="lg"
  >
    <div class="space-y-3">
      <!-- Copy Link -->
      <button
        @click="copyProfileLink"
        class="w-full flex items-center gap-3 px-4 py-3 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
        aria-label="Copy profile link to clipboard"
      >
        <Link class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
        <div class="flex-1 text-left">
          <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ t('user_profile.copy_link') }}</p>
          <p class="text-xs text-neutral-600 dark:text-neutral-400 break-all">{{ profileUrl }}</p>
        </div>
        <Copy v-if="!linkCopied" class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
        <Check v-else class="w-5 h-5 text-green-600 dark:text-green-400" />
      </button>

      <!-- QR Code -->
      <button
        @click="showQRCode = !showQRCode"
        class="w-full flex items-center gap-3 px-4 py-3 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
        :aria-label="showQRCode ? 'Hide QR code' : 'Show QR code'"
      >
        <QrCode class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
        <div class="flex-1 text-left">
          <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ t('user_profile.show_qr_code') }}</p>
          <p class="text-xs text-neutral-600 dark:text-neutral-400">{{ t('user_profile.qr_code_desc') }}</p>
        </div>
        <ChevronDown v-if="!showQRCode" class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
        <ChevronUp v-else class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
      </button>

      <!-- QR Code Display -->
      <div v-if="showQRCode" class="bg-white p-4 rounded-lg border border-neutral-300 flex justify-center">
        <canvas ref="qrCanvas" aria-label="QR code for profile"></canvas>
      </div>

      <!-- Export vCard -->
      <button
        @click="exportVCard"
        class="w-full flex items-center gap-3 px-4 py-3 bg-neutral-100 dark:bg-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
        aria-label="Export profile as vCard"
      >
        <Download class="w-5 h-5 text-neutral-600 dark:text-neutral-400" />
        <div class="flex-1 text-left">
          <p class="font-medium text-neutral-900 dark:text-neutral-100">{{ t('user_profile.export_vcard') }}</p>
          <p class="text-xs text-neutral-600 dark:text-neutral-400">{{ t('user_profile.vcard_desc') }}</p>
        </div>
      </button>

    </div>

    <template #footer>
      <button
        @click="visible = false"
        class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90"
      >
        {{ t('user_profile.close') }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { Share2, Link, Copy, Check, QrCode, ChevronDown, ChevronUp, Download } from 'lucide-vue-next'
import QRCode from 'qrcode'

const props = defineProps<{ profile: any; profileUrl: string; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { t } = useI18n()
const toastStore = useToastStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const linkCopied = ref(false)
const showQRCode = ref(false)
const qrCanvas = ref<HTMLCanvasElement | null>(null)

const copyProfileLink = async () => {
  try {
    await navigator.clipboard.writeText(props.profileUrl)
    linkCopied.value = true
    toastStore.success(t('user_profile.link_copied'))
    setTimeout(() => { linkCopied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
    toastStore.error(t('user_profile.link_copy_failed'))
  }
}

const generateQRCode = async () => {
  await nextTick()
  setTimeout(async () => {
    if (qrCanvas.value) {
      try {
        await QRCode.toCanvas(qrCanvas.value, props.profileUrl, {
          width: 256,
          margin: 2,
          color: { dark: '#000000', light: '#FFFFFF' }
        })
      } catch (err) {
        console.error('Failed to generate QR code:', err)
        toastStore.error(t('user_profile.qr_generation_failed'))
      }
    }
  }, 100)
}

const exportVCard = () => {
  const vcard = `BEGIN:VCARD
VERSION:3.0
FN:${props.profile.display_name || props.profile.hna}
NICKNAME:${props.profile.hna}
URL:${props.profileUrl}
NOTE:Parahub Profile ID: ${props.profile.id}
END:VCARD`

  const blob = new Blob([vcard], { type: 'text/vcard' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.profile.hna}.vcf`
  a.click()
  window.URL.revokeObjectURL(url)
  toastStore.success(t('user_profile.vcard_exported'))
}

watch(showQRCode, async (show) => {
  if (show) {
    await generateQRCode()
  }
})

watch(visible, async (show) => {
  if (show && showQRCode.value) {
    await generateQRCode()
  }
})
</script>
