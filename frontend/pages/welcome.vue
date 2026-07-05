<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary via-secondary to-primary">
    <div class="bg-neutral-100/95 backdrop-blur-sm rounded-2xl p-8 w-full max-w-lg">
      <img src="/images/para/welcome.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
      <h1 class="text-3xl font-bold text-center mb-2">Welcome to Parahub!</h1>
      <p class="text-center text-neutral-600 mb-8">Your account has been created successfully</p>
      
      <div v-if="credentials" class="space-y-6">
        <UiAlert variant="warning" title="Important: Save these credentials securely!">
          These are your login credentials. You can use them to sign in with your HNA and password.
        </UiAlert>
        
        <div class="space-y-4">
          <div class="bg-white rounded-lg p-4 border border-neutral-200">
            <label class="block text-sm font-medium text-neutral-700 mb-1">Your HNA (Human-Navigable Alias)</label>
            <div class="flex items-center gap-2">
              <input
                :value="credentials.hna"
                readonly
                class="flex-1 px-3 py-2 bg-neutral-50 border border-neutral-300 rounded-lg font-mono"
              />
              <button
                @click="copyToClipboard(credentials.hna, 'HNA')"
                class="px-3 py-2 bg-neutral-200 hover:bg-neutral-300 rounded-lg"
              >
                📋 Copy
              </button>
            </div>
          </div>
          
          <div class="bg-white rounded-lg p-4 border border-neutral-200">
            <label class="block text-sm font-medium text-neutral-700 mb-1">Your Password</label>
            <div class="flex items-center gap-2">
              <input
                :value="showPassword ? credentials.password : '••••••••••••'"
                :type="showPassword ? 'text' : 'password'"
                readonly
                class="flex-1 px-3 py-2 bg-neutral-50 border border-neutral-300 rounded-lg font-mono"
              />
              <button
                @click="showPassword = !showPassword"
                class="px-3 py-2 bg-neutral-200 hover:bg-neutral-300 rounded-lg"
              >
                {{ showPassword ? '🙈' : '👁️' }}
              </button>
              <button
                @click="copyToClipboard(credentials.password, 'Password')"
                class="px-3 py-2 bg-neutral-200 hover:bg-neutral-300 rounded-lg"
              >
                📋 Copy
              </button>
            </div>
          </div>
        </div>
        
        <UiAlert variant="info" title="Tip">
          <p>You can now sign in using either:</p>
          <ul class="mt-2 ml-6 list-disc">
            <li>Google Sign-In (OAuth)</li>
            <li>Your HNA and password</li>
          </ul>
        </UiAlert>
        
        <button
          @click="continueToApp"
          class="w-full bg-black text-white py-3 px-4 rounded-lg font-medium hover:bg-neutral-800"
        >
          Continue to Parahub
        </button>
      </div>
      
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const localePath = useLocalePath()
const showPassword = ref(false)
const copiedText = ref('')

// SSR-aware credential fetch: if no pending credentials, redirect before render.
// Prevents a brief flash of the welcome hero for users visiting /welcome directly.
const { data: credentials } = await useAsyncData('welcome-credentials', () =>
  $fetch('/api/v1/auth/generated-credentials/', {
    credentials: 'include',
    headers: useRequestHeaders(['cookie']),
  }).catch(() => null)
)

if (!credentials.value?.hna || !credentials.value?.password) {
  await navigateTo(localePath('/profile'))
}

const copyToClipboard = async (text, label) => {
  try {
    await navigator.clipboard.writeText(text)
    copiedText.value = label
    
    // Show success message
    const button = event.target
    const originalText = button.textContent
    button.textContent = '✅'
    setTimeout(() => {
      button.textContent = originalText
      copiedText.value = ''
    }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}

const continueToApp = () => {
  navigateTo(localePath('/'))
}

definePageMeta({
  middleware: 'auth',
})
</script>