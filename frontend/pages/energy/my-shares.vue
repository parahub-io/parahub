<template>
  <div>
    <Head>
      <Title>{{ $t('energy.shares.my_shares_title') }} — Parahub</Title>
    </Head>

    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">

      <!-- Back link -->
      <NuxtLink
        :to="localePath('/energy')"
        class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 mb-4"
      >
        <ArrowLeft :size="16" />
        {{ $t('energy.title') }}
      </NuxtLink>

      <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-1">
        {{ $t('energy.shares.my_shares_title') }}
      </h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">
        {{ $t('energy.shares.my_shares_subtitle') }}
      </p>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12" role="status">
        <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" />
        <span class="sr-only">Loading</span>
      </div>

      <template v-else-if="shares.length">
        <!-- Summary -->
        <div class="grid grid-cols-2 gap-3 mb-6">
          <div class="card p-4 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ totalInvested }}€</div>
            <div class="text-xs text-neutral-500">{{ $t('energy.shares.total_invested') }}</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ shares.length }}</div>
            <div class="text-xs text-neutral-500">{{ $t('energy.shares.active_shares') }}</div>
          </div>
        </div>

        <!-- Shares list -->
        <div class="space-y-3">
          <div
            v-for="s in shares"
            :key="s.id"
            class="card p-4 hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors"
          >
            <div class="flex items-center justify-between">
              <div class="flex-1 min-w-0">
                <div class="font-medium text-neutral-900 dark:text-neutral-100 text-sm truncate">
                  {{ s._entity_name || s.object_id.slice(0, 12) + '...' }}
                </div>
                <div class="flex items-center gap-3 mt-0.5 text-xs text-neutral-500">
                  <span class="font-medium text-secondary-600 dark:text-secondary-400">{{ s.share_percent }}%</span>
                  <span v-if="s.invested_amount">
                    {{ $t('energy.shares.invested') }}: {{ s.invested_amount }}{{ s.invested_currency === 'EUR' ? '€' : ` ${s.invested_currency}` }}
                  </span>
                </div>
              </div>
              <div class="text-right text-xs text-neutral-400 flex-shrink-0">
                <div v-if="s.invested_at">
                  {{ new Date(s.invested_at).toLocaleDateString() }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Empty state -->
      <div v-else class="text-center py-12">
        <Coins :size="48" class="mx-auto text-neutral-300 dark:text-neutral-600 mb-4" />
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('energy.shares.no_my_shares') }}
        </h3>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, Coins } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const authStore = useAuthStore()
const localePath = useLocalePath()

const shares = ref<any[]>([])
const loading = ref(true)

const totalInvested = computed(() =>
  shares.value
    .filter(s => s.invested_amount)
    .reduce((sum, s) => sum + parseFloat(s.invested_amount), 0)
    .toFixed(2)
)

onMounted(async () => {
  if (!authStore.isAuthenticated || !authStore.profile) {
    loading.value = false
    return
  }
  try {
    await authStore.ensureToken()
    shares.value = await $fetch<any[]>(`/api/v1/core/shares/`, {
      params: { profile_id: authStore.profile.id },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch {
    shares.value = []
  }
  loading.value = false
})
</script>
