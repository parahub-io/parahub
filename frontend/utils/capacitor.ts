import { Capacitor } from '@capacitor/core'

/**
 * Check if running inside Capacitor native shell (Android/iOS)
 */
export const isNative = (): boolean => Capacitor.isNativePlatform()

/**
 * Get the native platform name ('android', 'ios', or 'web')
 */
export const getPlatform = (): string => Capacitor.getPlatform()

/**
 * Browser running on iOS/iPadOS. Client-only — reads `navigator`, returns false
 * on the server. iPadOS 13+ reports itself as a Mac, so any touch at all is what
 * separates it from a desktop: no Mac has a touchscreen, so macOS reports 0
 * while an iPad reports several. The usual `> 1` threshold guards against
 * touchscreen laptops, which the `Mac` check has already excluded.
 */
export const isIosWeb = (): boolean => {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes('Mac') && navigator.maxTouchPoints > 0)
}
