<template>
  <div class="w-full">
    <!-- Header -->
    <div class="mb-6 flex justify-between items-center">
      <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.campaigns.my_campaigns') }}</h2>
      <button
        @click="navigateTo(localePath('/ads/campaigns/create'))"
        class="btn-primary btn-sm gap-2"
      >
        <Plus class="w-4 h-4" />
        {{ $t('ads.campaigns.create_new') }}
      </button>
    </div>

    <!-- Active / Archive toggle (subordinate to the route strip above — pills, not full-width) -->
    <UiTabs
      v-if="campaigns.length > 0"
      v-model="activeTab"
      :tabs="tabDefs"
      variant="pills"
      class="mb-4"
    />

    <!-- Campaigns list -->
    <div v-if="visibleCampaigns.length > 0" class="space-y-4">
      <div
        v-for="campaign in visibleCampaigns"
        :key="campaign.id"
        @click="selectedCampaign = { ...campaign }"
        class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6 cursor-pointer hover:border-primary/50 transition-colors"
      >
        <!-- Campaign image thumbnail -->
        <img
          v-if="campaign.image_url"
          :src="campaign.image_url"
          :alt="campaign.post_title"
          class="w-full h-[140px] object-cover rounded-t-lg -mx-6 -mt-6 mb-4"
          style="width: calc(100% + 3rem)"
          loading="lazy"
        />

        <div class="flex justify-between items-start mb-4">
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ campaign.name }}</h3>
            <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{{ campaign.post_title }}</p>
          </div>
          <UiBadge :variant="statusVariant(campaign.status)" type="soft" class="capitalize">
            {{ campaign.status }}
          </UiBadge>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.views') }}</p>
            <p class="font-semibold text-neutral-900 dark:text-neutral-100">{{ campaign.total_views }}</p>
          </div>
          <div>
            <p class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.clicks') }}</p>
            <p class="font-semibold text-neutral-900 dark:text-neutral-100">{{ campaign.total_clicks }}</p>
          </div>
          <div>
            <p class="text-neutral-500 dark:text-neutral-400">CTR</p>
            <p class="font-semibold text-neutral-900 dark:text-neutral-100">{{ campaign.ctr.toFixed(2) }}%</p>
          </div>
          <div>
            <p class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.spent') }}</p>
            <p class="font-semibold text-neutral-900 dark:text-neutral-100">{{ campaign.spent_sats }} / {{ campaign.budget_sats }} sats</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty archive -->
    <div v-else-if="activeTab === 'archived'" class="text-center py-12">
      <p class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaigns.archived_empty') }}</p>
    </div>

    <!-- Empty state -->
    <div v-else class="text-center py-12">
      <img src="/images/para/pointing.webp" alt="" aria-hidden="true" class="mx-auto h-32 w-auto mb-4" />
      <p class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaigns.empty') }}</p>
      <p class="text-sm text-neutral-400 dark:text-neutral-500 mt-2">{{ $t('ads.campaigns.empty_desc') }}</p>
      <button
        @click="navigateTo(localePath('/ads/campaigns/create'))"
        class="btn-primary mt-4"
      >
        {{ $t('ads.campaigns.create_first') }}
      </button>
    </div>

    <!-- Campaign Detail Modal -->
    <Teleport to="body">
    <div
      v-if="selectedCampaign"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      @click.self="selectedCampaign = null"
    >
      <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div class="sticky top-0 bg-white dark:bg-neutral-800 border-b border-neutral-200 dark:border-neutral-700 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.name }}</h2>
          <button @click="selectedCampaign = null" class="text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200">
            <X class="w-6 h-6" />
          </button>
        </div>

        <div class="p-6 space-y-6">
          <!-- Status + Actions -->
          <div class="flex items-center justify-between flex-wrap gap-2">
            <UiBadge :variant="statusVariant(selectedCampaign.status)" type="soft" class="capitalize">
              {{ selectedCampaign.status }}
            </UiBadge>
            <div class="flex gap-2">
              <UiButton
                variant="outline"
                :icon="Pencil"
                :disabled="actionLoading"
                @click="goToEdit"
              >
                {{ $t('ads.campaign_detail.edit') }}
              </UiButton>
              <UiButton
                variant="outline"
                :icon="Copy"
                :disabled="actionLoading"
                @click="duplicateCampaign"
              >
                {{ $t('ads.campaign_detail.duplicate') }}
              </UiButton>
              <UiButton v-if="selectedCampaign.status === 'draft'" variant="success" :icon="Play" :disabled="actionLoading" @click="updateStatus('active')">
                {{ $t('ads.campaign_detail.activate') }}
              </UiButton>
              <UiButton v-if="selectedCampaign.status === 'active'" variant="warning" :icon="Pause" :disabled="actionLoading" @click="updateStatus('paused')">
                {{ $t('ads.campaign_detail.pause') }}
              </UiButton>
              <UiButton v-if="selectedCampaign.status === 'paused'" variant="success" :icon="Play" :disabled="actionLoading" @click="updateStatus('active')">
                {{ $t('ads.campaign_detail.resume') }}
              </UiButton>
              <UiButton
                v-if="selectedCampaign.status !== 'archived' && selectedCampaign.total_views > 0"
                variant="outline"
                :icon="Archive"
                :disabled="actionLoading"
                @click="updateStatus('archived')"
              >
                {{ $t('ads.campaign_detail.archive') }}
              </UiButton>
              <UiButton
                v-if="selectedCampaign.status === 'archived'"
                variant="outline"
                :icon="ArchiveRestore"
                :disabled="actionLoading"
                @click="updateStatus('paused')"
              >
                {{ $t('ads.campaign_detail.unarchive') }}
              </UiButton>
              <UiButton
                v-if="selectedCampaign.total_views === 0"
                :variant="deletePending ? 'error' : 'outline-error'"
                :icon="Trash2"
                :disabled="actionLoading"
                @click="handleDelete"
              >
                {{ deletePending ? $t('ads.campaign_detail.delete_sure') : $t('ads.campaign_detail.delete') }}
              </UiButton>
            </div>
          </div>

          <!-- Error message -->
          <UiAlert v-if="actionError" variant="error">{{ actionError }}</UiAlert>

          <!-- Ad Content Preview -->
          <img
            v-if="selectedCampaign.image_url"
            :src="selectedCampaign.image_url"
            :alt="selectedCampaign.post_title"
            class="w-full h-[200px] object-cover rounded-lg"
          />
          <div class="bg-neutral-50 dark:bg-neutral-900 rounded-lg p-4 border border-neutral-200 dark:border-neutral-700">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ selectedCampaign.post_title }}</h3>
            <!-- post_content is nh3-sanitized server-side; rendered via v-html like FeedCard / ad detail -->
            <div class="text-neutral-700 dark:text-neutral-300 text-sm leading-relaxed ads-modal-content" v-html="selectedCampaign.post_content" />
            <a v-if="selectedCampaign.link" :href="selectedCampaign.link" target="_blank" rel="noopener noreferrer" class="inline-block mt-2 text-sm text-link break-all">
              {{ selectedCampaign.link }}
            </a>
          </div>

          <!-- Stats -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
              <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.views') }}</p>
              <p class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.total_views }}</p>
            </div>
            <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
              <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.clicks') }}</p>
              <p class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.total_clicks }}</p>
            </div>
            <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
              <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.reward') }}</p>
              <p class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.reward_sats }} sats</p>
            </div>
            <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3">
              <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.campaign_detail.budget') }}</p>
              <p class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.spent_sats }} / {{ selectedCampaign.budget_sats }}</p>
            </div>
          </div>

          <!-- Targeting -->
          <div class="text-sm text-neutral-600 dark:text-neutral-400 space-y-1">
            <p>{{ $t('ads.create_campaign.targeting') }}: {{ selectedCampaign.target_gender === 'any' ? $t('ads.profile.gender_any') : selectedCampaign.target_gender }}, {{ selectedCampaign.target_age_from }}–{{ selectedCampaign.target_age_to }}</p>
            <p v-if="selectedCampaign.target_latitude && selectedCampaign.target_radius_km > 0" class="flex items-center gap-1">
              <MapPin class="w-3.5 h-3.5 flex-shrink-0" />
              {{ $t('ads.create_campaign.within_km', { km: selectedCampaign.target_radius_km }) }}
              <span class="font-mono text-xs text-neutral-400 ml-1">{{ selectedCampaign.target_latitude.toFixed(4) }}, {{ selectedCampaign.target_longitude.toFixed(4) }}</span>
            </p>
            <div v-if="selectedCampaign.target_interest_ids?.length > 0" class="flex flex-wrap gap-1 mt-1">
              <span class="text-xs text-neutral-500 dark:text-neutral-400 mr-1">{{ $t('ads.create_campaign.interests') }}:</span>
              <span
                v-for="iid in selectedCampaign.target_interest_ids"
                :key="iid"
                class="px-2 py-0.5 text-xs rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300"
              >{{ interestLabel(iid) }}</span>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="selectedCampaign.include_self"
                @change="toggleSelfVisibility('include')"
                :disabled="actionLoading"
                class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-primary"
              />
              <span>{{ $t('ads.create_campaign.include_self') }}</span>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="selectedCampaign.exclude_self"
                @change="toggleSelfVisibility('exclude')"
                :disabled="actionLoading"
                class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-secondary focus:ring-primary"
              />
              <span>{{ $t('ads.create_campaign.exclude_self') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated, onUnmounted } from 'vue'
import { Plus, X, Play, Pause, Trash2, MapPin, Pencil, Copy, Archive, ArchiveRestore } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()

const campaigns = ref<any[]>([])
const selectedCampaign = ref<any>(null)
const actionLoading = ref(false)
const actionError = ref('')

const activeTab = useTabSync(['active', 'archived'])
const archivedCount = computed(() => campaigns.value.filter(c => c.status === 'archived').length)
const visibleCampaigns = computed(() =>
  activeTab.value === 'archived'
    ? campaigns.value.filter(c => c.status === 'archived')
    : campaigns.value.filter(c => c.status !== 'archived')
)
const tabDefs = computed(() => [
  { id: 'active', label: t('ads.campaigns.tab_active') },
  { id: 'archived', label: t('ads.campaigns.tab_archived'), badge: archivedCount.value || undefined },
])

function statusVariant(status: string): 'success' | 'neutral' | 'warning' | 'secondary' {
  if (status === 'active') return 'success'
  if (status === 'paused') return 'warning'
  if (status === 'completed') return 'secondary'
  return 'neutral'
}

// Interest names for the targeting summary (API returns ULIDs only)
const interestMap = ref<Record<string, string>>({})
async function loadInterestNames() {
  try {
    const interests = await $fetch<any[]>('/api/v1/ads/interests/')
    const map: Record<string, string> = {}
    for (const i of interests) map[i.id] = t(`ads.interests.${i.slug}`, i.name)
    interestMap.value = map
  } catch {}
}
function interestLabel(id: string): string {
  return interestMap.value[id] || id
}

function goToEdit() {
  if (!selectedCampaign.value) return
  const id = selectedCampaign.value.id
  // Close the modal first — this page is keepalive'd, an open modal would survive navigation
  selectedCampaign.value = null
  navigateTo(localePath({ path: '/ads/campaigns/create', query: { edit: id } }))
}

// Server-side copy into a fresh draft, then straight into the edit form —
// the copy has no views, so every field (reward/budget included) is editable
async function duplicateCampaign() {
  if (!selectedCampaign.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    await authStore.ensureToken()
    const copy = await $fetch<any>(`/api/v1/ads/campaigns/${selectedCampaign.value.id}/duplicate/`, {
      method: 'POST', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    selectedCampaign.value = null
    navigateTo(localePath({ path: '/ads/campaigns/create', query: { edit: copy.id } }))
  } catch (error: any) {
    actionError.value = error?.data?.detail || error?.message || 'Error'
    console.error('Failed to duplicate campaign:', error)
  } finally {
    actionLoading.value = false
  }
}

// Two-tap delete confirmation
const deletePending = ref(false)
let deleteResetTimer: ReturnType<typeof setTimeout> | null = null
function handleDelete() {
  if (!deletePending.value) {
    deletePending.value = true
    deleteResetTimer = setTimeout(() => { deletePending.value = false }, 3000)
    return
  }
  if (deleteResetTimer) clearTimeout(deleteResetTimer)
  deletePending.value = false
  deleteCampaign()
}
watch(selectedCampaign, () => {
  deletePending.value = false
  actionError.value = ''
  if (deleteResetTimer) clearTimeout(deleteResetTimer)
})

// ESC closes the modal
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && selectedCampaign.value) selectedCampaign.value = null
}

async function loadCampaigns() {
  try {
    await authStore.ensureToken()
    const response = await $fetch<any>('/api/v1/ads/campaigns/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    campaigns.value = response.items || []
  } catch (error) {
    console.error('Failed to load campaigns:', error)
  }
}

async function updateStatus(status: string) {
  if (!selectedCampaign.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    await authStore.ensureToken()
    const updated = await $fetch<any>(`/api/v1/ads/campaigns/${selectedCampaign.value.id}/`, {
      method: 'PUT', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    })
    selectedCampaign.value = updated
    await loadCampaigns()
  } catch (error: any) {
    const detail = error?.data?.detail || error?.message || 'Error'
    actionError.value = detail
    console.error('Failed to update campaign:', error)
  } finally {
    actionLoading.value = false
  }
}

async function toggleSelfVisibility(field: 'include' | 'exclude') {
  if (!selectedCampaign.value) return
  actionLoading.value = true
  try {
    await authStore.ensureToken()
    const body = field === 'include'
      ? { include_self: !selectedCampaign.value.include_self }
      : { exclude_self: !selectedCampaign.value.exclude_self }
    const updated = await $fetch<any>(`/api/v1/ads/campaigns/${selectedCampaign.value.id}/`, {
      method: 'PUT', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    selectedCampaign.value = updated
    await loadCampaigns()
  } catch (error) {
    console.error('Failed to update self-visibility:', error)
  } finally {
    actionLoading.value = false
  }
}

async function deleteCampaign() {
  if (!selectedCampaign.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/ads/campaigns/${selectedCampaign.value.id}/`, {
      method: 'DELETE', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    selectedCampaign.value = null
    await loadCampaigns()
  } catch (error: any) {
    actionError.value = error?.data?.detail || error?.message || 'Error'
    console.error('Failed to delete campaign:', error)
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => {
  loadCampaigns()
  loadInterestNames()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
onActivated(() => loadCampaigns())

definePageMeta({
  middleware: 'auth',
})
</script>

<style scoped>
.ads-modal-content :deep(a) {
  color: #4E4EC8;
  text-decoration: underline;
}
.ads-modal-content :deep(ul) { list-style: disc; padding-left: 1.5rem; }
.ads-modal-content :deep(ol) { list-style: decimal; padding-left: 1.5rem; }
.ads-modal-content :deep(blockquote) {
  border-left: 3px solid #4E4EC8;
  padding-left: 0.75rem;
  color: #9ca3af;
}
</style>
