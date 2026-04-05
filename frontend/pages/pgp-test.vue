<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="bg-white dark:bg-neutral-800 rounded-lg p-6">
        <div class="mb-6">
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
            PGP Signing Test
          </h1>
          <p class="text-neutral-600 dark:text-neutral-400">
            Test your PGP setup: signing, encryption, and decryption.
          </p>
        </div>

        <!-- No keys warning -->
        <UiAlert v-if="!hasKeys" variant="warning" title="No PGP Keys Found" class="mb-6">
              <p class="mb-2">
                You need to generate PGP keys before testing signatures.
              </p>
              <NuxtLink
                :to="localePath('/profile')"
                class="underline hover:no-underline"
              >
                Go to Profile Settings →
              </NuxtLink>
        </UiAlert>

        <div v-else class="space-y-8">
          <!-- Simple message signing -->
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Sign a Text Message
            </h2>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Message to Sign
                </label>
                <textarea
                  v-model="testMessage"
                  rows="3"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  placeholder="Enter any message to sign..."
                ></textarea>
              </div>

              <div v-if="messagePassphrase !== null">
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Passphrase (if you set one)
                </label>
                <input
                  v-model="messagePassphrase"
                  type="password"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  placeholder="Enter your passphrase"
                >
              </div>

              <button
                @click="signTestMessage"
                :disabled="signing || !testMessage"
                class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 disabled:opacity-50"
              >
                {{ signing ? 'Signing...' : 'Sign Message' }}
              </button>

              <div v-if="messageSignature" class="space-y-2">
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  Signature (Detached)
                </label>
                <textarea
                  :value="messageSignature"
                  readonly
                  rows="8"
                  class="w-full font-mono text-xs bg-neutral-100 dark:bg-neutral-700 rounded px-3 py-2"
                ></textarea>
                <div class="flex gap-2">
                  <button
                    @click="copySignature"
                    class="text-sm text-primary hover:underline"
                  >
                    Copy Signature
                  </button>
                  <button
                    @click="verifyTestSignature"
                    :disabled="verifying"
                    class="text-sm text-green-600 dark:text-green-400 hover:underline"
                  >
                    {{ verifying ? 'Verifying...' : 'Verify Signature' }}
                  </button>
                </div>

                <div v-if="verificationResult !== null" class="mt-2">
                  <div v-if="verificationResult" class="text-sm text-green-600 dark:text-green-400 flex items-center gap-2">
                    <CheckCircle class="w-5 h-5" />
                    Signature is valid!
                  </div>
                  <div v-else class="text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                    <XCircle class="w-5 h-5" />
                    Signature is invalid!
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Message encryption -->
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Encrypt & Decrypt Messages
            </h2>

            <div class="space-y-4">
              <!-- Encrypt section -->
              <div class="border-b border-neutral-200 dark:border-neutral-700 pb-4">
                <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                  Encrypt Message
                </h3>

                <div class="space-y-3">
                  <div>
                    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                      Message to Encrypt
                    </label>
                    <textarea
                      v-model="messageToEncrypt"
                      rows="3"
                      class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                      placeholder="Enter secret message..."
                    ></textarea>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                      Recipient's Public Key
                    </label>
                    <textarea
                      v-model="recipientPublicKey"
                      rows="6"
                      class="w-full font-mono text-xs px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                      placeholder="-----BEGIN PGP PUBLIC KEY BLOCK-----&#10;..."
                    ></textarea>
                    <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                      Tip: Use your own public key to test encryption/decryption
                    </p>
                  </div>

                  <button
                    @click="handleEncrypt"
                    :disabled="encrypting || !messageToEncrypt || !recipientPublicKey"
                    class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 disabled:opacity-50"
                  >
                    {{ encrypting ? 'Encrypting...' : 'Encrypt Message' }}
                  </button>

                  <div v-if="encryptedMessage" class="space-y-2">
                    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                      Encrypted Message
                    </label>
                    <textarea
                      :value="encryptedMessage"
                      readonly
                      rows="8"
                      class="w-full font-mono text-xs bg-neutral-100 dark:bg-neutral-700 rounded px-3 py-2"
                    ></textarea>
                    <button
                      @click="copyEncrypted"
                      class="text-sm text-primary hover:underline"
                    >
                      Copy Encrypted Message
                    </button>
                  </div>
                </div>
              </div>

              <!-- Decrypt section -->
              <div class="pt-4">
                <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                  Decrypt Message
                </h3>

                <div class="space-y-3">
                  <div>
                    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                      Encrypted Message
                    </label>
                    <textarea
                      v-model="messageToDecrypt"
                      rows="8"
                      class="w-full font-mono text-xs px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                      placeholder="-----BEGIN PGP MESSAGE-----&#10;..."
                    ></textarea>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                      Passphrase (if you set one)
                    </label>
                    <input
                      v-model="decryptPassphrase"
                      type="password"
                      class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                      placeholder="Enter your passphrase"
                    >
                  </div>

                  <button
                    @click="handleDecrypt"
                    :disabled="decrypting || !messageToDecrypt"
                    class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 disabled:opacity-50"
                  >
                    {{ decrypting ? 'Decrypting...' : 'Decrypt Message' }}
                  </button>

                  <UiAlert v-if="decryptedMessage" variant="success" title="Decrypted Message">
                    {{ decryptedMessage }}
                  </UiAlert>
                </div>
              </div>
            </div>
          </div>

          <!-- Key info -->
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-6">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Your PGP Key Info
            </h2>
            <div class="space-y-2 text-sm">
              <div>
                <span class="text-neutral-600 dark:text-neutral-400">Fingerprint:</span>
                <span class="ml-2 font-mono">{{ keyPair?.fingerprint }}</span>
              </div>
              <div>
                <span class="text-neutral-600 dark:text-neutral-400">Status:</span>
                <span class="ml-2 text-green-600 dark:text-green-400">Active</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="error" class="mt-4 text-sm text-red-600 dark:text-red-400">
          Error: {{ error }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const localePath = useLocalePath()
import { ref, onMounted } from 'vue'
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-vue-next'
import { usePGP } from '~/composables/usePGP'
import { useNotification } from '~/composables/useNotification'

definePageMeta({
  middleware: 'auth'
})

const { keyPair, hasKeys, loadKeys, signMessage, verifySignature, encryptMessage: encryptMessageFn, decryptMessage: decryptMessageFn, exportPublicKey, error } = usePGP()
const { showSuccess, showError } = useNotification()

// Message signing
const testMessage = ref('Hello, Parahub! This is a test message.')
const messagePassphrase = ref('')
const messageSignature = ref('')
const signing = ref(false)
const verifying = ref(false)
const verificationResult = ref(null)

// Message encryption
const messageToEncrypt = ref('This is a secret message!')
const recipientPublicKey = ref('')
const encryptedMessage = ref('')
const encrypting = ref(false)

// Message decryption
const messageToDecrypt = ref('')
const decryptPassphrase = ref('')
const decryptedMessage = ref('')
const decrypting = ref(false)

// Sign test message
const signTestMessage = async () => {
  signing.value = true
  verificationResult.value = null
  try {
    const signature = await signMessage(testMessage.value, messagePassphrase.value || undefined)
    messageSignature.value = signature
    showSuccess('Message signed successfully!')
  } catch (e) {
    showError(`Failed to sign message: ${e.message}`)
  } finally {
    signing.value = false
  }
}

// Copy signature
const copySignature = async () => {
  try {
    await navigator.clipboard.writeText(messageSignature.value)
    showSuccess('Signature copied to clipboard')
  } catch (e) {
    showError('Failed to copy to clipboard')
  }
}

// Verify test signature
const verifyTestSignature = async () => {
  verifying.value = true
  try {
    const isValid = await verifySignature(testMessage.value, messageSignature.value)
    verificationResult.value = isValid
    if (isValid) {
      showSuccess('Signature verified successfully!')
    } else {
      showError('Signature verification failed')
    }
  } catch (e) {
    showError(`Verification error: ${e.message}`)
    verificationResult.value = false
  } finally {
    verifying.value = false
  }
}

// Encrypt message
const handleEncrypt = async () => {
  encrypting.value = true
  try {
    const encrypted = await encryptMessageFn(messageToEncrypt.value, [recipientPublicKey.value])
    encryptedMessage.value = encrypted
    showSuccess('Message encrypted successfully!')
  } catch (e) {
    showError(`Failed to encrypt: ${e.message}`)
  } finally {
    encrypting.value = false
  }
}

// Copy encrypted message
const copyEncrypted = async () => {
  try {
    await navigator.clipboard.writeText(encryptedMessage.value)
    showSuccess('Encrypted message copied to clipboard')
  } catch (e) {
    showError('Failed to copy to clipboard')
  }
}

// Decrypt message
const handleDecrypt = async () => {
  decrypting.value = true
  decryptedMessage.value = ''
  try {
    const decrypted = await decryptMessageFn(messageToDecrypt.value, decryptPassphrase.value || undefined)
    decryptedMessage.value = decrypted
    showSuccess('Message decrypted successfully!')
  } catch (e) {
    showError(`Failed to decrypt: ${e.message}`)
  } finally {
    decrypting.value = false
  }
}

// Load keys on mount
onMounted(async () => {
  await loadKeys()

  // Pre-fill recipient with own public key for testing
  if (keyPair.value) {
    recipientPublicKey.value = exportPublicKey()
  }
})
</script>
