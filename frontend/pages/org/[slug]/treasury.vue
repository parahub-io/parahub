<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6">
      <!-- Back button -->
      <NuxtLink
        :to="localePath(`/org/${slug}`)"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg mb-4 transition-colors"
      >
        <ArrowLeft class="w-4 h-4" />
        {{ establishmentName || slug }}
      </NuxtLink>

      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-3">
            <Landmark class="w-7 h-7 text-yellow-600 dark:text-yellow-400" />
            {{ $t('treasury.title') }}
          </h1>
          <p class="mt-1 text-neutral-500 dark:text-neutral-400 text-sm">
            {{ $t('treasury.description') }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <!-- Save status -->
          <div v-if="canVote && saveStatus" class="flex items-center gap-1.5 text-xs">
            <template v-if="saveStatus === 'saved'">
              <Check class="w-3.5 h-3.5 text-green-600" />
              <span class="text-green-600 dark:text-green-400">{{ $t('treasury.saved') }}</span>
            </template>
            <template v-else-if="saveStatus === 'saving'">
              <div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-yellow-600"></div>
              <span class="text-neutral-500">{{ $t('treasury.saving') }}</span>
            </template>
            <template v-else-if="saveStatus === 'error'">
              <AlertCircle class="w-3.5 h-3.5 text-red-500" />
              <span class="text-red-500 dark:text-red-400">{{ saveError }}</span>
            </template>
          </div>
          <!-- Participation badge -->
          <span
            v-if="currentData"
            class="text-xs px-2.5 py-1 rounded-full font-medium"
            :class="currentData.total_participants > 0
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
              : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400'"
          >
            {{ $t('treasury.participation', { count: currentData.total_participants, total: currentData.total_eligible }) }}
          </span>
        </div>
      </div>

      <!-- Not eligible banner -->
      <UiAlert v-if="authStore.isAuthenticated && myData && !myData.is_eligible" variant="warning" :title="$t('treasury.not_eligible')" class="mb-6">
        <p class="text-xs">{{ $t('treasury.not_eligible_hint') }}</p>
      </UiAlert>

      <!-- Sign in prompt -->
      <ClientOnly>
        <UiAlert v-if="!authStore.isAuthenticated" variant="info" class="mb-6">{{ $t('treasury.sign_in_to_vote') }}</UiAlert>
      </ClientOnly>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
      </div>

      <!-- ─── Unified Budget ─── -->
      <section v-else-if="mergedCategories.length > 0" class="mb-8 space-y-3">
        <div
          v-for="cat in mergedCategories"
          :key="cat.id"
          class="bg-white dark:bg-neutral-800 rounded-lg p-4 border border-neutral-200 dark:border-neutral-700"
        >
          <!-- Category header -->
          <div class="flex items-center justify-between mb-1">
            <div class="flex items-center gap-2">
              <component
                :is="getCategoryIcon(cat.icon)"
                class="w-4 h-4 text-neutral-500 dark:text-neutral-400"
              />
              <span class="font-medium text-sm text-neutral-800 dark:text-neutral-200">
                {{ $t(`treasury.category.${cat.slug}`, cat.name) }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-neutral-900 dark:text-neutral-100">
                {{ cat.median_percent.toFixed(0) }}%
              </span>
              <span v-if="canVote && sliderValues[cat.id] != null" class="text-xs text-neutral-400">
                {{ $t('treasury.my_short') }} {{ Math.round(sliderValues[cat.id]) }}%
              </span>
              <span v-else-if="cat.voter_count > 0" class="text-xs text-neutral-400">
                {{ cat.voter_count }} {{ $t('treasury.voters') }}
              </span>
            </div>
          </div>

          <!-- Hint -->
          <p class="text-xs text-neutral-400 dark:text-neutral-500 mb-2 ml-6">
            {{ $t(`treasury.category_hint.${cat.slug}`, '') }}
          </p>

          <!-- Median bar -->
          <div class="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-2.5 overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-300 ease-out"
              :class="categoryBarColor(cat.slug)"
              :style="{ width: cat.median_percent + '%' }"
            ></div>
          </div>

          <!-- My slider (if eligible) -->
          <div v-if="canVote" class="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-700">
            <div class="flex items-center gap-3">
              <input
                type="range"
                :value="sliderValues[cat.id]"
                @input="onSliderChange(cat.id, parseFloat(($event.target as HTMLInputElement).value))"
                min="0"
                max="100"
                step="1"
                class="flex-1 h-1.5 rounded-lg appearance-none cursor-pointer accent-yellow-500 bg-neutral-200 dark:bg-neutral-600"
              />
              <input
                type="number"
                :value="Math.round(sliderValues[cat.id] ?? 0)"
                @change="onDirectInput(cat.id, ($event.target as HTMLInputElement).value)"
                min="0"
                max="100"
                step="1"
                class="w-14 text-right text-xs font-mono border border-neutral-300 dark:border-neutral-600 rounded px-1.5 py-0.5 bg-transparent text-neutral-700 dark:text-neutral-300 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              <span class="text-xs text-neutral-400">%</span>
            </div>
          </div>
        </div>
      </section>

      <!-- No votes placeholder -->
      <div v-else-if="!loading" class="text-center py-12 text-neutral-500 dark:text-neutral-400 mb-8">
        <BarChart3 class="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p>{{ $t('treasury.no_votes') }}</p>
      </div>

      <!-- ─── Epoch History ─── -->
      <section class="mb-8">
        <h2 class="text-lg font-semibold text-neutral-800 dark:text-neutral-200 mb-4 flex items-center gap-2">
          <History class="w-5 h-5" />
          {{ $t('treasury.history') }}
        </h2>

        <div v-if="loadingEpochs" class="flex justify-center py-6">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
        </div>

        <div v-else-if="epochs.length === 0" class="text-center py-6 text-neutral-500 dark:text-neutral-400 text-sm">
          {{ $t('treasury.no_epochs') }}
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="epoch in epochs"
            :key="epoch.id"
            class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden"
          >
            <button
              @click="toggleEpoch(epoch.id)"
              class="w-full flex items-center justify-between p-4 text-left hover:bg-neutral-50 dark:hover:bg-neutral-750 transition-colors"
            >
              <div>
                <span class="font-semibold text-neutral-900 dark:text-neutral-100">
                  {{ epoch.label }}
                </span>
                <span class="ml-2 text-xs text-neutral-500">
                  {{ $t('treasury.participation_short', { count: epoch.total_participants, total: epoch.total_eligible }) }}
                </span>
              </div>
              <ChevronDown
                class="w-5 h-5 text-neutral-400 transition-transform"
                :class="{ 'rotate-180': expandedEpochs.includes(epoch.id) }"
              />
            </button>

            <div v-if="expandedEpochs.includes(epoch.id)" class="border-t border-neutral-200 dark:border-neutral-700 p-4">
              <div v-if="epochDetails[epoch.id]" class="space-y-4">
                <div class="space-y-2">
                  <div
                    v-for="fa in epochDetails[epoch.id].frozen_allocations"
                    :key="fa.category_id"
                    class="flex items-center gap-3"
                  >
                    <span class="text-xs text-neutral-600 dark:text-neutral-400 w-36 truncate">
                      {{ $t(`treasury.category.${fa.slug}`, fa.name) }}
                    </span>
                    <div class="flex-1 bg-neutral-100 dark:bg-neutral-700 rounded-full h-2.5 overflow-hidden">
                      <div
                        class="h-full rounded-full"
                        :class="categoryBarColor(fa.slug)"
                        :style="{ width: fa.median_percent + '%' }"
                      ></div>
                    </div>
                    <span class="text-xs font-mono text-neutral-700 dark:text-neutral-300 w-12 text-right">
                      {{ fa.median_percent }}%
                    </span>
                  </div>
                </div>

                <div class="text-xs text-neutral-400 font-mono break-all">
                  {{ $t('treasury.merkle_root') }}: {{ epochDetails[epoch.id].merkle_root }}
                </div>

                <button
                  @click="toggleEpochVotes(epoch.id)"
                  class="text-xs text-yellow-600 dark:text-yellow-400 hover:underline"
                >
                  {{ showEpochVotes.includes(epoch.id) ? $t('treasury.collapse_votes') : $t('treasury.expand_votes') }}
                </button>

                <div v-if="showEpochVotes.includes(epoch.id)" class="space-y-1">
                  <div
                    v-for="ind in epochDetails[epoch.id].individual_allocations_snapshot"
                    :key="ind.profile_id"
                    class="flex items-center gap-3 text-xs py-1 border-b border-neutral-100 dark:border-neutral-700 last:border-0"
                  >
                    <span class="font-medium text-neutral-700 dark:text-neutral-300 w-24 truncate">
                      {{ ind.hna }}
                    </span>
                    <div class="flex-1 flex gap-1">
                      <template v-for="fa in epochDetails[epoch.id].frozen_allocations" :key="fa.category_id">
                        <div
                          class="h-4 rounded-sm text-[9px] flex items-center justify-center text-white font-mono"
                          :class="categoryBarColor(fa.slug)"
                          :style="{ width: (ind.allocations[fa.category_id] || 0) + '%' }"
                          :title="$t(`treasury.category.${fa.slug}`, fa.name) + ': ' + (ind.allocations[fa.category_id] || 0) + '%'"
                        >
                          <span v-if="(ind.allocations[fa.category_id] || 0) > 8">
                            {{ Math.round(ind.allocations[fa.category_id] || 0) }}
                          </span>
                        </div>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="flex justify-center py-4">
                <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-600"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ─── Audit Log (collapsed) ─── -->
      <section>
        <button
          @click="showAuditLog = !showAuditLog"
          class="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 mb-3"
        >
          <FileText class="w-4 h-4" />
          {{ $t('treasury.audit_log') }}
          <ChevronDown class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showAuditLog }" />
        </button>

        <div v-if="showAuditLog" class="space-y-2">
          <div v-if="loadingAudit" class="flex justify-center py-4">
            <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-600"></div>
          </div>
          <div v-else-if="auditLogs.length === 0" class="text-center py-4 text-neutral-400 text-sm">
            {{ $t('treasury.no_audit_entries') }}
          </div>
          <div
            v-for="log in auditLogs"
            :key="log.id"
            class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3 text-xs"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="font-medium text-neutral-700 dark:text-neutral-300">
                {{ log.action.replace('_', ' ') }}
              </span>
              <span class="text-neutral-400 font-mono">
                {{ formatDate(log.timestamp) }}
              </span>
            </div>
            <div class="text-neutral-500 dark:text-neutral-400">
              <span v-if="log.actor_hna">{{ log.actor_hna }}</span>
              <span v-else>system</span>
            </div>
            <div class="mt-1 font-mono text-[10px] text-neutral-400 break-all">
              {{ log.current_log_hash }}
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  Landmark, BarChart3, Check, AlertCircle, History,
  ChevronDown, FileText, Settings, Users, Rocket,
  Megaphone, HeartHandshake, Shield, ArrowLeft
} from 'lucide-vue-next'
import { useTreasuryWebSocket } from '~/composables/useTreasuryWebSocket'
import { usePGP } from '~/composables/usePGP'

