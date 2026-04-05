<script setup lang="ts">
import { computed, useSlots, type Component } from 'vue'

interface Tab {
  id: string
  label: string
  icon?: Component
  badge?: string | number
  to?: string
}

interface Props {
  modelValue: string
  tabs: Tab[]
  variant?: 'underline' | 'pills' | 'nav'
  fullWidth?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'underline',
  fullWidth: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const slots = useSlots()
const hasPanel = computed(() => !!slots.default)

function onKeydown(e: KeyboardEvent, index: number) {
  if (props.variant === 'nav') return
  let next = index
  if (e.key === 'ArrowRight') {
    next = (index + 1) % props.tabs.length
  } else if (e.key === 'ArrowLeft') {
    next = (index - 1 + props.tabs.length) % props.tabs.length
  } else if (e.key === 'Home') {
    next = 0
  } else if (e.key === 'End') {
    next = props.tabs.length - 1
  } else {
    return
  }
  e.preventDefault()
  emit('update:modelValue', props.tabs[next].id)
  const btn = (e.currentTarget as HTMLElement)
    .parentElement
    ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]
  btn?.focus()
}

const containerClass = computed(() => {
  if (props.variant === 'pills') {
    return 'flex bg-neutral-100 dark:bg-neutral-800 rounded-lg p-1'
  }
  if (props.variant === 'nav') {
    return 'flex gap-1 overflow-x-auto'
  }
  return ['flex -mb-px gap-1 overflow-x-auto border-b border-neutral-200 dark:border-neutral-700']
})

function tabClass(tab: Tab) {
  const active = tab.id === props.modelValue
  const base = props.fullWidth ? 'flex-1' : 'flex-shrink-0'

  if (props.variant === 'nav') {
    return [
      base,
      'px-4 py-2 rounded-lg font-medium text-sm whitespace-nowrap transition-colors flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
      active
        ? 'bg-primary text-neutral-900'
        : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800',
    ]
  }

  if (props.variant === 'pills') {
    return [
      base,
      'px-3 py-2 text-sm font-medium rounded-md transition-colors flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
      active
        ? 'bg-primary text-neutral-900 shadow-sm'
        : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300',
    ]
  }

  return [
    base,
    props.fullWidth ? 'min-w-fit' : '',
    'px-3 py-2.5 border-b-2 font-medium text-sm whitespace-nowrap transition-colors flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
    active
      ? 'border-primary border-b-[3px] bg-primary/10 dark:bg-primary/10 text-neutral-900 dark:text-neutral-100 rounded-t'
      : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:border-neutral-300',
  ]
}
</script>

<template>
  <nav v-if="variant === 'nav'" :class="containerClass" aria-label="Navigation tabs">
    <NuxtLink
      v-for="tab in tabs"
      :key="tab.id"
      :to="tab.to || ''"
      :class="tabClass(tab)"
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
  <div v-else>
    <div :class="containerClass" role="tablist">
      <button
        v-for="(tab, i) in tabs"
        :key="tab.id"
        :id="`tab-${tab.id}`"
        type="button"
        role="tab"
        :aria-selected="tab.id === modelValue"
        :aria-controls="hasPanel ? `tabpanel-${tab.id}` : undefined"
        :tabindex="tab.id === modelValue ? 0 : -1"
        :class="tabClass(tab)"
        @click="emit('update:modelValue', tab.id)"
        @keydown="onKeydown($event, i)"
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
      </button>
    </div>
    <div
      v-if="hasPanel"
      :id="`tabpanel-${modelValue}`"
      role="tabpanel"
      :aria-labelledby="`tab-${modelValue}`"
      tabindex="0"
    >
      <slot />
    </div>
  </div>
</template>
