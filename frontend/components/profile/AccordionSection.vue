<template>
  <div
    class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden"
    :data-section-id="sectionId"
  >
    <!-- Accordion Header -->
    <button
      @click="toggle"
      @keydown.enter="toggle"
      @keydown.space.prevent="toggle"
      :aria-expanded="isOpen"
      :aria-controls="`${sectionId}-content`"
      class="w-full px-6 py-4 flex items-center justify-between hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
    >
      <div class="flex items-center gap-3">
        <component :is="icon" class="w-5 h-5 text-neutral-600 dark:text-neutral-400" aria-hidden="true" />
        <h2 :id="`${sectionId}-heading`" class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {{ title }}
        </h2>
        <!-- Status Indicator -->
        <Check v-if="status?.complete" class="w-4 h-4 text-green-600 dark:text-green-400" aria-label="Completed" />
        <AlertCircle v-else-if="status?.icon === 'alert'" class="w-4 h-4 text-amber-600 dark:text-amber-400" aria-label="Action required" />
        <Minus v-else-if="status?.icon === 'minus'" class="w-4 h-4 text-neutral-400" aria-label="Optional" />
      </div>
      <ChevronDown v-if="!isOpen" class="w-5 h-5 text-neutral-600 dark:text-neutral-400" aria-hidden="true" />
      <ChevronUp v-else class="w-5 h-5 text-neutral-600 dark:text-neutral-400" aria-hidden="true" />
    </button>

    <!-- Accordion Content -->
    <div
      v-show="isOpen"
      :id="`${sectionId}-content`"
      role="region"
      :aria-labelledby="`${sectionId}-heading`"
      class="px-6 pt-4 pb-6"
      :class="{ 'transition-all duration-300': animationEnabled }"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, ChevronUp, Check, AlertCircle, Minus } from 'lucide-vue-next'

const props = defineProps<{
  sectionId: string
  title: string
  icon: any
  openSections: string[]
  status?: { complete: boolean; icon?: string }
  animationEnabled?: boolean
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
}>()

const isOpen = computed(() => props.openSections.includes(props.sectionId))

const toggle = () => {
  emit('toggle', props.sectionId)
}
</script>
