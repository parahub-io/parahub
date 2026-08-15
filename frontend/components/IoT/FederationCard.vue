<template>
  <NuxtLink :to="localePath('/federation')" class="card p-6 block hover:border-primary transition-colors">
    <!-- Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-secondary/10 flex items-center justify-center">
          <Globe class="w-5 h-5 text-secondary" aria-hidden="true" />
        </div>
        <div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('federation.title') }}</h3>
          <span class="text-xs text-neutral-500 font-mono">{{ manifest?.domain || '—' }}</span>
        </div>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <div class="w-2.5 h-2.5 rounded-full" :class="statusDotClass"></div>
        <span class="text-sm text-neutral-500">{{ statusText }}</span>
      </div>
    </div>

    <!-- Registry counters -->
    <div v-if="stats" class="space-y-1.5">
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('federation.stats.organizations') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ stats.organizations }}</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('federation.stats.peers') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ stats.peers }}</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('federation.stats.migrations') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ stats.migrations }}</span>
      </div>
      <div class="flex justify-between text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ $t('federation.peers.last_fetch') }}:</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ lastFetchLabel }}</span>
      </div>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
import { Globe } from 'lucide-vue-next'

const localePath = useLocalePath()

const manifest = ref<any>(null)
const stats = ref<any>(null)
const syncStatuses = ref<any[]>([])

// Peers that answered a git fetch — the honest "is this node actually federated" signal
const statusDotClass = computed(() => {
  if (!stats.value) return 'bg-neutral-400'
  return stats.value.connected_peers > 0 ? 'bg-green-500' : 'bg-neutral-400'
})

const statusText = computed(() => {
  if (!stats.value) return '…'
  return `${stats.value.connected_peers}/${stats.value.peers}`
})

const lastFetchLabel = computed(() => {
  const stamps = syncStatuses.value
    .map(s => s.last_fetch)
    .filter(Boolean)
    .map(s => new Date(s).getTime())
    .filter(t => !Number.isNaN(t))
  if (!stamps.length) return '—'
  return new Date(Math.max(...stamps)).toLocaleString()
})

async function fetchFederation() {
  try {
    const [manifestRes, statsRes] = await Promise.all([
      $fetch('/api/v1/federation/node/', { credentials: 'include' }),
      $fetch('/api/v1/federation/stats/', { credentials: 'include' }),
    ])
    manifest.value = manifestRes
    stats.value = statsRes
  } catch {
    // Silent — card shows without counters
  }

  // Git sync status is staff-only; the card lives on a staff-gated tab
  try {
    const authStore = useAuthStore()
    await authStore.ensureToken()
    const syncRes = await $fetch('/api/v1/federation/sync/status/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    }) as any
    syncStatuses.value = syncRes?.peers || []
  } catch {
    // Silent — last fetch stays "—"
  }
}

onMounted(fetchFederation)
</script>
