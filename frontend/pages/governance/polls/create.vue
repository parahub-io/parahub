<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-24 pt-24">
    <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-6">
        <button @click="router.push(localePath('/governance/polls'))" class="text-link mb-4 flex items-center gap-1">
          <ArrowLeft class="w-4 h-4" />
          {{ $t('governance.pollDetail.backToList') }}
        </button>

        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('governance.createPollForm.title') }}
        </h1>
        <p class="text-neutral-600 dark:text-neutral-400 mt-2">
          {{ $t('governance.createPollForm.description') }}
        </p>
      </div>

      <!-- Form -->
      <form @submit.prevent="createPoll" class="space-y-6">
        <!-- Basic Info -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.createPollForm.basicInfo') }}</h2>

          <!-- Title -->
          <div class="mb-4">
            <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
              {{ $t('governance.createPollForm.pollTitle') }} <span class="text-error">*</span>
            </label>
            <input
              v-model="form.title"
              type="text"
              required
              minlength="5"
              maxlength="200"
              :placeholder="$t('governance.createPollForm.titlePlaceholder')"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
          </div>

          <!-- Description -->
          <div class="mb-4">
            <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
              {{ $t('governance.createPollForm.pollDescription') }} <span class="text-error">*</span>
            </label>
            <textarea
              v-model="form.description"
              required
              minlength="10"
              rows="4"
              :placeholder="$t('governance.createPollForm.descriptionPlaceholder')"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            ></textarea>
          </div>

          <!-- Context -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.contextType') }} <span class="text-error">*</span>
              </label>
              <select
                v-model="form.context_type"
                required
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              >
                <option value="organization">{{ $t('governance.contextTypes.organization') }}</option>
                <option value="community">{{ $t('governance.contextTypes.community') }}</option>
                <option value="tszh">{{ $t('governance.contextTypes.tszh') }}</option>
                <option value="adhoc">{{ $t('governance.contextTypes.adhoc') }}</option>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ form.context_type === 'adhoc' ? $t('governance.createPollForm.creatorProfile') : $t('governance.contextTypes.organization') }} <span class="text-error">*</span>
              </label>

              <!-- Ad-hoc: Show profile ID (readonly) -->
              <input
                v-if="form.context_type === 'adhoc'"
                v-model="form.context_id"
                type="text"
                readonly
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-neutral-100 dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 cursor-not-allowed"
              />

              <!-- Organization/Community/TSZH: Show dropdown if organizations available -->
              <select
                v-else-if="shouldShowDropdown"
                v-model="form.context_id"
                required
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              >
                <option value="" disabled>{{ $t('governance.createPollForm.selectOrganization') }}</option>
                <option
                  v-for="org in organizations"
                  :key="org.id"
                  :value="org.id"
                >
                  {{ org.name }} ({{ org.organization_type }})
                </option>
                <option value="__manual__">{{ $t('governance.createPollForm.enterManualUlid') }}</option>
              </select>

              <!-- Fallback: Manual ULID input -->
              <div v-else class="space-y-2">
                <input
                  v-model="form.context_id"
                  type="text"
                  required
                  minlength="26"
                  maxlength="26"
                  placeholder="01K7M4MDWPFZ5WQ4A5GRPP"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
                />
                <button
                  v-if="manualContextIdInput && organizations.length > 0"
                  type="button"
                  @click="manualContextIdInput = false"
                  class="text-xs text-link"
                >
                  {{ $t('governance.createPollForm.backToDropdown') }}
                </button>
              </div>

              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                <span v-if="form.context_type === 'adhoc'">{{ $t('governance.createPollForm.autoProfileHint') }}</span>
                <span v-else-if="loadingOrganizations">{{ $t('governance.createPollForm.loadingOrganizations') }}</span>
                <span v-else-if="shouldShowDropdown">{{ $t('governance.createPollForm.selectFromListHint') }}</span>
                <span v-else-if="manualContextIdInput">{{ $t('governance.createPollForm.manualUlidHint') }}</span>
                <span v-else>{{ $t('governance.createPollForm.contextIdHint') }} ({{ organizations.length === 0 ? $t('governance.createPollForm.noOrganizations') : $t('governance.createPollForm.manualInput') }})</span>
              </p>
            </div>
          </div>
        </div>

        <!-- Options -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.createPollForm.options') }}</h2>

          <div class="space-y-3 mb-4">
            <div
              v-for="(option, index) in form.options"
              :key="index"
              class="flex gap-2"
            >
              <input
                v-model="form.options[index]"
                type="text"
                required
                :placeholder="$t('governance.createPollForm.optionPlaceholder')"
                class="flex-1 px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              />
              <button
                v-if="form.options.length > 2"
                type="button"
                @click="removeOption(index)"
                class="px-3 py-2 text-error hover:bg-error-50 dark:hover:bg-error-900/20 rounded-lg transition-colors"
              >
                <X class="w-5 h-5" />
              </button>
            </div>
          </div>

          <button
            v-if="form.options.length < 10"
            type="button"
            @click="addOption"
            class="px-4 py-2 text-secondary dark:text-secondary hover:bg-secondary-50 dark:hover:bg-secondary-900/20 rounded-lg transition-colors flex items-center gap-2"
          >
            <Plus class="w-4 h-4" />
            {{ $t('governance.createPollForm.addOption') }}
          </button>
        </div>

        <!-- Timing -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.createPollForm.timing') }}</h2>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.startTime') }}
              </label>
              <input
                v-model="form.start_time"
                type="datetime-local"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('governance.createPollForm.startTimeHint') }}
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.endTime') }}
              </label>
              <input
                v-model="form.end_time"
                type="datetime-local"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              />
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ $t('governance.createPollForm.endTimeHint') }}
              </p>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
              {{ $t('governance.createPollForm.warningHours') }}
            </label>
            <input
              v-model.number="form.warning_hours"
              type="number"
              min="1"
              max="168"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
            />
            <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              {{ $t('governance.createPollForm.warningHoursHint') }}
            </p>
          </div>
        </div>

        <!-- Rules -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.createPollForm.rules') }}</h2>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.quorumType') }}
              </label>
              <select
                v-model="form.quorum_type"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              >
                <option value="simple_majority">{{ $t('governance.quorumTypes.simple_majority') }}</option>
                <option value="qualified_majority">{{ $t('governance.quorumTypes.qualified_majority') }}</option>
                <option value="unanimous">{{ $t('governance.quorumTypes.unanimous') }}</option>
                <option value="custom">{{ $t('governance.quorumTypes.custom') }}</option>
              </select>
            </div>

            <div v-if="form.quorum_type === 'custom'">
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.quorumPercent') }}
              </label>
              <input
                v-model.number="form.quorum_percent"
                type="number"
                min="0"
                max="100"
                step="0.01"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              />
            </div>
          </div>

          <div class="space-y-3">
            <label class="flex items-center gap-2">
              <input
                v-model="form.allow_delegation"
                type="checkbox"
                class="rounded"
              />
              <span class="text-sm text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.allowDelegation') }}
              </span>
            </label>

            <label class="flex items-center gap-2">
              <input
                v-model="form.public_results"
                type="checkbox"
                class="rounded"
              />
              <span class="text-sm text-neutral-700 dark:text-neutral-300">
                {{ $t('governance.createPollForm.publicResults') }}
              </span>
            </label>

            <div>
              <label class="flex items-center gap-2">
                <input
                  v-model="form.require_wot_verified"
                  type="checkbox"
                  class="rounded"
                />
                <span class="text-sm text-neutral-700 dark:text-neutral-300">
                  {{ $t('governance.createPollForm.requireWotVerified') }}
                </span>
              </label>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 ml-6 mt-1">
                {{ $t('governance.createPollForm.requireWotVerifiedHint') }}
              </p>
            </div>
          </div>
        </div>

        <!-- Eligible Voters -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.createPollForm.eligibleVoters') }}</h2>

          <!-- Add all org members button -->
          <div v-if="form.context_type !== 'adhoc' && form.context_id && form.context_id !== '__manual__'" class="mb-4">
            <button
              type="button"
              :disabled="loadingMembers"
              @click="addAllOrgMembers"
              class="px-4 py-2 text-secondary dark:text-secondary hover:bg-secondary-50 dark:hover:bg-secondary-900/20 rounded-lg transition-colors flex items-center gap-2 text-sm"
            >
              <Users class="w-4 h-4" />
              {{ loadingMembers ? $t('governance.createPollForm.loadingMembers') : $t('governance.createPollForm.addAllMembers') }}
            </button>
          </div>

          <!-- Profile search input -->
          <div class="relative mb-3">
            <div class="flex items-center gap-2">
              <Search class="w-4 h-4 text-neutral-400 absolute left-3 z-10" />
              <input
                ref="voterSearchRef"
                v-model="voterSearchQuery"
                type="text"
                :placeholder="$t('governance.createPollForm.searchVotersPlaceholder')"
                class="w-full pl-9 pr-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
                @input="onVoterSearch"
                @focus="showVoterDropdown = true"
                @keydown.escape="showVoterDropdown = false"
              />
            </div>
            <!-- Search loading -->
            <div v-if="searchingVoters" class="absolute right-3 top-1/2 -translate-y-1/2">
              <div class="w-4 h-4 border-2 border-secondary border-t-transparent rounded-full animate-spin"></div>
            </div>

            <!-- Search results dropdown -->
            <div
              v-if="showVoterDropdown && voterSearchResults.length > 0"
              class="absolute z-50 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg shadow-lg max-h-60 overflow-y-auto"
            >
              <button
                v-for="profile in voterSearchResults"
                :key="profile.id"
                type="button"
                class="w-full text-left px-3 py-2 hover:bg-secondary-50 dark:hover:bg-secondary-900/30 border-b border-neutral-100 dark:border-neutral-700 last:border-b-0 flex items-center gap-3"
                :class="{ 'opacity-50 cursor-not-allowed': isVoterAlreadyAdded(profile.id) }"
                :disabled="isVoterAlreadyAdded(profile.id)"
                @click="addVoter(profile)"
              >
                <div class="w-8 h-8 rounded-full bg-secondary-100 dark:bg-secondary-900/30 flex items-center justify-center flex-shrink-0">
                  <span class="text-sm font-medium text-secondary">{{ (profile.display_name || profile.hna)?.[0]?.toUpperCase() }}</span>
                </div>
                <div class="min-w-0">
                  <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ profile.display_name || profile.hna }}</div>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ profile.hna }}</div>
                </div>
                <span v-if="isVoterAlreadyAdded(profile.id)" class="text-xs text-neutral-400 ml-auto flex-shrink-0">{{ $t('governance.createPollForm.alreadyAdded') }}</span>
              </button>
            </div>

            <!-- No results -->
            <div
              v-if="showVoterDropdown && !searchingVoters && voterSearchQuery.length >= 2 && voterSearchResults.length === 0"
              class="absolute z-50 w-full mt-1 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg shadow-lg p-3 text-sm text-neutral-500"
            >
              {{ $t('governance.createPollForm.noProfilesFound') }}
            </div>

            <!-- Click outside handler -->
            <div v-if="showVoterDropdown" class="fixed inset-0 z-40" @click="showVoterDropdown = false"></div>
          </div>

          <!-- Selected voters chips -->
          <div v-if="selectedVoters.length > 0" class="flex flex-wrap gap-2 mb-3">
            <div
              v-for="voter in selectedVoters"
              :key="voter.id"
              class="flex items-center gap-1.5 px-3 py-1.5 bg-secondary-50 dark:bg-secondary-900/20 border border-secondary-200 dark:border-secondary-800 rounded-full text-sm"
            >
              <span class="text-neutral-900 dark:text-neutral-100">{{ voter.display_name || voter.hna }}</span>
              <button type="button" @click="removeVoter(voter.id)" class="text-neutral-400 hover:text-error transition-colors">
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <!-- Voter count -->
          <p class="text-xs text-neutral-500 dark:text-neutral-400">
            <template v-if="selectedVoters.length > 0">
              {{ $t('governance.createPollForm.votersSelected', { count: selectedVoters.length }) }}
            </template>
            <template v-else>
              {{ $t('governance.createPollForm.eligibleVotersHint') }}
            </template>
          </p>
        </div>

        <!-- Error -->
        <UiAlert v-if="error" variant="error">{{ error }}</UiAlert>

        <!-- Actions -->
        <div class="flex gap-3 justify-end">
          <button
            type="button"
            @click="router.push(localePath('/governance/polls'))"
            class="px-6 py-3 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
          >
            {{ $t('governance.createPollForm.cancel') }}
          </button>
          <button
            type="submit"
            :disabled="creating"
            class="btn-secondary gap-2"
          >
            <Vote class="w-5 h-5" />
            {{ creating ? $t('governance.createPollForm.creating') : $t('governance.createPollForm.create') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ArrowLeft, Plus, X, Vote, Search, Users } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const { t: $t } = useI18n()

// Organizations list
const organizations = ref<Array<{id: string, name: string, organization_type: string}>>([])
const loadingOrganizations = ref(false)
const manualContextIdInput = ref(false)

// Form state
const form = ref({
  title: '',
  description: '',
  context_type: 'organization',
  context_id: '',
  options: ['', ''],
  start_time: '',
  end_time: '',
  warning_hours: 24,
  quorum_type: 'simple_majority',
  quorum_percent: 50.00,
  allow_delegation: true,
  public_results: true,
  require_wot_verified: false,
})

const creating = ref(false)
const error = ref('')

// Voter search state
interface VoterProfile {
  id: string
  hna: string
  display_name: string
}
const selectedVoters = ref<VoterProfile[]>([])
const voterSearchQuery = ref('')
const voterSearchResults = ref<VoterProfile[]>([])
const searchingVoters = ref(false)
const showVoterDropdown = ref(false)
const voterSearchRef = ref<HTMLInputElement | null>(null)
const loadingMembers = ref(false)
let voterSearchTimer: ReturnType<typeof setTimeout> | null = null

// Load user's organizations
async function loadOrganizations() {
  loadingOrganizations.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/geo/establishments/', {
      params: { my_memberships: true },
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    organizations.value = (response?.items || []) as any[]
  } catch (e) {
    console.error('Failed to load organizations:', e)
  } finally {
    loadingOrganizations.value = false
  }
}

