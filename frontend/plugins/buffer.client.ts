/**
 * Buffer polyfill for browser environment
 * Required by bip39, bitcoinjs-lib and other Node.js crypto libraries
 */
import { Buffer } from 'buffer'

// Make Buffer available globally
globalThis.Buffer = Buffer

export default defineNuxtPlugin(() => {
  // Buffer is now available globally
})
