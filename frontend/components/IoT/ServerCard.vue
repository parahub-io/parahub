<template>
  <div class="device-card">
    <!-- Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
          <Server class="w-5 h-5 text-emerald-500" />
        </div>
        <div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">parahub</h3>
          <span class="text-xs text-neutral-500">{{ $t('server_card.subtitle') }}</span>
        </div>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <div class="w-2.5 h-2.5 rounded-full" :class="statusDotClass"></div>
        <span class="text-sm text-neutral-500">{{ statusText }}</span>
      </div>
    </div>

    <!-- Metrics -->
    <div v-if="health" class="space-y-1.5 mb-3">
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">CPU:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ health.cpu_percent }}%</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">RAM:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ health.ram_percent }}%</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('server_card.disk') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ health.disk_percent }}%</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">Docker:</span>
        <span class="text-neutral-900 dark:text-neutral-100">
          <span class="text-green-600 dark:text-green-400">{{ health.containers_running }}</span>
          / {{ health.containers_total }}
        </span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('server_card.uptime') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ formatUptime(health.uptime_seconds) }}</span>
      </div>
    </div>

    <!-- Dashboard links — go through Django auth redirect -->
    <div class="flex flex-wrap gap-2 pt-3 border-t border-neutral-200 dark:border-neutral-700">
      <button @click="openMonitor('netdata')" class="btn-secondary text-sm">
        <Activity class="w-4 h-4 mr-1" />
        NetData
      </button>
      <button @click="openMonitor('status')" class="btn-secondary text-sm">
        <HeartPulse class="w-4 h-4 mr-1" />
        Uptime
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Server, Activity, HeartPulse } from 'lucide-vue-next'

interface ServerHealth {
  cpu_percent: number
  ram_percent: number
  disk_percent: number
  containers_running: number
  containers_total: number
  uptime_seconds: number
  netdata_url: string
  uptime_kuma_url: string
}

const health = ref<ServerHealth | null>(null)

const statusDotClass = computed(() => {
  if (!health.value) return 'bg-neutral-400'
  if (health.value.cpu_percent > 90 || health.value.ram_percent > 90) return 'bg-yellow-500 animate-pulse'
  return 'bg-green-500'
})

const statusText = computed(() => {
  if (!health.value) return '...'
  if (health.value.cpu_percent > 90 || health.value.ram_percent > 90) return 'Load'
  return 'OK'
})

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  if (days > 0) return `${days}d ${hours}h`
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

async function openMonitor(service: string) {
  const authStore = useAuthStore()
  await authStore.ensureToken()
  // Pass JWT via query param — Django validates and redirects with signed monitoring token
  window.open(`/api/v1/iot/monitor/${service}/?token=${authStore.token}`, '_blank', 'noopener')
}

async function fetchHealth() {
  try {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    const data = await $fetch<ServerHealth>('/api/v1/iot/server/health', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    health.value = data
  } catch {
    // Silent — card shows without metrics
  }
}

onMounted(fetchHealth)
</script>

<style scoped>
.device-card {
  @apply bg-neutral-100 dark:bg-neutral-800 rounded-lg p-6 border border-neutral-200 dark:border-neutral-700;
  @apply hover:border-primary transition-colors;
}
</style>
