<template>
  <div v-if="videos.length > 0 || loading" class="space-y-3">
    <!-- Loading -->
    <div v-if="loading" class="py-6 text-center">
      <div class="inline-block h-6 w-6 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
    </div>

    <!-- Video list -->
    <template v-else>
      <div v-for="video in videos" :key="video.id" class="rounded-lg overflow-hidden">
        <VideoPlayer
          :embed-url="video.embed_url"
          :title="video.title"
        />
        <div class="flex items-center justify-between mt-2 px-1">
          <div class="min-w-0">
            <NuxtLink
              v-if="video.peertube_url"
              :to="localePath(`/videos/${video.peertube_uuid}`)"
              class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary truncate block"
            >
              {{ video.title }}
            </NuxtLink>
            <p v-else class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
              {{ video.title }}
            </p>
            <p v-if="video.duration_seconds" class="text-xs text-neutral-500">
              {{ formatDuration(video.duration_seconds) }}
            </p>
          </div>
          <button
            v-if="canDelete(video)"
            @click="handleDelete(video)"
            class="p-1.5 rounded shrink-0 transition-colors"
            :class="pendingDeleteId === video.id ? 'text-white bg-error' : 'text-neutral-400 hover:text-error'"
            :title="pendingDeleteId === video.id ? $t('common.confirm') : $t('common.delete')"
          >
            <component :is="pendingDeleteId === video.id ? Check : Trash2" class="w-4 h-4" />
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Trash2, Check } from 'lucide-vue-next'

const props = defineProps<{
  objectId: string
  editable?: boolean
}>()

const emit = defineEmits<{
  deleted: [videoId: string]
}>()

const localePath = useLocalePath()
const authStore = useAuthStore()

interface VideoItem {
  id: string
  object_id: string
  peertube_uuid: string
  peertube_url: string
  title: string
  description: string
  duration_seconds: number | null
  thumbnail_url: string
  embed_url: string
  hls_url: string
  order: number
  uploaded_by_id: string
  is_published: boolean
}

const videos = ref<VideoItem[]>([])
const loading = ref(true)
const pendingDeleteId = ref<string | null>(null)
let pendingDeleteTimer: ReturnType<typeof setTimeout> | null = null

async function fetchVideos() {
  if (!props.objectId || props.objectId.length !== 26) {
    loading.value = false
    return
  }

  try {
    const data = await $fetch<VideoItem[]>('/api/v1/core/videos/', {
      params: { object_id: props.objectId },
    })
    videos.value = data
  } catch (e) {
    console.error('Failed to fetch videos:', e)
  } finally {
    loading.value = false
  }
}

function canDelete(video: VideoItem): boolean {
  if (!props.editable) return false
  const profileId = authStore.profile?.id
  return !!profileId && video.uploaded_by_id === profileId
}

async function handleDelete(video: VideoItem) {
  if (pendingDeleteId.value !== video.id) {
    pendingDeleteId.value = video.id
    if (pendingDeleteTimer) clearTimeout(pendingDeleteTimer)
    pendingDeleteTimer = setTimeout(() => { pendingDeleteId.value = null }, 3000)
    return
  }
  pendingDeleteId.value = null
  if (pendingDeleteTimer) clearTimeout(pendingDeleteTimer)

  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/core/videos/${video.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    videos.value = videos.value.filter(v => v.id !== video.id)
    emit('deleted', video.id)
  } catch (e) {
    console.error('Failed to delete video:', e)
  }
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

onMounted(fetchVideos)

watch(() => props.objectId, fetchVideos)
</script>
