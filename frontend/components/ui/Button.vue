<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Loader2 } from 'lucide-vue-next'

interface Props {
  variant?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'outline' | 'outline-success' | 'outline-warning' | 'outline-error' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  icon?: Component
  iconOnly?: boolean
  loading?: boolean
  disabled?: boolean
  tag?: 'button' | 'a'
  to?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  iconOnly: false,
  loading: false,
  disabled: false,
  tag: 'button',
})

defineOptions({ inheritAttrs: false })

const classes = computed(() => {
  const base = `btn-${props.variant}`
  const parts = [base]

  if (props.iconOnly) {
    parts.push('btn-icon')
  }

  if (props.size !== 'md') {
    parts.push(`btn-${props.size}`)
  }

  return parts
})

const iconSizeClass = computed(() => {
  const sizes: Record<string, string> = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
  }
  return sizes[props.size]
})

const resolvedTag = computed(() => {
  if (props.to) return resolveComponent('NuxtLink')
  return props.tag
})

const isDisabled = computed(() => props.disabled || props.loading)
const isLink = computed(() => !!props.to || props.tag === 'a')
</script>

<template>
  <component
    :is="resolvedTag"
    :class="classes"
    :disabled="isDisabled || undefined"
    :aria-disabled="isLink && isDisabled ? 'true' : undefined"
    :aria-busy="loading || undefined"
    :to="to || undefined"
    v-bind="$attrs"
  >
    <Loader2
      v-if="loading"
      :class="[iconSizeClass, 'animate-spin', 'shrink-0']"
      :aria-hidden="true"
    />
    <span v-if="loading && iconOnly" class="sr-only">Loading</span>
    <component
      v-else-if="icon"
      :is="icon"
      :class="[iconSizeClass, 'shrink-0']"
      :aria-hidden="true"
    />
    <slot v-if="!iconOnly" />
  </component>
</template>