const { t } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { loadKeys, signCanonicalPayload, hasKeys } = usePGP()

const slug = computed(() => route.params.slug as string)

// ── State ──
const loading = ref(true)
const loadingEpochs = ref(true)
const loadingAudit = ref(false)
const saving = ref(false)
const saveStatus = ref<'saved' | 'saving' | 'error' | null>(null)
const saveError = ref('')
const establishmentName = ref('')
const establishmentId = ref('')

interface MedianItem {
  category_id: string
  slug: string
  name: string
  icon: string
  median_percent: number
  voter_count: number
}
interface CurrentData {
  medians: MedianItem[]
  total_eligible: number
  total_participants: number
  participation_percent: number
}
interface CategoryItem {
  id: string
  name: string
  slug: string
  icon: string
  order: number
}
interface MyData {
  is_eligible: boolean
  needs_update: boolean
  allocation: { id: string; allocations: Record<string, number>; pgp_signature: string; updated_at: string } | null
}
interface EpochItem {
  id: string
  label: string
  status: string
  total_eligible: number
  total_participants: number
  finalized_at: string | null
}
interface AuditItem {
  id: string
  action: string
  actor_hna: string | null
  current_log_hash: string
  timestamp: string
}

interface MergedCategory {
  id: string
  name: string
  slug: string
  icon: string
  order: number
  median_percent: number
  voter_count: number
}

