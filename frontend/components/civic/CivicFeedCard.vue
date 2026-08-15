<template>
  <div
    @click="router.push(localePath(`/governance/polls/${item.id}`))"
    class="card p-6 cursor-pointer hover:border-primary transition-colors"
  >
    <div class="flex flex-wrap justify-between items-start gap-2 mb-3">
      <div class="flex flex-wrap items-center gap-2">
        <CivicScopeBadge
          v-if="badgeVisible"
          :level="item.kind === 'civic' ? item.scope_level : null"
          :name="item.kind === 'civic' ? item.scope_name : undefined"
        />
        <UiBadge v-if="item.kind === 'civic'" variant="secondary" type="soft" :title="$t('civic.badgeHint')">
          {{ $t('civic.badge') }}
        </UiBadge>
        <!-- A neighbour's proposal that gathered enough support to reach the ballot -->
        <UiBadge v-if="item.citizen_authored" variant="primary" type="soft">
          <Lightbulb class="w-3.5 h-3.5 mr-1 inline" aria-hidden="true" />{{ $t('civic.citizen.badge') }}
        </UiBadge>
        <span
          v-if="item.status !== 'active'"
          class="px-3 py-1 rounded-full text-xs font-semibold" :class="statusClass(item.status)"
        >
          {{ $t(`governance.status.${item.status}`, item.status) }}
        </span>
      </div>
      <div class="flex items-center gap-3 text-sm text-neutral-500 dark:text-neutral-400">
        <span v-if="item.kind === 'civic'" class="flex items-center gap-1">
          <Users class="w-4 h-4" aria-hidden="true" />
          {{ item.n_display }}
        </span>
        <span v-else>{{ item.total_voted }} / {{ item.total_eligible }}</span>
        <CheckCircle
          v-if="item.has_voted"
          class="w-5 h-5 text-success"
          :title="$t('civic.feed.voted')"
          aria-hidden="true"
        />
      </div>
    </div>

    <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
      {{ pickI18n(item.title_i18n, item.title, locale) }}
    </h3>
    <p class="text-neutral-600 dark:text-neutral-400 line-clamp-2">
      {{ pickI18n(item.description_i18n, item.description, locale) }}
    </p>

    <div v-if="item.civic_destination" class="mt-3 flex items-start gap-2 text-sm text-secondary dark:text-secondary-400">
      <Send class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <span>{{ pickI18n(item.civic_destination_i18n, item.civic_destination, locale) }}</span>
    </div>

    <CivicEciGauge
      v-if="item.scope_level === 'eu'"
      :supporters="item.eci_supporters"
      :countries="item.eci_countries"
    />

    <div class="mt-3 flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
      <span class="flex items-center gap-1">
        <Calendar class="w-3.5 h-3.5" aria-hidden="true" />
        {{ formatDate(item.created_at) }}
      </span>
      <span v-if="item.comments_enabled" class="flex items-center gap-1">
        <MessageSquare class="w-3.5 h-3.5" aria-hidden="true" />
        {{ $t('civic.feed.commentsEnabled') }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Users, Calendar, CheckCircle, Send, MessageSquare, Lightbulb } from 'lucide-vue-next'

const props = defineProps<{
  item: any
  // Force the scope badge (history list mixes scopes); by default only
  // household/condominium items carry it — the section header names the rest
  showScope?: boolean
}>()

const router = useRouter()
const localePath = useLocalePath()
const { t: $t, locale } = useI18n()

const badgeVisible = computed(() =>
  props.showScope
  || props.item.scope_level === 'household'
  || props.item.scope_level === 'condominium')

function statusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-success-100 text-success-700 dark:bg-success-900/30 dark:text-success-300'
    case 'ended': return 'bg-neutral-100 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300'
    case 'draft': return 'bg-warning-100 text-warning-700 dark:bg-warning-900/30 dark:text-warning-300'
    case 'cancelled': return 'bg-error-100 text-error-700 dark:bg-error-900/30 dark:text-error-300'
    default: return 'bg-neutral-100 text-neutral-700'
  }
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}
</script>
