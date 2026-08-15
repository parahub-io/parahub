import { storeToRefs } from 'pinia'
import { useToastStore } from '~/stores/toast'

/**
 * Legacy toast API, kept for the components that still call it.
 *
 * It used to hold its own `ref([])` of notifications — a fresh, private list on
 * every call — while the only renderer (`<Toast/>` in app.vue) reads the Pinia
 * toast store. Every showSuccess/showError was therefore dropped on the floor,
 * which turned failed actions into "the button does nothing". Delegate instead.
 */
export const useNotification = () => {
  const toastStore = useToastStore()
  const { toasts } = storeToRefs(toastStore)

  const showNotification = (message, type = 'info', duration = 3000) =>
    toastStore.addToast({ type, message, duration })

  return {
    notifications: toasts,
    showNotification,
    removeNotification: (id) => toastStore.removeToast(id),
    showSuccess: (message, duration = 3000) => showNotification(message, 'success', duration),
    showError: (message, duration = 5000) => showNotification(message, 'error', duration),
    showWarning: (message, duration = 4000) => showNotification(message, 'warning', duration),
    showInfo: (message, duration = 3000) => showNotification(message, 'info', duration),
  }
}