const currentData = ref<CurrentData | null>(null)
const categories = ref<CategoryItem[]>([])
const myData = ref<MyData | null>(null)
const sliderValues = ref<Record<string, number>>({})
const epochs = ref<EpochItem[]>([])
const epochDetails = ref<Record<string, any>>({})
const expandedEpochs = ref<string[]>([])
const showEpochVotes = ref<string[]>([])
const showAuditLog = ref(false)
const auditLogs = ref<AuditItem[]>([])

// ── Computed ──
const canVote = computed(() => {
  return authStore.isAuthenticated && myData.value?.is_eligible
})

const mergedCategories = computed<MergedCategory[]>(() => {
  return categories.value.map(cat => {
    const median = currentData.value?.medians.find(m => m.category_id === cat.id)
    return {
      ...cat,
      median_percent: median?.median_percent ?? 0,
      voter_count: median?.voter_count ?? 0,
    }
  })
})

// ── Icon mapping ──
const iconMap: Record<string, any> = {
  settings: Settings,
  users: Users,
  rocket: Rocket,
  megaphone: Megaphone,
  'heart-handshake': HeartHandshake,
  shield: Shield,
}
function getCategoryIcon(icon: string) {
  return iconMap[icon] || Landmark
}

// ── Category bar colors ──
function categoryBarColor(slug: string): string {
  const colors: Record<string, string> = {
    'operations': 'bg-neutral-500',
    'team': 'bg-secondary',
    'development': 'bg-purple-500',
    'marketing': 'bg-rose-500',
    'community': 'bg-green-500',
    'reserve': 'bg-amber-500',
  }
  return colors[slug] || 'bg-yellow-500'
}

