<script setup lang="ts">
import { computed, type Component } from 'vue'

interface RouteTab {
  label: string
  to: string
  icon?: Component
  badge?: string | number
}

interface Props {
  tabs: RouteTab[]
  fullWidth?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  fullWidth: false,
})

const route = useRoute()

function norm(p: string): string {
  const stripped = p.replace(/\/+$/, '')
  return stripped === '' ? '/' : stripped
}

// Active = the tab whose `to` is the longest prefix of the current path.
// Lets an index route (/condo/x) and its children (/condo/x/quotas) coexist:
// the child wins on /condo/x/quotas, the index wins on /condo/x.
const activeTo = computed(() => {
  const path = norm(route.path)
  let best: string | null = null
  let bestLen = -1
  for (const tab of props.tabs) {
    const to = norm(tab.to)
    if (path === to || path.startsWith(to + '/')) {
      if (to.length > bestLen) {
        best = tab.to
        bestLen = to.length
      }
    }
  }
  return best
})

function isActive(tab: RouteTab): boolean {
  return activeTo.value !== null && norm(tab.to) === norm(activeTo.value)
}

function tabClass(tab: RouteTab) {
  return [
    props.fullWidth ? 'flex-1' : 'flex-shrink-0',
    'px-4 py-2 rounded-lg font-medium text-sm whitespace-nowrap transition-colors flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
    isActive(tab)
      ? 'bg-primary text-neutral-900'
      : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800',
  ]
}
</script>

<template>
  <nav class="flex gap-1 overflow-x-auto" aria-label="Navigation tabs">
    <NuxtLink
      v-for="tab in tabs"
      :key="tab.to"
      :to="tab.to"
      :class="tabClass(tab)"
      :aria-current="isActive(tab) ? 'page' : undefined"
    >
      <component
        v-if="tab.icon"
        :is="tab.icon"
        class="w-4 h-4"
        :aria-hidden="true"
      />
      {{ tab.label }}
      <UiBadge
        v-if="tab.badge !== undefined"
        variant="primary"
        type="solid"
        size="sm"
      >
        {{ tab.badge }}
      </UiBadge>
    </NuxtLink>
  </nav>
</template>
