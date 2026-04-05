/**
 * Seed phrase composable for Parahub
 *
 * Manages BIP39 mnemonic generation and storage.
 * The seed phrase is used to derive all cryptographic keys (Bitcoin, PGP).
 *
 * Note: Seed is stored unencrypted in localStorage for simplicity.
 * Security relies on device-level protection.
 */

import { ref, computed } from 'vue'

// Storage keys
const STORAGE_KEY_SEED = 'parahub_seed'
const STORAGE_KEY_SEED_VERSION = 'parahub_seed_version'
const CURRENT_VERSION = 2  // Bumped version for unencrypted storage

export const useSeed = () => {
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Generate a new 12-word BIP39 mnemonic
   */
  const generateMnemonic = async (): Promise<string[]> => {
    if (!process.client) {
      throw new Error('Seed generation can only be done on client side')
    }

    const bip39 = await import('bip39')
    const mnemonic = bip39.generateMnemonic(128) // 128 bits = 12 words
    return mnemonic.split(' ')
  }

  /**
   * Validate a mnemonic phrase
   */
  const validateMnemonic = async (words: string[]): Promise<boolean> => {
    if (!process.client) return false

    try {
      const bip39 = await import('bip39')
      const mnemonic = words.join(' ')
      return bip39.validateMnemonic(mnemonic)
    } catch {
      return false
    }
  }

  /**
   * Convert mnemonic to seed bytes (512-bit)
   */
  const mnemonicToSeed = async (words: string[], passphrase: string = ''): Promise<Uint8Array> => {
    if (!process.client) {
      throw new Error('Seed derivation can only be done on client side')
    }

    const bip39 = await import('bip39')
    const mnemonic = words.join(' ')
    const seedBuffer = await bip39.mnemonicToSeed(mnemonic, passphrase)
    return new Uint8Array(seedBuffer)
  }

  /**
   * Save seed words to localStorage (unencrypted)
   */
  const saveSeed = (words: string[]): void => {
    if (!process.client) return
    const data = {
      version: CURRENT_VERSION,
      words: words
    }
    localStorage.setItem(STORAGE_KEY_SEED, JSON.stringify(data))
    localStorage.setItem(STORAGE_KEY_SEED_VERSION, CURRENT_VERSION.toString())
  }

  /**
   * Load seed words from localStorage
   */
  const loadSeed = (): string[] | null => {
    if (!process.client) return null

    const stored = localStorage.getItem(STORAGE_KEY_SEED)
    if (!stored) return null

    try {
      const data = JSON.parse(stored)

      // Handle v2 format (unencrypted)
      if (data.version === 2 && Array.isArray(data.words)) {
        return data.words
      }

      // Handle legacy v1 format (encrypted) - cannot decrypt without PIN
      // User needs to restore from seed phrase
      if (data.version === 1) {
        console.warn('Legacy encrypted seed found. Please restore from seed phrase.')
        return null
      }

      return null
    } catch {
      return null
    }
  }

  /**
   * Check if seed exists in localStorage
   */
  const hasSeed = (): boolean => {
    if (!process.client) return false
    return loadSeed() !== null
  }

  /**
   * Clear seed from localStorage
   */
  const clearSeed = (): void => {
    if (!process.client) return
    localStorage.removeItem(STORAGE_KEY_SEED)
    localStorage.removeItem(STORAGE_KEY_SEED_VERSION)
    // Also clear legacy key
    localStorage.removeItem('parahub_encrypted_seed')
  }

  /**
   * Get BIP39 wordlist for autocomplete
   */
  const getWordlist = async (): Promise<string[]> => {
    if (!process.client) return []
    const bip39 = await import('bip39')
    // @ts-ignore - wordlists is exported
    return bip39.wordlists?.english || []
  }

  /**
   * Derive HD key from seed at given path
   * Returns { privateKey, publicKey, chainCode }
   */
  const derivePath = async (words: string[], path: string): Promise<{
    privateKey: Uint8Array
    publicKey: Uint8Array
    chainCode: Uint8Array
  }> => {
    if (!process.client) {
      throw new Error('Key derivation can only be done on client side')
    }

    const { HDKey } = await import('@scure/bip32')
    const seed = await mnemonicToSeed(words)
    const master = HDKey.fromMasterSeed(seed)
    const derived = master.derive(path)

    if (!derived.privateKey || !derived.publicKey) {
      throw new Error('Failed to derive key at path: ' + path)
    }

    return {
      privateKey: derived.privateKey,
      publicKey: derived.publicKey,
      chainCode: derived.chainCode!
    }
  }

  /**
   * Generate random indices for seed verification
   * Returns 3 random word indices (0-11)
   */
  const getVerificationIndices = (): number[] => {
    const indices: number[] = []
    while (indices.length < 3) {
      const idx = Math.floor(Math.random() * 12)
      if (!indices.includes(idx)) {
        indices.push(idx)
      }
    }
    return indices.sort((a, b) => a - b)
  }

  /**
   * Zero-fill array for security (clear sensitive data from memory)
   */
  const zeroFill = (arr: Uint8Array): void => {
    for (let i = 0; i < arr.length; i++) {
      arr[i] = 0
    }
  }

  return {
    loading,
    error,
    generateMnemonic,
    validateMnemonic,
    mnemonicToSeed,
    saveSeed,
    loadSeed,
    hasSeed,
    clearSeed,
    getWordlist,
    derivePath,
    getVerificationIndices,
    zeroFill
  }
}
