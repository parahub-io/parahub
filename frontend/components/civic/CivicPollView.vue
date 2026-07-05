<template>
  <div class="space-y-6">
    <!-- Scope + status row -->
    <div class="flex flex-wrap items-center gap-2">
      <CivicScopeBadge :level="poll.scope_level" :name="poll.scope_name" />
      <UiBadge variant="secondary" type="soft" :title="$t('civic.badgeHint')">{{ $t('civic.badge') }}</UiBadge>
      <UiBadge v-if="poll.status === 'ended'" variant="neutral" type="soft">{{ $t('civic.results.ended') }}</UiBadge>
    </div>

    <!-- Efficacy: where this goes / outcome -->
    <UiAlert v-if="poll.civic_destination" variant="info" :icon="Send">
      <span class="font-medium">{{ $t('civic.destination') }}:</span> {{ poll.civic_destination }}
    </UiAlert>
    <UiAlert v-if="poll.civic_outcome" variant="success" :icon="CheckCircle" :title="$t('civic.outcome')">
      {{ poll.civic_outcome }}
    </UiAlert>

    <!-- Consent inline screen (U6) -->
    <CivicConsentInline
      v-if="showConsent"
      :loading="voting"
      @accept="acceptConsentAndVote"
      @decline="showConsent = false"
    />

    <!-- Locked ballot: standing delegation holds this voice (Phase 2.5) -->
    <div
      v-else-if="poll.status === 'active' && results?.delegation && !overrideMode && (results?.my_vote_via || !results?.my_vote)"
      class="card p-4 border-secondary/40"
    >
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1 flex items-center gap-2">
        <GitBranch class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
        {{ $t('civic.delegations.lockedTitle', { name: results.delegation.delegate_display_name || results.delegation.delegate_hna.split('@')[0] }) }}
      </h2>
      <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
        <template v-if="results.delegation.has_cast">
          {{ $t('civic.delegations.lockedCast', { date: formatDateTime(results.delegation.cast_at) }) }}
          <template v-if="myVote && myVoteText"> — <span class="font-medium text-neutral-800 dark:text-neutral-200">{{ myVoteText }}</span></template>
        </template>
        <template v-else>{{ $t('civic.delegations.lockedNotCast') }}</template>
      </p>
      <UiButton variant="outline" size="sm" @click="overrideMode = true">
        {{ $t('civic.delegations.override') }}
      </UiButton>
    </div>

    <!-- Vote panel -->
    <div v-else-if="poll.status === 'active'" class="card p-4">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1 flex items-center gap-2">
        <Vote class="w-5 h-5" aria-hidden="true" />
        {{ $t('civic.vote.title') }}
      </h2>
      <p v-if="myVote || results?.my_values" class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
        {{ $t('civic.vote.changeHint') }}
      </p>

      <div v-if="!authStore.isAuthenticated" class="py-4">
        <UiButton variant="primary" :to="localePath('/auth/login')">{{ $t('civic.vote.loginCta') }}</UiButton>
      </div>

      <!-- Slider ballot (U3): status-quo-relative axes -->
      <div v-else-if="poll.poll_type === 'sliders'" class="space-y-5">
        <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('civic.sliders.hint') }}</p>
        <div v-for="option in poll.options" :key="option.id">
          <div class="flex justify-between items-baseline mb-1 gap-2">
            <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200">{{ option.text }}</span>
            <span class="text-xs font-medium text-secondary dark:text-secondary-400 whitespace-nowrap">
              {{ anchorLabel(sliderValues[option.id] ?? 0) }}
            </span>
          </div>
          <input
            type="range" min="-2" max="2" step="1"
            :value="sliderValues[option.id] ?? 0"
            @input="sliderValues[option.id] = Number(($event.target as HTMLInputElement).value)"
            class="w-full accent-secondary"
          />
          <div class="flex justify-between text-[10px] text-neutral-400 dark:text-neutral-500 mt-0.5">
            <span>{{ $t('civic.sliders.a_m2') }}</span>
            <span>{{ $t('civic.sliders.a_0') }}</span>
            <span>{{ $t('civic.sliders.a_p2') }}</span>
          </div>
        </div>
        <UiButton variant="primary" :loading="voting" @click="castSliderVote">
          {{ $t('civic.sliders.submit') }}
        </UiButton>
        <p v-if="voteError" class="text-sm text-error">{{ voteError }}</p>
        <p v-if="justChanged" class="text-sm text-success">{{ $t('civic.vote.changed') }}</p>
      </div>

      <div v-else class="space-y-2">
        <button
          v-for="option in poll.options"
          :key="option.id"
          @click="castVote(option.id)"
          :disabled="voting || option.id === myVote"
          class="w-full text-left px-4 py-3 rounded-lg border transition-colors flex items-center justify-between gap-3"
          :class="option.id === myVote
            ? 'border-secondary bg-secondary/10 dark:bg-secondary/20 text-neutral-900 dark:text-neutral-100'
            : 'border-neutral-300 dark:border-neutral-600 hover:bg-primary-100 dark:hover:bg-primary-900/40 text-neutral-800 dark:text-neutral-200'"
        >
          <span class="font-medium">{{ option.text }}</span>
          <CheckCircle v-if="option.id === myVote" class="w-5 h-5 text-secondary dark:text-secondary-400 shrink-0" aria-hidden="true" />
        </button>

        <p v-if="voteError" class="text-sm text-error mt-2">{{ voteError }}</p>
        <p v-if="justChanged" class="text-sm text-success mt-2">{{ $t('civic.vote.changed') }}</p>
      </div>
    </div>

    <!-- Results -->
    <div class="card p-4">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
          <BarChart3 class="w-5 h-5" aria-hidden="true" />
          {{ $t('civic.results.title') }}
        </h2>
        <span class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ $t('civic.results.participation') }}: {{ results?.n_display ?? '…' }}
        </span>
      </div>

      <!-- Loading -->
      <div v-if="!results" class="py-8 text-center" role="status" aria-live="polite">
        <div class="animate-spin rounded-full h-6 w-6 mx-auto border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Hidden until own vote (U2) -->
      <div v-else-if="results.hidden" class="py-12 text-center">
        <Lock class="w-12 h-12 mx-auto text-neutral-400 mb-3" aria-hidden="true" />
        <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('civic.results.hiddenTitle') }}
        </h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('civic.results.hiddenHint') }}</p>
      </div>

      <template v-else>
        <UiAlert v-if="results.quantized" variant="info" class="mb-4">
          {{ $t('civic.results.fewVotes') }}
        </UiAlert>
        <UiAlert v-if="results.frozen" variant="info" class="mb-4">
          {{ $t('civic.results.frozen') }}
        </UiAlert>

        <!-- Slider axes: 5-bucket distribution + median (U3) -->
        <div v-if="results.poll_type === 'sliders'" class="space-y-6">
          <div v-for="axis in results.axes" :key="axis.option_id">
            <div class="flex justify-between items-baseline mb-2 gap-2">
              <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200">{{ axis.text }}</span>
              <span v-if="axis.median !== null" class="text-xs text-neutral-600 dark:text-neutral-400 whitespace-nowrap">
                {{ $t('civic.sliders.median') }}:
                <span class="font-semibold text-secondary dark:text-secondary-400">{{ anchorLabel(Math.round(axis.median)) }}</span>
                ({{ axis.median > 0 ? '+' : '' }}{{ axis.median }})
              </span>
            </div>
            <div class="grid grid-cols-5 gap-1 items-end h-16">
              <div v-for="v in [-2, -1, 0, 1, 2]" :key="v" class="flex flex-col items-center justify-end h-full">
                <div
                  class="w-full rounded-t transition-all duration-700 ease-out"
                  :class="axis.median !== null && Math.round(axis.median) === v ? 'bg-secondary' : 'bg-neutral-300 dark:bg-neutral-600'"
                  :style="`height: ${Math.max(axis.distribution_pct?.[String(v)] ?? 0, 2)}%`"
                ></div>
              </div>
            </div>
            <div class="grid grid-cols-5 gap-1 text-center text-[10px] text-neutral-500 dark:text-neutral-400 mt-1">
              <span v-for="v in [-2, -1, 0, 1, 2]" :key="v">
                {{ axis.distribution_pct?.[String(v)] ?? 0 }}%
              </span>
            </div>
            <div class="grid grid-cols-5 gap-1 text-center text-[10px] text-neutral-400 dark:text-neutral-500">
              <span>{{ $t('civic.sliders.a_m2') }}</span>
              <span>{{ $t('civic.sliders.a_m1') }}</span>
              <span>{{ $t('civic.sliders.a_0') }}</span>
              <span>{{ $t('civic.sliders.a_p1') }}</span>
              <span>{{ $t('civic.sliders.a_p2') }}</span>
            </div>
            <p v-if="axis.median_verified !== null" class="text-xs text-neutral-500 dark:text-neutral-400 mt-1" :title="$t('civic.results.verifiedHint')">
              {{ $t('civic.results.verified') }}: {{ anchorLabel(Math.round(axis.median_verified)) }} ({{ axis.median_verified > 0 ? '+' : '' }}{{ axis.median_verified }})
            </p>
          </div>
        </div>

        <!-- Bars: dual display all / verified (A5) -->
        <div v-else class="space-y-4">
          <div v-for="opt in results.options" :key="opt.option_id">
            <div class="flex justify-between items-baseline mb-1 gap-2">
              <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200">{{ opt.text }}</span>
              <span class="text-sm text-neutral-600 dark:text-neutral-400 whitespace-nowrap">
                {{ opt.percent }}%<template v-if="opt.count !== null"> · {{ opt.count }}</template>
              </span>
            </div>
            <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-3 overflow-hidden">
              <div
                class="bg-secondary h-3 rounded-full transition-all duration-700 ease-out"
                :style="`width: ${opt.percent}%`"
              ></div>
            </div>
            <div class="flex items-center gap-2 mt-1" :title="$t('civic.results.verifiedHint')">
              <div class="flex-1 bg-neutral-100 dark:bg-neutral-800 rounded-full h-1.5 overflow-hidden">
                <div
                  class="bg-success h-1.5 rounded-full transition-all duration-700 ease-out"
                  :style="`width: ${opt.percent_verified}%`"
                ></div>
              </div>
              <span class="text-xs text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
                {{ $t('civic.results.verified') }}: {{ opt.percent_verified }}%<template v-if="opt.count_verified !== null"> · {{ opt.count_verified }}</template>
              </span>
            </div>
          </div>
        </div>

        <!-- Municipality breakdown (k>=5) -->
        <div v-if="results.by_territory && results.by_territory.length" class="mt-6">
          <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2 flex items-center gap-2">
            <MapPin class="w-4 h-4" aria-hidden="true" />
            {{ $t('civic.results.byTerritory') }}
          </h3>
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
            <div v-for="terr in results.by_territory" :key="terr.code" class="px-4 py-2 text-sm flex justify-between gap-3">
              <span class="text-neutral-800 dark:text-neutral-200">{{ terr.name }}</span>
              <span class="text-neutral-500 dark:text-neutral-400 whitespace-nowrap">{{ $t('civic.feed.participation', { n: terr.n }) }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- Receipt verification (A3) -->
      <div v-if="receipt" class="mt-6 pt-4 border-t border-neutral-200 dark:border-neutral-700">
        <UiButton variant="ghost" size="sm" :icon="ShieldCheck" :loading="verifying" @click="verifyReceipt">
          {{ $t('civic.receipt.check') }}
        </UiButton>
        <UiAlert v-if="receiptStatus === 'ok'" variant="success" class="mt-2">{{ $t('civic.receipt.ok') }}</UiAlert>
        <UiAlert v-else-if="receiptStatus === 'fail'" variant="error" class="mt-2">{{ $t('civic.receipt.fail') }}</UiAlert>
        <UiAlert v-else-if="receiptStatus === 'chain'" variant="error" class="mt-2">{{ $t('civic.receipt.chainBroken') }}</UiAlert>
      </div>
    </div>

    <!-- Comments: local scopes only (U4) -->
    <CivicComments
      v-if="poll.scope_level === 'parish' || poll.scope_level === 'municipality'"
      :object-id="poll.id"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Vote, CheckCircle, Lock, BarChart3, MapPin, Send, ShieldCheck, GitBranch } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useRealtimeStore } from '~/stores/realtime'

