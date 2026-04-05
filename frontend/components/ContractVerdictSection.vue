<template>
  <div class="space-y-4">
    <!-- Verdict display (when exists) -->
    <div v-if="contract.verdict" class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.verdict.title').toUpperCase() }}</div>
      <div class="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded p-3 space-y-2">
        <div class="flex items-center gap-2">
          <span :class="verdictBadgeClass" class="px-2 py-0.5 rounded text-xs font-medium">
            {{ verdictLabel }}
          </span>
          <span v-if="contract.verdict.amount_awarded" class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {{ contract.verdict.amount_awarded }} {{ contract.verdict.currency }}
          </span>
        </div>
        <p class="text-sm text-neutral-700 dark:text-neutral-300">{{ contract.verdict.summary }}</p>
        <div class="text-xs text-neutral-400 dark:text-neutral-500">
          <NuxtLink :to="localePath(`/arbiters/${contract.arbiter_id}`)" class="text-link">
            {{ contract.verdict.arbiter_display_name }}
          </NuxtLink>
          &middot; {{ new Date(contract.verdict.created_at).toLocaleDateString() }}
        </div>

        <!-- Arbiter ratings -->
        <div v-if="contract.verdict.creator_arbiter_rating || contract.verdict.partner_arbiter_rating" class="flex gap-4 text-xs text-neutral-500 dark:text-neutral-400 pt-1 border-t border-neutral-200 dark:border-neutral-700">
          <span v-if="contract.verdict.creator_arbiter_rating">
            {{ contract.creator_display_name }}: {{ '★'.repeat(contract.verdict.creator_arbiter_rating) }}{{ '☆'.repeat(5 - contract.verdict.creator_arbiter_rating) }}
          </span>
          <span v-if="contract.verdict.partner_arbiter_rating">
            {{ contract.partner_display_name }}: {{ '★'.repeat(contract.verdict.partner_arbiter_rating) }}{{ '☆'.repeat(5 - contract.verdict.partner_arbiter_rating) }}
          </span>
        </div>

        <!-- Rate arbiter button (if I haven't rated yet) -->
        <div v-if="canRateArbiter" class="pt-2 border-t border-neutral-200 dark:border-neutral-700">
          <div class="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('contracts.verdict.rate_arbiter') }}</div>
          <div class="flex items-center gap-2">
            <div class="flex gap-1">
              <button
                v-for="star in 5"
                :key="star"
                type="button"
                @click="arbiterRating = star"
                class="text-xl transition-colors"
                :class="star <= arbiterRating ? 'text-yellow-400' : 'text-neutral-300 dark:text-neutral-600'"
              >
                ★
              </button>
            </div>
            <button
              @click="$emit('rate-arbiter', { contractId: contract.id, rating: arbiterRating })"
              :disabled="ratingArbiter"
              class="btn-primary btn-xs"
            >
              {{ ratingArbiter ? '...' : $t('contracts.verdict.your_rating') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Submit verdict (arbiter only, no verdict yet) -->
    <div v-if="isArbiter && !contract.verdict && contract.arbitration_room_id" class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.verdict.submit').toUpperCase() }}</div>
      <div class="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded p-3 space-y-3">
        <div>
          <label class="block text-xs font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.verdict.type_label') }}</label>
          <select v-model="verdictForm.verdict_type" class="w-full px-2 py-1.5 text-sm border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100">
            <option value="FAVOR_CREATOR">{{ $t('contracts.verdict.favor_creator') }}</option>
            <option value="FAVOR_PARTNER">{{ $t('contracts.verdict.favor_partner') }}</option>
            <option value="PARTIAL">{{ $t('contracts.verdict.partial') }}</option>
            <option value="DISMISSED">{{ $t('contracts.verdict.dismissed') }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.verdict.summary_label') }}</label>
          <textarea
            v-model="verdictForm.summary"
            rows="3"
            :placeholder="$t('contracts.verdict.summary_placeholder')"
            class="w-full px-2 py-1.5 text-sm border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
          ></textarea>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="block text-xs font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.verdict.amount_label') }}</label>
            <input v-model="verdictForm.amount_awarded" type="number" step="0.01" class="w-full px-2 py-1.5 text-sm border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100" />
          </div>
          <div>
            <label class="block text-xs font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.verdict.currency_label') }}</label>
            <input v-model="verdictForm.currency" type="text" maxlength="3" placeholder="EUR" class="w-full px-2 py-1.5 text-sm border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100" />
          </div>
        </div>
        <button
          @click="$emit('submit-verdict', { contractId: contract.id, ...verdictForm })"
          :disabled="submittingVerdict || !verdictForm.summary.trim()"
          class="btn-primary btn-sm w-full"
        >
          {{ submittingVerdict ? $t('contracts.verdict.submitting') : $t('contracts.verdict.submit') }}
        </button>
      </div>
    </div>

    <!-- Arbitration level indicator + escalate -->
    <div v-if="contract.arbitration_room_id" class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.arbitration.level').toUpperCase() }}</div>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-1">
          <span
            v-for="level in 3"
            :key="level"
            :class="[
              'w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border-2',
              level <= contract.arbitration_level
                ? 'border-amber-500 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                : 'border-neutral-300 dark:border-neutral-600 text-neutral-400 dark:text-neutral-500'
            ]"
          >
            {{ level }}
          </span>
        </div>
        <span class="text-xs text-neutral-600 dark:text-neutral-400">
          {{ levelLabel }}
        </span>
        <button
          v-if="canEscalate"
          @click="$emit('escalate', contract.id)"
          class="ml-auto btn-outline-warning btn-xs"
          :disabled="escalating"
        >
          {{ $t('contracts.arbitration.escalate') }}
        </button>
      </div>
      <div v-if="contract.arbitration_escalated_at" class="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
        {{ $t('contracts.arbitration.escalated_at') }}: {{ new Date(contract.arbitration_escalated_at).toLocaleDateString() }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useAuthStore } from '~/stores/auth'

const props = defineProps({
  contract: { type: Object, required: true },
  submittingVerdict: { type: Boolean, default: false },
  ratingArbiter: { type: Boolean, default: false },
  escalating: { type: Boolean, default: false },
})

defineEmits(['submit-verdict', 'rate-arbiter', 'escalate'])

const { t: $t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const arbiterRating = ref(5)
const verdictForm = ref({
  verdict_type: 'FAVOR_CREATOR',
  summary: '',
  amount_awarded: null,
  currency: 'EUR',
})

const myId = computed(() => authStore.activeProfile?.id)
const isArbiter = computed(() => myId.value === props.contract.arbiter_id)
const isCreator = computed(() => myId.value === props.contract.creator_id)
const isPartner = computed(() => myId.value === props.contract.partner_id)

const canRateArbiter = computed(() => {
  if (!props.contract.verdict) return false
  if (isCreator.value && props.contract.verdict.creator_arbiter_rating == null) return true
  if (isPartner.value && props.contract.verdict.partner_arbiter_rating == null) return true
  return false
})

const canEscalate = computed(() => {
  if (!props.contract.arbitration_room_id) return false
  if (props.contract.arbitration_level >= 3) return false
  return isCreator.value || isPartner.value
})

const levelLabel = computed(() => {
  const l = props.contract.arbitration_level
  if (l === 1) return $t('contracts.arbitration.level_p2p')
  if (l === 2) return $t('contracts.arbitration.level_cac')
  return $t('contracts.arbitration.level_court')
})

const verdictLabel = computed(() => {
  const v = props.contract.verdict?.verdict_type
  const map = {
    FAVOR_CREATOR: $t('contracts.verdict.favor_creator'),
    FAVOR_PARTNER: $t('contracts.verdict.favor_partner'),
    PARTIAL: $t('contracts.verdict.partial'),
    DISMISSED: $t('contracts.verdict.dismissed'),
  }
  return map[v] || v
})

const verdictBadgeClass = computed(() => {
  const v = props.contract.verdict?.verdict_type
  if (v === 'FAVOR_CREATOR') return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
  if (v === 'FAVOR_PARTNER') return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
  if (v === 'PARTIAL') return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
  return 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400'
})
</script>
