<template>
  <div v-if="shares.length || isOwner" class="card p-4 mb-6">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
        <Coins :size="16" />
        {{ $t('energy.shares.title') }} ({{ shares.length }})
      </h3>
      <button
        v-if="isOwner && !showAddForm"
        @click="showAddForm = true"
        class="text-xs text-secondary-600 dark:text-secondary-400 hover:underline"
      >
        + {{ $t('energy.shares.add') }}
      </button>
    </div>

    <!-- Add form -->
    <form v-if="showAddForm" @submit.prevent="addShare" class="space-y-3 mb-4 p-3 bg-neutral-50 dark:bg-neutral-800/50 rounded-lg">
      <div>
        <input
          v-model="form.profile_id"
          required
          :placeholder="$t('energy.shares.profile_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm font-mono focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
        />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <input
          v-model.number="form.share_percent"
          type="number"
          step="0.001"
          min="0.001"
          max="100"
          required
          :placeholder="$t('energy.shares.percent_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
        />
        <input
          v-model.number="form.invested_amount"
          type="number"
          step="0.01"
          min="0"
          :placeholder="$t('energy.shares.amount_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
        />
      </div>
      <div class="flex gap-2">
        <UiButton variant="outline" size="xs" @click="showAddForm = false">{{ $t('common.cancel') }}</UiButton>
        <UiButton variant="primary" tag="button" type="submit" size="xs" :loading="adding">{{ $t('energy.shares.add') }}</UiButton>
      </div>
    </form>

    <!-- Share list -->
    <div v-if="shares.length" class="space-y-2">
      <div
        v-for="s in shares"
        :key="s.id"
        class="flex items-center justify-between py-2 text-sm"
      >
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-neutral-900 dark:text-neutral-100 truncate">{{ s.profile_name || s.profile_id.slice(0, 8) }}</span>
          <span class="px-1.5 py-0.5 rounded text-xs bg-secondary-100 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400 flex-shrink-0">
            {{ s.share_percent }}%
          </span>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span v-if="s.invested_amount" class="text-xs text-neutral-400">
            {{ s.invested_amount }}{{ s.invested_currency === 'EUR' ? '€' : ` ${s.invested_currency}` }}
          </span>
          <button
            v-if="isOwner"
            @click="removeShare(s)"
            class="p-1 text-error-400 hover:text-error-600 rounded"
          >
            <Trash2 :size="14" />
          </button>
        </div>
      </div>
    </div>
    <p v-else-if="!showAddForm" class="text-xs text-neutral-400 italic">{{ $t('energy.shares.no_shares') }}</p>

    <!-- Total bar -->
    <div v-if="shares.length" class="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700 flex items-center gap-3 text-xs">
      <div class="flex-1 h-2 bg-neutral-100 dark:bg-neutral-700 rounded-full overflow-hidden">
        <div
          class="h-full bg-secondary-500 rounded-full transition-all"
          :style="{ width: `${Math.min(totalPercent, 100)}%` }"
        />
      </div>
      <span class="text-neutral-500 flex-shrink-0">
        {{ $t('energy.shares.total_allocated', { percent: totalPercent.toFixed(1) }) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Coins, Trash2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const props = defineProps<{
  objectId: string
  isOwner: boolean
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const shares = ref<any[]>([])
const showAddForm = ref(false)
const adding = ref(false)
const form = ref({ profile_id: '', share_percent: null as number | null, invested_amount: null as number | null })

const totalPercent = computed(() =>
  shares.value.reduce((sum, s) => sum + parseFloat(s.share_percent), 0)
)

const fetchShares = async () => {
  try {
    shares.value = await $fetch<any[]>(`/api/v1/core/shares/?object_id=${props.objectId}`)
  } catch { shares.value = [] }
}

const addShare = async () => {
  if (!form.value.profile_id || !form.value.share_percent) return
  adding.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/core/shares/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        object_id: props.objectId,
        profile_id: form.value.profile_id,
        share_type: 'INVESTMENT',
        share_percent: form.value.share_percent,
        invested_amount: form.value.invested_amount || undefined,
      },
    })
    toastStore.success(t('energy.shares.added'))
    showAddForm.value = false
    form.value = { profile_id: '', share_percent: null, invested_amount: null }
    await fetchShares()
  } catch (e: any) {
    toastStore.error(e?.data?.error || t('common.error'))
  } finally { adding.value = false }
}

const removeShare = async (s: any) => {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/core/shares/${s.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    shares.value = shares.value.filter(x => x.id !== s.id)
  } catch (e: any) {
    toastStore.error(e?.data?.error || t('common.error'))
  }
}

onMounted(fetchShares)
</script>