// Auto-populate context_id for adhoc (use profile ID)
watch(() => form.value.context_type, (newType) => {
  if (newType === 'adhoc' && authStore.profile?.id) {
    form.value.context_id = authStore.profile.id
    manualContextIdInput.value = false
  } else if (newType !== 'adhoc' && form.value.context_id === authStore.profile?.id) {
    // Clear if switching away from adhoc
    form.value.context_id = ''
    manualContextIdInput.value = false
  }
})

// Watch for manual input selection
watch(() => form.value.context_id, (newValue) => {
  if (newValue === '__manual__') {
    manualContextIdInput.value = true
    form.value.context_id = ''
  }
})

// Should show dropdown for organization selection
const shouldShowDropdown = computed(() => {
  return form.value.context_type !== 'adhoc' && organizations.value.length > 0 && !manualContextIdInput.value
})

// On mount
onMounted(() => {
  loadOrganizations()
})

// Add/remove options
function addOption() {
  if (form.value.options.length < 10) {
    form.value.options.push('')
  }
}

function removeOption(index: number) {
  if (form.value.options.length > 2) {
    form.value.options.splice(index, 1)
  }
}

// Voter search with debounce
function onVoterSearch() {
  showVoterDropdown.value = true
  if (voterSearchTimer) clearTimeout(voterSearchTimer)
  if (voterSearchQuery.value.length < 2) {
    voterSearchResults.value = []
    return
  }
  voterSearchTimer = setTimeout(() => searchVoters(), 300)
}

