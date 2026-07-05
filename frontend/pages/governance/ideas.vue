<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <button @click="router.push(localePath('/governance/polls'))" class="text-link mb-4 flex items-center gap-1">
        <ArrowLeft class="w-4 h-4" aria-hidden="true" />
        {{ $t('governance.polls') }}
      </button>
      <PageHeader
        :title="$t('civic.ideas.title')"
        :create-label="authStore.isAuthenticated ? $t('civic.ideas.create') : undefined"
        @create="showForm = !showForm"
      />
      <p class="text-sm text-neutral-500 dark:text-neutral-400 -mt-3 mb-6">
        {{ $t('civic.ideas.hint', { threshold }) }}
      </p>

      <!-- Create form -->
      <div v-if="showForm" class="card p-4 mb-6">
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('civic.ideas.formTitle') }}
            </label>
            <input v-model="form.title" maxlength="200"
                   class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent" />
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('civic.ideas.formBody') }}
            </label>
            <textarea v-model="form.body" rows="3" maxlength="4000"
                      class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"></textarea>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <select v-model="form.territory_id"
                    class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
              <option value="" disabled>—</option>
              <option v-for="t in myChain" :key="t.id" :value="t.id">{{ $t(`civic.level.${t.level}`) }} · {{ t.name }}</option>
            </select>
            <select v-model="form.topic_slug"
                    class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 px-3 py-2 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent">
              <option value="">—</option>
              <option v-for="t in topics" :key="t.slug" :value="t.slug">{{ t.icon }} {{ topicName(t) }}</option>
            </select>
          </div>
          <div class="flex items-center gap-3">
            <UiButton variant="primary" size="sm" :loading="creating"
                      :disabled="form.title.trim().length < 5 || form.body.trim().length < 10 || !form.territory_id"
                      @click="submitIdea">
              {{ $t('civic.ideas.submit') }}
            </UiButton>
            <span v-if="createError" class="text-sm text-error">{{ createError }}</span>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-12 w-12 mx-auto border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Empty -->
      <div v-else-if="ideas.length === 0" class="py-12 text-center">
        <Lightbulb class="w-12 h-12 mx-auto text-neutral-400 mb-3" aria-hidden="true" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300">{{ $t('civic.ideas.empty') }}</h3>
      </div>

      <!-- Ideas list -->
      <div v-else class="space-y-4">
        <div v-for="idea in ideas" :key="idea.id" class="card p-5">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <CivicScopeBadge :level="idea.territory_level" :name="idea.territory_name" />
            <UiBadge v-if="idea.status === 'review'" variant="warning" type="soft">{{ $t('civic.ideas.statusReview') }}</UiBadge>
            <UiBadge v-else-if="idea.status === 'promoted'" variant="success" type="soft">{{ $t('civic.ideas.statusPromoted') }}</UiBadge>
            <UiBadge v-else-if="idea.status === 'rejected'" variant="error" type="soft">{{ $t('civic.ideas.statusRejected') }}</UiBadge>
          </div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ idea.title }}</h3>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 whitespace-pre-line mb-3">{{ idea.body }}</p>

          <!-- Support progress toward the threshold -->
          <div v-if="idea.status === 'open' || idea.status === 'review'" class="mb-3">
            <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2 overflow-hidden">
              <div class="bg-secondary h-2 rounded-full transition-all duration-500"
                   :style="`width: ${Math.min(100, idea.support_count / idea.threshold * 100)}%`"></div>
            </div>
            <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              {{ $t('civic.ideas.supporters', { n: idea.support_count, threshold: idea.threshold }) }}
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <template v-if="idea.status === 'open' || idea.status === 'review'">
              <UiButton
                v-if="authStore.isAuthenticated"
                :variant="idea.supported_by_me ? 'secondary' : 'outline'"
                size="sm" :icon="ThumbsUp"
                @click="toggleSupport(idea)"
              >
                {{ idea.supported_by_me ? $t('civic.ideas.supported') : $t('civic.ideas.support') }}
              </UiButton>
            </template>
            <UiButton
              v-if="idea.status === 'promoted' && idea.promoted_poll_id"
              variant="secondary" size="sm"
              :to="localePath(`/governance/polls/${idea.promoted_poll_id}`)"
            >
              {{ $t('civic.ideas.openPoll') }}
            </UiButton>

            <!-- Staff formulation review -->
            <template v-if="isStaff && (idea.status === 'review' || idea.status === 'open')">
              <UiButton variant="outline-success" size="sm"
                        :to="localePath(`/governance/polls/create?from_idea=${idea.id}&territory=${idea.territory_id}&title=${encodeURIComponent(idea.title)}`)">
                {{ $t('civic.ideas.promote') }}
              </UiButton>
              <UiButton :variant="pendingReject === idea.id ? 'error' : 'outline-error'" size="sm"
                        @click="rejectIdea(idea)">
                {{ pendingReject === idea.id ? $t('civic.ideas.rejectSure') : $t('civic.ideas.reject') }}
              </UiButton>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, Lightbulb, ThumbsUp } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()

