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

      <!-- Enter seed words -->
      <div class="space-y-6">
        <!-- Quick paste: single line input -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('seedRestore.pasteAllWords') }}
          </label>
          <textarea
            v-model="bulkInput"
            rows="2"
            :placeholder="$t('seedRestore.pasteAllWordsPlaceholder')"
            class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
            autocomplete="off"
            autocapitalize="off"
            @input="handleBulkInput"
          />
        </div>

        <div class="flex items-center gap-3">
          <div class="flex-1 h-px bg-neutral-300 dark:bg-neutral-600"></div>
          <span class="text-xs text-neutral-500">{{ $t('common.or') }}</span>
          <div class="flex-1 h-px bg-neutral-300 dark:bg-neutral-600"></div>
        </div>

        <!-- Individual word inputs -->
        <div class="grid grid-cols-3 gap-3">
          <div
            v-for="(_, index) in 12"
            :key="index"
            class="relative"
          >
            <span class="absolute left-3 top-3 text-xs text-neutral-400">{{ index + 1 }}</span>
            <input
              v-model="words[index]"
              type="text"
              :placeholder="$t('seedRestore.wordPlaceholder')"
              class="w-full pt-7 pb-2 px-3 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              autocomplete="off"
              autocapitalize="off"
              @input="handleWordInput(index, $event)"
              @keydown="handleKeydown(index, $event)"
            />
            <!-- Autocomplete dropdown -->
            <div
              v-if="autocompleteIndex === index && filteredWords.length > 0"
              class="absolute z-10 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg max-h-40 overflow-y-auto"
            >
              <button
                v-for="(word, i) in filteredWords.slice(0, 5)"
                :key="word"
                type="button"
                class="w-full px-3 py-2 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-700"
                :class="{ 'bg-neutral-100 dark:bg-neutral-700': selectedAutocomplete === i }"
                @click="selectWord(index, word)"
              >
                {{ word }}
              </button>
            </div>
          </div>
        </div>

        <!-- Error message -->
        <p v-if="validationError" class="text-red-500 text-sm text-center">
          {{ $t('seedRestore.invalidMnemonic') }}
        </p>

        <!-- Paste button -->
        <button
          type="button"
          class="w-full flex items-center justify-center space-x-2 py-3 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          @click="pasteFromClipboard"
        >
          <ClipboardPaste class="w-4 h-4" />
          <span>{{ $t('seedRestore.pasteWords') }}</span>
        </button>

        <!-- Continue button -->
        <button
          type="button"
          class="w-full py-3 bg-primary text-black rounded-lg font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="!allWordsFilled || saving"
          @click="validateAndRestore"
        >
          {{ saving ? $t('seedRestore.restoring') : $t('common.continue') }}
        </button>
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
import { ref, computed, onMounted } from 'vue'
import { KeyRound, ClipboardPaste } from 'lucide-vue-next'
import { useSeed } from '~/composables/useSeed'
import { usePGP } from '~/composables/usePGP'
import { useAuthStore } from '~/stores/auth'

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()
const authStore = useAuthStore()

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
const words = ref<string[]>(Array(12).fill(''))
const bulkInput = ref('')
const validationError = ref(false)
const saving = ref(false)

// Autocomplete
const wordlist = ref<string[]>([])
const autocompleteIndex = ref<number | null>(null)
const selectedAutocomplete = ref(0)

// Computed
const allWordsFilled = computed(() => {
  return words.value.every(w => w.trim().length > 0)
})

// Handle bulk input (all 12 words in one field)
const handleBulkInput = () => {
  const inputWords = bulkInput.value.trim().toLowerCase().split(/\s+/)
  if (inputWords.length >= 1) {
    for (let i = 0; i < 12; i++) {
      words.value[i] = inputWords[i] || ''
    }
    validationError.value = false
  }
}

const filteredWords = computed(() => {
  if (autocompleteIndex.value === null) return []
  const currentWord = words.value[autocompleteIndex.value].toLowerCase().trim()
  if (!currentWord) return []
  return wordlist.value.filter(w => w.startsWith(currentWord))
})

// Methods
const handleWordInput = (index: number, event: Event) => {
  const input = (event.target as HTMLInputElement).value.toLowerCase().trim()
  words.value[index] = input
  autocompleteIndex.value = index
  selectedAutocomplete.value = 0
  validationError.value = false
}

const handleKeydown = (index: number, event: KeyboardEvent) => {
  if (autocompleteIndex.value !== index || filteredWords.value.length === 0) {
    if (event.key === 'Tab' && !event.shiftKey && index < 11) {
      return
    }
    return
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    selectedAutocomplete.value = Math.min(selectedAutocomplete.value + 1, filteredWords.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    selectedAutocomplete.value = Math.max(selectedAutocomplete.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    selectWord(index, filteredWords.value[selectedAutocomplete.value])
  } else if (event.key === 'Escape') {
    autocompleteIndex.value = null
  }
}

const selectWord = (index: number, word: string) => {
  words.value[index] = word
  autocompleteIndex.value = null

  // Focus next input
  if (index < 11) {
    const inputs = document.querySelectorAll('input[type="text"]')
    const nextInput = inputs[index + 1] as HTMLInputElement
    nextInput?.focus()
  }
}

const pasteFromClipboard = async () => {
  try {
    const text = await navigator.clipboard.readText()
    const pastedWords = text.trim().split(/\s+/)

    if (pastedWords.length === 12) {
      words.value = pastedWords.map(w => w.toLowerCase().trim())
      validationError.value = false
    }
  } catch (e) {
    console.error('Failed to paste:', e)
  }
}

const validateAndRestore = async () => {
  validationError.value = false

  const isValid = await validateMnemonic(words.value)
  if (!isValid) {
    validationError.value = true
    return
  }

  // Valid mnemonic, save and generate keys
  saving.value = true

  try {
    // Save seed (no encryption) — this is the critical step
    saveSeed(words.value)
  } catch (e: any) {
    console.error('Failed to save seed:', e)
    alert(t('seedRestore.restoreFailed'))
    saving.value = false
    return
  }

  // Seed saved — PGP key generation is non-fatal
  try {
    const name = authStore.profile?.display_name || authStore.profile?.hna || 'Parahub User'
    const email = authStore.user?.email || `${words.value[0]}@seed.parahub.io`
    await generateKeysFromSeed(words.value, name, email)

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
