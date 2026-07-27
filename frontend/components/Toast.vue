<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-[100] space-y-2 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto flex items-start gap-3 max-w-sm px-4 py-3 rounded-lg shadow-lg border"
          :class="toastClasses(toast.type)"
          role="alert"
          :aria-live="toast.type === 'error' ? 'assertive' : 'polite'"
        >
          <component :is="getIcon(toast.type)" class="w-5 h-5 flex-shrink-0 mt-0.5" :class="iconClasses(toast.type)" />
          <div class="flex-1 min-w-0">
            <p v-if="toast.title" class="font-semibold text-sm mb-1" :class="titleClasses(toast.type)">
              {{ toast.title }}
            </p>
            <p class="text-sm" :class="messageClasses(toast.type)">
              {{ toast.message }}
            </p>
          </div>
          <button
            @click="removeToast(toast.id)"
            class="flex-shrink-0 hover:opacity-70 transition-opacity"
            :class="closeClasses(toast.type)"
            aria-label="Close notification"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'
import { storeToRefs } from 'pinia'

const toastStore = useToastStore()
const { toasts } = storeToRefs(toastStore)

const getIcon = (type: string) => {
  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertTriangle,
    info: Info
  }
  return icons[type as keyof typeof icons] || Info
}

const toastClasses = (type: string) => {
  const classes = {
    success: 'bg-success-50 dark:bg-success-900 border-success-300 dark:border-success-700',
    error: 'bg-error-50 dark:bg-error-900 border-error-300 dark:border-error-700',
    warning: 'bg-warning-50 dark:bg-warning-900 border-warning-300 dark:border-warning-700',
    info: 'bg-secondary-50 dark:bg-secondary-900 border-secondary-300 dark:border-secondary-700'
  }
  return classes[type as keyof typeof classes] || classes.info
}

const iconClasses = (type: string) => {
  const classes = {
    success: 'text-success-600 dark:text-success-400',
    error: 'text-error-600 dark:text-error-400',
    warning: 'text-warning-600 dark:text-warning-400',
    info: 'text-secondary dark:text-secondary-400'
  }
  return classes[type as keyof typeof classes] || classes.info
}

const titleClasses = (type: string) => {
  const classes = {
    success: 'text-success-900 dark:text-success-100',
    error: 'text-error-900 dark:text-error-100',
    warning: 'text-warning-900 dark:text-warning-100',
    info: 'text-secondary-900 dark:text-secondary-100'
  }
  return classes[type as keyof typeof classes] || classes.info
}

const messageClasses = (type: string) => {
  const classes = {
    success: 'text-success-800 dark:text-success-200',
    error: 'text-error-800 dark:text-error-200',
    warning: 'text-warning-800 dark:text-warning-200',
    info: 'text-secondary-800 dark:text-secondary-200'
  }
  return classes[type as keyof typeof classes] || classes.info
}

const closeClasses = (type: string) => {
  const classes = {
    success: 'text-success-600 dark:text-success-400',
    error: 'text-error-600 dark:text-error-400',
    warning: 'text-warning-600 dark:text-warning-400',
    info: 'text-secondary dark:text-secondary-400'
  }
  return classes[type as keyof typeof classes] || classes.info
}

const removeToast = (id: string) => {
  toastStore.removeToast(id)
}
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.8);
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>
