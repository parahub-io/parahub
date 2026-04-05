<template>
  <div :class="['space-y-1', levelIndent]">
    <template v-for="category in categories" :key="category.id">
      <div class="flex items-center gap-1">
        <!-- Expand/collapse button for categories with children -->
        <button
          v-if="category.children && category.children.length"
          type="button"
          @click.stop="$emit('toggle-expand', category.id)"
          class="flex-shrink-0 p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded"
        >
          <ChevronRight :class="[levelStyles.chevron, 'text-neutral-600 dark:text-neutral-300 transition-transform', { 'rotate-90': expandedSubcategories[category.id] }]" />
        </button>
        <!-- Spacer for categories without children -->
        <div v-else :class="['flex-shrink-0', levelStyles.spacer]"></div>

        <!-- Category button -->
        <button
          type="button"
          @click="$emit('select', category)"
          :class="[
            'flex-1 text-left px-3 rounded flex items-center justify-between',
            levelStyles.button,
            { 'bg-primary bg-opacity-20 font-medium': selectedId === category.id },
            // Visual hints: in 'create' mode, parent categories are disabled (grayed out)
            (mode === 'create' && category.children && category.children.length > 0)
              ? 'text-neutral-400 dark:text-neutral-600 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-700'
              : 'hover:bg-primary hover:bg-opacity-10'
          ]"
        >
          <span class="text-neutral-900 dark:text-neutral-100">{{ category.icon }} {{ category.name }}</span>
          <Check v-if="selectedId === category.id" :class="levelStyles.check" class="text-primary" />
        </button>
      </div>

      <!-- Recursive: render children if expanded -->
      <CategoryTreeLevel
        v-if="expandedSubcategories[category.id] && category.children && category.children.length"
        :categories="category.children"
        :selected-id="selectedId"
        :level="level + 1"
        :mode="mode"
        :expanded-subcategories="expandedSubcategories"
        @select="$emit('select', $event)"
        @toggle-expand="$emit('toggle-expand', $event)"
      />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  categories: {
    type: Array,
    required: true
  },
  selectedId: {
    type: [String, null],
    default: null
  },
  level: {
    type: Number,
    default: 1
  },
  expandedSubcategories: {
    type: Object,
    default: () => ({})
  },
  mode: {
    type: String,
    default: 'filter',
    validator: (value) => ['filter', 'create'].includes(value)
  }
})

defineEmits(['select', 'toggle-expand'])

// Adjust styles based on nesting level
const levelIndent = computed(() => {
  const indents = {
    1: 'ml-6',
    2: 'ml-4',
    3: 'ml-3',
    4: 'ml-2',
    5: 'ml-1'
  }
  return indents[Math.min(props.level, 5)] || 'ml-1'
})

const levelStyles = computed(() => {
  if (props.level === 1) {
    return {
      button: 'py-1.5 text-sm',
      check: 'w-4 h-4',
      chevron: 'w-4 h-4',
      spacer: 'w-6'
    }
  } else if (props.level === 2) {
    return {
      button: 'py-1 text-xs',
      check: 'w-3 h-3',
      chevron: 'w-3 h-3',
      spacer: 'w-5'
    }
  } else {
    // Level 3+: even smaller
    return {
      button: 'py-0.5 text-xs',
      check: 'w-3 h-3',
      chevron: 'w-3 h-3',
      spacer: 'w-4'
    }
  }
})
</script>
