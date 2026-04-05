<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="fixed inset-0 z-50 overflow-y-auto">
        <!-- Backdrop -->
        <div
          @click="handleBackdropClick"
          class="fixed inset-0 bg-neutral-900 bg-opacity-75 transition-opacity"
          :class="backdropClass"
        ></div>

        <!-- Modal container -->
        <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
          <!-- Modal content -->
          <div
            ref="modalRef"
            class="relative inline-block w-full px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl transition-all sm:my-8 sm:align-middle sm:p-6"
            :class="sizeClass"
            role="dialog"
            aria-modal="true"
            :aria-labelledby="titleId"
          >
            <!-- Header -->
            <div class="flex items-start justify-between mb-4">
              <h3
                v-if="$slots.title || title"
                :id="titleId"
                class="text-lg font-medium text-neutral-900 dark:text-neutral-100 flex items-center gap-2"
              >
                <component v-if="icon" :is="icon" class="w-5 h-5" :class="iconClass" />
                <slot name="title">{{ title }}</slot>
              </h3>
              <button
                v-if="showClose"
                @click="close"
                class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
                :aria-label="closeAriaLabel"
              >
                <X class="w-5 h-5" />
              </button>
            </div>

            <!-- Body -->
            <div class="modal-body">
              <slot></slot>
            </div>

            <!-- Footer -->
            <div v-if="$slots.footer" class="mt-4 flex justify-end gap-3">
              <slot name="footer"></slot>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { onMounted, onUnmounted, ref, watch, computed } from 'vue'

interface Props {
  modelValue: boolean
  title?: string
  icon?: any
  iconClass?: string
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full'
  showClose?: boolean
  closeOnBackdrop?: boolean
  closeAriaLabel?: string
  backdropClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  showClose: true,
  closeOnBackdrop: true,
  closeAriaLabel: 'Close modal',
  backdropClass: ''
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()

const modalRef = ref<HTMLElement | null>(null)
const titleId = computed(() => `modal-title-${Math.random().toString(36).substr(2, 9)}`)

const sizeClass = computed(() => {
  const sizes = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-4xl',
    'full': 'max-w-6xl'
  }
  return sizes[props.size]
})

const close = () => {
  emit('update:modelValue', false)
  emit('close')
}

const handleBackdropClick = () => {
  if (props.closeOnBackdrop) {
    close()
  }
}

// Focus trap
const trapFocus = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && props.showClose) {
    close()
  }

  if (e.key === 'Tab' && modalRef.value) {
    const focusableElements = modalRef.value.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    const firstElement = focusableElements[0] as HTMLElement
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement

    if (e.shiftKey && document.activeElement === firstElement) {
      lastElement?.focus()
      e.preventDefault()
    } else if (!e.shiftKey && document.activeElement === lastElement) {
      firstElement?.focus()
      e.preventDefault()
    }
  }
}

// Prevent body scroll when modal is open
watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', trapFocus)

    // Focus first focusable element
    setTimeout(() => {
      const firstFocusable = modalRef.value?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      firstFocusable?.focus()
    }, 100)
  } else {
    document.body.style.overflow = ''
    document.removeEventListener('keydown', trapFocus)
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', trapFocus)
})
</script>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
