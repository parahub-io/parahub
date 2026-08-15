<template>
  <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-4">
    <h2 class="flex items-center gap-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
      <Ban class="w-4 h-4 text-primary" />
      {{ $t('moderation.blocked_users') }}
    </h2>
    <div class="space-y-4">
      <p class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ $t('moderation.blocked_users_desc') }}
      </p>

      <div v-if="loading" class="flex justify-center py-4" role="status">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <div v-else-if="blocked.length" class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <div
          v-for="profile in blocked"
          :key="profile.id"
          class="flex items-center gap-3 px-3 py-2.5"
        >
          <img
            v-if="profile.avatar_url"
            :src="profile.avatar_url"
            :alt="profile.local_name"
            class="w-8 h-8 rounded-full object-cover shrink-0"
          />
          <div v-else class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center shrink-0">
            <User class="w-4 h-4 text-neutral-500 dark:text-neutral-400" aria-hidden="true" />
          </div>
          <NuxtLink :to="localePath(`/@${profile.local_name}`)" class="min-w-0 flex-1">
            <span class="block text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ profile.display_name || profile.local_name }}</span>
            <span class="block text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ profile.hna }}</span>
          </NuxtLink>
          <UiButton variant="outline" size="sm" :loading="unblockingId === profile.id" @click="unblock(profile)">
            {{ $t('moderation.unblock') }}
          </UiButton>
        </div>
      </div>

      <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">
        {{ $t('moderation.blocked_empty') }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Ban, User } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const { t: $t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()

const blocked = ref<any[]>([])
const loading = ref(true)
const unblockingId = ref<string | null>(null)

async function loadBlocked() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<{ items: any[]; count: number }>('/api/v1/profiles/blocked/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    blocked.value = res.items
  } catch (error) {
    console.error('Failed to load blocked users:', error)
  } finally {
    loading.value = false
  }
}

async function unblock(profile: any) {
  unblockingId.value = profile.id
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/profiles/${profile.id}/block/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    blocked.value = blocked.value.filter(p => p.id !== profile.id)
    toastStore.success($t('moderation.unblocked_toast'))
  } catch (error) {
    console.error('Failed to unblock:', error)
    toastStore.error($t('moderation.block_error'))
  } finally {
    unblockingId.value = null
  }
}

onMounted(loadBlocked)
</script>
