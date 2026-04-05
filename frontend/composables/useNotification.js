import { ref } from 'vue'

export const useNotification = () => {
  const notifications = ref([])
  let notificationId = 0

  const showNotification = (message, type = 'info', duration = 3000) => {
    const id = ++notificationId
    const notification = {
      id,
      message,
      type,
      visible: true
    }

    notifications.value.push(notification)

    if (duration > 0) {
      setTimeout(() => {
        removeNotification(id)
      }, duration)
    }

    return id
  }

  const removeNotification = (id) => {
    const index = notifications.value.findIndex(n => n.id === id)
    if (index > -1) {
      notifications.value.splice(index, 1)
    }
  }

  const showSuccess = (message, duration = 3000) => {
    return showNotification(message, 'success', duration)
  }

  const showError = (message, duration = 5000) => {
    return showNotification(message, 'error', duration)
  }

  const showWarning = (message, duration = 4000) => {
    return showNotification(message, 'warning', duration)
  }

  const showInfo = (message, duration = 3000) => {
    return showNotification(message, 'info', duration)
  }

  return {
    notifications,
    showNotification,
    removeNotification,
    showSuccess,
    showError,
    showWarning,
    showInfo
  }
}