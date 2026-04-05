<template>
  <div class="p-3 rounded-lg border bg-neutral-50 dark:bg-neutral-900/20 border-neutral-300 dark:border-neutral-600">
    <div class="flex items-start justify-between gap-2 mb-2">
      <div class="flex items-center gap-2 flex-1 min-w-0">
        <span class="font-mono text-xs break-all text-neutral-600 dark:text-neutral-400">
          {{ entry.fingerprint }}
        </span>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <span
          class="px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap"
          :class="{
            'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200': entry.action === 'CREATED',
            'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200': entry.action === 'REVOKED',
            'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200': entry.action === 'EXPIRED'
          }"
        >
          {{ entry.action }}
        </span>
        <button
          @click="emit('export', entry)"
          class="p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded"
          title="Export public key"
        >
          <Download class="w-3 h-3 text-neutral-600 dark:text-neutral-400" />
        </button>
      </div>
    </div>

    <div class="text-xs text-neutral-600 dark:text-neutral-400 space-y-1">
      <div>
        <strong>Valid:</strong> {{ formatDate(entry.valid_from) }}
        <span v-if="entry.valid_until"> - {{ formatDate(entry.valid_until) }}</span>
        <span v-else> - Present</span>
        ({{ entry.validity_days }} days)
      </div>
      <div v-if="entry.created_from_ip">
        <strong>From:</strong> {{ entry.created_from_ip }}
      </div>
      <div v-if="entry.user_agent" class="truncate" :title="entry.user_agent">
        <strong>Browser:</strong> {{ entry.user_agent }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download } from 'lucide-vue-next'

const props = defineProps<{
  entry: any
}>()

const emit = defineEmits<{
  'export': [entry: any]
}>()

const { locale } = useI18n()

const formatDate = (dateString: string) => {
  const date = new Date(dateString)
  return new Intl.DateTimeFormat(locale.value, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}
</script>
