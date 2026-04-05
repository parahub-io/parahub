<template>
  <div v-if="establishments.length > 0">
    <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
      {{ $t('directory.act_as.post_as') }}
    </label>
    <div class="flex flex-wrap gap-2">
      <!-- Personal (default) -->
      <button
        type="button"
        @click="select(null)"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm border transition-colors',
          !modelValue
            ? 'border-primary bg-primary/10 text-neutral-900 dark:text-neutral-100 font-medium'
            : 'border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800'
        ]"
      >
        {{ $t('directory.act_as.personal') }}
      </button>
      <!-- Establishments -->
      <button
        v-for="est in establishments"
        :key="est.id"
        type="button"
        @click="select(est.id)"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm border transition-colors flex items-center gap-1.5',
          modelValue === est.id
            ? 'border-primary bg-primary/10 text-neutral-900 dark:text-neutral-100 font-medium'
            : 'border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800'
        ]"
      >
        <img
          v-if="est.logo_url"
          :src="est.logo_url"
          :alt="est.name"
          class="w-4 h-4 rounded-full object-cover"
        >
        <Building2 v-else class="w-4 h-4" />
        {{ est.name }}
        <span class="text-xs text-neutral-400 dark:text-neutral-500 font-normal">{{ est.role }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Building2 } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: String, default: null }
})

const emit = defineEmits(['update:modelValue'])

const authStore = useAuthStore()

interface PostableEstablishment {
  id: string
  name: string
  slug: string | null
  logo_url: string | null
  role: string
}

const establishments = ref<PostableEstablishment[]>([])

const select = (id: string | null) => {
  emit('update:modelValue', id)
}

const fetchEstablishments = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.accessToken) return

    const data = await $fetch<PostableEstablishment[]>('/api/v1/geo/establishments/my-postable/', {
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })
    establishments.value = data
  } catch (err) {
    // Silently fail — selector just won't show
    console.error('Failed to fetch postable establishments:', err)
  }
}

onMounted(() => {
  fetchEstablishments()
})
</script>
