<template>
  <div class="call-container bg-neutral-900">
    <!-- Loading state -->
    <div v-if="loading" class="h-full flex flex-col items-center justify-center text-white">
      <Loader2 class="w-12 h-12 animate-spin text-primary mb-4" />
      <p class="text-lg">{{ t('call.connecting') }}</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="h-full flex flex-col items-center justify-center text-white p-6">
      <AlertTriangle class="w-16 h-16 text-red-500 mb-4" />
      <h2 class="text-xl font-bold mb-2">{{ t('call.error_title') }}</h2>
      <p class="text-neutral-400 mb-6 text-center">{{ error }}</p>
      <NuxtLink :to="localePath('/')" class="btn-primary">
        {{ t('call.return_home') }}
      </NuxtLink>
    </div>

    <!-- Jitsi iframe -->
    <div v-else-if="jitsiUrl" class="relative h-full">
      <iframe
        ref="jitsiIframe"
        :src="jitsiUrl"
        class="w-full h-full border-0"
        allow="camera; microphone; display-capture; fullscreen; autoplay"
        allowfullscreen
        @load="onIframeLoad"
      />

      <!-- Close button overlay -->
      <button
        @click="endCall"
        class="btn-error absolute top-4 right-4 p-3 rounded-full shadow-lg z-10"
        :aria-label="t('call.end_call')"
      >
        <X class="w-6 h-6" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loader2, AlertTriangle, X } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()

definePageMeta({
  middleware: 'auth'
})

useHead({
  title: 'Call - Parahub'
})

// State
const loading = ref(true)
const error = ref<string | null>(null)
const jitsiUrl = ref<string | null>(null)
const jitsiIframe = ref<HTMLIFrameElement | null>(null)
const roomName = ref<string | null>(null)

onMounted(async () => {
  // Get target or room from query params
  const targetProfileId = route.query.target as string
  const existingRoom = route.query.room as string

  if (existingRoom) {
    // Join existing room
    await joinRoom(existingRoom)
  } else if (targetProfileId) {
    // Create new room for call with target user
    await createRoom(targetProfileId)
  } else {
    // No target specified - create a personal room
    await createRoom()
  }
})

async function createRoom(targetProfileId?: string) {
  loading.value = true
  error.value = null

  try {
    await authStore.ensureToken()

    const body = targetProfileId ? { target_profile_id: targetProfileId } : {}

    const response = await $fetch<{
      success: boolean
      room_name?: string
      jwt_token?: string
      jitsi_url?: string
      error?: string
    }>('/api/v1/jitsi/create-room', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body
    })

    if (response.success && response.jitsi_url) {
      roomName.value = response.room_name || null
      jitsiUrl.value = response.jitsi_url
    } else {
      error.value = response.error || t('call.error_create_room')
    }
  } catch (err: any) {
    console.error('[call.vue] Failed to create room:', err)
    // Handle 401 Unauthorized - redirect to login
    if (err.statusCode === 401 || err.status === 401) {
      navigateTo(localePath('/login'))
      return
    }
    error.value = err.data?.detail || err.data?.error || err.message || t('call.error_create_room')
  } finally {
    loading.value = false
  }
}

async function joinRoom(room: string) {
  loading.value = true
  error.value = null

  try {
    await authStore.ensureToken()

    const response = await $fetch<{
      success: boolean
      jwt_token?: string
      jitsi_url?: string
      error?: string
    }>(`/api/v1/jitsi/join-room/${encodeURIComponent(room)}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (response.success && response.jitsi_url) {
      roomName.value = room
      jitsiUrl.value = response.jitsi_url
    } else {
      error.value = response.error || t('call.error_join_room')
    }
  } catch (err: any) {
    console.error('[call.vue] Failed to join room:', err)
    // Handle 401 Unauthorized - redirect to login
    if (err.statusCode === 401 || err.status === 401) {
      navigateTo(localePath('/login'))
      return
    }
    error.value = err.data?.detail || err.data?.error || err.message || t('call.error_join_room')
  } finally {
    loading.value = false
  }
}

function onIframeLoad() {}

function endCall() {
  // Clean up and navigate back
  jitsiUrl.value = null
  roomName.value = null

  // Navigate to previous page or home
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push(localePath('/'))
  }

  toastStore.info(t('call.ended'))
}
</script>

<style scoped>
/* Override default layout constraints */
.call-container {
  position: fixed;
  top: 80px; /* navbar height */
  left: 0;
  right: 0;
  bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  z-index: 40;
}
</style>