async function searchVoters() {
  searchingVoters.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/profiles/search/', {
      params: { q: voterSearchQuery.value, page_size: 10 },
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    voterSearchResults.value = (res?.items || []).map((p: any) => ({
      id: p.id,
      hna: p.hna,
      display_name: p.display_name || p.hna,
    }))
  } catch (e) {
    console.error('Voter search failed:', e)
    voterSearchResults.value = []
  } finally {
    searchingVoters.value = false
  }
}

function addVoter(profile: VoterProfile) {
  if (!isVoterAlreadyAdded(profile.id)) {
    selectedVoters.value.push(profile)
  }
  voterSearchQuery.value = ''
  voterSearchResults.value = []
  showVoterDropdown.value = false
}

function removeVoter(id: string) {
  selectedVoters.value = selectedVoters.value.filter(v => v.id !== id)
}

function isVoterAlreadyAdded(id: string): boolean {
  return selectedVoters.value.some(v => v.id === id)
}

// Add all org members as voters
async function addAllOrgMembers() {
  if (!form.value.context_id || form.value.context_id === '__manual__') return
  loadingMembers.value = true
  try {
    await authStore.ensureToken()
    const members = await $fetch<any[]>(`/api/v1/geo/establishments/${form.value.context_id}/members/`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    let added = 0
    for (const m of members || []) {
      if (!isVoterAlreadyAdded(m.profile_id)) {
        selectedVoters.value.push({
          id: m.profile_id,
          hna: m.profile_hna,
          display_name: m.profile_display_name || m.profile_hna,
        })
        added++
      }
    }
  } catch (e) {
    console.error('Failed to load org members:', e)
  } finally {
    loadingMembers.value = false
  }
}

// Create poll
async function createPoll() {
  creating.value = true
  error.value = ''

  try {
    await authStore.ensureToken()

    // Collect eligible voter IDs from selected profiles
    const eligibleVoterIds = selectedVoters.value.map(v => v.id)

    // Filter out empty options
    const options = form.value.options.filter(o => o.trim().length > 0)

    if (options.length < 2) {
      error.value = $t('governance.errors.minOptions')
      creating.value = false
      return
    }

    // Prepare payload
    const payload: any = {
      context_type: form.value.context_type,
      context_id: form.value.context_id,
      title: form.value.title,
      description: form.value.description,
      options: options,
      poll_type: 'multiple_choice',
      quorum_type: form.value.quorum_type,
      quorum_percent: form.value.quorum_percent,
      allow_delegation: form.value.allow_delegation,
      public_results: form.value.public_results,
      require_wot_verified: form.value.require_wot_verified,
      warning_hours: form.value.warning_hours,
    }

    if (form.value.start_time) {
      payload.start_time = new Date(form.value.start_time).toISOString()
    }

    if (form.value.end_time) {
      payload.end_time = new Date(form.value.end_time).toISOString()
    }

    if (eligibleVoterIds.length > 0) {
      payload.eligible_voter_ids = eligibleVoterIds
    }

    const createdPoll = await $fetch('/api/v1/governance/polls/', {
      method: 'POST',
      body: payload,
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    // Redirect to created poll
    router.push(localePath(`/governance/polls/${createdPoll.id}`))
  } catch (e: any) {
    console.error('Failed to create poll:', e)
    error.value = e.data?.message || e.message || $t('governance.errors.creatingPoll')
  } finally {
    creating.value = false
  }
}

// Redirect if not authenticated
if (process.client && !authStore.isAuthenticated) {
  router.push(localePath('/login'))
}

definePageMeta({
  middleware: 'auth',
})
</script>