// ── Auto-save debounce ──
let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveAllocation()
  }, 800)
}

// ── Slider logic ──
function onSliderChange(catId: string, newValue: number) {
  sliderValues.value[catId] = newValue
  redistributeOthers(catId, newValue)
  scheduleSave()
}

function onDirectInput(catId: string, rawValue: string) {
  let v = parseFloat(rawValue)
  if (isNaN(v)) v = 0
  v = Math.max(0, Math.min(100, v))
  sliderValues.value[catId] = v
  redistributeOthers(catId, v)
  scheduleSave()
}

function redistributeOthers(changedId: string, newValue: number) {
  const remaining = 100 - newValue
  const otherIds = categories.value.map(c => c.id).filter(id => id !== changedId)
  const othersSum = otherIds.reduce((s, id) => s + (sliderValues.value[id] ?? 0), 0)

  if (othersSum > 0) {
    const scale = remaining / othersSum
    let runningTotal = newValue
    for (let i = 0; i < otherIds.length; i++) {
      if (i === otherIds.length - 1) {
        sliderValues.value[otherIds[i]] = Math.max(0, parseFloat((100 - runningTotal).toFixed(1)))
      } else {
        const scaled = parseFloat(((sliderValues.value[otherIds[i]] ?? 0) * scale).toFixed(1))
        sliderValues.value[otherIds[i]] = Math.max(0, scaled)
        runningTotal += scaled
      }
    }
  } else if (otherIds.length > 0) {
    const equal = parseFloat((remaining / otherIds.length).toFixed(1))
    let runningTotal = newValue
    for (let i = 0; i < otherIds.length; i++) {
      if (i === otherIds.length - 1) {
        sliderValues.value[otherIds[i]] = Math.max(0, parseFloat((100 - runningTotal).toFixed(1)))
      } else {
        sliderValues.value[otherIds[i]] = equal
        runningTotal += equal
      }
    }
  }
}

// ── API calls ──
const apiBase = computed(() => `/api/v1/treasury/${slug.value}`)

async function fetchEstablishment() {
  try {
    const data: any = await $fetch(`/api/v1/geo/establishments/${slug.value}/`)
    establishmentName.value = data.name
    establishmentId.value = data.id
  } catch (e) {
    console.error('Failed to fetch establishment:', e)
  }
}

async function fetchCurrent() {
  try {
    currentData.value = await $fetch(`${apiBase.value}/current/`)
  } catch (e) {
    console.error('Failed to fetch current budget:', e)
  }
}

async function fetchCategories() {
  try {
    categories.value = await $fetch(`${apiBase.value}/categories/`)
  } catch (e) {
    console.error('Failed to fetch categories:', e)
  }
}

