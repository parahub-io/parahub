/**
 * Accessibility composable for Parahub
 * Provides utility functions for ARIA live regions, focus management, and announcements
 */

export const useA11y = () => {
  /**
   * Announce a message to screen readers via ARIA live region
   */
  const announceToScreenReader = (message: string, urgent = false) => {
    if (process.client) {
      const regionId = urgent ? 'urgent-announcements' : 'announcements'
      const region = document.getElementById(regionId)
      if (region) {
        region.textContent = message
        // Clear after announcement to allow re-announcing same message
        setTimeout(() => {
          region.textContent = ''
        }, 1000)
      }
    }
  }

  /**
   * Focus trap utility for modals and dialogs
   */
  const trapFocus = (element: HTMLElement) => {
    if (!element) return

    const focusableElements = element.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )

    const firstElement = focusableElements[0]
    const lastElement = focusableElements[focusableElements.length - 1]

    if (!firstElement) return

    // Focus first element
    firstElement.focus()

    // Handle tab navigation
    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return

      if (e.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          lastElement.focus()
          e.preventDefault()
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          firstElement.focus()
          e.preventDefault()
        }
      }
    }

    element.addEventListener('keydown', handleTabKey)
    return () => element.removeEventListener('keydown', handleTabKey)
  }

  /**
   * Set ARIA error state for form inputs
   */
  const setAriaError = (inputRef: Ref<HTMLElement | null>, errorId: string, hasError: boolean) => {
    if (inputRef.value) {
      inputRef.value.setAttribute('aria-invalid', hasError ? 'true' : 'false')
      if (hasError) {
        inputRef.value.setAttribute('aria-describedby', errorId)
      } else {
        inputRef.value.removeAttribute('aria-describedby')
      }
    }
  }

  /**
   * Generate unique IDs for ARIA attributes
   */
  const generateId = (prefix = 'a11y') => {
    return `${prefix}-${Math.random().toString(36).substr(2, 9)}`
  }

  /**
   * Announce device status changes for IoT components
   */
  const announceDeviceStatus = (deviceName: string, status: string) => {
    // For now, use English messages (can be enhanced with i18n later)
    const message = `Device ${deviceName}: ${status}`
    announceToScreenReader(message)
  }

  /**
   * Announce location updates for tracking devices
   */
  const announceLocationUpdate = (deviceName: string) => {
    // For now, use English messages (can be enhanced with i18n later)
    const message = `Device location ${deviceName} updated`
    announceToScreenReader(message)
  }

  /**
   * Announce form submission success
   */
  const announceFormSuccess = (message: string) => {
    announceToScreenReader(message)
  }

  /**
   * Announce form errors
   */
  const announceFormError = (message: string) => {
    announceToScreenReader(message, true) // urgent
  }

  return {
    announceToScreenReader,
    trapFocus,
    setAriaError,
    generateId,
    announceDeviceStatus,
    announceLocationUpdate,
    announceFormSuccess,
    announceFormError
  }
}