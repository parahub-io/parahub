<template>
  <div ref="triggerElement" class="relative inline-block" @mouseenter="show" @mouseleave="hide" @focus="show" @blur="hide">
    <slot></slot>
    <Teleport to="body">
      <Transition name="tooltip">
        <div
          v-if="isVisible"
          ref="tooltipRef"
          :style="tooltipStyle"
          class="absolute z-[90] px-2 py-1 text-xs font-medium text-white bg-neutral-900 dark:bg-neutral-700 rounded shadow-lg pointer-events-none whitespace-nowrap max-w-xs"
          role="tooltip"
        >
          {{ text }}
          <div class="tooltip-arrow" :style="arrowStyle"></div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

interface Props {
  text: string
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

const props = withDefaults(defineProps<Props>(), {
  position: 'top',
  delay: 300
})

const isVisible = ref(false)
const tooltipRef = ref<HTMLElement | null>(null)
const triggerElement = ref<HTMLElement | null>(null)
const triggerRect = ref<DOMRect | null>(null)
let timeoutId: ReturnType<typeof setTimeout> | null = null

const tooltipStyle = computed(() => {
  if (!triggerRect.value) return {}

  const spacing = 8
  let top = 0
  let left = 0

  switch (props.position) {
    case 'top':
      top = triggerRect.value.top - spacing
      left = triggerRect.value.left + triggerRect.value.width / 2
      return {
        top: `${top}px`,
        left: `${left}px`,
        transform: 'translate(-50%, -100%)'
      }
    case 'bottom':
      top = triggerRect.value.bottom + spacing
      left = triggerRect.value.left + triggerRect.value.width / 2
      return {
        top: `${top}px`,
        left: `${left}px`,
        transform: 'translate(-50%, 0)'
      }
    case 'left':
      top = triggerRect.value.top + triggerRect.value.height / 2
      left = triggerRect.value.left - spacing
      return {
        top: `${top}px`,
        left: `${left}px`,
        transform: 'translate(-100%, -50%)'
      }
    case 'right':
      top = triggerRect.value.top + triggerRect.value.height / 2
      left = triggerRect.value.right + spacing
      return {
        top: `${top}px`,
        left: `${left}px`,
        transform: 'translate(0, -50%)'
      }
  }
})

const arrowStyle = computed(() => {
  const arrowSize = 4
  switch (props.position) {
    case 'top':
      return {
        bottom: `${-arrowSize}px`,
        left: '50%',
        transform: 'translateX(-50%)',
        borderLeft: `${arrowSize}px solid transparent`,
        borderRight: `${arrowSize}px solid transparent`,
        borderTop: `${arrowSize}px solid var(--arrow-color)`
      }
    case 'bottom':
      return {
        top: `${-arrowSize}px`,
        left: '50%',
        transform: 'translateX(-50%)',
        borderLeft: `${arrowSize}px solid transparent`,
        borderRight: `${arrowSize}px solid transparent`,
        borderBottom: `${arrowSize}px solid var(--arrow-color)`
      }
    case 'left':
      return {
        right: `${-arrowSize}px`,
        top: '50%',
        transform: 'translateY(-50%)',
        borderTop: `${arrowSize}px solid transparent`,
        borderBottom: `${arrowSize}px solid transparent`,
        borderLeft: `${arrowSize}px solid var(--arrow-color)`
      }
    case 'right':
      return {
        left: `${-arrowSize}px`,
        top: '50%',
        transform: 'translateY(-50%)',
        borderTop: `${arrowSize}px solid transparent`,
        borderBottom: `${arrowSize}px solid transparent`,
        borderRight: `${arrowSize}px solid var(--arrow-color)`
      }
  }
})

const show = async () => {
  if (timeoutId) {
    clearTimeout(timeoutId)
  }

  timeoutId = setTimeout(async () => {
    if (!triggerElement.value) {
      return
    }
    triggerRect.value = triggerElement.value.getBoundingClientRect()
    isVisible.value = true
    await nextTick()
  }, props.delay)
}

const hide = () => {
  if (timeoutId) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
  isVisible.value = false
}
</script>

<style scoped>
.tooltip-arrow {
  position: absolute;
  width: 0;
  height: 0;
  --arrow-color: var(--color-neutral-900, var(--arrow-color));
}

:root.dark .tooltip-arrow {
  --arrow-color: var(--color-neutral-700, #404040);
}

.tooltip-enter-active,
.tooltip-leave-active {
  transition: opacity 0.15s ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
}
</style>