async function fetchMy() {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    myData.value = await $fetch(`${apiBase.value}/my/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })

    // Initialize sliders
    if (myData.value?.allocation?.allocations) {
      sliderValues.value = { ...myData.value.allocation.allocations }
      saveStatus.value = 'saved'
    } else if (categories.value.length > 0) {
      // Default: equal distribution
      const equal = parseFloat((100 / categories.value.length).toFixed(1))
      const vals: Record<string, number> = {}
      categories.value.forEach((cat, i) => {
        if (i === categories.value.length - 1) {
          vals[cat.id] = parseFloat((100 - Object.values(vals).reduce((s, v) => s + v, 0)).toFixed(1))
        } else {
          vals[cat.id] = equal
        }
      })
      sliderValues.value = vals
    }

    // Ensure all active categories have a value
    for (const cat of categories.value) {
      if (!(cat.id in sliderValues.value)) {
        sliderValues.value[cat.id] = 0
      }
    }
  } catch (e) {
    console.error('Failed to fetch my allocation:', e)
  }
}

async function saveAllocation() {
  if (!authStore.isAuthenticated || !canVote.value) return

  // Validate sum
  const total = Object.values(sliderValues.value).reduce((s, v) => s + v, 0)
  if (Math.abs(total - 100) > 0.1) return

  saving.value = true
  saveStatus.value = 'saving'
  saveError.value = ''
  try {
    await authStore.ensureToken()

    const timestamp = new Date().toISOString()
    const canonicalPayload = {
      allocations: Object.fromEntries(
        Object.entries(sliderValues.value).sort(([a], [b]) => a.localeCompare(b))
      ),
      establishment_slug: slug.value,
      timestamp,
    }
    const pgpSignature = await signCanonicalPayload(canonicalPayload)

    await $fetch(`${apiBase.value}/my/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        allocations: sliderValues.value,
        pgp_signature: pgpSignature,
        signed_payload: { timestamp },
      },
    })
    saveStatus.value = 'saved'
    // WebSocket will update medians; also fetch as fallback
    await fetchCurrent()
  } catch (e: any) {
    console.error('Failed to save allocation:', e)
    saveStatus.value = 'error'
    // Extract meaningful error from backend response
    const msg = e?.data?.detail || e?.data?.message || ''
    if (msg.includes('Signature required') || msg.includes('PGP')) {
      saveError.value = t('treasury.error_signature_required')
    } else {
      saveError.value = t('treasury.error_save_failed')
    }
  } finally {
    saving.value = false
  }
}

async function fetchEpochs() {
  try {
    const res: any = await $fetch(`${apiBase.value}/epochs/`)
    epochs.value = res.items || []
  } catch (e) {
    console.error('Failed to fetch epochs:', e)
  } finally {
    loadingEpochs.value = false
  }
}

async function toggleEpoch(epochId: string) {
  const idx = expandedEpochs.value.indexOf(epochId)
  if (idx >= 0) {
    expandedEpochs.value.splice(idx, 1)
    return
  }
  expandedEpochs.value.push(epochId)
  if (!epochDetails.value[epochId]) {
    try {
      epochDetails.value[epochId] = await $fetch(`${apiBase.value}/epochs/${epochId}/`)
    } catch (e) {
      console.error('Failed to fetch epoch detail:', e)
    }
  }
}

function toggleEpochVotes(epochId: string) {
  const idx = showEpochVotes.value.indexOf(epochId)
  if (idx >= 0) {
    showEpochVotes.value.splice(idx, 1)
  } else {
    showEpochVotes.value.push(epochId)
  }
}

async function fetchAuditLog() {
  loadingAudit.value = true
  try {
    const res: any = await $fetch(`${apiBase.value}/audit-log/`)
    auditLogs.value = res.items || []
  } catch (e) {
    console.error('Failed to fetch audit log:', e)
  } finally {
    loadingAudit.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

// ── WebSocket ──
const { onMediansUpdated } = useTreasuryWebSocket(establishmentId)
onMediansUpdated.value = (data: any) => {
  if (currentData.value && data.medians) {
    currentData.value = {
      medians: data.medians,
      total_eligible: data.total_eligible,
      total_participants: data.total_participants,
      participation_percent: data.participation_percent,
    }
  }
}

// ── Lifecycle ──
onMounted(async () => {
  loadKeys()
  await fetchEstablishment()
  await fetchCategories()
  await Promise.all([fetchCurrent(), fetchEpochs(), fetchMy()])
  loading.value = false
})

onUnmounted(() => {
  if (saveTimer) clearTimeout(saveTimer)
})

watch(showAuditLog, (v) => {
  if (v && auditLogs.value.length === 0) {
    fetchAuditLog()
  }
})
</script>
