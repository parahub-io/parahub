<script setup lang="ts">
import { MessageCircle, Trash2, Send, User } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

const props = defineProps<{
  postId: string
  allowComments: boolean
  commentsCount: number
}>()

const { t, locale } = useI18n()
const authStore = useAuthStore()
const toast = useToastStore()

const comments = ref<any[]>([])
const loading = ref(true)
const newText = ref('')
const sending = ref(false)

async function fetchComments() {
  loading.value = true
  try {
    comments.value = await $fetch<any[]>('/api/v1/core/comments/', {
      params: { object_id: props.postId },
    })
  } catch { /* ignore */ }
  loading.value = false
}

async function submit() {
  if (!newText.value.trim() || sending.value) return
  sending.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/core/comments/', {
      method: 'POST',
      body: { object_id: props.postId, text: newText.value.trim() },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    comments.value.push(res)
    newText.value = ''
  } catch (e: any) {
    toast.error(e.data?.error || 'Failed to post comment')
  }
  sending.value = false
}

async function deleteComment(id: string) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/core/comments/${id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    comments.value = comments.value.filter(c => c.id !== id)
  } catch {
    toast.error('Failed to delete comment')
  }
}

onMounted(fetchComments)
</script>

<template>
  <div v-if="allowComments" class="card p-4">
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
      <MessageCircle class="w-5 h-5" />
      {{ t('cms.comments') }}
      <span v-if="comments.length > 0" class="text-sm font-normal text-neutral-500">({{ comments.length }})</span>
    </h2>

    <!-- Comment form -->
    <div v-if="authStore.isAuthenticated" class="flex gap-2 mb-4">
      <textarea
        v-model="newText"
        :placeholder="t('cms.writeComment')"
        rows="2"
        maxlength="2000"
        class="flex-1 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
        @keydown.meta.enter="submit"
        @keydown.ctrl.enter="submit"
      />
      <UiButton
        variant="primary"
        size="sm"
        :icon="Send"
        :loading="sending"
        :disabled="!newText.trim()"
        @click="submit"
        class="self-end"
      >
        {{ t('cms.publish') }}
      </UiButton>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-4">
      <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
    </div>

    <!-- Comments list -->
    <div v-else-if="comments.length > 0" class="space-y-3">
      <div
        v-for="comment in comments"
        :key="comment.id"
        class="flex gap-3 text-sm"
      >
        <User class="w-5 h-5 text-neutral-400 shrink-0 mt-0.5" />
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ comment.author_display_name || comment.author_name }}</span>
            <span class="text-xs text-neutral-400">{{ new Date(comment.created_at).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) }}</span>
            <button
              v-if="authStore.activeProfile?.id === comment.author_id"
              @click="deleteComment(comment.id)"
              class="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <Trash2 class="w-3.5 h-3.5" />
              <span>{{ t('common.delete') }}</span>
            </button>
          </div>
          <p class="text-neutral-700 dark:text-neutral-300 whitespace-pre-line">{{ comment.text }}</p>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">
      {{ t('cms.noComments') }}
    </p>
  </div>
</template>
