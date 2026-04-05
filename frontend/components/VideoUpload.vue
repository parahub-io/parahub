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

const uploading = ref(false)
const processing = ref(false)
const progress = ref(0)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement>()
let currentXhr: XMLHttpRequest | null = null

const ACCEPT = 'video/mp4,video/webm,video/ogg,video/quicktime,video/x-matroska'
const MAX_SIZE = 4 * 1024 * 1024 * 1024 // 4GB

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
  uploading.value = false
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
  processing.value = false
  progress.value = 0

  try {
    await authStore.ensureToken()

    const formData = new FormData()
    formData.append('videofile', file)
    formData.append('name', file.name.replace(/\.[^.]+$/, ''))

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
    emit('uploaded', result)
    toast.success(t('videos.upload.success'))

    // If objectId provided, auto-register as ObjectVideo
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
  } catch (e: any) {
    if (e.message !== 'cancelled') {
      toast.error(e.message || t('videos.upload.failed'))
    }
  } finally {
    currentXhr = null
    uploading.value = false
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
        <template v-if="processing">{{ t('videos.upload.processing') }}</template>
        <template v-else>{{ t('videos.upload.uploading') }} {{ progress }}%</template>
      </div>
      <div class="w-full max-w-xs bg-neutral-700 rounded-full h-2">
        <div
          class="bg-primary h-2 rounded-full transition-all duration-300"
          :style="{ width: `${progress}%` }"
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
