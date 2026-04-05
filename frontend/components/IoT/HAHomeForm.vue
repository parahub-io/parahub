<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
    <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
      {{ editing ? $t('ha.edit_home') : $t('ha.add_home') }}
    </h3>

    <form @submit.prevent="submit" class="space-y-4">
      <!-- Name -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('ha.name') }}
        </label>
        <input v-model="form.name" type="text" required maxlength="100"
               class="input-base w-full"
               :placeholder="$t('ha.name_placeholder')" />
      </div>

      <!-- URL -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('ha.url') }}
        </label>
        <input v-model="form.url" type="url" required
               class="input-base w-full"
               placeholder="http://[200:xxxx::]:8123" />
        <p class="text-xs text-neutral-500 mt-1">{{ $t('ha.url_hint') }}</p>
      </div>

      <!-- Access Token -->
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('ha.access_token') }}
        </label>
        <div class="relative">
          <input v-model="form.accessToken" :type="showToken ? 'text' : 'password'" :required="!editing"
                 class="input-base w-full pr-10"
                 :placeholder="editing ? $t('ha.token_unchanged') : $t('ha.token_placeholder')" />
          <button type="button" @click="showToken = !showToken"
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300">
            <component :is="showToken ? EyeOff : Eye" class="w-4 h-4" />
          </button>
        </div>
        <p class="text-xs text-neutral-500 mt-1">{{ $t('ha.token_hint') }}</p>
      </div>

      <!-- Error -->
      <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

      <!-- Actions -->
      <div class="flex items-center gap-3 pt-2">
        <button type="submit" class="btn-primary gap-1" :disabled="submitting">
          <Loader2 v-if="submitting" class="w-4 h-4 animate-spin" />
          {{ editing ? $t('ha.save') : $t('ha.add') }}
        </button>
        <button type="button" @click="$emit('cancel')" class="btn-outline">
          {{ $t('ha.cancel') }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { Eye, EyeOff, Loader2 } from 'lucide-vue-next'
import type { HAHome } from '~/stores/ha'

const props = defineProps<{
  home?: HAHome | null
  propertyId?: string | null
}>()

const emit = defineEmits<{
  submit: [data: { name: string; url: string; accessToken: string }]
  cancel: []
}>()

const editing = computed(() => !!props.home)
const showToken = ref(false)
const submitting = ref(false)
const error = ref('')

const form = reactive({
  name: props.home?.name || '',
  url: props.home?.url || '',
  accessToken: '',
})

const haStore = useHAStore()

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    if (editing.value && props.home) {
      const data: Record<string, any> = {}
      if (form.name !== props.home.name) data.name = form.name
      if (form.url !== props.home.url) data.url = form.url
      if (form.accessToken) data.access_token = form.accessToken
      await haStore.updateHome(props.home.id, data)
    } else {
      if (!form.accessToken) { error.value = 'Access token is required'; return }
      await haStore.createHome(form.name, form.url, form.accessToken, props.propertyId || undefined)
    }
    emit('submit', { name: form.name, url: form.url, accessToken: form.accessToken })
  } catch (e: any) {
    error.value = e.data?.detail || e.message || 'Failed'
  } finally {
    submitting.value = false
  }
}
</script>
