<template>
  <div class="p-6">
    <!-- Title is rendered by the wrapping <Modal> (opensky/index.vue) — no local heading here to avoid a duplicate. -->

    <!-- Drag & Drop Zone -->
    <div
      class="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors"
      :class="isDragging ? 'border-primary bg-primary/5' : 'border-neutral-300 dark:border-neutral-600 hover:border-primary/50'"
      @dragenter.prevent="isDragging = true"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent.stop="handleDrop"
      @click="triggerFileInput"
    >
      <Upload class="w-12 h-12 mx-auto mb-4 text-neutral-400" />
      <p class="mb-2">{{ $t('opensky.drag_drop_jpg', 'Drag & drop JPG photos') }}</p>
      <p class="text-sm text-neutral-500">{{ $t('opensky.select_multiple', 'Select all photos from the mission folder') }}</p>
      <button type="button" class="mt-2 px-4 py-2 bg-neutral-200 dark:bg-neutral-700 rounded hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors">
        {{ $t('opensky.select_files', 'Select Files') }}
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".jpg,.jpeg"
        multiple
        class="hidden"
        @change="handleFileSelect"
      />
    </div>

    <!-- Selected Files Info -->
    <div v-if="selectedFiles.length > 0" class="mt-4 space-y-2">
      <div class="flex items-center justify-between text-sm text-neutral-600 dark:text-neutral-400">
        <span>{{ selectedFiles.length }} {{ $t('opensky.files_selected', 'file(s) selected') }}</span>
        <div class="flex items-center gap-3">
          <span>{{ formatSize(totalSize) }} {{ $t('opensky.total', 'total') }}</span>
          <button @click="clearFiles" class="text-error hover:text-error-700 text-xs">
            {{ $t('opensky.clear_all', 'Clear all') }}
          </button>
        </div>
      </div>
      <!-- File list with max height and scroll -->
      <div class="max-h-48 overflow-y-auto space-y-2 pr-1">
        <div v-for="(file, index) in selectedFiles" :key="index" class="p-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-xs text-neutral-400 w-8 shrink-0">{{ index + 1 }}.</span>
              <p class="font-medium truncate">{{ file.name }}</p>
              <p class="text-sm text-neutral-500 shrink-0">{{ formatSize(file.size) }}</p>
            </div>
            <button @click="removeFile(index)" class="text-neutral-500 hover:text-error shrink-0 ml-2">
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Upload Progress -->
    <div v-if="uploading" class="mt-4">
      <div class="h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
        <div
          class="h-full bg-primary transition-all duration-300"
          :style="{ width: uploadProgress + '%' }"
        ></div>
      </div>
      <p v-if="multiUploadState" class="text-sm text-center mt-2">
        <span v-if="multiUploadState.totalBatches > 1">
          Batch {{ multiUploadState.currentBatch }}/{{ multiUploadState.totalBatches }} •
        </span>
        {{ $t('opensky.uploading_file', 'File') }} {{ multiUploadState.currentFile }}/{{ multiUploadState.totalFiles }}
        <span v-if="multiUploadState.totalBatches === 1"> • {{ multiUploadState.currentFileName }}</span>
      </p>
      <p v-else class="text-sm text-center mt-2">{{ uploadProgress }}% {{ $t('opensky.uploaded', 'uploaded') }}</p>
    </div>

    <!-- Photo count warning -->
    <UiAlert v-if="photoCountWarning" variant="warning" class="mt-4">{{ photoCountWarning }}</UiAlert>

    <!-- Error Message -->
    <UiAlert v-if="errorMessage" variant="error" class="mt-4">{{ errorMessage }}</UiAlert>

    <!-- License consent (new missions only — appends inherit the original consent) -->
    <label v-if="!missionId" class="mt-4 flex items-start gap-2 text-sm text-neutral-600 dark:text-neutral-400 cursor-pointer">
      <input type="checkbox" v-model="licenseConsent" class="mt-0.5 shrink-0 accent-primary" />
      <span>
        {{ $t('opensky.license_consent_label', 'I am the author of these photos (or hold the rights) and I publish them under the CC BY-SA 4.0 license.') }}
        <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener" class="text-link">{{ $t('opensky.license_learn_more', 'License details') }}</a>
      </span>
    </label>

    <!-- Submit -->
    <button
      @click="upload"
      :disabled="selectedFiles.length === 0 || uploading || (!missionId && !licenseConsent)"
      class="mt-4 w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <span v-if="uploading" class="flex items-center justify-center gap-2">
        <Loader2 class="w-5 h-5 animate-spin" />
        {{ $t('opensky.uploading', 'Uploading...') }}
      </span>
      <span v-else>{{ $t('opensky.upload_process', 'Upload & Process') }}</span>
    </button>

    <!-- Info -->
    <p class="mt-4 text-sm text-neutral-500">
      {{ missionId
        ? $t('opensky.upload_info_append', 'Upload oblique photos from the same tile. Photos must be within the same area as the original mission.')
        : $t('opensky.upload_info_hex', 'Upload all photos (nadir + oblique) together for best results. GPS EXIF required. One tile per mission.')
      }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { Upload, X, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  missionId?: string
}>()

const emit = defineEmits<{
  uploaded: [mission: any]
  close: []
}>()

const { uploadMultipleFiles, uploading, uploadProgress, multiUploadState, formatSize } = useOpenSky()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const isDragging = ref(false)
const errorMessage = ref('')

// Author/license affirmation. It's the same declaration every upload (the pilot is
// always the author), so we remember the last choice and pre-tick it next time
// instead of forcing a fresh click. Client-only to avoid SSR hydration mismatch.
const LICENSE_CONSENT_KEY = 'opensky:licenseConsent'
const licenseConsent = ref(false)
watch(licenseConsent, (v) => {
  if (import.meta.client) localStorage.setItem(LICENSE_CONSENT_KEY, v ? 'true' : 'false')
})

const totalSize = computed(() => selectedFiles.value.reduce((sum, f) => sum + f.size, 0))

const { t } = useI18n()

const photoCountWarning = computed(() => {
  if (selectedFiles.value.length > 600) {
    return t('opensky.too_many_photos_warning', 'Over 600 photos — are you uploading multiple tiles? Upload one tile per mission for best results.')
  }
  return ''
})

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    validateAndAddFiles(Array.from(input.files))
  }
}

