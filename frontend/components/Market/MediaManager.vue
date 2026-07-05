<template>
  <div>
    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
      {{ $t('market.edit_modal.media_label') }}
    </label>

    <div class="space-y-3">
      <!-- Unified media grid: photos + video in one orderable strip. Index 0 = cover. -->
      <div v-if="media.length > 0" class="grid grid-cols-5 gap-2">
        <div
          v-for="(m, index) in media"
          :key="m.kind + ':' + m.id"
          class="relative aspect-square rounded-lg overflow-hidden border-2 transition-shadow"
          :class="[
            dragOverIndex === index ? 'border-primary ring-2 ring-primary' : 'border-neutral-300 dark:border-neutral-600',
            busy ? '' : 'cursor-grab'
          ]"
          :draggable="!busy"
          @dragstart="onDragStart(index, $event)"
          @dragover.prevent="dragOverIndex = index"
          @dragleave="dragOverIndex === index && (dragOverIndex = null)"
          @drop.prevent="onDrop(index)"
          @dragend="onDragEnd"
        >
          <!-- Thumbnail -->
          <img
            v-if="m.kind === 'photo' ? m.url : m.thumbnail_url"
            :src="m.kind === 'photo' ? m.url : m.thumbnail_url"
            :alt="index === 0 ? $t('market.create_modal.image_main') : `#${index + 1}`"
            class="w-full h-full object-cover pointer-events-none"
          />
          <span v-else class="w-full h-full flex items-center justify-center bg-neutral-200 dark:bg-neutral-700">
            <Play class="w-5 h-5 text-neutral-500" />
          </span>

          <!-- Video badge -->
          <span v-if="m.kind === 'video'" class="absolute inset-0 flex items-center justify-center bg-black/25 pointer-events-none">
            <Play class="w-6 h-6 text-white fill-white drop-shadow" />
          </span>

          <!-- Delete (confirm-on-second-click) -->
          <button
            type="button"
            :disabled="busy && deletingKey !== mkey(m)"
            @click="onDeleteClick(m)"
            class="absolute top-1 right-1 !p-1 !rounded-full text-white transition-colors disabled:opacity-50"
            :class="pendingDeleteKey === mkey(m) ? 'bg-error' : 'btn-error'"
            :aria-label="pendingDeleteKey === mkey(m) ? $t('common.confirm') : $t('common.remove')"
            :title="pendingDeleteKey === mkey(m) ? $t('common.confirm') : $t('common.remove')"
          >
            <Loader2 v-if="deletingKey === mkey(m)" class="w-3 h-3 animate-spin" aria-hidden="true" />
            <Check v-else-if="pendingDeleteKey === mkey(m)" class="w-3 h-3" aria-hidden="true" />
            <X v-else class="w-3 h-3" aria-hidden="true" />
          </button>

          <!-- Reorder controls (work on touch + keyboard, unlike native drag) -->
          <div class="absolute top-1 left-1 flex gap-0.5">
            <button
              type="button"
              :disabled="busy || index === 0"
              @click="moveTo(index, index - 1)"
              class="w-5 h-5 flex items-center justify-center rounded-full bg-black/50 hover:bg-black/70 text-white disabled:opacity-30"
              :aria-label="$t('market.edit_modal.move_earlier')"
            >
              <ChevronLeft class="w-3 h-3" aria-hidden="true" />
            </button>
            <button
              type="button"
              :disabled="busy || index === media.length - 1"
              @click="moveTo(index, index + 1)"
              class="w-5 h-5 flex items-center justify-center rounded-full bg-black/50 hover:bg-black/70 text-white disabled:opacity-30"
              :aria-label="$t('market.edit_modal.move_later')"
            >
              <ChevronRight class="w-3 h-3" aria-hidden="true" />
            </button>
          </div>

          <!-- Position label -->
          <div class="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs text-center py-1 pointer-events-none">
            {{ index === 0 ? $t('market.create_modal.image_main') : `#${index + 1}` }}
          </div>
        </div>
      </div>

      <!-- Add photo -->
      <div v-if="photoCount < 5">
        <input
          ref="imageInput"
          type="file"
          accept="image/*"
          multiple
          @change="handleSelect"
          class="hidden"
          :aria-label="$t('market.create_modal.images_label')"
        >
        <input
          ref="cameraInput"
          type="file"
          accept="image/*"
          capture="environment"
          @change="handleSelect"
          class="hidden"
          :aria-label="$t('market.create_modal.take_photo')"
        >

        <!-- Desktop: single button -->
        <button
          type="button"
          @click="imageInput?.click()"
          :disabled="busy"
          class="btn-outline hidden md:block w-full border-dashed border-2 hover:border-primary hover:bg-primary/5 disabled:opacity-50"
        >
          <Loader2 v-if="uploading" class="w-4 h-4 inline animate-spin mr-1" aria-hidden="true" />
          {{ $t('market.create_modal.add_photo', { current: photoCount }) }}
        </button>

        <!-- Mobile: camera + gallery. type="button" REQUIRED — UiButton renders a
             bare <button> that would otherwise submit the surrounding edit form. -->
        <div class="md:hidden grid grid-cols-2 gap-2">
          <UiButton type="button" variant="outline" :icon="Camera" :loading="uploading" :disabled="busy" class="border-dashed border-2 hover:border-primary hover:bg-primary/5" @click="cameraInput?.click()">
            {{ $t('market.create_modal.take_photo') }}
          </UiButton>
          <UiButton type="button" variant="outline" :icon="ImageIcon" :loading="uploading" :disabled="busy" class="border-dashed border-2 hover:border-primary hover:bg-primary/5" @click="imageInput?.click()">
            {{ $t('market.create_modal.from_gallery') }}
          </UiButton>
        </div>
      </div>

      <!-- Add video -->
      <div v-if="videoCount < 10">
        <p class="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1.5">
          {{ $t('market.edit_modal.add_video') }}
        </p>
        <VideoUpload :object-id="itemId" @uploaded="onVideoUploaded" />
      </div>

      <p class="text-xs text-neutral-500 dark:text-neutral-400">
        {{ $t('market.edit_modal.media_help') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { X, Check, Camera, ImageIcon, Loader2, Play, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import imageCompression from 'browser-image-compression'

const props = defineProps({
  // Item ULID (= object_id for ObjectPhoto/ObjectVideo)
  itemId: { type: String, required: true },
  // Existing photos [{ id, url, order, caption }] — seeds the grid; videos fetched here
  initialPhotos: { type: Array, default: () => [] },
})

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()

const imageInput = ref(null)
const cameraInput = ref(null)
const uploading = ref(false)
const deletingKey = ref(null)

// Unified, ordered media list. Each entry: { kind: 'photo'|'video', id, order, ... }
const media = ref([])

const photoCount = computed(() => media.value.filter(m => m.kind === 'photo').length)
const videoCount = computed(() => media.value.filter(m => m.kind === 'video').length)
const busy = computed(() => uploading.value || deletingKey.value !== null)

const mkey = (m) => `${m.kind}:${m.id}`

// --- Initial load: seed photos, fetch videos, merge into one ordered list -----
async function loadMedia() {
  const photos = (props.initialPhotos || []).map(p => ({
    kind: 'photo', id: p.id, url: p.url, order: p.order ?? 0, caption: p.caption || '',
  }))
  let videos = []
  try {
    const data = await $fetch('/api/v1/core/videos/', { params: { object_id: props.itemId } })
    videos = (data || []).map(v => ({
      kind: 'video', id: v.id, order: v.order ?? 0,
      thumbnail_url: v.thumbnail_url, embed_url: v.embed_url, title: v.title,
      duration_seconds: v.duration_seconds, is_published: v.is_published,
    }))
  } catch (e) {
    console.error('Failed to load videos:', e)
  }
  media.value = sortMedia([...photos, ...videos])
}

onMounted(loadMedia)
// The edit page is kept-alive: switching to a different item refetches in place
// (loadedEditId stays truthy, so this component is NOT remounted). Re-seed on id change.
watch(() => props.itemId, loadMedia)

// Same ordering as the public gallery: by `order`, tie → video first (legacy).
function sortMedia(list) {
  return [...list].sort((a, b) => (a.order - b.order) || (a.kind === 'video' ? -1 : 1))
}

// --- Reorder ------------------------------------------------------------------
const dragIndex = ref(null)
const dragOverIndex = ref(null)

function onDragStart(index, ev) {
  if (busy.value) return
  dragIndex.value = index
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move'
}
function onDrop(index) {
  if (dragIndex.value !== null && dragIndex.value !== index) moveTo(dragIndex.value, index)
  onDragEnd()
}
function onDragEnd() {
  dragIndex.value = null
  dragOverIndex.value = null
}

function moveTo(from, to) {
  if (busy.value) return
  if (to < 0 || to >= media.value.length || from === to) return
  const arr = [...media.value]
  const [item] = arr.splice(from, 1)
  arr.splice(to, 0, item)
  media.value = arr
  persistOrder()
}

// Coalesce rapid reorders into the latest sequence (one in-flight save at a time).
let saving = false
let dirty = false
async function persistOrder() {
  dirty = true
  if (saving) return
  saving = true
  try {
    await authStore.ensureToken()
    while (dirty) {
      dirty = false
      const order = media.value.map(m => ({ type: m.kind, id: m.id }))
      await $fetch(`/api/v1/items/${props.itemId}/media-order/`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: { order },
      })
    }
    media.value.forEach((m, i) => { m.order = i })
  } catch (err) {
    console.error('Failed to save media order:', err)
    toastStore.error($t('market.notifications.order_save_error'))
  } finally {
    saving = false
  }
}

// --- Add photos ---------------------------------------------------------------
const compressionOptions = {
  maxSizeMB: 1,
  maxWidthOrHeight: 1920,
  useWebWorker: true,
  preserveExif: true,
  fileType: 'image/jpeg',
}

const handleSelect = async (event) => {
  const files = Array.from(event.target.files || [])
  event.target.value = '' // allow re-selecting the same file later
  if (files.length === 0) return

  const remainingSlots = 5 - photoCount.value
  if (files.length > remainingSlots) {
    toastStore.error($t('market.notifications.max_photos', { count: remainingSlots }))
    return
  }

  uploading.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.token) {
      toastStore.error($t('market.notifications.login_required_action'))
      return
    }

    let added = false
    for (const file of files) {
      if (!file.type.startsWith('image/')) {
        toastStore.error($t('market.notifications.not_image', { filename: file.name }))
        continue
      }
      if (file.size > 15 * 1024 * 1024) {
        toastStore.error($t('market.notifications.file_too_large', { filename: file.name }))
        continue
      }
      if (photoCount.value >= 5) {
        toastStore.error($t('market.notifications.max_photos', { count: 0 }))
        break
      }

      let toUpload = file
      try {
        toUpload = await imageCompression(file, compressionOptions)
      } catch (e) {
        console.error('Image compression failed, using original:', e)
      }

      // Append at the end of the combined list — a unique order that never
      // collides with an existing photo slot (the upload endpoint overwrites on
      // a duplicate order). persistOrder() then normalises the whole sequence.
      const formData = new FormData()
      formData.append('image', toUpload, file.name)
      formData.append('order', String(media.value.length))
      formData.append('caption', '')

      try {
        const photo = await $fetch(`/api/v1/items/${props.itemId}/images/`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${authStore.token}` },
          credentials: 'include',
          body: formData,
        })
        media.value = [...media.value, { kind: 'photo', id: photo.id, url: photo.url, order: photo.order, caption: photo.caption || '' }]
        added = true
      } catch (err) {
        console.error('Failed to upload image:', err)
        const data = err.data || err.response?._data
        toastStore.error(`${$t('market.notifications.photo_add_error')} ${data?.error || ''}`.trim())
      }
    }
    if (added) persistOrder()
  } finally {
    uploading.value = false
  }
}

// --- Add video ----------------------------------------------------------------
// VideoUpload registers the ObjectVideo before emitting `uploaded`, so refetching
// here reliably sees the new row. Pull in any videos we don't yet have, append.
async function onVideoUploaded() {
  try {
    const data = await $fetch('/api/v1/core/videos/', { params: { object_id: props.itemId } })
    const known = new Set(media.value.filter(m => m.kind === 'video').map(m => m.id))
    const fresh = (data || [])
      .filter(v => !known.has(v.id))
      .map(v => ({
        kind: 'video', id: v.id, order: v.order ?? 0,
        thumbnail_url: v.thumbnail_url, embed_url: v.embed_url, title: v.title,
        duration_seconds: v.duration_seconds, is_published: v.is_published,
      }))
    if (fresh.length) {
      media.value = [...media.value, ...fresh]
      persistOrder()
    }
  } catch (e) {
    console.error('Failed to refresh videos:', e)
  }
}

// --- Delete -------------------------------------------------------------------
const pendingDeleteKey = ref(null)
let pendingDeleteTimer = null

function onDeleteClick(m) {
  if (busy.value) return
  if (pendingDeleteKey.value !== mkey(m)) {
    pendingDeleteKey.value = mkey(m)
    if (pendingDeleteTimer) clearTimeout(pendingDeleteTimer)
    pendingDeleteTimer = setTimeout(() => { pendingDeleteKey.value = null }, 3000)
    return
  }
  if (pendingDeleteTimer) clearTimeout(pendingDeleteTimer)
  pendingDeleteKey.value = null
  removeMedia(m)
}

async function removeMedia(m) {
  deletingKey.value = mkey(m)
  try {
    await authStore.ensureToken()
    if (!authStore.token) {
      toastStore.error($t('market.notifications.login_required_action'))
      return
    }
    const url = m.kind === 'photo'
      ? `/api/v1/items/${props.itemId}/images/${m.id}/`
      : `/api/v1/core/videos/${m.id}/`
    await $fetch(url, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${authStore.token}` },
      credentials: 'include',
    })
    media.value = media.value.filter(x => mkey(x) !== mkey(m))
    toastStore.success(m.kind === 'photo'
      ? $t('market.notifications.photo_deleted')
      : $t('market.notifications.video_deleted'))
    persistOrder()
  } catch (err) {
    console.error('Failed to delete media:', err)
    const data = err.data || err.response?._data
    toastStore.error(`${$t(m.kind === 'photo' ? 'market.notifications.photo_delete_error' : 'market.notifications.video_delete_error')} ${data?.error || ''}`.trim())
  } finally {
    deletingKey.value = null
  }
}
</script>
