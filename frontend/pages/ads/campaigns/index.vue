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

    <!-- Campaigns list -->
    <div v-if="campaigns.length > 0" class="space-y-4">
      <div
        v-for="campaign in campaigns"
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
          <span
            :class="statusClass(campaign.status)"
            class="px-3 py-1 rounded-full text-xs font-medium capitalize"
          >
            {{ campaign.status }}
          </span>
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

    <!-- Empty state -->
    <div v-else class="text-center py-12">
      <img src="/images/para/pointing.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
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
    <div
      v-if="selectedCampaign"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      @click.self="selectedCampaign = null"
    >
      <div class="bg-white dark:bg-neutral-800 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div class="sticky top-0 bg-white dark:bg-neutral-800 border-b border-neutral-200 dark:border-neutral-700 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">{{ selectedCampaign.name }}</h2>
          <button @click="selectedCampaign = null" class="text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200">
            <X class="w-6 h-6" />
          </button>
        </div>

        <div class="p-6 space-y-6">
          <!-- Status + Actions -->
          <div class="flex items-center justify-between flex-wrap gap-2">
            <span :class="statusClass(selectedCampaign.status)" class="px-3 py-1 rounded-full text-sm font-medium capitalize">
              {{ selectedCampaign.status }}
            </span>
            <div class="flex gap-2">
              <button v-if="selectedCampaign.status === 'draft'" @click="updateStatus('active')" :disabled="actionLoading" class="btn-success gap-2">
                <Play class="w-4 h-4" />
                {{ $t('ads.campaign_detail.activate') }}
              </button>
              <button v-if="selectedCampaign.status === 'active'" @click="updateStatus('paused')" :disabled="actionLoading" class="btn-warning flex items-center gap-2">
                <Pause class="w-4 h-4" />
                {{ $t('ads.campaign_detail.pause') }}
              </button>
              <button v-if="selectedCampaign.status === 'paused'" @click="updateStatus('active')" :disabled="actionLoading" class="btn-success gap-2">
                <Play class="w-4 h-4" />
                {{ $t('ads.campaign_detail.resume') }}
              </button>
              <button v-if="selectedCampaign.total_views === 0" @click="deleteCampaign" :disabled="actionLoading" class="btn-outline-error flex items-center gap-2">
                <Trash2 class="w-4 h-4" />
                {{ $t('ads.campaign_detail.delete') }}
              </button>
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
            <p class="text-neutral-700 dark:text-neutral-300 text-sm whitespace-pre-wrap">{{ selectedCampaign.post_content }}</p>
            <a v-if="selectedCampaign.link" :href="selectedCampaign.link" target="_blank" class="inline-block mt-2 text-sm text-primary hover:underline">
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
                class="px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary"
              >{{ iid }}</span>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="selectedCampaign.include_self"
                @change="toggleSelfVisibility('include')"
                :disabled="actionLoading"
                class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
              />
              <span>{{ $t('ads.create_campaign.include_self') }}</span>
            </div>
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                :checked="selectedCampaign.exclude_self"
                @change="toggleSelfVisibility('exclude')"
                :disabled="actionLoading"
                class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
              />
              <span>{{ $t('ads.create_campaign.exclude_self') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onActivated } from 'vue'
import { Plus, Megaphone, X, Play, Pause, Trash2, MapPin } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()

const campaigns = ref<any[]>([])
const selectedCampaign = ref<any>(null)
const actionLoading = ref(false)
const actionError = ref('')

function statusClass(status: string) {
  return {
    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300': status === 'active',
    'bg-neutral-100 text-neutral-800 dark:bg-neutral-900/30 dark:text-neutral-300': status === 'draft',
    'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300': status === 'paused',
    'bg-secondary-100 text-secondary-800 dark:bg-secondary-900/30 dark:text-secondary-300': status === 'completed',
  }
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
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/ads/campaigns/${selectedCampaign.value.id}/`, {
      method: 'DELETE', credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    selectedCampaign.value = null
    await loadCampaigns()
  } catch (error) {
    console.error('Failed to delete campaign:', error)
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => loadCampaigns())
onActivated(() => loadCampaigns())

definePageMeta({
  middleware: 'auth',
})
</script>
