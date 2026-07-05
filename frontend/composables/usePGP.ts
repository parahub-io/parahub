/**
 * PGP composable for Parahub
 *
 * Uses OpenPGP.js for client-side cryptographic operations.
 * Keys are Ed25519 (ECC) for better security and smaller size.
 *
 * PGP keys are DETERMINISTICALLY derived from BIP39 seed phrase,
 * allowing full recovery from the 12-word mnemonic.
 */

import { ref, computed } from 'vue'

// Dynamic import helper for OpenPGP (client-side only)
const getOpenPGP = async () => {
  if (!process.client) {
    throw new Error('OpenPGP can only be used on the client side')
  }
  return await import('openpgp')
}

// PGP key derivation path (for deterministic generation from seed)
// Uses unique path that doesn't conflict with BIP44/84
const PGP_DERIVATION_PATH = "m/19910605'/0'/0'"

// Fixed creation date for seed-derived keys. An OpenPGP v4 fingerprint is a hash
// over the key material AND its creation timestamp, so a moving date would make
// "recovery from seed" produce a different fingerprint on every regeneration.
// Pinning the date keeps "same seed → same key". Value is arbitrary but MUST NOT
// change, or previously-derived keys would no longer reproduce.
const PGP_KEY_CREATION_DATE = new Date('2020-01-01T00:00:00Z')

interface PGPKeyPair {
  publicKey: string
  privateKey: string
  fingerprint: string
}

interface PGPSignatureHeaders {
  'X-PGP-Signature': string
  'X-PGP-Timestamp': string
  'X-PGP-Nonce': string
}

const STORAGE_KEY = 'parahub_pgp_keys'

