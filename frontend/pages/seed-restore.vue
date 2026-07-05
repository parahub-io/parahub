<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 pt-24 pb-8 px-4">
    <div class="max-w-lg mx-auto">
      <!-- Header -->
      <div class="text-center mb-8">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-primary/20 flex items-center justify-center">
          <KeyRound class="w-8 h-8 text-primary" />
        </div>
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('seedRestore.title') }}
        </h1>
        <p class="mt-2 text-neutral-600 dark:text-neutral-400">
          {{ $t('seedRestore.subtitle') }}
        </p>
      </div>

      <!-- Enter seed phrase -->
      <div class="space-y-5">
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('seedRestore.pasteAllWords') }}
          </label>
          <textarea
            v-model="bulkInput"
            rows="3"
            :placeholder="$t('seedRestore.pasteAllWordsPlaceholder')"
            class="w-full px-3 py-2 rounded-lg border bg-white dark:bg-neutral-800 text-sm font-mono focus:outline-none focus:ring-2 focus:border-transparent resize-none"
            :class="showInvalid
              ? 'border-error focus:ring-error'
              : 'border-neutral-300 dark:border-neutral-600 focus:ring-primary'"
            autocomplete="off"
            autocapitalize="off"
            autocorrect="off"
            spellcheck="false"
          />

          <!-- Live feedback: per-word validity + count + checksum -->
          <div v-if="parsedWords.length" class="mt-3 space-y-2">
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="(w, i) in parsedWords"
                :key="i"
                class="px-2 py-0.5 rounded text-xs font-mono"
                :class="wordState(w) === 'invalid'
                  ? 'bg-error/10 text-error border border-error/40'
                  : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300'"
              >
                {{ w }}
              </span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span :class="parsedWords.length === 12 ? 'text-neutral-500' : 'text-warning'">
                {{ $t('seedRestore.wordCount', { count: parsedWords.length }) }}
              </span>
              <span
                v-if="parsedWords.length === 12 && checksumValid === true"
                class="inline-flex items-center gap-1 text-success"
              >
                <Check class="w-3.5 h-3.5" />{{ $t('seedRestore.validPhrase') }}
              </span>
              <span
                v-else-if="parsedWords.length === 12 && checksumValid === false"
                class="text-error"
              >
                {{ $t('seedRestore.invalidMnemonic') }}
              </span>
            </div>
          </div>
        </div>

        <!-- Continue button -->
        <UiButton
          type="button"
          variant="primary"
          class="w-full"
          :loading="saving"
          :disabled="parsedWords.length !== 12 || checksumValid === false || saving"
          @click="validateAndRestore"
        >
          {{ saving ? $t('seedRestore.restoring') : $t('common.continue') }}
        </UiButton>
      </div>

      <!-- Loading state -->
      <div v-if="saving" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 text-center">
          <div class="animate-spin w-8 h-8 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full mx-auto"></div>
          <p class="mt-4 text-neutral-600 dark:text-neutral-400">{{ $t('seedRestore.restoring') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { KeyRound, Check } from 'lucide-vue-next'
import { useSeed } from '~/composables/useSeed'
import { usePGP } from '~/composables/usePGP'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()
const toast = useToastStore()

const {
  validateMnemonic,
  saveSeed,
  getWordlist
} = useSeed()

const {
  generateKeysFromSeed,
  exportPublicKey
} = usePGP()

// State
const bulkInput = ref('')
const saving = ref(false)
const wordlist = ref<string[]>([])
const checksumValid = ref<boolean | null>(null)

// Words parsed from the single input (paste or type, whitespace-separated)
const parsedWords = computed(() =>
  bulkInput.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
)

// Per-word state for the chip row.
// 'partial' = valid BIP39 prefix (still being typed) → don't flag as error.
const wordState = (w: string): 'known' | 'partial' | 'invalid' => {
  if (!wordlist.value.length) return 'known' // wordlist not loaded yet — don't false-flag
  if (wordlist.value.includes(w)) return 'known'
  return wordlist.value.some(x => x.startsWith(w)) ? 'partial' : 'invalid'
}

// Only paint the textarea red once a full 12-word phrase fails its checksum.
const showInvalid = computed(() => parsedWords.value.length === 12 && checksumValid.value === false)

// Live checksum once all 12 words are present (BIP39 validation runs client-side).
watch(parsedWords, async (words) => {
  checksumValid.value = words.length === 12 ? await validateMnemonic(words) : null
})

const validateAndRestore = async () => {
  const words = parsedWords.value

  const isValid = await validateMnemonic(words)
  if (!isValid) {
    checksumValid.value = false
    return
  }

  // Valid mnemonic, save and generate keys
  saving.value = true

  try {
    // Save seed (no encryption) — this is the critical step
    saveSeed(words)
  } catch (e: any) {
    console.error('Failed to save seed:', e)
    toast.error(t('seedRestore.restoreFailed'))
    saving.value = false
    return
  }

  // Seed saved — PGP key generation is non-fatal
  try {
    const name = authStore.profile?.display_name || authStore.profile?.hna || 'Parahub User'
    const email = authStore.user?.email || `${words[0]}@seed.parahub.io`
    await generateKeysFromSeed(words, name, email)

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
  router.push(localePath('/wallet'))
}

// Lifecycle
onMounted(async () => {
  wordlist.value = await getWordlist()
})

definePageMeta({
  middleware: 'auth',
})
</script>
