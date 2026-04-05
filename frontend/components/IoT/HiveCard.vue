<template>
  <NuxtLink
    :to="localePath('/yellow-gate')"
    class="device-card block"
  >
    <!-- Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden">
          <img src="/img/agents/forge.png" alt="Hive" class="w-9 h-9 object-contain" />
        </div>
        <div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Hive</h3>
          <span class="text-xs text-neutral-500">{{ $t('yellow_hive.title') }}</span>
        </div>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <div class="w-2.5 h-2.5 rounded-full" :class="hasRunning ? 'bg-green-500 animate-pulse' : 'bg-neutral-400'"></div>
        <span class="text-sm text-neutral-500">{{ hasRunning ? $t('yellow_hive.status_running') : $t('yellow_hive.status_idle') }}</span>
      </div>
    </div>

    <!-- Agent list -->
    <div class="space-y-2 mb-3">
      <div
        v-for="agent in agents"
        :key="agent.name"
        class="flex items-center justify-between text-sm"
      >
        <div class="flex items-center gap-2">
          <img :src="`/img/agents/${agent.name}.png`" :alt="agent.display_name" class="w-5 h-5 object-contain" />
          <div class="w-2 h-2 rounded-full" :class="statusDot(agent.status)"></div>
          <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ agent.display_name }}</span>
          <span class="text-neutral-400">{{ agent.role }}</span>
          <span v-if="issueCount(agent.name)" class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold leading-none text-white bg-primary rounded-full">{{ issueCount(agent.name) }}</span>
        </div>
        <span v-if="agent.last_session" class="text-neutral-400 text-xs">
          {{ formatRelative(agent.last_session.finished_at || agent.last_session.started_at) }}
        </span>
      </div>
    </div>

    <!-- Stats summary -->
    <div v-if="stats" class="flex gap-4 pt-3 border-t border-neutral-200 dark:border-neutral-700 text-xs text-neutral-500">
      <span><strong class="text-neutral-700 dark:text-neutral-300">{{ stats.total_sessions }}</strong> sessions</span>
      <span><strong class="text-neutral-700 dark:text-neutral-300">{{ stats.total_hours }}h</strong> total</span>
      <span><strong class="text-green-600 dark:text-green-400">{{ stats.success_rate }}%</strong> success</span>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">

const { t: $t } = useI18n()
const localePath = useLocalePath()
const agentsStore = useAgentsStore()

const agents = computed(() => agentsStore.agents)
const stats = computed(() => agentsStore.stats)
const hasRunning = computed(() => agents.value.some(a => a.status === 'running'))

function statusDot(status: string): string {
  const m: Record<string, string> = {
    running: 'bg-green-500 animate-pulse',
    idle: 'bg-neutral-400',
    failed: 'bg-red-500',
  }
  return m[status] || 'bg-neutral-400'
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return $t('yellow_hive.time_just_now')
  if (diff < 3600) return $t('yellow_hive.time_minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return $t('yellow_hive.time_hours_ago', { n: Math.floor(diff / 3600) })
  return $t('yellow_hive.time_days_ago', { n: Math.floor(diff / 86400) })
}

function issueCount(name: string): number {
  return agentsStore.issues.filter(issue =>
    (issue.assignees || []).some((a: any) => a.login === name)
  ).length
}

onMounted(() => {
  agentsStore.fetchAgents()
  agentsStore.fetchStats()
  agentsStore.fetchIssues('open')
})
</script>

<style scoped>
.device-card {
  @apply bg-neutral-100 dark:bg-neutral-800 rounded-lg p-6 border border-neutral-200 dark:border-neutral-700;
  @apply hover:border-primary transition-colors;
}
</style>