export const usePGP = () => {
  const keyPair = ref<PGPKeyPair | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Check if keys exist in localStorage
  const hasKeys = computed(() => !!keyPair.value)

  /**
   * Load existing keys from localStorage
   */
  const loadKeys = async () => {
    // Only run on client-side
    if (!process.client) {
      return false
    }

    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        keyPair.value = JSON.parse(stored)
        return true
      }
      return false
    } catch (e) {
      console.error('Failed to load PGP keys:', e)
      error.value = 'Failed to load stored keys'
      return false
    }
  }

  /**
   * Generate new PGP key pair (Ed25519 ECC)
   *
   * Uses Ed25519 curve for signing (more secure, smaller keys than RSA).
   * Compatible with GnuPG 2.1+ on server side.
   */
  const generateKeys = async (name: string, email: string, passphrase?: string) => {
    loading.value = true
    error.value = null

    try {
      const openpgp = await getOpenPGP()

      const { privateKey, publicKey } = await openpgp.generateKey({
        type: 'ecc',
        curve: 'curve25519',  // Ed25519 for signing, Curve25519 for encryption
        userIDs: [{ name, email }],
        passphrase: passphrase || undefined,
        format: 'armored'
      })

      // Get fingerprint
      const publicKeyObj = await openpgp.readKey({ armoredKey: publicKey })
      const fingerprint = publicKeyObj.getFingerprint()

      keyPair.value = {
        publicKey,
        privateKey,
        fingerprint
      }

      // Store in localStorage (client-side only)
      if (process.client) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(keyPair.value))
      }

      return keyPair.value
    } catch (e: any) {
      console.error('Failed to generate PGP keys:', e)
      error.value = e.message || 'Failed to generate keys'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * Generate PGP keys deterministically from seed phrase
   *
   * This creates reproducible keys from the same mnemonic, allowing
   * users to regenerate their PGP identity when restoring from seed.
   *
   * Determinism is achieved by:
   * 1. Deriving key material from BIP39 seed at path m/19910605'/0'/0'
   * 2. Expanding it with HKDF-SHA256 into the Ed25519 (signing) and X25519
   *    (encryption) key material, computing the public points ourselves.
   * 3. Injecting that material into OpenPGP.js key generation and pinning a
   *    fixed creation date, so the fingerprint is fully reproducible.
   *
   * NOTE: OpenPGP.js 6.x removed `config.customRandom` (the v5 hook this used to
   * rely on), so seeding randomness no longer works — we must build the key
   * material directly. We override the packet `generate()` step with our
   * precomputed material instead of letting OpenPGP draw from the CSPRNG.
   *
   * IMPORTANT: Same seed = same PGP key (name/email are just metadata).
   * The fingerprint is identical regardless of name/email used.
   */
  const generateKeysFromSeed = async (
    words: string[],
    name: string = 'Parahub User',
    email: string = 'user@parahub.io'
  ): Promise<PGPKeyPair> => {
    loading.value = true
    error.value = null

    try {
      const openpgp = await getOpenPGP()
      const { HDKey } = await import('@scure/bip32')
      const { sha256 } = await import('@noble/hashes/sha2.js')
      const { hkdf } = await import('@noble/hashes/hkdf.js')
      const { ed25519, x25519 } = await import('@noble/curves/ed25519.js')
      const bip39 = await import('bip39')

      // Convert mnemonic to seed and derive key material at PGP-specific path
      const mnemonic = words.join(' ')
      const seedBuffer = await bip39.mnemonicToSeed(mnemonic)
      const seed = new Uint8Array(seedBuffer)
      const master = HDKey.fromMasterSeed(seed)
      const derived = master.derive(PGP_DERIVATION_PATH)

      if (!derived.privateKey) {
        throw new Error('Failed to derive PGP key material from seed')
      }

      // Create deterministic seed ONLY from derived key (not from identity),
      // so the same seed = the same PGP key regardless of name/email.
      const domainSeparator = new TextEncoder().encode('parahub-pgp-v1')
      const combined = new Uint8Array(domainSeparator.length + derived.privateKey.length)
      combined.set(domainSeparator, 0)
      combined.set(derived.privateKey, domainSeparator.length)
      const deterministicSeed = sha256(combined)

      // Expand into key material with stable HKDF counters (matches the old
      // PRNG call order: counter 0 = signing key, counter 1 = encryption key).
      const expand = (counter: number, length: number) =>
        hkdf(sha256, deterministicSeed, new Uint8Array(0),
          new TextEncoder().encode(`openpgp-keygen-${counter}`), length)

      const edSeed = expand(0, 32)                // Ed25519 signing seed (primary)
      const edPub = ed25519.getPublicKey(edSeed)  // 32-byte public point
      const xPriv = expand(1, 32)                 // X25519 encryption scalar (subkey)
      const xPub = x25519.getPublicKey(xPriv)     // 32-byte u-coordinate

      // OpenPGP.js does not export the OID / KDFParams constructors, so capture
      // the (curve-constant) instances it builds for a throwaway key and reuse
      // them — only the key points/scalars need to be deterministic.
      const template = await openpgp.generateKey({
        type: 'ecc', curve: 'curve25519', userIDs: [{ name, email }], format: 'object'
      })
      const edOID = (template as any).privateKey.keyPacket.publicParams.oid
      const subParams = (template as any).privateKey.subkeys[0].keyPacket.publicParams
      const xOID = subParams.oid
      const kdfParams = subParams.kdfParams

      // Prefix a public EC point with the 0x40 native-format leading byte.
      const withLead = (point: Uint8Array) => {
        const out = new Uint8Array(point.length + 1)
        out[0] = 0x40
        out.set(point, 1)
        return out
      }

      const EDDSA = openpgp.enums.publicKey.eddsaLegacy
      const ECDH = openpgp.enums.publicKey.ecdh

      // Override the per-packet key-material generation with our deterministic
      // material. `this.algorithm` is already set when generate() is called.
      const SecretKeyProto: any = (openpgp as any).SecretKeyPacket.prototype
      const SecretSubkeyProto: any = (openpgp as any).SecretSubkeyPacket.prototype
      const origGenerate = SecretKeyProto.generate
      const origSubGenerate = Object.prototype.hasOwnProperty.call(SecretSubkeyProto, 'generate')
        ? SecretSubkeyProto.generate
        : null

      function deterministicGenerate(this: any) {
        if (this.algorithm === EDDSA) {
          this.publicParams = { oid: edOID, Q: withLead(edPub) }
          this.privateParams = { seed: edSeed }
        } else if (this.algorithm === ECDH) {
          // curve25519Legacy stores the scalar big-endian and pre-clamped.
          const d = xPriv.slice().reverse()
          d[0] = (d[0] & 127) | 64
          d[31] &= 248
          this.publicParams = { oid: xOID, Q: withLead(xPub), kdfParams }
          this.privateParams = { d }
        } else {
          throw new Error(`Unexpected key algorithm for seed derivation: ${this.algorithm}`)
        }
        this.isEncrypted = false
      }

      SecretKeyProto.generate = deterministicGenerate
      if (origSubGenerate) SecretSubkeyProto.generate = deterministicGenerate

      try {
        const { privateKey, publicKey } = await openpgp.generateKey({
          type: 'ecc',
          curve: 'curve25519',
          userIDs: [{ name, email }],
          date: PGP_KEY_CREATION_DATE,
          format: 'armored'
        })

        // Get fingerprint
        const publicKeyObj = await openpgp.readKey({ armoredKey: publicKey })
        const fingerprint = publicKeyObj.getFingerprint()

        keyPair.value = {
          publicKey,
          privateKey,
          fingerprint
        }

        // Store in localStorage
        if (process.client) {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(keyPair.value))
        }

        return keyPair.value
      } finally {
        // Always restore the original key-material generators
        SecretKeyProto.generate = origGenerate
        if (origSubGenerate) SecretSubkeyProto.generate = origSubGenerate
      }
    } catch (e: any) {
      console.error('Failed to generate PGP keys from seed:', e)
      error.value = e.message || 'Failed to generate keys from seed'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * Sign a message with private key
   */
  const signMessage = async (message: string, passphrase?: string): Promise<string> => {
    if (!keyPair.value) {
      throw new Error('No PGP keys available')
    }

    try {
      const openpgp = await getOpenPGP()

      const privateKeyObj = await openpgp.readPrivateKey({
        armoredKey: keyPair.value.privateKey
      })

      const decryptedPrivateKey = passphrase
        ? await openpgp.decryptKey({
            privateKey: privateKeyObj,
            passphrase
          })
        : privateKeyObj

      const signResult = await openpgp.sign({
        message: await openpgp.createMessage({ text: message }),
        signingKeys: decryptedPrivateKey,
        detached: true
      })

      return signResult
    } catch (e: any) {
      console.error('Failed to sign message:', e)
      throw new Error(e.message || 'Failed to sign message')
    }
  }

  /**
   * Create canonical string for HTTP request signing
   * Format: [method]\n[uri]\n[sha256(body)]\n[timestamp]\n[nonce]
   */
  const createCanonicalString = async (
    method: string,
    uri: string,
    body: any,
    timestamp: number,
    nonce: string
  ): Promise<string> => {
    const bodyString = body ? JSON.stringify(body) : ''

    // Calculate SHA256 of body
    const encoder = new TextEncoder()
    const data = encoder.encode(bodyString)
    const hashBuffer = await crypto.subtle.digest('SHA-256', data)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    const bodyHash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')

    return `${method}\n${uri}\n${bodyHash}\n${timestamp}\n${nonce}`
  }

  /**
   * Generate nonce (random 32-char hex string)
   */
  const generateNonce = (): string => {
    const array = new Uint8Array(16)
    crypto.getRandomValues(array)
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('')
  }

  /**
   * Sign an HTTP request and return headers
   */
  const signRequest = async (
    method: string,
    uri: string,
    body: any = null,
    passphrase?: string
  ): Promise<PGPSignatureHeaders> => {
    const timestamp = Math.floor(Date.now() / 1000)
    const nonce = generateNonce()

    const canonicalString = await createCanonicalString(method, uri, body, timestamp, nonce)
    const signature = await signMessage(canonicalString, passphrase)

    return {
      'X-PGP-Signature': btoa(signature), // Base64 encode
      'X-PGP-Timestamp': timestamp.toString(),
      'X-PGP-Nonce': nonce
    }
  }

  /**
   * Verify a signature (for testing)
   */
  const verifySignature = async (message: string, signature: string, publicKeyArmored?: string): Promise<boolean> => {
    try {
      const openpgp = await getOpenPGP()

      const publicKeyToUse = publicKeyArmored || keyPair.value?.publicKey
      if (!publicKeyToUse) {
        throw new Error('No public key available')
      }

      const publicKeyObj = await openpgp.readKey({ armoredKey: publicKeyToUse })
      const messageObj = await openpgp.createMessage({ text: message })
      const signatureObj = await openpgp.readSignature({ armoredSignature: signature })

      const verificationResult = await openpgp.verify({
        message: messageObj,
        signature: signatureObj,
        verificationKeys: publicKeyObj
      })

      const { verified } = verificationResult.signatures[0]
      await verified

      return true
    } catch (e) {
      console.error('Signature verification failed:', e)
      return false
    }
  }

  /**
   * Delete keys from storage
   */
  const deleteKeys = () => {
    if (process.client) {
      localStorage.removeItem(STORAGE_KEY)
    }
    keyPair.value = null
  }

  /**
   * Export public key for upload to server
   */
  const exportPublicKey = (): string | null => {
    return keyPair.value?.publicKey || null
  }

  /**
   * Export private key (for backup/transfer to another device)
   */
  const exportPrivateKey = (): string | null => {
    return keyPair.value?.privateKey || null
  }

  /**
   * Import private key from armored text
   */
  const importPrivateKey = async (privateKeyArmored: string, passphrase?: string): Promise<void> => {
    try {
      const openpgp = await getOpenPGP()

      // Read and validate private key
      const privateKeyObj = await openpgp.readPrivateKey({
        armoredKey: privateKeyArmored
      })

      // Test decryption if passphrase provided
      if (passphrase) {
        await openpgp.decryptKey({
          privateKey: privateKeyObj,
          passphrase
        })
      }

      // Extract public key
      const publicKey = privateKeyObj.toPublic().armor()
      const fingerprint = privateKeyObj.getFingerprint()

      // Store keypair
      keyPair.value = {
        publicKey,
        privateKey: privateKeyArmored,
        fingerprint
      }

      // Save to localStorage
      if (process.client) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(keyPair.value))
      }
    } catch (e: any) {
      console.error('Failed to import private key:', e)
      throw new Error(e.message || 'Failed to import private key')
    }
  }

  /**
   * Encrypt a message for recipient(s)
   */
  const encryptMessage = async (message: string, recipientPublicKeys: string[]): Promise<string> => {
    try {
      const openpgp = await getOpenPGP()

      // Read recipient public keys
      const publicKeys = await Promise.all(
        recipientPublicKeys.map(key => openpgp.readKey({ armoredKey: key }))
      )

      // Encrypt message
      const encrypted = await openpgp.encrypt({
        message: await openpgp.createMessage({ text: message }),
        encryptionKeys: publicKeys
      })

      return encrypted as string
    } catch (e: any) {
      console.error('Failed to encrypt message:', e)
      throw new Error(e.message || 'Failed to encrypt message')
    }
  }

  /**
   * Decrypt a message with private key
   */
  const decryptMessage = async (encryptedMessage: string, passphrase?: string): Promise<string> => {
    if (!keyPair.value) {
      throw new Error('No PGP keys available')
    }

    try {
      const openpgp = await getOpenPGP()

      // Read private key
      const privateKeyObj = await openpgp.readPrivateKey({
        armoredKey: keyPair.value.privateKey
      })

      // Decrypt private key if needed
      const decryptedPrivateKey = passphrase
        ? await openpgp.decryptKey({
            privateKey: privateKeyObj,
            passphrase
          })
        : privateKeyObj

      // Read encrypted message
      const messageObj = await openpgp.readMessage({
        armoredMessage: encryptedMessage
      })

      // Decrypt
      const { data: decrypted } = await openpgp.decrypt({
        message: messageObj,
        decryptionKeys: decryptedPrivateKey
      })

      return decrypted as string
    } catch (e: any) {
      console.error('Failed to decrypt message:', e)
      throw new Error(e.message || 'Failed to decrypt message')
    }
  }

  /**
   * Compute SHA256 hash of a file with progress callback (client-side only)
   */
  const computeFileSHA256 = async (
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<string> => {
    const chunkSize = 1024 * 1024 // 1MB chunks
    const chunks = Math.ceil(file.size / chunkSize)
    let currentChunk = 0

    // Use FileReader for chunked reading (better for large files)
    const readChunk = (start: number, end: number): Promise<ArrayBuffer> => {
      return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (e) => resolve(e.target?.result as ArrayBuffer)
        reader.onerror = reject
        reader.readAsArrayBuffer(file.slice(start, end))
      })
    }

    // Collect all chunks
    const allChunks: Uint8Array[] = []
    let totalLength = 0

    for (let i = 0; i < chunks; i++) {
      const start = i * chunkSize
      const end = Math.min(start + chunkSize, file.size)
      const chunk = await readChunk(start, end)
      const uint8Chunk = new Uint8Array(chunk)
      allChunks.push(uint8Chunk)
      totalLength += uint8Chunk.length

      currentChunk++
      if (onProgress) {
        onProgress(Math.round((currentChunk / chunks) * 100))
      }
    }

    // Combine all chunks
    const combined = new Uint8Array(totalLength)
    let position = 0
    for (const chunk of allChunks) {
      combined.set(chunk, position)
      position += chunk.length
    }

    // Compute final hash
    const hashBuffer = await crypto.subtle.digest('SHA-256', combined)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  }

  /**
   * Sign a canonical JSON payload for server-side verification.
   *
   * Recursively sorts keys to match Python's json.dumps(sort_keys=True, separators=(',',':')).
   * Returns empty string if no PGP keys are available (graceful skip).
   */
  const signCanonicalPayload = async (payload: Record<string, any>): Promise<string> => {
    if (!keyPair.value) {
      return ''
    }

    const sortedStringify = (obj: any): string => {
      if (obj === null || obj === undefined) return JSON.stringify(obj)
      if (typeof obj !== 'object') return JSON.stringify(obj)
      if (Array.isArray(obj)) {
        return '[' + obj.map(item => sortedStringify(item)).join(',') + ']'
      }
      const keys = Object.keys(obj).sort()
      const parts = keys.map(k => JSON.stringify(k) + ':' + sortedStringify(obj[k]))
      return '{' + parts.join(',') + '}'
    }

    const canonicalMessage = sortedStringify(payload)
    return await signMessage(canonicalMessage)
  }

  return {
    keyPair,
    loading,
    error,
    hasKeys,
    loadKeys,
    generateKeys,
    generateKeysFromSeed,
    signMessage,
    signCanonicalPayload,
    signRequest,
    verifySignature,
    deleteKeys,
    exportPublicKey,
    exportPrivateKey,
    importPrivateKey,
    encryptMessage,
    decryptMessage,
    computeFileSHA256
  }
}