const props = defineProps<{ poll: any }>()

const { t: $t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const realtimeStore = useRealtimeStore()

const results = ref<any>(null)
const myVote = ref<string | null>(null)
const voting = ref(false)
const voteError = ref('')
const justChanged = ref(false)
const showConsent = ref(false)
const pendingOptionId = ref<string | null>(null)
const pendingSliderSubmit = ref(false)
const sliderValues = ref<Record<string, number>>({})
const overrideMode = ref(false)

const myVoteText = computed(() => {
  if (!myVote.value) return ''
  return (props.poll.options || []).find((o: any) => o.id === myVote.value)?.text || ''
})

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

function anchorLabel(v: number): string {
  const key = v <= -2 ? 'a_m2' : v === -1 ? 'a_m1' : v === 0 ? 'a_0' : v === 1 ? 'a_p1' : 'a_p2'
  return $t(`civic.sliders.${key}`)
}

function syncSliderValues() {
  const mine = results.value?.my_values as Record<string, number> | null
  for (const option of props.poll.options || []) {
    if (mine && mine[option.id] !== undefined) sliderValues.value[option.id] = mine[option.id]
    else if (sliderValues.value[option.id] === undefined) sliderValues.value[option.id] = 0
  }
}

async function castSliderVote() {
  if (voting.value) return
  voteError.value = ''
  justChanged.value = false
  voting.value = true
  try {
    const headers = await authedHeaders()
    const values: Record<string, number> = {}
    for (const option of props.poll.options || []) values[option.id] = sliderValues.value[option.id] ?? 0
    const res: any = await $fetch(`/api/v1/governance/civic/polls/${props.poll.id}/opinion-vote/`, {
      method: 'POST', credentials: 'include', headers,
      body: { values },
    })
    if (res.receipt) {
      receipt.value = res.receipt
      try { localStorage.setItem(RECEIPT_KEY, res.receipt) } catch { /* private mode */ }
    }
    justChanged.value = !!res.changed
    if (res.results) {
      results.value = res.results
      syncSliderValues()
    } else {
      await fetchResults()
    }
    showConsent.value = false
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    const detail = e?.response?._data?.detail || e?.data?.detail || ''
    if (status === 422) {
      pendingSliderSubmit.value = true
      showConsent.value = true
    } else if (status === 429) {
      voteError.value = $t('civic.vote.cooldown')
    } else {
      voteError.value = detail || $t('civic.vote.notActive')
    }
  } finally {
    voting.value = false
  }
}

const receipt = ref<string | null>(null)
const receiptStatus = ref<'ok' | 'fail' | 'chain' | null>(null)
const verifying = ref(false)

const RECEIPT_KEY = `civic_receipt_${props.poll.id}`

async function authedHeaders(): Promise<Record<string, string>> {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function fetchResults() {
  try {
    const headers = await authedHeaders()
    const data: any = await $fetch(`/api/v1/governance/civic/polls/${props.poll.id}/opinion-results/`, {
      credentials: 'include',
      headers,
    })
    results.value = data
    myVote.value = data.my_vote
    syncSliderValues()
  } catch {
    /* keep previous state; page-level error handling covers hard failures */
  }
}

async function castVote(optionId: string) {
  if (voting.value) return
  voteError.value = ''
  justChanged.value = false
  voting.value = true
  try {
    const headers = await authedHeaders()
    const res: any = await $fetch(`/api/v1/governance/civic/polls/${props.poll.id}/opinion-vote/`, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: { option_id: optionId },
    })
    if (res.receipt) {
      receipt.value = res.receipt
      try { localStorage.setItem(RECEIPT_KEY, res.receipt) } catch { /* private mode */ }
    }
    if (res.changed) justChanged.value = true
    if (res.results) {
      results.value = res.results
      myVote.value = res.results.my_vote
    } else {
      await fetchResults()
    }
    showConsent.value = false
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    const detail = e?.response?._data?.detail || e?.data?.detail || ''
    if (status === 422) {
      // Consent required — open the inline consent screen, remember the choice
      pendingOptionId.value = optionId
      showConsent.value = true
    } else if (status === 429) {
      voteError.value = $t('civic.vote.cooldown')
    } else if (status === 403 && props.poll.scope_name) {
      voteError.value = $t('civic.vote.outOfScope', { name: props.poll.scope_name })
      if (detail) voteError.value = detail
    } else {
      voteError.value = detail || $t('civic.vote.notActive')
    }
  } finally {
    voting.value = false
  }
}

async function acceptConsentAndVote() {
  voting.value = true
  try {
    const headers = await authedHeaders()
    await $fetch('/api/v1/governance/civic/consent/', {
      method: 'POST',
      credentials: 'include',
      headers,
      body: { granted: true },
    })
    showConsent.value = false
    if (pendingOptionId.value) {
      const optionId = pendingOptionId.value
      pendingOptionId.value = null
      voting.value = false
      await castVote(optionId)
      return
    }
    if (pendingSliderSubmit.value) {
      pendingSliderSubmit.value = false
      voting.value = false
      await castSliderVote()
      return
    }
  } catch {
    voteError.value = $t('civic.vote.notActive')
  } finally {
    voting.value = false
  }
}

async function verifyReceipt() {
  if (!receipt.value) return
  verifying.value = true
  receiptStatus.value = null
  try {
    const res: any = await $fetch(`/api/v1/governance/civic/polls/${props.poll.id}/verify-receipt/`, {
      query: { hash: receipt.value },
    })
    if (!res.chain_valid) receiptStatus.value = 'chain'
    else receiptStatus.value = res.included ? 'ok' : 'fail'
  } catch {
    receiptStatus.value = 'fail'
  } finally {
    verifying.value = false
  }
}

// Realtime: throttled server-side; refetch keeps hidden/quantization logic server-authoritative
function onResultsUpdated(data: any) {
  if (data.poll_id === props.poll.id) fetchResults()
}

onMounted(() => {
  try { receipt.value = localStorage.getItem(RECEIPT_KEY) } catch { /* private mode */ }
  fetchResults()
  realtimeStore.joinRoom('poll', props.poll.id)
  realtimeStore.on('civic.results_updated', onResultsUpdated)
})

onUnmounted(() => {
  realtimeStore.off('civic.results_updated', onResultsUpdated)
  realtimeStore.leaveRoom('poll', props.poll.id)
})
</script>
