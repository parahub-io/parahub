<template>
  <div class="card p-5">
    <div class="flex flex-wrap items-center gap-2 mb-2">
      <CivicScopeBadge v-if="showScope" :level="idea.territory_level" :name="idea.territory_name" />
      <UiBadge variant="secondary" type="soft">
        <Lightbulb class="w-3.5 h-3.5 mr-1 inline" aria-hidden="true" />{{ $t('civic.ideas.badge') }}
      </UiBadge>
      <UiBadge v-if="idea.status === 'review'" variant="warning" type="soft">{{ $t('civic.ideas.statusReview') }}</UiBadge>
      <UiBadge v-else-if="idea.status === 'promoted'" variant="success" type="soft">{{ $t('civic.ideas.statusPromoted') }}</UiBadge>
      <UiBadge v-else-if="idea.status === 'rejected'" variant="error" type="soft">{{ $t('civic.ideas.statusRejected') }}</UiBadge>
    </div>

    <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ displayTitle }}</h3>

    <!-- MT indicator + toggle back to the author's original text -->
    <div v-if="idea.is_translated" class="flex items-center gap-3 mb-1 text-xs text-neutral-500 dark:text-neutral-400">
      <span v-if="!showOriginal" class="inline-flex items-center gap-1">
        <Languages class="w-3.5 h-3.5" aria-hidden="true" />
        {{ $t('civic.translation.auto_translated') }}
      </span>
      <button class="underline underline-offset-2 hover:text-secondary" @click="showOriginal = !showOriginal">
        {{ showOriginal ? $t('civic.translation.show_translation') : $t('civic.translation.show_original') }}
      </button>
    </div>

    <p
      class="text-sm text-neutral-600 dark:text-neutral-400 whitespace-pre-line mb-3"
      :class="{ 'line-clamp-3': dense }"
    >{{ displayBody }}</p>

    <!-- Support progress toward the threshold of this territory -->
    <div v-if="pending" class="mb-3">
      <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2 overflow-hidden">
        <div
          class="bg-secondary h-2 rounded-full transition-all duration-500"
          :style="`width: ${Math.min(100, idea.support_count / Math.max(1, idea.threshold) * 100)}%`"
        ></div>
      </div>
      <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
        {{ $t('civic.ideas.supporters', { n: idea.support_count, threshold: idea.threshold }) }}
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <UiButton
        v-if="pending && authStore.isAuthenticated"
        :variant="idea.supported_by_me ? 'secondary' : 'outline'"
        size="sm" :icon="ThumbsUp" :loading="busy"
        @click="toggleSupport"
      >
        {{ idea.supported_by_me ? $t('civic.ideas.supported') : $t('civic.ideas.support') }}
      </UiButton>
      <UiButton
        v-if="idea.status === 'promoted' && idea.promoted_poll_id"
        variant="secondary" size="sm"
        :to="localePath(`/governance/polls/${idea.promoted_poll_id}`)"
      >
        {{ $t('civic.ideas.openPoll') }}
      </UiButton>

      <!-- Staff moderation: a takedown after the fact, not a gate before it -->
      <template v-if="isStaff">
        <UiButton
          v-if="pending"
          variant="outline-success" size="sm"
          :to="localePath(`/governance/polls/create?from_idea=${idea.id}&territory=${idea.territory_id}&title=${encodeURIComponent(idea.title)}`)"
        >
          {{ $t('civic.ideas.promote') }}
        </UiButton>
        <UiButton
          v-if="idea.status !== 'rejected'"
          :variant="pendingReject ? 'error' : 'outline-error'" size="sm"
          @click="reject"
        >
          {{ pendingReject ? $t('civic.ideas.rejectSure') : $t('civic.ideas.reject') }}
        </UiButton>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { Languages, Lightbulb, ThumbsUp } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const props = defineProps<{
  idea: any
  // Feed placement: the section header already names the territory, and the
  // body is clamped so an idea never outshouts the ballots around it
  dense?: boolean
  showScope?: boolean
}>()

const emit = defineEmits<{
  // replaced row after a support toggle
  (e: 'update', idea: any): void
  // the support tipped the threshold (a poll now exists) or staff took it down
  (e: 'changed'): void
}>()

const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t, locale } = useI18n()

const busy = ref(false)
const showOriginal = ref(false)
const pendingReject = ref(false)
let rejectTimer: ReturnType<typeof setTimeout> | null = null

// Post-hoc takedown of an idea (and the poll it minted): `moderation.review`.
const { can } = useCapabilities()
const isStaff = computed(() => can('moderation.review'))
const pending = computed(() => props.idea.status === 'open' || props.idea.status === 'review')
const displayTitle = computed(() =>
  props.idea.translated_title && !showOriginal.value ? props.idea.translated_title : props.idea.title)
const displayBody = computed(() =>
  props.idea.translated_body && !showOriginal.value ? props.idea.translated_body : props.idea.body)

async function authed(): Promise<Record<string, string>> {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function toggleSupport() {
  if (busy.value) return
  busy.value = true
  try {
    const headers = await authed()
    const action = props.idea.supported_by_me ? 'unsupport' : 'support'
    // translate_to keeps the card translated — the response replaces the row
    const updated: any = await $fetch(`/api/v1/governance/civic/ideas/${props.idea.id}/${action}/`, {
      method: 'POST', credentials: 'include', headers,
      query: { translate_to: locale.value },
    })
    emit('update', updated)
    // Crossing the threshold mints the poll server-side — the feed must reload
    if (updated.status === 'promoted' && props.idea.status !== 'promoted') emit('changed')
  } catch { /* consent/scope errors: keep state */ } finally {
    busy.value = false
  }
}

// Two-tap destructive confirmation (design-system pattern)
async function reject() {
  if (!pendingReject.value) {
    pendingReject.value = true
    if (rejectTimer) clearTimeout(rejectTimer)
    rejectTimer = setTimeout(() => { pendingReject.value = false }, 3000)
    return
  }
  pendingReject.value = false
  try {
    const headers = await authed()
    await $fetch(`/api/v1/governance/civic/ideas/${props.idea.id}/reject/`, {
      method: 'POST', credentials: 'include', headers, body: { note: '' },
    })
    emit('changed')
  } catch { /* staff only */ }
}

onBeforeUnmount(() => { if (rejectTimer) clearTimeout(rejectTimer) })
</script>
