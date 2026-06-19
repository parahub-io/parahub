<script setup lang="ts">
import { Image, Upload, Trash2, X } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

const { t } = useI18n()
const props = defineProps<{
  postId: string
  editable?: boolean
}>()

const authStore = useAuthStore()
const toast = useToastStore()

const photos = ref<any[]>([])
const loading = ref(true)
const uploading = ref(false)
const lightboxIdx = ref(-1)

async function fetchPhotos() {
  if (!props.postId) {
    photos.value = []
    loading.value = false
    return
  }
  loading.value = true
  try {
    photos.value = await $fetch<any[]>('/api/v1/core/photos/', {
      params: { object_id: props.postId },
    })
  } catch { /* ignore */ }
  loading.value = false
}

async function uploadPhoto(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('image', file)
    formData.append('object_id', props.postId)
    formData.append('order', String(photos.value.length))

    const res = await $fetch<any>('/api/v1/core/photos/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    photos.value.push(res)
    toast.success(t('cms.photoUploaded'))
  } catch (e: any) {
    toast.error(e.data?.error || t('cms.photoUploadFailed'))
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function deletePhoto(photoId: string) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/core/photos/${photoId}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    photos.value = photos.value.filter(p => p.id !== photoId)
    toast.success(t('cms.photoDeleted'))
  } catch {
    toast.error(t('cms.photoDeleteFailed'))
  }
}

// Re-fetch when postId changes (e.g. navigating between ?edit=A → ?edit=B).
// `immediate: true` replaces onMounted — runs on initial mount too.
watch(() => props.postId, fetchPhotos, { immediate: true })
</script>

<template>
  <div v-if="loading" class="flex justify-center py-4">
    <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
  </div>

  <div v-else-if="photos.length > 0 || editable" class="card p-4">
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
      <Image class="w-5 h-5" />
      {{ t('cms.photos') }}
      <span v-if="photos.length > 0" class="text-sm font-normal text-neutral-500">({{ photos.length }})</span>
    </h2>

    <!-- Gallery grid -->
    <div v-if="photos.length > 0" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mb-3">
      <div v-for="(photo, idx) in photos" :key="photo.id" class="relative group">
        <img
          :src="photo.url"
          :alt="photo.caption || ''"
          class="w-full h-32 object-cover rounded-lg cursor-pointer"
          @click="lightboxIdx = idx"
        />
        <button
          v-if="editable"
          @click="deletePhoto(photo.id)"
          class="absolute top-1 right-1 p-1 bg-black/50 rounded-full text-white opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Upload button (edit mode) -->
    <label v-if="editable" class="btn-outline btn-sm cursor-pointer inline-flex items-center gap-2">
      <Upload class="w-4 h-4" />
      {{ uploading ? '...' : t('cms.uploadPhoto') }}
      <input type="file" accept="image/*" class="hidden" @change="uploadPhoto" :disabled="uploading" />
    </label>

    <!-- Lightbox -->
    <Teleport to="body">
      <div
        v-if="lightboxIdx >= 0"
        class="fixed inset-0 z-[200] bg-black/90 flex items-center justify-center"
        @click.self="lightboxIdx = -1"
      >
        <button
          @click="lightboxIdx = -1"
          class="absolute top-4 right-4 p-2 text-white/80 hover:text-white"
        >
          <X class="w-6 h-6" />
        </button>
        <button
          v-if="lightboxIdx > 0"
          @click="lightboxIdx--"
          class="absolute left-4 p-2 text-white/80 hover:text-white text-3xl"
        >
          &lsaquo;
        </button>
        <button
          v-if="lightboxIdx < photos.length - 1"
          @click="lightboxIdx++"
          class="absolute right-4 p-2 text-white/80 hover:text-white text-3xl"
        >
          &rsaquo;
        </button>
        <img
          :src="photos[lightboxIdx]?.url"
          :alt="photos[lightboxIdx]?.caption || ''"
          class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
        />
      </div>
    </Teleport>
  </div>
</template>