const extractFiles = (dt: DataTransfer | null): File[] => {
  if (!dt) return []
  const out: File[] = []
  // Prefer items API — slightly more robust than .files (handles cases where
  // .files is empty but items has 'file' kind entries, e.g. some Linux WMs)
  if (dt.items && dt.items.length > 0) {
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i]
      if (item.kind === 'file') {
        const f = item.getAsFile()
        if (f) out.push(f)
      }
    }
  }
  if (out.length === 0 && dt.files && dt.files.length > 0) {
    for (let i = 0; i < dt.files.length; i++) out.push(dt.files[i])
  }
  return out
}

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  const files = extractFiles(event.dataTransfer)
  if (files.length > 0) {
    validateAndAddFiles(files)
  }
}

// Window-level drop catcher: while the upload form is mounted (modal open),
// prevent the browser from navigating to file:// when the user drops a file
// outside the dashed dropzone. Forwards the drop into the regular handler.
const handleWindowDragOver = (event: DragEvent) => {
  // Must preventDefault on dragover for the drop event to fire on window
  if (event.dataTransfer?.types?.includes('Files')) {
    event.preventDefault()
  }
}
const handleWindowDrop = (event: DragEvent) => {
  if (!event.dataTransfer?.types?.includes('Files')) return
  // If the dropzone already handled it, .prevent set defaultPrevented=true
  if (event.defaultPrevented) return
  event.preventDefault()
  const files = extractFiles(event.dataTransfer)
  if (files.length > 0) {
    validateAndAddFiles(files)
  }
}

onMounted(() => {
  window.addEventListener('dragover', handleWindowDragOver)
  window.addEventListener('drop', handleWindowDrop)
  if (localStorage.getItem(LICENSE_CONSENT_KEY) === 'true') licenseConsent.value = true
})
onBeforeUnmount(() => {
  window.removeEventListener('dragover', handleWindowDragOver)
  window.removeEventListener('drop', handleWindowDrop)
})

const validateAndAddFiles = (files: File[]) => {
  errorMessage.value = ''

  for (const file of files) {
    if (!file.name.toLowerCase().match(/\.jpe?g$/)) {
      errorMessage.value = `${file.name}: ${t('opensky.only_jpg', 'Only JPG files are allowed')}`
      continue
    }

    // Reject 0-byte files. Common cause: dragging from a network mount (NFS/SMB),
    // phone via MTP, or cloud-storage placeholder — the browser gets a "ghost"
    // File reference without real metadata. The native file picker reads the
    // file properly, so the workaround is to use the "Select Files" button.
    if (file.size === 0) {
      errorMessage.value = `${file.name}: ${t('opensky.empty_file_error', 'File is empty (0 bytes). If dragging from a network mount, phone, or cloud storage, copy to a local folder first — or use the "Select Files" button.')}`
      continue
    }

    // Check for duplicates
    if (selectedFiles.value.some(f => f.name === file.name && f.size === file.size)) {
      continue
    }

    selectedFiles.value.push(file)
  }
}

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1)
  errorMessage.value = ''
}

const clearFiles = () => {
  selectedFiles.value = []
  errorMessage.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const upload = async () => {
  if (selectedFiles.value.length === 0) return

  errorMessage.value = ''

  try {
    let mission
    if (props.missionId) {
      mission = await uploadMultipleFiles(selectedFiles.value, undefined, false, props.missionId)
    } else {
      mission = await uploadMultipleFiles(selectedFiles.value, undefined, false, undefined, licenseConsent.value)
    }

    emit('uploaded', mission)
    emit('close')

    const photoCount = mission.source_photos_count
    useToastStore().success(`Mission uploaded with ${photoCount} photos! Processing will start shortly.`)
  } catch (error: any) {
    errorMessage.value = error.message || 'Upload failed. Please try again.'
  }
}
</script>
