<template>
  <div v-if="!barterLoading" class="mb-4">
    <!-- Has Barter Chains -->
    <div v-if="barterOpportunities && barterOpportunities.chains_count > 0">
      <!-- Mobile: Simple Banner with Button -->
      <div class="md:hidden bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/30 rounded-lg p-3 space-y-3">
        <div class="flex items-center gap-2">
          <RefreshCw class="w-5 h-5 text-primary" />
          <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {{ $t('barter.stats.chains_found') }}: {{ barterOpportunities.chains_count }}
          </span>
        </div>
        <NuxtLink
          :to="localePath('/barter')"
          class="block w-full text-center px-3 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 text-sm"
        >
          {{ $t('barter.view_chains') }}
        </NuxtLink>
      </div>

      <!-- Desktop: Inline Stats Bar -->
      <div class="hidden md:flex items-center justify-between bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/30 rounded-lg p-3">
        <div class="flex items-center gap-4">
          <RefreshCw class="w-5 h-5 text-primary" />
          <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('barter.description') }}</span>
          <span class="text-sm text-neutral-600 dark:text-neutral-400">
            {{ $t('barter.stats.chains_found') }}: <strong class="text-neutral-900 dark:text-neutral-100">{{ barterOpportunities.chains_count }}</strong>
          </span>
        </div>
        <NuxtLink
          :to="localePath('/barter')"
          class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 text-sm"
        >
          {{ $t('barter.view_chains') }}
        </NuxtLink>
      </div>
    </div>

    <!-- No Barter Chains - Promotional Banner -->
    <div v-else>
      <!-- Mobile: Collapsible Info Banner -->
      <div class="md:hidden">
        <button
          @click="barterExpanded = !barterExpanded"
          class="w-full bg-gradient-to-r from-secondary-50 to-purple-50 dark:from-secondary-900/30 dark:to-purple-950/30 border border-secondary-200 dark:border-secondary-800 rounded-lg p-3 flex items-center justify-between text-left hover:from-secondary-100 hover:to-purple-100 dark:hover:from-secondary-900/50 dark:hover:to-purple-950/50 transition-colors"
        >
          <div class="flex items-center gap-2">
            <RefreshCw class="w-5 h-5 text-primary" />
            <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">
              {{ $t('barter.promo.title') }}
            </span>
          </div>
          <ChevronDown class="w-4 h-4 text-neutral-600 dark:text-neutral-400 transition-transform" :class="{ 'rotate-180': barterExpanded }" />
        </button>

        <!-- Expanded info -->
        <div v-if="barterExpanded" class="mt-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-3">
          <p class="text-sm text-neutral-700 dark:text-neutral-300">
            {{ $t('barter.promo.description') }}
          </p>
          <div class="flex items-start gap-2 text-xs text-neutral-600 dark:text-neutral-400">
            <span>💡</span>
            <p>{{ $t('barter.promo.how_it_works') }}</p>
          </div>
          <NuxtLink
            :to="localePath('/barter')"
            class="block w-full text-center px-3 py-2 bg-gradient-to-r from-secondary to-purple-500 text-white font-medium rounded-lg hover:from-secondary-600 hover:to-purple-600 text-sm"
          >
            {{ $t('barter.promo.learn_more') }}
          </NuxtLink>
        </div>
      </div>

      <!-- Desktop: Inline Promo Banner -->
      <NuxtLink
        :to="localePath('/barter')"
        class="hidden md:flex items-center justify-between bg-gradient-to-r from-secondary-50 to-purple-50 dark:from-secondary-900/30 dark:to-purple-950/30 border border-secondary-200 dark:border-secondary-800 rounded-lg p-3 hover:from-secondary-100 hover:to-purple-100 dark:hover:from-secondary-900/50 dark:hover:to-purple-950/50 transition-colors group"
      >
        <div class="flex items-center gap-3">
          <RefreshCw class="w-6 h-6 text-primary" />
          <div>
            <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('barter.promo.title') }}</div>
            <div class="text-xs text-neutral-600 dark:text-neutral-400">{{ $t('barter.promo.tagline') }}</div>
          </div>
        </div>
        <div class="px-3 py-1 bg-gradient-to-r from-secondary to-purple-500 text-white text-xs font-medium rounded-full group-hover:from-secondary-600 group-hover:to-purple-600 transition-colors">
          {{ $t('barter.promo.learn_more') }}
        </div>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { RefreshCw, ChevronDown } from 'lucide-vue-next'

const authStore = useAuthStore()
const localePath = useLocalePath()

const barterOpportunities = ref(null)
const barterLoading = ref(true)
const barterExpanded = ref(false)

const fetchBarterOpportunities = async () => {
  if (!authStore.isAuthenticated) {
    barterLoading.value = false
    return
  }

  try {
    await authStore.ensureToken()

    const response = await $fetch('/api/v1/barter/opportunities', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    barterOpportunities.value = response
  } catch (error) {
    console.error('Failed to fetch barter opportunities:', error)
  } finally {
    barterLoading.value = false
  }
}

onMounted(() => {
  fetchBarterOpportunities()
})
</script>
