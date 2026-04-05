<template>
  <div class="space-y-3">
    <!-- Preview -->
    <div
      v-if="previewUrl"
      class="relative group rounded-xl overflow-hidden border border-neutral-200 dark:border-neutral-700"
    >
      <img
        :src="previewUrl"
        alt="Campaign banner"
        class="w-full max-h-[280px] object-cover"
      />
      <div class="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center">
        <button
          type="button"
          @click="removeImage"
          class="opacity-0 group-hover:opacity-100 transition-opacity px-3 py-1.5 bg-red-600 text-white text-xs font-medium rounded-lg flex items-center gap-1.5"
        >
          <Trash2 class="w-3.5 h-3.5" />
          {{ $t('ads.create_campaign.image_remove') }}
        </button>
      </div>
    </div>

    <!-- Drop zone -->
    <div
      v-else
      @dragover.prevent="dragActive = true"
      @dragleave="dragActive = false"
      @drop.prevent="handleDrop"
      @click="triggerFileInput"
      :class="[
        'relative flex flex-col items-center justify-center gap-2 py-8 px-4 rounded-xl border-2 border-dashed cursor-pointer transition-all',
        dragActive
          ? 'border-primary bg-primary-100 dark:bg-primary-900/30'
          : 'border-neutral-300 dark:border-neutral-600 hover:border-primary/50 hover:bg-neutral-50 dark:hover:bg-neutral-800/50',
      ]"
    >
      <div class="w-12 h-12 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
        <ImagePlus class="w-6 h-6 text-neutral-400" />
      </div>
      <p class="text-sm text-neutral-600 dark:text-neutral-400">
        {{ $t('ads.create_campaign.image_upload') }}
      </p>
      <p class="text-xs text-neutral-400 dark:text-neutral-500">
        {{ $t('ads.create_campaign.image_upload_hint') }}
      </p>
      <Loader2 v-if="uploading" class="w-5 h-5 animate-spin text-primary absolute top-3 right-3" />
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      class="hidden"
      @change="handleFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ImagePlus, Trash2, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  campaignId?: string
  modelValue?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [url: string | null]
  'file-selected': [file: File]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const dragActive = ref(false)
const uploading = ref(false)
const previewUrl = ref<string | null>(props.modelValue || null)

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) processFile(file)
}

function handleDrop(e: DragEvent) {
  dragActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) processFile(file)
}

async function processFile(file: File) {
  if (file.size > 10 * 1024 * 1024) {
    alert('Image must be under 10 MB')
    return
  }

  // Show local preview immediately
  previewUrl.value = URL.createObjectURL(file)
  emit('file-selected', file)

  // If campaign already exists, upload immediately
  if (props.campaignId) {
    await uploadFile(file)
  }
}

async function uploadFile(file: File) {
  if (!props.campaignId) return
  uploading.value = true
  try {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('image', file)
    const res = await $fetch<{ image_url: string }>(`/api/v1/ads/campaigns/${props.campaignId}/image/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: formData,
    })
    previewUrl.value = res.image_url
    emit('update:modelValue', res.image_url)
  } catch (err) {
    console.error('Failed to upload image:', err)
  } finally {
    uploading.value = false
  }
}

function removeImage() {
  previewUrl.value = null
  emit('update:modelValue', null)
  emit('file-selected', null as any)
  if (fileInput.value) fileInput.value.value = ''
}

// Expose for parent to trigger upload after campaign creation
defineExpose({ uploadFile, previewUrl })
</script>
