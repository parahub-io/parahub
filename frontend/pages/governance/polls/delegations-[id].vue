<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-24 pt-24">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-6">
        <button @click="router.push(localePath(`/governance/polls/${pollId}`))" class="text-link mb-4 flex items-center gap-1">
          <ArrowLeft class="w-4 h-4" />
          {{ $t('governance.pollDetail.backToPoll') }}
        </button>

        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('governance.delegationChains.title') }}
        </h1>
        <p class="text-neutral-600 dark:text-neutral-400 mt-2">
          {{ $t('governance.delegationChains.description') }}
        </p>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-secondary"></div>
      </div>

      <!-- Error State -->
      <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

      <!-- Empty State -->
      <div v-else-if="!chains || chains.length === 0" class="text-center py-12">
        <GitBranch class="w-12 h-12 mx-auto mb-4 text-neutral-300 dark:text-neutral-600" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('governance.noDelegations') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400">
          {{ $t('governance.noDelegationsDescription') }}
        </p>
      </div>

      <!-- Chains List -->
      <div v-else class="space-y-6">
        <!-- Summary -->
        <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">{{ $t('governance.pollDetail.statistics') }}</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="text-center">
              <div class="text-2xl font-bold text-secondary dark:text-secondary-400">{{ chains.length }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.delegationChains.chains') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-neutral-700 dark:text-neutral-300">{{ totalDelegators }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.delegationChains.totalDelegators') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-success dark:text-success-400">{{ votedChains }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.delegationChains.votedChains') }}</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-neutral-700 dark:text-neutral-300">{{ longestChain }}</div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.delegationChains.longestChain') }}</div>
            </div>
          </div>
        </div>

        <!-- Chains -->
        <div
          v-for="(chain, index) in chains"
          :key="index"
          class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6"
        >
          <!-- Chain Header -->
          <div class="flex justify-between items-center mb-4">
            <div>
              <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('governance.delegationChains.chain') }} #{{ index + 1 }}</span>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {{ $t('governance.delegationChains.length') }}: {{ chain.length }}
                </span>
                <span v-if="chain.has_voted" class="px-2 py-0.5 text-xs bg-success-100 dark:bg-success-900/30 text-success-700 dark:text-success-300 rounded-full">
                  ✓ {{ $t('governance.delegationChains.voted') }}
                </span>
                <span v-else class="px-2 py-0.5 text-xs bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-300 rounded-full">
                  ⏳ {{ $t('governance.delegationChains.waiting') }}
                </span>
              </div>
            </div>
          </div>

          <!-- Chain Visualization -->
          <div class="space-y-3">
            <div
              v-for="(profileId, i) in chain.chain"
              :key="profileId"
              class="flex items-center gap-3"
            >
              <!-- Node -->
              <div class="flex-shrink-0 w-10 h-10 rounded-full bg-secondary-100 dark:bg-secondary-900/30 flex items-center justify-center">
                <User class="w-5 h-5 text-secondary dark:text-secondary-400" />
              </div>

              <!-- Info -->
              <div class="flex-1">
                <div class="font-medium text-neutral-900 dark:text-neutral-100">
                  {{ getProfileName(profileId) }}
                </div>
                <div class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ i === 0 ? $t('governance.delegator') : i === chain.chain.length - 1 ? $t('governance.finalDelegate') : $t('governance.intermediate') }}
                </div>
              </div>

              <!-- Arrow -->
              <div v-if="i < chain.chain.length - 1" class="flex-shrink-0">
                <ArrowDown class="w-5 h-5 text-neutral-400 dark:text-neutral-600" />
              </div>
            </div>

            <!-- Vote Info -->
            <UiAlert v-if="chain.has_voted" variant="success" :icon="CheckCircle" class="mt-4">
              {{ getProfileName(chain.final_delegate_id) }} {{ $t('governance.voted') }}{{ chain.vote_option_id ? `: ${getOptionText(chain.vote_option_id)}` : '' }}
            </UiAlert>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, GitBranch, User, ArrowDown, CheckCircle } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

const pollId = computed(() => route.params.id as string)

// State
const chains = ref<any[]>([])
const poll = ref<any>(null)
const loading = ref(false)
const error = ref('')

// Profile name cache: { id: display_name || hna }
const profileNames = ref<Record<string, string>>({})

// Fetch delegation chains
async function fetchDelegationChains() {
  loading.value = true
  error.value = ''

  try {
    // Fetch poll details for options
    poll.value = await $fetch(`/api/v1/governance/polls/${pollId.value}/`, {
      credentials: 'include',
    })

    // Fetch delegation chains
    chains.value = await $fetch(`/api/v1/governance/polls/${pollId.value}/delegations/`, {
      credentials: 'include',
    })

    // Build profile name cache from chain_profiles
    for (const chain of chains.value) {
      if (chain.chain_profiles) {
        for (const [profileId, profile] of Object.entries(chain.chain_profiles)) {
          const p = profile as { display_name?: string; hna?: string }
          profileNames.value[profileId] = p.display_name || p.hna || ''
        }
      }
    }
  } catch (e: any) {
    console.error('Failed to fetch delegation chains:', e)
    error.value = e.data?.message || e.message || t('governance.errors.loadingDelegationChains')
  } finally {
    loading.value = false
  }
}

// Computed stats
const totalDelegators = computed(() => {
  return chains.value.reduce((sum, chain) => sum + chain.length - 1, 0)
})

const votedChains = computed(() => {
  return chains.value.filter(chain => chain.has_voted).length
})

const longestChain = computed(() => {
  return chains.value.reduce((max, chain) => Math.max(max, chain.length), 0)
})

// Helpers
function getProfileName(profileId: string): string {
  return profileNames.value[profileId] || `ID: ${profileId.substring(0, 8)}...`
}

function getOptionText(optionId: string): string {
  if (!poll.value?.options) return ''
  const option = poll.value.options.find((o: any) => o.id === optionId)
  return option?.text || ''
}

// Lifecycle
onMounted(() => {
  fetchDelegationChains()
})

definePageMeta({})
</script>
