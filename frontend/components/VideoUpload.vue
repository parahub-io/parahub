<script setup lang="ts">
import { Video, X, Loader2 } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

const props = defineProps<{
  objectId?: string
}>()

const emit = defineEmits<{
  uploaded: [data: { peertube_uuid: string; title: string }]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToastStore()
const { downscale } = useVideoDownscale()

const uploading = ref(false)
const compressing = ref(false)
const compressProgress = ref(0)
const processing = ref(false)
const progress = ref(0)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement>()
let currentXhr: XMLHttpRequest | null = null
let currentAbort: AbortController | null = null

const ACCEPT = 'video/mp4,video/webm,video/ogg,video/quicktime,video/x-matroska'
const MAX_SIZE = 4 * 1024 * 1024 * 1024 // 4GB

function fmtMB(bytes: number): string {
  const mb = bytes / 1048576
  return `${mb >= 10 ? Math.round(mb) : mb.toFixed(1)} MB`
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}

function onDragLeave() {
  dragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) handleFile(file)
}

function cancelUpload() {
  if (currentXhr) {
    currentXhr.abort()
    currentXhr = null
  }
  if (currentAbort) {
    currentAbort.abort()
    currentAbort = null
  }
  uploading.value = false
  compressing.value = false
  compressProgress.value = 0
  processing.value = false
  progress.value = 0
}

async function handleFile(file: File) {
  if (!file.type.startsWith('video/')) {
    toast.error(t('videos.upload.invalidType'))
    return
  }
  if (file.size > MAX_SIZE) {
    toast.error(t('videos.upload.tooLarge'))
    return
  }

  uploading.value = true
  compressing.value = false
  compressProgress.value = 0
  processing.value = false
  progress.value = 0

  try {
    // Downscale ≤1080p client-side before upload (4K → ~4-5× smaller, no visible
    // loss since PeerTube caps at 1080p anyway). Falls back to the original file
    // if WebCodecs is unavailable or anything fails — never blocks the upload.
    const abort = new AbortController()
    currentAbort = abort
    compressing.value = true
    const compressed = await downscale(
      file,
      (pct) => {
        compressProgress.value = pct
      },
      abort.signal,
    )
    compressing.value = false
    currentAbort = null
    if (abort.signal.aborted) return // cancelled during compression — don't upload
    const uploadFile = compressed.file

    await authStore.ensureToken()

    const formData = new FormData()
    formData.append('videofile', uploadFile)
    formData.append('name', uploadFile.name.replace(/\.[^.]+$/, ''))

    const xhr = new XMLHttpRequest()
    currentXhr = xhr

    const result = await new Promise<{ peertube_uuid: string; title: string }>((resolve, reject) => {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          progress.value = Math.round((e.loaded / e.total) * 100)
          if (e.loaded >= e.total) {
            processing.value = true
          }
        }
      })

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText))
        } else {
          try {
            const err = JSON.parse(xhr.responseText)
            reject(new Error(err.error || 'Upload failed'))
          } catch {
            reject(new Error('Upload failed'))
          }
        }
      })

      xhr.addEventListener('error', () => reject(new Error('Network error')))
      xhr.addEventListener('abort', () => reject(new Error('cancelled')))

      xhr.open('POST', '/api/v1/core/videos/upload/')
      xhr.setRequestHeader('Authorization', `Bearer ${authStore.token}`)
      xhr.withCredentials = true
      xhr.send(formData)
    })

    currentXhr = null

    // Register as ObjectVideo BEFORE emitting `uploaded`. The parent reacts to
    // `uploaded` by refetching the video list; emitting first races this POST —
    // the refetch would run before the row exists and miss the just-uploaded
    // video, so it stays invisible until a hard reload.
    if (props.objectId) {
      await $fetch('/api/v1/core/videos/', {
        method: 'POST',
        body: {
          object_id: props.objectId,
          peertube_uuid: result.peertube_uuid,
          title: result.title,
        },
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    }

    emit('uploaded', result)

    let successMsg = t('videos.upload.success')
    if (compressed.didCompress) {
      successMsg += ' · ' + t('videos.upload.optimized', {
        from: fmtMB(compressed.originalSize),
        to: fmtMB(compressed.newSize),
        ratio: (compressed.originalSize / compressed.newSize).toFixed(1),
      })
    }
    toast.success(successMsg)
  } catch (e: any) {
    if (e.message !== 'cancelled') {
      toast.error(e.message || t('videos.upload.failed'))
    }
  } finally {
    currentXhr = null
    currentAbort = null
    uploading.value = false
    compressing.value = false
    compressProgress.value = 0
    processing.value = false
    progress.value = 0
    if (fileInput.value) fileInput.value.value = ''
  }
}
</script>

<template>
  <div
    class="video-upload-zone"
    :class="{ 'drag-over': dragOver, uploading }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- Uploading state -->
    <div v-if="uploading" class="flex flex-col items-center gap-3 py-6">
      <Loader2 class="w-8 h-8 text-primary animate-spin" />
      <div class="text-sm text-neutral-400">
        <template v-if="compressing">{{ t('videos.upload.compressing') }} {{ compressProgress }}%</template>
        <template v-else-if="processing">{{ t('videos.upload.processing') }}</template>
        <template v-else>{{ t('videos.upload.uploading') }} {{ progress }}%</template>
      </div>
      <div class="w-full max-w-xs bg-neutral-700 rounded-full h-2">
        <div
          class="bg-primary h-2 rounded-full transition-all duration-300"
          :style="{ width: `${compressing ? compressProgress : progress}%` }"
        />
      </div>
      <button
        type="button"
        class="text-xs text-neutral-500 hover:text-red-400 flex items-center gap-1 mt-1"
        @click="cancelUpload"
      >
        <X class="w-3 h-3" />
        {{ t('common.cancel') }}
      </button>
    </div>

    <!-- Drop zone -->
    <label v-else class="flex flex-col items-center gap-2 py-6 cursor-pointer">
      <Video class="w-8 h-8 text-neutral-400" />
      <span class="text-sm text-neutral-400">
        {{ t('videos.upload.dropOrClick') }}
      </span>
      <span class="text-xs text-neutral-500">MP4, WebM, OGG — {{ t('videos.upload.maxSize') }}</span>
      <input
        ref="fileInput"
        type="file"
        :accept="ACCEPT"
        class="hidden"
        @change="onFileSelect"
      />
    </label>
  </div>
</template>

<style scoped>
.video-upload-zone {
  @apply border-2 border-dashed border-neutral-600 rounded-lg transition-colors;
}
.video-upload-zone:hover,
.video-upload-zone.drag-over {
  @apply border-primary bg-primary/5;
}
.video-upload-zone.uploading {
  @apply border-primary/50;
}
</style>
