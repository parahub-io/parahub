<template>
  <div>
    <div v-if="!stats" class="text-neutral-500 text-sm italic py-8 text-center">
      Loading stats...
    </div>
    <div v-else>
      <!-- Summary cards -->
      <div class="grid grid-cols-3 gap-4 mb-6">
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.total_sessions }}</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('yellow_hive.total_sessions') }}</div>
        </div>
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.total_hours }}h</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('yellow_hive.total_hours') }}</div>
        </div>
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold" :class="stats.success_rate >= 90 ? 'text-success dark:text-success-400' : stats.success_rate >= 70 ? 'text-warning dark:text-warning-400' : 'text-error dark:text-error-400'">
            {{ stats.success_rate }}%
          </div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('yellow_hive.success_rate') }}</div>
        </div>
      </div>

      <!-- Per-agent breakdown -->
      <div class="space-y-3 mb-6">
        <div v-for="(data, name) in stats.by_agent" :key="name" class="flex items-center gap-3">
          <span class="w-14 text-sm font-medium text-neutral-700 dark:text-neutral-300 capitalize">{{ name }}</span>
          <div class="flex-1 bg-neutral-200 dark:bg-neutral-700 rounded-full h-4 overflow-hidden">
            <div
              class="h-full rounded-full bg-primary transition-all"
              :style="{ width: maxHours > 0 ? `${(data.hours / maxHours) * 100}%` : '0%' }"
            ></div>
          </div>
          <span class="text-sm text-neutral-500 w-20 text-right">{{ data.hours }}h / {{ data.sessions }}</span>
        </div>
      </div>

      <!-- Last 7 days chart -->
      <h4 class="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">Last 7 days</h4>
      <div class="flex items-end gap-1 h-24">
        <div
          v-for="day in stats.last_7_days"
          :key="day.date"
          class="flex-1 flex flex-col items-center gap-1"
        >
          <div
            class="w-full rounded-t bg-primary/80 transition-all min-h-[2px]"
            :style="{ height: maxDaySessions > 0 ? `${(day.sessions / maxDaySessions) * 80}px` : '2px' }"
            :title="`${day.date}: ${day.sessions} sessions, ${day.hours}h`"
          ></div>
          <span class="text-[10px] text-neutral-400">{{ day.date.slice(5) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { t: $t } = useI18n()
const agentsStore = useAgentsStore()

const stats = computed(() => agentsStore.stats)

const maxHours = computed(() => {
  if (!stats.value) return 0
  return Math.max(...Object.values(stats.value.by_agent).map(a => a.hours), 0.1)
})

const maxDaySessions = computed(() => {
  if (!stats.value) return 0
  return Math.max(...stats.value.last_7_days.map(d => d.sessions), 1)
})

onMounted(() => {
  agentsStore.fetchStats()
})
</script>
