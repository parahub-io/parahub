<script setup lang="ts">
import { ref, watch, nextTick, type Component } from 'vue'
import { AlertTriangle, X } from 'lucide-vue-next'

interface Props {
  modelValue: boolean
  title: string
  message?: string
  icon?: Component
  variant?: 'error' | 'warning'
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'error',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
  cancel: []
}>()

function close() {
  emit('update:modelValue', false)
  emit('cancel')
}

function confirm() {
  emit('confirm')
}

const overlayRef = ref<HTMLElement | null>(null)

watch(() => props.modelValue, async (open) => {
  if (open) {
    await nextTick()
    overlayRef.value?.focus()
  }
})

const variantConfig = {
  error: {
    iconBg: 'bg-error-100 dark:bg-error-900/30',
    iconColor: 'text-error-600 dark:text-error-400',
    confirmBtn: 'btn-error',
  },
  warning: {
    iconBg: 'bg-warning-100 dark:bg-warning-900/30',
    iconColor: 'text-warning-600 dark:text-warning-400',
    confirmBtn: 'btn-warning',
  },
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]"
      @click.self="close"
      @keydown.esc="close"
      tabindex="-1"
      ref="overlayRef"
    >
      <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-300 dark:border-neutral-600 shadow-xl max-w-sm w-full mx-4 p-6">
        <!-- Icon + Close -->
        <div class="flex items-start justify-between mb-4">
          <div :class="variantConfig[variant].iconBg" class="w-10 h-10 rounded-full flex items-center justify-center">
            <component :is="icon || AlertTriangle" :class="variantConfig[variant].iconColor" class="w-5 h-5" />
          </div>
          <button
            @click="close"
            class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Title + Message -->
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ title }}</h3>
        <p v-if="message" class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">{{ message }}</p>
        <div v-else class="mb-6"><slot /></div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            @click="close"
            class="flex-1 btn-outline"
          >
            {{ cancelLabel || $t('common.cancel') || 'Cancel' }}
          </button>
          <button
            @click="confirm"
            class="flex-1"
            :class="variantConfig[variant].confirmBtn"
            :disabled="loading"
          >
            <span v-if="loading" class="inline-block animate-spin rounded-full h-4 w-4 border-2 border-white/30 border-t-white mr-2"></span>
            {{ confirmLabel || title }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
