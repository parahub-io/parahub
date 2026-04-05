<template>
  <div v-if="distributions.length || isOwner" class="card p-4 mb-6">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
        <Banknote :size="16" />
        {{ $t('energy.distributions.title') }} ({{ distributions.length }})
      </h3>
      <button
        v-if="isOwner && !showCreateForm"
        @click="showCreateForm = true"
        class="text-xs text-secondary-600 dark:text-secondary-400 hover:underline"
      >
        + {{ $t('energy.distributions.create') }}
      </button>
    </div>

    <!-- Create form -->
    <form v-if="showCreateForm" @submit.prevent="createDist" class="space-y-3 mb-4 p-3 bg-neutral-50 dark:bg-neutral-800/50 rounded-lg">
      <div class="grid grid-cols-2 gap-3">
        <input
          v-model="form.period_label"
          required
          :placeholder="$t('energy.distributions.period_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
        />
        <input
          v-model.number="form.total_amount"
          type="number"
          step="0.01"
          min="0.01"
          required
          :placeholder="$t('energy.distributions.amount_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
        />
      </div>
      <div class="flex gap-2">
        <UiButton variant="outline" size="xs" @click="showCreateForm = false">{{ $t('common.cancel') }}</UiButton>
        <UiButton variant="primary" tag="button" type="submit" size="xs" :loading="creating">{{ $t('energy.distributions.create') }}</UiButton>
      </div>
    </form>

    <!-- Distribution list -->
    <div v-if="distributions.length" class="space-y-2">
      <div
        v-for="d in distributions"
        :key="d.id"
        class="p-3 rounded-lg border border-neutral-200 dark:border-neutral-700"
      >
        <div class="flex items-center justify-between mb-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ d.period_label }}</span>
            <span
              class="px-1.5 py-0.5 rounded text-xs"
              :class="{
                'bg-neutral-100 dark:bg-neutral-700 text-neutral-500': d.status === 'DRAFT',
                'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400': d.status === 'APPROVED',
                'bg-success-100 dark:bg-success-900/30 text-success-700 dark:text-success-400': d.status === 'DISTRIBUTED',
              }"
            >
              {{ $t(`energy.distributions.status_${d.status}`) }}
            </span>
          </div>
          <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ d.total_amount }}€</span>
        </div>

        <div v-if="d.lines_count > 0" class="text-xs text-neutral-400">
          {{ $t('energy.distributions.lines_paid', { paid: d.lines_paid, total: d.lines_count }) }}
        </div>

        <!-- Owner actions -->
        <div v-if="isOwner && d.status === 'DRAFT'" class="mt-2">
          <UiButton variant="primary" size="xs" :loading="d._approving" @click="approveDist(d)">
            {{ $t('energy.distributions.approve') }}
          </UiButton>
        </div>

        <!-- Lines (expanded for APPROVED) -->
        <div v-if="d.status === 'APPROVED' && d._lines" class="mt-2 space-y-1">
          <div
            v-for="line in d._lines"
            :key="line.id"
            class="flex items-center justify-between text-xs py-1"
          >
            <span class="text-neutral-600 dark:text-neutral-400">{{ line.profile_name || line.profile_id.slice(0, 8) }}</span>
            <div class="flex items-center gap-2">
              <span class="text-neutral-700 dark:text-neutral-300">{{ line.amount }}€ ({{ line.share_percent }}%)</span>
              <UiButton
                v-if="isOwner && line.status === 'PENDING'"
                variant="outline" size="xs"
                @click="markPaid(d, line)"
              >
                {{ $t('energy.distributions.mark_paid') }}
              </UiButton>
              <span v-else-if="line.status === 'PAID'" class="text-success-500">&#10003;</span>
            </div>
          </div>
        </div>

        <!-- Toggle lines -->
        <button
          v-if="d.lines_count > 0 && d.status !== 'DRAFT'"
          @click="toggleLines(d)"
          class="text-xs text-secondary-500 hover:underline mt-1"
        >
          {{ d._lines ? $t('common.hide') : $t('common.show_details') }}
        </button>
      </div>
    </div>
    <p v-else-if="!showCreateForm" class="text-xs text-neutral-400 italic">{{ $t('energy.distributions.no_distributions') }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Banknote } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const props = defineProps<{
  objectId: string
  isOwner: boolean
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const distributions = ref<any[]>([])
const showCreateForm = ref(false)
const creating = ref(false)
const form = ref({ period_label: '', total_amount: null as number | null })

const authHeaders = async () => {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

const fetchDistributions = async () => {
  try {
    distributions.value = await $fetch<any[]>(`/api/v1/core/distributions/?object_id=${props.objectId}`)
  } catch { distributions.value = [] }
}

const createDist = async () => {
  if (!form.value.period_label || !form.value.total_amount) return
  creating.value = true
  try {
    await $fetch('/api/v1/core/distributions/', {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
      body: {
        object_id: props.objectId,
        period_label: form.value.period_label,
        total_amount: form.value.total_amount,
      },
    })
    toastStore.success(t('energy.distributions.created'))
    showCreateForm.value = false
    form.value = { period_label: '', total_amount: null }
    await fetchDistributions()
  } catch (e: any) {
    toastStore.error(e?.data?.error || t('common.error'))
  } finally { creating.value = false }
}

const approveDist = async (d: any) => {
  d._approving = true
  try {
    const result = await $fetch<any>(`/api/v1/core/distributions/${d.id}/approve/`, {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
    })
    toastStore.success(t('energy.distributions.approved', { count: result.lines_count }))
    await fetchDistributions()
  } catch (e: any) {
    toastStore.error(e?.data?.error || t('common.error'))
  } finally { d._approving = false }
}

const toggleLines = async (d: any) => {
  if (d._lines) {
    d._lines = null
    return
  }
  try {
    d._lines = await $fetch<any[]>(`/api/v1/core/distributions/${d.id}/lines/`)
  } catch { d._lines = [] }
}

const markPaid = async (d: any, line: any) => {
  try {
    await $fetch(`/api/v1/core/distributions/${d.id}/lines/${line.id}/pay/`, {
      method: 'POST',
      credentials: 'include',
      headers: await authHeaders(),
    })
    line.status = 'PAID'
    d.lines_paid = (d.lines_paid || 0) + 1
    if (d.lines_paid >= d.lines_count) d.status = 'DISTRIBUTED'
  } catch (e: any) {
    toastStore.error(e?.data?.error || t('common.error'))
  }
}

onMounted(fetchDistributions)
</script>
