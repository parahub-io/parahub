import { defineStore } from 'pinia'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title?: string
  message: string
  duration?: number
}

interface ToastState {
  toasts: Toast[]
}

export const useToastStore = defineStore('toast', {
  state: (): ToastState => ({
    toasts: []
  }),

  actions: {
    addToast(toast: Omit<Toast, 'id'>) {
      const id = Math.random().toString(36).substring(2, 9)
      const duration = toast.duration ?? 5000

      this.toasts.push({
        id,
        ...toast
      })

      // Auto-remove after duration
      if (duration > 0) {
        setTimeout(() => {
          this.removeToast(id)
        }, duration)
      }

      return id
    },

    removeToast(id: string) {
      const index = this.toasts.findIndex(t => t.id === id)
      if (index !== -1) {
        this.toasts.splice(index, 1)
      }
    },

    success(message: string, title?: string, duration?: number) {
      return this.addToast({ type: 'success', message, title, duration })
    },

    error(message: string, title?: string, duration?: number) {
      return this.addToast({ type: 'error', message, title, duration })
    },

    warning(message: string, title?: string, duration?: number) {
      return this.addToast({ type: 'warning', message, title, duration })
    },

    info(message: string, title?: string, duration?: number) {
      return this.addToast({ type: 'info', message, title, duration })
    },

    clearAll() {
      this.toasts = []
    }
  }
})
