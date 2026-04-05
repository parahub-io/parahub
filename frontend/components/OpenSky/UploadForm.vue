<template>
  <div class="p-6">
    <h2 class="text-xl font-bold mb-4">{{ missionId ? $t('opensky.add_photos_title', 'Add Photos to Mission') : $t('opensky.upload_title', 'Upload Drone Photos') }}</h2>

    <!-- Drag & Drop Zone -->
    <div
      class="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors"
      :class="isDragging ? 'border-primary bg-primary/5' : 'border-neutral-300 dark:border-neutral-600 hover:border-primary/50'"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="handleDrop"
      @click="triggerFileInput"
    >
      <Upload class="w-12 h-12 mx-auto mb-4 text-neutral-400" />
      <p class="mb-2">{{ $t('opensky.drag_drop_multi', 'Drag & drop JPG photos or ZIP archives') }}</p>
      <p class="text-sm text-neutral-500">{{ $t('opensky.select_multiple', 'Direct JPG upload is faster (no ZIP compression needed)') }}</p>
      <button type="button" class="mt-2 px-4 py-2 bg-neutral-200 dark:bg-neutral-700 rounded hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors">
        {{ $t('opensky.select_files', 'Select Files') }}
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".zip,.jpg,.jpeg"
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

    <!-- Mission Name (optional, hidden when appending) -->
    <div v-if="!missionId" class="mt-4">
      <label class="block text-sm font-medium mb-1">{{ $t('opensky.mission_name', 'Mission name (optional)') }}</label>
      <input
        v-model="missionName"
        type="text"
        :placeholder="$t('opensky.mission_name_placeholder', 'e.g., Downtown Survey 2024')"
        class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
      />
    </div>

    <!-- Satellite Alignment Option (staff only) -->
    <label v-if="authStore.user?.is_staff" class="flex items-center gap-2 mt-3 cursor-pointer select-none">
      <input
        type="checkbox"
        v-model="satelliteAlign"
        class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
      />
      <span class="text-sm">{{ $t('opensky.satellite_align', 'Align to satellite imagery') }}</span>
      <span class="text-xs text-neutral-500">{{ $t('opensky.satellite_align_hint', '(corrects GPS offset)') }}</span>
    </label>

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

    <!-- Submit -->
    <button
      @click="upload"
      :disabled="selectedFiles.length === 0 || uploading"
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
        : $t('opensky.upload_info_hex', 'Upload photos from one tile at a time. Use the tile grid on the map to plan flights. GPS EXIF required. Max 2GB.')
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

const { uploadMission, uploadMultipleFiles, uploading, uploadProgress, multiUploadState, formatSize } = useOpenSky()
const authStore = useAuthStore()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFiles = ref<File[]>([])
const missionName = ref('')
const satelliteAlign = ref(false)
const isDragging = ref(false)
const errorMessage = ref('')

const totalSize = computed(() => selectedFiles.value.reduce((sum, f) => sum + f.size, 0))

const { t } = useI18n()

const photoCountWarning = computed(() => {
  const jpgCount = selectedFiles.value.filter(f => f.name.toLowerCase().match(/\.jpe?g$/)).length
  if (jpgCount > 600) {
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

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    validateAndAddFiles(Array.from(files))
  }
}

const validateAndAddFiles = (files: File[]) => {
  errorMessage.value = ''
  const maxSize = 2 * 1024 * 1024 * 1024 // 2GB per file

  // Check if mixing JPG and ZIP
  const existingTypes = selectedFiles.value.length > 0
    ? (selectedFiles.value[0].name.toLowerCase().endsWith('.zip') ? 'zip' : 'jpg')
    : null

  for (const file of files) {
    const isZip = file.name.toLowerCase().endsWith('.zip')
    const isJpg = file.name.toLowerCase().match(/\.jpe?g$/)

    // Check file type
    if (!isZip && !isJpg) {
      errorMessage.value = `${file.name}: Only JPG or ZIP files are allowed`
      continue
    }

    // Don't mix JPG and ZIP
    const newType = isZip ? 'zip' : 'jpg'
    if (existingTypes && existingTypes !== newType) {
      errorMessage.value = 'Cannot mix JPG and ZIP files. Choose one type.'
      continue
    }

    // Check file size (only for ZIP, JPG will be batched)
    if (isZip && file.size > maxSize) {
      errorMessage.value = `${file.name}: ZIP too large (max 2GB)`
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
    const isSingleZip = selectedFiles.value.length === 1 &&
                        selectedFiles.value[0].name.toLowerCase().endsWith('.zip')

    if (props.missionId) {
      // Appending to existing mission (e.g. adding oblique photos)
      mission = await uploadMultipleFiles(selectedFiles.value, undefined, satelliteAlign.value, props.missionId)
    } else if (isSingleZip) {
      // Single ZIP file: use original upload (immediate processing)
      mission = await uploadMission(selectedFiles.value[0], missionName.value || undefined, satelliteAlign.value)
    } else {
      // Multiple files or JPG: use batched multi-file upload
      mission = await uploadMultipleFiles(selectedFiles.value, missionName.value || undefined, satelliteAlign.value)
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
