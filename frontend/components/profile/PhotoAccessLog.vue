<template>
  <!-- Who opened one of the owner's private photos. Collapsed by default to keep
       the photo row compact — the same reading for the WoT and Para-ID logs. -->
  <details class="mt-3">
    <summary class="cursor-pointer select-none text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300">
      {{ title }}
    </summary>
    <p v-if="!accesses.length" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
      {{ $t('profile.photo_access.empty') }}
    </p>
    <ul v-else class="mt-1 space-y-1">
      <li
        v-for="a in visible"
        :key="`${a.viewer_id}-${a.viewed_at}`"
        class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-300"
      >
        <Eye class="w-3 h-3 flex-shrink-0 text-neutral-400" />
        <NuxtLink :to="localePath(`/@${a.viewer_hna.split('@')[0]}`)" class="text-link truncate">
          {{ a.viewer_display_name || a.viewer_hna }}
        </NuxtLink>
        <span class="text-neutral-400">{{ formatDate(a.viewed_at) }}</span>
        <span v-if="a.views > 1" class="text-neutral-400">×{{ a.views }}</span>
      </li>
    </ul>
    <button
      v-if="accesses.length > 5"
      @click="showAll = !showAll"
      class="mt-1 text-xs text-link"
    >
      {{ showAll
        ? $t('profile.photo_access.less')
        : $t('profile.photo_access.more', { count: accesses.length - 5 }) }}
    </button>
  </details>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Eye } from 'lucide-vue-next'

interface PhotoAccess {
  viewer_id: string
  viewer_hna: string
  viewer_display_name: string
  viewed_at: string   // last view of that day
  views: number       // opens by this viewer that day
}

const props = defineProps<{
  title: string
  accesses: PhotoAccess[]
}>()

const { locale } = useI18n()
const localePath = useLocalePath()

const showAll = ref(false)
const visible = computed(() => showAll.value ? props.accesses : props.accesses.slice(0, 5))

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(locale.value, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
</script>
