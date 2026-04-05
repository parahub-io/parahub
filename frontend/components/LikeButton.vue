<template>
  <button
    @click.stop="toggle"
    :disabled="loading"
    class="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
    :class="{ 'text-red-500 dark:text-red-400': liked }"
    :aria-label="liked ? $t('unlike') : $t('like')"
  >
    <Heart
      :size="size"
      :class="liked ? 'fill-red-500 text-red-500 dark:fill-red-400 dark:text-red-400' : ''"
    />
    <span v-if="likesCount > 0" class="text-sm font-medium">{{ likesCount }}</span>
  </button>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Heart } from 'lucide-vue-next'

const props = defineProps({
  targetId: { type: String, required: true },
  targetType: { type: String, default: 'item' },
  size: { type: Number, default: 20 },
})

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t } = useI18n()

const liked = ref(false)
const likesCount = ref(0)
const loading = ref(false)

async function fetchStatus() {
  try {
    const res = await $fetch(`/api/v1/likes/status/${props.targetId}/`, {
      credentials: 'include',
      headers: authStore.accessToken
        ? { Authorization: `Bearer ${authStore.accessToken}` }
        : {},
    })
    liked.value = res.liked
    likesCount.value = res.likes_count
  } catch (e) {
    // silent
  }
}

async function toggle() {
  if (!authStore.isAuthenticated) {
    toastStore.warning(t('login_required'))
    return
  }

  loading.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch('/api/v1/likes/toggle/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      body: { target_id: props.targetId, target_type: props.targetType },
    })
    liked.value = res.liked
    likesCount.value = res.likes_count
  } catch (e) {
    console.error('Like toggle failed:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (authStore.isAuthenticated) await authStore.ensureToken()
  fetchStatus()
})
</script>
