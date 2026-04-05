<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 pt-24 pb-8 px-4">
    <div class="max-w-lg mx-auto">
      <!-- Header -->
      <div class="text-center mb-8">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-primary/20 flex items-center justify-center">
          <Shield class="w-8 h-8 text-primary" />
        </div>
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('seed.title') }}
        </h1>
        <p class="mt-2 text-neutral-600 dark:text-neutral-400">
          {{ stepDescription }}
        </p>
      </div>

      <!-- Step indicator -->
      <div class="flex justify-center mb-8">
        <div class="flex items-center space-x-2">
          <div
            v-for="s in 2"
            :key="s"
            class="w-3 h-3 rounded-full transition-colors"
            :class="{
              'bg-primary': s <= currentStep,
              'bg-neutral-300 dark:bg-neutral-600': s > currentStep
            }"
          />
        </div>
      </div>

      <!-- Step 1: Show mnemonic -->
      <div v-if="currentStep === 1" class="space-y-6">
        <!-- Warning: Old key will be expired -->
        <UiAlert v-if="hasExistingServerKey" variant="warning" :title="$t('seed.existingKeyWarningTitle')">
          {{ $t('seed.existingKeyWarningText') }}
        </UiAlert>

        <UiAlert variant="warning" :title="$t('seed.warningTitle')">
          {{ $t('seed.warningText') }}
        </UiAlert>

        <!-- Mnemonic words grid -->
        <div class="grid grid-cols-3 gap-3">
          <div
            v-for="(word, index) in mnemonic"
            :key="index"
            class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3 text-center"
          >
            <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ index + 1 }}</span>
            <p class="font-mono text-sm mt-1">{{ word }}</p>
          </div>
        </div>

        <!-- Copy button -->
        <button
          type="button"
          class="w-full flex items-center justify-center space-x-2 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          @click="copyMnemonic"
        >
          <Copy class="w-4 h-4" />
          <span>{{ copied ? $t('common.copied') : $t('seed.copyWords') }}</span>
        </button>

        <!-- Continue button -->
        <button
          type="button"
          class="w-full py-3 bg-primary text-black rounded-lg font-medium hover:bg-primary/90 transition-colors"
          @click="currentStep = 2"
        >
          {{ $t('seed.iWroteIt') }}
        </button>

        <!-- Restore link -->
        <div class="text-center pt-4 border-t border-neutral-200 dark:border-neutral-700 space-y-2">
          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ $t('seed.alreadyHaveSeed') }}
            <NuxtLink
              :to="localePath('/seed-restore')"
              class="text-primary hover:underline font-medium"
            >
              {{ $t('seed.restoreFromSeed') }}
            </NuxtLink>
          </p>
          <p>
            <button
              type="button"
              class="text-sm text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
              @click="skipSetup"
            >
              {{ $t('seed.skipForNow') }}
            </button>
          </p>
        </div>
      </div>

      <!-- Step 2: Verify words -->
      <div v-else-if="currentStep === 2" class="space-y-6">
        <p class="text-center text-neutral-600 dark:text-neutral-400">
          {{ $t('seed.verifyDescription') }}
        </p>

        <div class="space-y-4">
          <div
            v-for="(idx, i) in verificationIndices"
            :key="i"
            class="space-y-2"
          >
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {{ $t('seed.enterWord') }} #{{ idx + 1 }}
            </label>
            <input
              v-model="verificationInputs[i]"
              type="text"
              :placeholder="$t('seed.wordPlaceholder')"
              class="w-full px-4 py-3 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              autocomplete="off"
              autocapitalize="off"
              @input="verificationInputs[i] = ($event.target as HTMLInputElement).value.toLowerCase().trim()"
            />
          </div>
        </div>

        <p v-if="verificationError" class="text-red-500 text-sm text-center">
          {{ $t('seed.verificationFailed') }}
        </p>

        <div class="flex space-x-3">
          <button
            type="button"
            class="flex-1 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            @click="currentStep = 1"
          >
            {{ $t('common.back') }}
          </button>
          <button
            type="button"
            class="flex-1 py-3 bg-primary text-black rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            :disabled="!canVerify || saving"
            @click="verifyAndFinish"
          >
            {{ saving ? $t('seed.saving') : $t('common.continue') }}
          </button>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="saving" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 text-center">
          <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto"></div>
          <p class="mt-4 text-neutral-600 dark:text-neutral-400">{{ $t('seed.saving') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Shield, AlertTriangle, Copy } from 'lucide-vue-next'
import { useSeed } from '~/composables/useSeed'
import { usePGP } from '~/composables/usePGP'
import { useAuthStore } from '~/stores/auth'

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()

const {
  generateMnemonic,
  saveSeed,
  hasSeed,
  clearSeed,
  getVerificationIndices
} = useSeed()

import { useLightning } from '~/composables/useLightning'
const { disconnect: disconnectWallet } = useLightning()

const {
  generateKeysFromSeed,
  exportPublicKey,
  deleteKeys: deletePGPKeys
} = usePGP()

// State
const currentStep = ref(1)
const mnemonic = ref<string[]>([])
const verificationIndices = ref<number[]>([])
const verificationInputs = ref<string[]>(['', '', ''])
const verificationError = ref(false)
const saving = ref(false)
const copied = ref(false)
const profileLoaded = ref(false)

// Computed
const stepDescription = computed(() => {
  switch (currentStep.value) {
    case 1: return t('seed.step1Description')
    case 2: return t('seed.step2Description')
    default: return ''
  }
})

const canVerify = computed(() => {
  return verificationInputs.value.every(input => input.length > 0)
})

// Check if user has existing PGP key on server
const hasExistingServerKey = computed(() => {
  return profileLoaded.value && !!authStore.profile?.pgp_fingerprint
})

// Methods
const copyMnemonic = async () => {
  try {
    await navigator.clipboard.writeText(mnemonic.value.join(' '))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

const verifyAndFinish = async () => {
  verificationError.value = false

  // Verify words
  for (let i = 0; i < verificationIndices.value.length; i++) {
    const expectedWord = mnemonic.value[verificationIndices.value[i]]
    const inputWord = verificationInputs.value[i].toLowerCase().trim()

    if (expectedWord !== inputWord) {
      verificationError.value = true
      return
    }
  }

  // Words verified, save and generate keys
  saving.value = true

  try {
    // Clear old data before saving new seed
    clearSeed()
    await disconnectWallet()
    deletePGPKeys()

    // Save seed (no encryption) — this is the critical step
    saveSeed(mnemonic.value)
  } catch (e: any) {
    console.error('Failed to save seed:', e)
    alert(t('seed.saveFailed'))
    saving.value = false
    return
  }

  // Seed saved — PGP key generation is non-fatal
  try {
    const name = authStore.profile?.display_name || authStore.profile?.hna || 'Parahub User'
    const email = authStore.user?.email || `${mnemonic.value[0]}@seed.parahub.io`
    await generateKeysFromSeed(mnemonic.value, name, email)

    // Upload public key to server if logged in
    if (authStore.isAuthenticated) {
      try {
        await authStore.ensureToken()
        const publicKey = exportPublicKey()
        if (publicKey) {
          await $fetch('/api/v1/profiles/me/keys/', {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${authStore.token}`,
              'Content-Type': 'application/json'
            },
            body: { public_key: publicKey }
          })
        }
      } catch (e) {
        console.warn('Failed to upload PGP key to server:', e)
      }
    }
  } catch (e: any) {
    // Non-fatal: seed is saved, PGP keys can be regenerated from seed later
    console.warn('Seed saved but PGP key generation failed:', e)
  }

  // Always navigate — seed is saved regardless of PGP outcome
  saving.value = false
  const next = route.query.next as string || '/profile'
  router.push(localePath(next))
}

// Skip setup and go back
const skipSetup = () => {
  const next = route.query.next as string
  if (next) {
    router.push(localePath(next))
  } else {
    router.back()
  }
}

// Lifecycle
onMounted(async () => {
  // Check session and load profile (needed for hasExistingServerKey check)
  // This works even without auth middleware
  try {
    const isAuth = await authStore.ensureSession()
    if (isAuth) {
      await authStore.ensureToken()  // Get JWT token first
      await authStore.fetchUser()
    }
  } catch (e) {
    console.warn('Failed to check session:', e)
  }
  profileLoaded.value = true

  // Generate mnemonic (allow regeneration even if seed exists)
  mnemonic.value = await generateMnemonic()
  verificationIndices.value = getVerificationIndices()
})

definePageMeta({
  middleware: 'auth',
})
</script>
