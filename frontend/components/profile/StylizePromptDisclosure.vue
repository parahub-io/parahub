<script setup lang="ts">
/**
 * The restyler's own prompt, offered for copy-paste.
 *
 * The weekly quota exists because each restyle costs real money, not because
 * the style is a secret — so a member who has spent theirs, or who would
 * rather run their own model on their own bill, gets the exact text the
 * product sends. Fetched from the backend (never hardcoded here) so it cannot
 * drift from `parahub/services/avatar_stylizer.py`, and lazily on first open
 * so the profile page does not pay for a panel most visits never expand.
 */
import { Copy, Check, Loader2 } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()

const open = ref(false)
const loading = ref(false)
const failed = ref(false)
const data = ref<{ image_size: string; prompt: string } | null>(null)
const copied = ref(false)

async function load() {
  if (data.value || loading.value) return
  loading.value = true
  failed.value = false
  try {
    await authStore.ensureToken()
    data.value = await $fetch('/api/v1/profiles/me/avatar/stylize/prompt/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch (error) {
    console.error('Stylize prompt fetch error:', error)
    failed.value = true
  } finally {
    loading.value = false
  }
}

function onToggle(event: Event) {
  open.value = (event.target as HTMLDetailsElement).open
  if (open.value) load()
}

async function copyPrompt() {
  if (!data.value) return
  try {
    await navigator.clipboard.writeText(data.value.prompt)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch (error) {
    console.error('Clipboard write failed:', error)
  }
}
</script>

<template>
  <details class="mt-2 group" @toggle="onToggle">
    <summary class="text-xs text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 cursor-pointer select-none">
      {{ t('profile.photos.stylize_prompt_toggle') }}
    </summary>

    <div class="mt-2 rounded-lg border border-neutral-200 dark:border-neutral-700 p-3">
      <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
        {{ t('profile.photos.stylize_prompt_hint') }}
      </p>

      <div v-if="loading" class="flex items-center gap-2 text-xs text-neutral-500">
        <Loader2 class="w-3.5 h-3.5 animate-spin" />
        {{ t('common.loading') }}
      </div>

      <p v-else-if="failed" class="text-xs text-neutral-500 dark:text-neutral-400">
        {{ t('profile.photos.stylize_prompt_failed') }}
      </p>

      <template v-else-if="data">
        <pre class="text-[11px] leading-relaxed text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words font-mono max-h-64 overflow-y-auto mb-2">{{ data.prompt }}</pre>
        <div class="flex flex-wrap items-center gap-2">
          <button class="btn-outline btn-sm" @click="copyPrompt">
            <span class="flex items-center gap-2">
              <Check v-if="copied" class="w-3.5 h-3.5" />
              <Copy v-else class="w-3.5 h-3.5" />
              {{ copied ? t('common.copied') : t('profile.photos.stylize_prompt_copy') }}
            </span>
          </button>
        </div>
        <p class="text-[11px] text-neutral-400 mt-2">
          {{ t('profile.photos.stylize_prompt_reference', { size: data.image_size }) }}
        </p>
      </template>
    </div>
  </details>
</template>
