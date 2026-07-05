<template>
  <div class="card p-4">
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
      <MessageSquare class="w-5 h-5" aria-hidden="true" />
      {{ $t('civic.comments.title') }}
      <span v-if="comments.length" class="text-sm font-normal text-neutral-500 dark:text-neutral-400">({{ comments.length }})</span>
    </h2>

    <!-- Structurally separate from the vote: commenting never reveals how you voted.
         Disclosing a stance in the text is the author's voluntary choice. -->
    <div v-if="authStore.isAuthenticated" class="mb-4">
      <textarea
        v-model="draft"
        rows="2"
        maxlength="2000"
        :placeholder="$t('civic.comments.placeholder')"
        class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
      ></textarea>
      <div class="flex justify-end mt-2">
        <UiButton variant="secondary" size="sm" :loading="posting" :disabled="!draft.trim()" @click="postComment">
          {{ $t('civic.comments.submit') }}
        </UiButton>
      </div>
    </div>
    <p v-else class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">{{ $t('civic.comments.login') }}</p>

    <div v-if="comments.length === 0" class="py-6 text-center text-sm text-neutral-500 dark:text-neutral-400">
      {{ $t('civic.comments.empty') }}
    </div>

    <div v-else class="space-y-4">
      <div v-for="c in comments" :key="c.id" class="flex gap-3">
        <div class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center shrink-0">
          <User class="w-4 h-4 text-neutral-500 dark:text-neutral-400" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline gap-2">
            <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200">
              {{ c.author_display_name || c.author_name }}
            </span>
            <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ formatDate(c.created_at) }}</span>
          </div>
          <p class="text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-line break-words">{{ c.text }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { MessageSquare, User } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const props = defineProps<{ objectId: string }>()

const { t: $t, locale } = useI18n()
const authStore = useAuthStore()

const comments = ref<any[]>([])
const draft = ref('')
const posting = ref(false)

async function loadComments() {
  try {
    comments.value = await $fetch('/api/v1/core/comments/', { query: { object_id: props.objectId } })
  } catch { /* non-critical */ }
}

async function postComment() {
  if (!draft.value.trim() || posting.value) return
  posting.value = true
  try {
    await authStore.ensureToken()
    const created: any = await $fetch('/api/v1/core/comments/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { object_id: props.objectId, text: draft.value.trim() },
    })
    comments.value.push(created)
    draft.value = ''
  } catch { /* rate limit / gate errors are non-critical here */ }
  posting.value = false
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

onMounted(loadComments)
</script>
