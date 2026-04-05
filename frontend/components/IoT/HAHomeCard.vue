<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 transition-shadow hover:shadow-md">
    <!-- Header -->
    <div class="flex justify-between items-start mb-3">
      <div class="flex-1 min-w-0">
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ home.name }}</h3>
        <p v-if="home.location_name" class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ home.location_name }}</p>
      </div>

      <!-- Status dot + version -->
      <div class="flex items-center gap-2 shrink-0 ml-2">
        <span v-if="home.ha_version" class="text-xs text-neutral-400">{{ home.ha_version }}</span>
        <span class="w-2.5 h-2.5 rounded-full" :class="statusColor" :title="home.status" />
      </div>
    </div>

    <!-- Stats row -->
    <div class="flex items-center gap-4 text-sm text-neutral-600 dark:text-neutral-400 mb-3">
      <div class="flex items-center gap-1">
        <Cpu class="w-4 h-4" />
        <span>{{ home.entity_count }} {{ $t('ha.entities') }}</span>
      </div>
      <div v-if="home.last_seen" class="flex items-center gap-1">
        <Clock class="w-4 h-4" />
        <span>{{ timeAgo(home.last_seen) }}</span>
      </div>
    </div>

    <!-- Error banner -->
    <UiAlert v-if="home.status === 'error' && home.last_error" variant="error" class="mb-3">{{ home.last_error }}</UiAlert>

    <!-- Actions -->
    <div class="flex items-center gap-2 flex-wrap">
      <button @click="$emit('discover', home)" class="btn-primary btn-sm gap-1">
        <Search class="w-3.5 h-3.5" />
        {{ $t('ha.discover') }}
      </button>
      <button @click="$emit('sync', home)" class="btn-outline btn-sm gap-1" :disabled="syncing">
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': syncing }" />
        {{ $t('ha.sync') }}
      </button>
      <button @click="$emit('test', home)" class="btn-outline btn-sm gap-1">
        <Zap class="w-3.5 h-3.5" />
        {{ $t('ha.test') }}
      </button>

      <!-- Dropdown -->
      <div class="relative ml-auto" ref="menuRef">
        <button @click="menuOpen = !menuOpen" class="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500 transition-colors">
          <MoreVertical class="w-4 h-4" />
        </button>
        <div v-if="menuOpen" class="absolute right-0 mt-1 w-36 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg z-10 py-1">
          <button @click="menuOpen = false; $emit('edit', home)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-300">
            {{ $t('ha.edit') }}
          </button>
          <button @click="menuOpen = false; $emit('delete', home)" class="w-full text-left px-3 py-1.5 text-sm hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400">
            {{ $t('ha.delete_home') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Cpu, Clock, Search, RefreshCw, Zap, MoreVertical } from 'lucide-vue-next'
import type { HAHome } from '~/stores/ha'

const props = defineProps<{
  home: HAHome
  syncing?: boolean
}>()

defineEmits<{
  discover: [home: HAHome]
  sync: [home: HAHome]
  test: [home: HAHome]
  edit: [home: HAHome]
  delete: [home: HAHome]
}>()

const menuOpen = ref(false)
const menuRef = ref<HTMLElement>()

const statusColor = computed(() => ({
  'bg-green-500': props.home.status === 'online',
  'bg-neutral-400': props.home.status === 'offline',
  'bg-red-500': props.home.status === 'error',
}))

function timeAgo(dt: string) {
  const diff = (Date.now() - new Date(dt).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// Close menu on outside click
if (import.meta.client) {
  const handler = (e: MouseEvent) => {
    if (menuRef.value && !menuRef.value.contains(e.target as Node)) menuOpen.value = false
  }
  onMounted(() => document.addEventListener('click', handler))
  onUnmounted(() => document.removeEventListener('click', handler))
}
</script>
