<template>
  <div v-if="loading" class="flex justify-center py-3">
    <div class="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
  <div v-else-if="activities.length" class="space-y-2">
    <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
      <Clock :size="14" />
      {{ t('map.panel.activity') }}
      <span class="text-xs font-normal text-neutral-500">({{ activities.length }})</span>
    </h3>
    <div class="space-y-1.5">
      <div
        v-for="item in activities"
        :key="item.id"
        class="flex items-start gap-2 text-xs text-neutral-600 dark:text-neutral-400"
      >
        <component :is="iconFor(item.type)" :size="12" class="mt-0.5 flex-shrink-0" />
        <div class="flex-1 min-w-0">
          <span v-if="item.type === 'photo'">{{ t('map.panel.activity_photo', { name: item.actor_name }) }}</span>
          <span v-else-if="item.type === 'comment'">{{ t('map.panel.activity_comment', { name: item.actor_name }) }}</span>
          <span v-else-if="item.type === 'ownership' && item.action === 'claim'">{{ t('map.panel.activity_claimed', { name: item.actor_name }) }}</span>
          <span v-else-if="item.type === 'ownership' && item.action === 'transfer'">{{ t('map.panel.activity_transferred', { from: item.previous_owner_name, to: item.new_owner_name }) }}</span>
        </div>
        <span class="text-neutral-400 flex-shrink-0 whitespace-nowrap">{{ formatTime(item.created_at) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Camera, MessageSquare, ShieldCheck, Clock } from 'lucide-vue-next'

const { t } = useI18n()

interface ActivityItem {
  type: 'photo' | 'comment' | 'ownership'
  id: string
  actor_name?: string
  action?: string
  new_owner_name?: string
  previous_owner_name?: string
  text?: string
  url?: string
  caption?: string
  created_at: string
}

const props = defineProps<{
  worldObjectId: string | null
}>()

const activities = ref<ActivityItem[]>([])
const loading = ref(false)

function iconFor(type: string) {
  if (type === 'photo') return Camera
  if (type === 'comment') return MessageSquare
  return ShieldCheck
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d`
  return d.toLocaleDateString()
}

async function fetchActivity(objectId: string) {
  loading.value = true
  try {
    activities.value = await $fetch(`/api/v1/geo/world-objects/${objectId}/activity/`)
  } catch {
    activities.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.worldObjectId, (newId) => {
  activities.value = []
  if (newId) fetchActivity(newId)
}, { immediate: true })
</script>
