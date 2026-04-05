<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Info, CheckCircle, AlertTriangle, XCircle, X } from 'lucide-vue-next'

interface Props {
  variant?: 'info' | 'success' | 'warning' | 'error'
  icon?: Component | null
  title?: string
  dismissible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'info',
  dismissible: false,
})

const emit = defineEmits<{ dismiss: [] }>()

const showIcon = computed(() => props.icon !== null)

const variantClasses: Record<string, { bg: string; border: string; icon: string; title: string; text: string }> = {
  info: {
    bg: 'bg-secondary-50 dark:bg-secondary-900/20',
    border: 'border-secondary-200 dark:border-secondary-800',
    icon: 'text-secondary',
    title: 'text-secondary-800 dark:text-secondary-200',
    text: 'text-secondary-700 dark:text-secondary-300',
  },
  success: {
    bg: 'bg-success-50 dark:bg-success-900/20',
    border: 'border-success-200 dark:border-success-800',
    icon: 'text-success',
    title: 'text-success-800 dark:text-success-200',
    text: 'text-success-700 dark:text-success-300',
  },
  warning: {
    bg: 'bg-warning-50 dark:bg-warning-900/20',
    border: 'border-warning-200 dark:border-warning-800',
    icon: 'text-warning',
    title: 'text-warning-800 dark:text-warning-200',
    text: 'text-warning-700 dark:text-warning-300',
  },
  error: {
    bg: 'bg-error-50 dark:bg-error-900/20',
    border: 'border-error-200 dark:border-error-800',
    icon: 'text-error',
    title: 'text-error-800 dark:text-error-200',
    text: 'text-error-700 dark:text-error-300',
  },
}

const v = computed(() => variantClasses[props.variant])
</script>

<template>
  <div
    :class="[v.bg, v.border, v.text]"
    class="flex items-start gap-3 p-4 rounded-lg border"
    role="alert"
  >
    <template v-if="showIcon">
      <component v-if="icon" :is="icon" :class="v.icon" class="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <Info v-else-if="variant === 'info'" :class="v.icon" class="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <CheckCircle v-else-if="variant === 'success'" :class="v.icon" class="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <AlertTriangle v-else-if="variant === 'warning'" :class="v.icon" class="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <XCircle v-else :class="v.icon" class="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
    </template>
    <div class="flex-1 min-w-0">
      <p v-if="title" :class="v.title" class="text-sm font-medium">{{ title }}</p>
      <div class="text-sm"><slot /></div>
    </div>
    <button
      v-if="dismissible"
      class="flex-shrink-0 p-1 rounded-lg opacity-60 hover:opacity-100 transition-opacity"
      :class="v.text"
      aria-label="Dismiss"
      @click="emit('dismiss')"
    >
      <X class="w-4 h-4" />
    </button>
  </div>
</template>
