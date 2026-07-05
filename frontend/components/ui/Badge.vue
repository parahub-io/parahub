<script setup lang="ts">
import { computed } from 'vue'

// `info` is an alias of `secondary` (brand blue = info); `default` is an alias of `neutral`.
// Both exist because the rest of the codebase routinely passes them to <UiBadge>.
// `offer`/`want` = market listing-direction tokens (teal/violet) — prefer <MarketListingType>
// over passing these directly, so the icon + label stay consistent site-wide.
type BadgeVariant = 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'neutral' | 'info' | 'default' | 'offer' | 'want'

interface Props {
  variant?: BadgeVariant
  type?: 'solid' | 'soft' | 'outline' | 'dot'
  size?: 'sm' | 'md' | 'lg'
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'neutral',
  type: 'soft',
  size: 'md',
})

const solidClasses: Record<BadgeVariant, string> = {
  primary: 'bg-primary text-neutral-900',
  secondary: 'bg-secondary text-white',
  success: 'bg-success text-white',
  warning: 'bg-warning text-white',
  error: 'bg-error text-white',
  neutral: 'bg-neutral-500 text-white',
  info: 'bg-secondary text-white',
  default: 'bg-neutral-500 text-white',
  offer: 'bg-offer text-white',
  want: 'bg-want text-white',
}

const softClasses: Record<BadgeVariant, string> = {
  primary: 'bg-primary-100 text-primary-800 dark:bg-primary-900 dark:text-primary-200',
  secondary: 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200',
  success: 'bg-success-100 text-success-800 dark:bg-success-900 dark:text-success-200',
  warning: 'bg-warning-100 text-warning-800 dark:bg-warning-900 dark:text-warning-200',
  error: 'bg-error-100 text-error-800 dark:bg-error-900 dark:text-error-200',
  neutral: 'bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300',
  info: 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200',
  default: 'bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300',
  offer: 'bg-offer-100 text-offer-800 dark:bg-offer-900 dark:text-offer-200',
  want: 'bg-want-100 text-want-800 dark:bg-want-900 dark:text-want-200',
}

const outlineClasses: Record<BadgeVariant, string> = {
  primary: 'border border-primary text-primary',
  secondary: 'border border-secondary text-secondary',
  success: 'border border-success text-success',
  warning: 'border border-warning text-warning',
  error: 'border border-error text-error',
  neutral: 'border border-neutral-400 text-neutral-600 dark:border-neutral-500 dark:text-neutral-400',
  info: 'border border-secondary text-secondary',
  default: 'border border-neutral-400 text-neutral-600 dark:border-neutral-500 dark:text-neutral-400',
  offer: 'border border-offer text-offer',
  want: 'border border-want text-want',
}

const dotClasses: Record<BadgeVariant, string> = {
  primary: 'bg-primary',
  secondary: 'bg-secondary',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error',
  neutral: 'bg-neutral-400',
  info: 'bg-secondary',
  default: 'bg-neutral-400',
  offer: 'bg-offer',
  want: 'bg-want',
}

const sizeClasses: Record<string, string> = {
  sm: 'text-xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-1',
  lg: 'text-sm px-2.5 py-1',
}

const dotSizeClasses: Record<string, string> = {
  sm: 'w-1.5 h-1.5',
  md: 'w-2 h-2',
  lg: 'w-2.5 h-2.5',
}

const classes = computed(() => {
  if (props.type === 'dot') {
    return ['inline-block rounded-full', dotClasses[props.variant], dotSizeClasses[props.size]]
  }

  const typeMap: Record<string, Record<string, string>> = {
    solid: solidClasses,
    soft: softClasses,
    outline: outlineClasses,
  }

  return [
    'inline-flex items-center font-medium rounded-full whitespace-nowrap',
    sizeClasses[props.size],
    typeMap[props.type]?.[props.variant],
  ]
})
</script>

<template>
  <span
    v-if="type === 'dot'"
    :class="classes"
    role="status"
    :aria-label="ariaLabel"
  />
  <span
    v-else
    :class="classes"
    :aria-label="ariaLabel"
  >
    <slot />
  </span>
</template>