const ideas = ref<any[]>([])
const topics = ref<any[]>([])
const myChain = ref<any[]>([])
const loading = ref(true)
const showForm = ref(false)
const creating = ref(false)
const createError = ref('')
const pendingReject = ref<string | null>(null)
let rejectTimer: ReturnType<typeof setTimeout> | null = null

const form = ref({ title: '', body: '', territory_id: '', topic_slug: '' })

const isStaff = computed(() => !!authStore.user?.is_staff)
const threshold = computed(() => ideas.value[0]?.threshold ?? 10)

async function authed(): Promise<Record<string, string>> {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

function topicName(t: any): string {
  return t.name_i18n?.[locale.value] || t.name
}

async function load() {
  loading.value = true
  try {
    const headers = await authed()
    const query: Record<string, string> = {}
    if (!authStore.isAuthenticated) {
      const guess = (navigator.language?.split('-')[1] || '').toUpperCase()
      if (guess) query.country = guess
    }
    ideas.value = await $fetch('/api/v1/governance/civic/ideas/', { credentials: 'include', headers, query })
  } catch { ideas.value = [] }
  loading.value = false
}

async function submitIdea() {
  creating.value = true
  createError.value = ''
  try {
    const headers = await authed()
    await $fetch('/api/v1/governance/civic/ideas/', {
      method: 'POST', credentials: 'include', headers,
      body: {
        territory_id: form.value.territory_id,
        title: form.value.title.trim(),
        body: form.value.body.trim(),
        topic_slug: form.value.topic_slug || null,
      },
    })
    form.value = { title: '', body: '', territory_id: form.value.territory_id, topic_slug: '' }
    showForm.value = false
    await load()
  } catch (e: any) {
    createError.value = e?.response?._data?.detail || e?.data?.detail || String(e?.message || e)
  } finally {
    creating.value = false
  }
}

async function toggleSupport(idea: any) {
  try {
    const headers = await authed()
    const action = idea.supported_by_me ? 'unsupport' : 'support'
    const updated: any = await $fetch(`/api/v1/governance/civic/ideas/${idea.id}/${action}/`, {
      method: 'POST', credentials: 'include', headers,
    })
    const index = ideas.value.findIndex(i => i.id === idea.id)
    if (index >= 0) ideas.value[index] = updated
  } catch { /* consent/scope errors: keep state */ }
}

// Two-tap destructive confirmation (design-system pattern)
async function rejectIdea(idea: any) {
  if (pendingReject.value !== idea.id) {
    pendingReject.value = idea.id
    if (rejectTimer) clearTimeout(rejectTimer)
    rejectTimer = setTimeout(() => { pendingReject.value = null }, 3000)
    return
  }
  pendingReject.value = null
  try {
    const headers = await authed()
    await $fetch(`/api/v1/governance/civic/ideas/${idea.id}/reject/`, {
      method: 'POST', credentials: 'include', headers, body: { note: '' },
    })
    await load()
  } catch { /* staff only */ }
}

onMounted(async () => {
  load()
  try { topics.value = await $fetch('/api/v1/governance/civic/topics/') } catch { /* empty */ }
  if (authStore.isAuthenticated) {
    try {
      const headers = await authed()
      const res: any = await $fetch('/api/v1/governance/civic/residency/', { credentials: 'include', headers })
      myChain.value = res.chain || []
      if (myChain.value.length && !form.value.territory_id) {
        form.value.territory_id = myChain.value[0].id  // deepest level preselected
      }
    } catch { /* no residency */ }
  }
})
</script>
