<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { ExternalLink } from 'lucide-vue-next'

/**
 * Unified nav button used by AppNavigation in three shapes:
 *   - size="top"    5-across top bar, icon+label column, rounded-2xl, flex-1
 *   - size="grid"   dropdown grid cell, smaller icon+label column, rounded-lg h-16
 *   - size="footer" dropdown footer pill, icon+label inline, rounded-lg px-3 py-2, resting fill
 *
 * Renders as NuxtLink for internal grid/footer items, <a> for top items and
 * externals (to match AppNavigation's existing handleNavClick preventDefault
 * flow on top-row), <button> when `action` is set (site-menu / logout).
 */
const props = withDefaults(
  defineProps<{
    to?: string
    action?: 'site-menu' | 'logout' | null
    external?: boolean
    icon: Component
    label?: string
    badge?: number | null
    size?: 'top' | 'grid' | 'footer'
    variant?: 'default' | 'sos'
    active?: boolean
    dragHovered?: boolean
    flush?: boolean
    ariaLabel?: string
    ariaExpanded?: boolean
  }>(),
  {
    size: 'top',
    variant: 'default',
    active: false,
    dragHovered: false,
    flush: false,
    badge: null,
    action: null,
  },
)

defineEmits<{
  click: [event: MouseEvent]
  touchstart: [event: TouchEvent]
}>()

const localePath = useLocalePath()

const tag = computed<'NuxtLink' | 'a' | 'button'>(() => {
  if (props.action) return 'button'
  if (props.external) return 'a'
  if (props.size === 'top') return 'a'
  return 'NuxtLink'
})

const isActiveStyle = computed(() => props.active || props.dragHovered)

const baseClass = computed(() => {
  if (props.size === 'top') {
    return 'flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]'
  }
  if (props.size === 'grid') {
    return `flex flex-col items-center justify-center group cursor-pointer py-2 aspect-[1.618] min-h-[72px] w-full ${props.flush ? '' : 'rounded-lg '}relative overflow-hidden min-w-0`
  }
  return 'flex flex-1 items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors'
})

const stateClass = computed(() => {
  if (isActiveStyle.value) {
    return 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
  }
  if (props.variant === 'sos') {
    // soft-red resting fill, full red on hover; flush bento tiles need an
    // opaque dark fill so the 1px gap hairlines around the tile keep reading
    const sosBg = props.flush && props.size === 'grid' ? 'bg-error-50 dark:bg-error-900' : 'bg-error-50 dark:bg-error-900/20'
    return `${sosBg} text-error hover:bg-error hover:text-white`
  }
  const baseColor = props.size === 'footer' ? 'text-neutral-600' : 'text-neutral-700'
  // footer pills carry a resting neutral fill so they read as buttons on the panel
  const footerBg = props.size === 'footer' ? 'bg-neutral-200 dark:bg-neutral-700 ' : ''
  // flush grid tiles (bento) sit on an opaque panel fill so the 1px gap hairlines read
  const flushBg = props.flush && props.size === 'grid' ? 'bg-neutral-100 dark:bg-neutral-800 ' : ''
  return `${footerBg}${flushBg}${baseColor} dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40`
})

const iconClass = computed(() => {
  if (props.size === 'top') return 'w-6 h-6 md:w-8 md:h-8 mb-0 sm:mb-1'
  if (props.size === 'grid') return 'w-8 h-8 sm:w-10 sm:h-10 mb-1'
  return 'w-3.5 h-3.5'
})

const labelClass = computed(() => {
  if (props.size === 'top') return 'hidden sm:block text-xs font-medium'
  if (props.size === 'grid') return 'block text-xs font-medium text-center max-w-full truncate px-0.5'
  // footer pills: icon-only on phones, icon+label from sm up (keeps ≤5 pills fitting narrow widths)
  return 'hidden sm:inline'
})

const internalHref = computed(() => (props.to ? localePath(props.to) : undefined))
</script>

<template>
  <NuxtLink
    v-if="tag === 'NuxtLink'"
    :to="internalHref!"
    :aria-label="ariaLabel || label"
    data-nav-button
    :data-nav-path="to || null"
    :class="[baseClass, stateClass]"
    @click="$emit('click', $event)"
    @touchstart="$emit('touchstart', $event)"
  >
    <div v-if="badge != null && badge > 0" class="relative">
      <component :is="icon" :class="iconClass" />
      <div class="absolute -top-1 -right-1 min-w-[16px] h-[16px] bg-error text-white text-[10px] font-bold rounded-full flex items-center justify-center px-0.5 ring-2 ring-neutral-100 dark:ring-neutral-800">
        {{ badge > 99 ? '99+' : badge }}
      </div>
    </div>
    <component v-else :is="icon" :class="iconClass" />
    <ExternalLink v-if="external && size === 'grid'" class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
    <span v-if="label" :class="labelClass">{{ label }}</span>
  </NuxtLink>

  <a
    v-else-if="tag === 'a'"
    :href="external ? to : internalHref"
    :target="external ? '_blank' : undefined"
    :rel="external ? 'noopener noreferrer' : undefined"
    :aria-label="ariaLabel || label"
    data-nav-button
    :data-nav-path="to || null"
    :class="[baseClass, stateClass]"
    @click="$emit('click', $event)"
    @touchstart="$emit('touchstart', $event)"
  >
    <div v-if="badge != null && badge > 0" class="relative">
      <component :is="icon" :class="iconClass" />
      <div class="absolute -top-1 -right-1 min-w-[18px] h-[18px] bg-error text-white text-xs font-bold rounded-full flex items-center justify-center px-1 ring-2 ring-neutral-100 dark:ring-neutral-800">
        {{ badge > 99 ? '99+' : badge }}
      </div>
    </div>
    <component v-else :is="icon" :class="iconClass" />
    <ExternalLink v-if="external && size === 'grid'" class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
    <span v-if="label" :class="labelClass">{{ label }}</span>
  </a>

  <button
    v-else
    type="button"
    :aria-label="ariaLabel || label"
    :aria-expanded="ariaExpanded"
    data-nav-button
    :data-nav-action="action"
    :class="[baseClass, stateClass]"
    @click="$emit('click', $event)"
    @touchstart="$emit('touchstart', $event)"
  >
    <component :is="icon" :class="iconClass" />
    <span v-if="label" :class="labelClass">{{ label }}</span>
    <slot />
  </button>
</template>
