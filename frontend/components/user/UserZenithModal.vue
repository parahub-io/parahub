<template>
  <Modal
    v-model="visible"
    :title="t('zenith.ask_zenith_title', { name: profile?.display_name || profile?.hna })"
    :icon="Bot"
    icon-class="text-purple-600"
    size="lg"
    @close="closeZenithModal"
  >
    <div class="space-y-4">
      <!-- Chat messages -->
      <div class="h-64 overflow-y-auto bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 space-y-3">
        <!-- Welcome message -->
        <div v-if="zenithMessages.length === 0" class="text-center py-8">
          <Bot class="w-12 h-12 text-neutral-400 mx-auto mb-3" />
          <p class="text-sm text-neutral-600 dark:text-neutral-400">
            {{ t('zenith.ask_anything', { name: profile?.display_name || profile?.hna }) }}
          </p>
        </div>

        <!-- Messages -->
        <div
          v-for="(message, index) in zenithMessages"
          :key="index"
          class="flex"
          :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[80%] rounded-lg px-3 py-2 text-sm"
            :class="message.role === 'user'
              ? 'bg-primary text-black'
              : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100'"
          >
            {{ message.content }}
          </div>
        </div>

        <!-- Loading indicator -->
        <div v-if="zenithAsking" class="flex justify-start">
          <div class="bg-neutral-200 dark:bg-neutral-700 rounded-lg px-3 py-2">
            <div class="flex items-center gap-2">
              <Loader2 class="w-4 h-4 animate-spin" />
              <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ t('zenith.thinking') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Input -->
      <form @submit.prevent="askZenith" class="flex gap-2">
        <input
          v-model="zenithQuestion"
          type="text"
          :placeholder="t('zenith.ask_placeholder')"
          :disabled="zenithAsking"
          class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <button
          type="submit"
          :disabled="!zenithQuestion.trim() || zenithAsking"
          class="btn-primary flex items-center gap-2"
        >
          <Send class="w-4 h-4" />
        </button>
      </form>
    </div>

    <template #footer>
      <button
        @click="closeZenithModal"
        class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
      >
        {{ t('user_profile.close') }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { Bot, Loader2, Send } from 'lucide-vue-next'

const props = defineProps<{ profile: any; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const zenithQuestion = ref('')
const zenithAsking = ref(false)
const zenithMessages = ref<Array<{role: 'user' | 'assistant', content: string}>>([])

const closeZenithModal = () => {
  visible.value = false
  zenithQuestion.value = ''
}

const askZenith = async () => {
  if (!zenithQuestion.value.trim() || zenithAsking.value) return

  const question = zenithQuestion.value.trim()
  zenithQuestion.value = ''

  zenithMessages.value.push({
    role: 'user',
    content: question
  })

  zenithAsking.value = true

  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/zenith/ask', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        question: question,
        target_profile_id: props.profile.id
      }
    }) as any

    zenithMessages.value.push({
      role: 'assistant',
      content: response.answer
    })
  } catch (error: any) {
    console.error('Failed to ask Zenith:', error)
    const errorMsg = error.data?.error || t('zenith.ask_failed')
    zenithMessages.value.push({
      role: 'assistant',
      content: `Error: ${errorMsg}`
    })
    toastStore.error(errorMsg)
  } finally {
    zenithAsking.value = false
  }
}

watch(visible, (show) => {
  if (show) {
    zenithMessages.value = []
    zenithQuestion.value = ''
  }
})
</script>
