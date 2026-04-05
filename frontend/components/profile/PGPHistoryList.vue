<template>
  <div v-if="show" class="border-t border-neutral-300 dark:border-neutral-600 pt-4" :class="containerClass">
    <h4 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
      Previous Keys
    </h4>

    <div v-if="loading" class="text-center py-4">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" />
    </div>

    <div v-else-if="inactiveKeys.length > 0" class="space-y-3">
      <PGPHistoryEntry
        v-for="key in inactiveKeys"
        :key="key.id"
        :entry="key"
        @export="emit('export', key)"
      />
    </div>

    <div v-else class="text-center py-4 text-neutral-500 dark:text-neutral-400 text-sm">
      No previous keys
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import PGPHistoryEntry from './PGPHistoryEntry.vue'

const props = defineProps<{
  show: boolean
  history: any[]
  loading: boolean
  containerClass?: string
}>()

const emit = defineEmits<{
  'export': [key: any]
}>()

const inactiveKeys = computed(() => {
  return props.history.filter(k => !k.is_active)
})
</script>
