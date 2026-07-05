<template>
  <div class="py-6">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="bg-white dark:bg-neutral-800 rounded-lg p-6">
        <img
          :src="hasKeys && keyPair ? '/images/para/thumbs_up.webp' : '/images/para/pointing.webp'"
          alt="Para"
          class="mx-auto h-32 w-auto mb-4"
        />
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-2 text-center">
          PGP Key Setup
        </h1>
        <p class="text-neutral-600 dark:text-neutral-400 mb-6 text-center">
          Generate your PGP keys to sign critical operations on Parahub.
          Your private key never leaves your device.
        </p>

        <!-- Has keys state -->
        <div v-if="hasKeys && keyPair" class="space-y-4">
          <UiAlert variant="success" title="PGP Keys Active">
            Your PGP keys are configured and ready to use.
          </UiAlert>

          <!-- Key info -->
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
              Key Information
            </h3>

            <div class="space-y-3">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Fingerprint
                </label>
                <div class="font-mono text-sm bg-neutral-100 dark:bg-neutral-700 rounded px-3 py-2 break-all">
                  {{ keyPair.fingerprint }}
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Public Key
                </label>
                <textarea
                  :value="keyPair.publicKey"
                  readonly
                  rows="6"
                  class="w-full font-mono text-xs bg-neutral-100 dark:bg-neutral-700 rounded px-3 py-2"
                ></textarea>
                <button
                  @click="copyPublicKey"
                  class="mt-2 text-sm text-primary hover:underline"
                >
                  Copy to clipboard
                </button>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3">
            <button
              @click="showDeleteConfirm = true"
              class="px-4 py-2 border border-red-300 dark:border-red-600 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900"
            >
              Delete Keys
            </button>
          </div>

          <NuxtLink
            :to="localePath('/pgp-test')"
            class="block text-center px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
          >
            Test PGP Signing →
          </NuxtLink>
        </div>

        <!-- Generate keys form -->
        <form v-else @submit.prevent="handleGenerate" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Your Name
            </label>
            <input
              v-model="form.name"
              type="text"
              required
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
              placeholder="John Doe"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Email
            </label>
            <input
              v-model="form.email"
              type="email"
              required
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
              placeholder="john@example.com"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Passphrase (Optional but recommended)
            </label>
            <input
              v-model="form.passphrase"
              type="password"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
              placeholder="Enter a strong passphrase"
            >
            <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Used to encrypt your private key. You'll need this for signing operations.
            </p>
          </div>

          <UiAlert variant="warning" title="Important">
            Your private key will be stored in your browser's localStorage.
            Make sure to backup your keys securely. If you lose them, you won't be able to sign transactions.
          </UiAlert>

          <button
            type="submit"
            :disabled="loading"
            class="btn-primary w-full gap-2"
          >
            <Loader2 v-if="loading" class="h-5 w-5 animate-spin" />
            {{ loading ? 'Generating Keys...' : 'Generate PGP Keys' }}
          </button>

          <div v-if="error" class="text-sm text-red-600 dark:text-red-400">
            {{ error }}
          </div>
        </form>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    
      <div v-if="showDeleteConfirm" class="fixed inset-0 z-50 overflow-y-auto">
        <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
          <div @click="showDeleteConfirm = false" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

          <div class="relative inline-block w-full max-w-md px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
            <div class="sm:flex sm:items-start">
              <div class="w-full">
                <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100 mb-4">
                  Delete PGP Keys?
                </h3>

                <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
                  This will permanently delete your PGP keys from this browser.
                  You will need to generate new keys to sign transactions.
                </p>

                <UiAlert variant="error" class="mb-4">
                  This action cannot be undone. Make sure you have a backup if needed.
                </UiAlert>

                <div class="flex justify-end gap-3">
                  <button
                    @click="showDeleteConfirm = false"
                    class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
                  >
                    Cancel
                  </button>
                  <button
                    @click="confirmDelete"
                    class="btn-error"
                  >
                    Delete Keys
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { CheckCircle, Loader2 } from 'lucide-vue-next'
import { usePGP } from '~/composables/usePGP'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'

definePageMeta({
  middleware: 'auth'
})

const { keyPair, loading, error, hasKeys, loadKeys, generateKeys, deleteKeys, exportPublicKey } = usePGP()
const authStore = useAuthStore()
const localePath = useLocalePath()
const { showSuccess, showError } = useNotification()

const form = ref({
  name: '',
  email: '',
  passphrase: ''
})

const uploading = ref(false)
const showDeleteConfirm = ref(false)

// Generate keys
const handleGenerate = async () => {
  try {
    await generateKeys(form.value.name, form.value.email, form.value.passphrase || undefined)
    showSuccess('PGP keys generated successfully!')

    // Automatically upload public key to server
    await uploadPublicKey()
  } catch (e) {
    showError(`Failed to generate keys: ${e.message}`)
  }
}

// Copy public key to clipboard
const copyPublicKey = async () => {
  try {
    await navigator.clipboard.writeText(keyPair.value.publicKey)
    showSuccess('Public key copied to clipboard')
  } catch (e) {
    showError('Failed to copy to clipboard')
  }
}

// Upload public key to server
const uploadPublicKey = async () => {
  uploading.value = true
  try {
    const publicKey = exportPublicKey()
    if (!publicKey) {
      throw new Error('No public key available')
    }

    await $fetch('/api/v1/profiles/me/keys/', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`,
        'Content-Type': 'application/json'
      },
      body: { public_key: publicKey }
    })

    showSuccess('Public key uploaded to server successfully!')
  } catch (e) {
    console.error('Failed to upload public key:', e)
    showError('Failed to upload public key to server')
  } finally {
    uploading.value = false
  }
}

// Confirm and delete keys
const confirmDelete = () => {
  deleteKeys()
  showDeleteConfirm.value = false
  showSuccess('PGP keys deleted')
}

// Load keys on mount
onMounted(async () => {
  await loadKeys()

  // Pre-fill form with user info if available
  if (!hasKeys.value && authStore.profile) {
    form.value.name = authStore.profile.first_name && authStore.profile.last_name
      ? `${authStore.profile.first_name} ${authStore.profile.last_name}`
      : authStore.profile.hna || 'Anonymous'
    form.value.email = authStore.user?.email || ''
  }
})
</script>

<style scoped>

</style>
