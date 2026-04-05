import { Capacitor } from '@capacitor/core'

/**
 * Check if running inside Capacitor native shell (Android/iOS)
 */
export const isNative = (): boolean => Capacitor.isNativePlatform()

/**
 * Get the native platform name ('android', 'ios', or 'web')
 */
export const getPlatform = (): string => Capacitor.getPlatform()
