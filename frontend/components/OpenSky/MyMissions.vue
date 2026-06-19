<template>
  <div>
    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" role="status"><span class="sr-only">Loading...</span></div>
    </div>

    <!-- Not authenticated — show all missions -->
    <div v-else-if="!authStore.isAuthenticated">
      <OpenSkyMissionGrid
        :missions="allMissions"
        :loading="loadingAll"
      />
      <div v-if="!loadingAll && allMissions.length === 0" class="text-center py-12 text-neutral-500">
        <Camera class="w-12 h-12 mx-auto mb-4 opacity-50" />
        <h3 class="text-lg font-medium">{{ $t('opensky.no_missions', 'No missions yet') }}</h3>
        <p class="text-sm mt-1">{{ $t('opensky.be_first', 'Be the first to contribute aerial imagery!') }}</p>
      </div>
    </div>

    <!-- Authenticated -->
    <div v-else>
      <!-- Filter toggle -->
      <UiTabs v-model="activeFilter" :tabs="filterTabs" variant="pills" class="mb-6" />

      <!-- Summary (own missions only) -->
      <div v-if="!showAllPilots && myMissions.length > 0" class="mb-6 p-4 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
        <div class="flex flex-wrap gap-4 text-sm">
          <div>
            <span class="text-neutral-500">{{ $t('opensky.total_missions', 'Total:') }}</span>
            <span class="ml-1 font-semibold">{{ myMissions.length }}</span>
          </div>
          <div>
            <span class="text-neutral-500">{{ $t('opensky.published_count', 'Published:') }}</span>
            <span class="ml-1 font-semibold text-success">{{ publishedCount }}</span>
          </div>
          <div v-if="processingCount > 0">
            <span class="text-neutral-500">{{ $t('opensky.processing_count', 'Processing:') }}</span>
            <span class="ml-1 font-semibold text-warning">{{ processingCount }}</span>
          </div>
          <div v-if="failedCount > 0">
            <span class="text-neutral-500">{{ $t('opensky.failed_count', 'Failed:') }}</span>
            <span class="ml-1 font-semibold text-error">{{ failedCount }}</span>
          </div>
        </div>
      </div>

      <!-- Empty state (own missions) -->
      <div v-if="!showAllPilots && !loading && myMissions.length === 0" class="text-center py-12 text-neutral-500">
        <Upload class="w-12 h-12 mx-auto mb-4 opacity-50" />
        <h3 class="text-lg font-medium">{{ $t('opensky.no_your_missions', 'You haven\'t uploaded any missions yet') }}</h3>
        <p class="text-sm mt-1">{{ $t('opensky.upload_cta', 'Upload drone photos to create your first mission!') }}</p>
      </div>

      <!-- Grid -->
      <OpenSkyMissionGrid
        v-if="showAllPilots || myMissions.length > 0"
        :missions="displayedMissions"
        :loading="showAllPilots ? loadingAll : loading"
        :can-delete="!showAllPilots"
        :my-profile-id="showAllPilots ? authStore.activeProfile?.id : undefined"
        @delete="handleDelete"
        @view-3d="handleView3d"
        @download-3d="handleDownload3d"
        @add-photos="$emit('add-photos', $event)"
      />

      <!-- Empty state (all pilots) -->
      <div v-if="showAllPilots && !loadingAll && allMissions.length === 0" class="text-center py-12 text-neutral-500">
        <Camera class="w-12 h-12 mx-auto mb-4 opacity-50" />
        <h3 class="text-lg font-medium">{{ $t('opensky.no_missions', 'No missions yet') }}</h3>
        <p class="text-sm mt-1">{{ $t('opensky.be_first', 'Be the first to contribute aerial imagery!') }}</p>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    <UiConfirmModal
      :model-value="!!deletingMissionId"
      @update:model-value="deletingMissionId = null"
      :title="$t('opensky.delete_confirm_title', 'Delete Mission?')"
      :message="$t('opensky.delete_confirm_text', 'This will permanently delete the mission and all associated tiles. This action cannot be undone.')"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('common.delete', 'Delete')"
      :loading="deleting"
      @confirm="confirmDelete"
    />

    <!-- 3D Viewer modal -->
    <Modal
      v-model="show3dViewer"
      :title="$t('opensky.viewer_3d_title', '3D Model Viewer')"
      size="2xl"
    >
      <ClientOnly>
        <OpenSkyModelViewer3D
          v-if="viewing3dMissionId && show3dViewer"
          :glb-url="getMeshGlbUrl(viewing3dMissionId)"
          :auth-token="authStore.token || ''"
          :glb-size-mb="viewing3dGlbSize"
        />
      </ClientOnly>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { Loader2, Upload, Camera, Trash2 } from 'lucide-vue-next'

defineEmits<{
  'add-photos': [missionId: string]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { missions: allMissionsRef, myMissions, loading, fetchMyMissions, fetchMissions, deleteMission, downloadMesh, getMeshGlbUrl, connectRealtimeUpdates, disconnectRealtimeUpdates } = useOpenSky()

const activeFilter = ref('mine')
const filterTabs = computed(() => [
  { id: 'mine', label: t('opensky.filter_mine', 'My missions') },
  { id: 'all', label: t('opensky.filter_all_pilots', 'All pilots') },
])
const showAllPilots = computed(() => activeFilter.value === 'all')
const loadingAll = ref(false)
const allMissions = allMissionsRef

const displayedMissions = computed(() => showAllPilots.value ? allMissions.value : myMissions.value)

const deletingMissionId = ref<string | null>(null)
const deleting = ref(false)

const show3dViewer = ref(false)
const viewing3dMissionId = ref<string | null>(null)
const viewing3dGlbSize = ref(0)

const publishedCount = computed(() => myMissions.value.filter(m => m.status === 'PUBLISHED').length)
const processingCount = computed(() => myMissions.value.filter(m => m.status === 'PROCESSING' || m.status === 'QUEUED').length)
const failedCount = computed(() => myMissions.value.filter(m => m.status === 'FAILED').length)

const handleDelete = (missionId: string) => {
  deletingMissionId.value = missionId
}

const confirmDelete = async () => {
  if (!deletingMissionId.value) return

  deleting.value = true
  try {
    await deleteMission(deletingMissionId.value)
    useToastStore().success('Mission deleted')
  } catch (error) {
    useToastStore().error('Failed to delete mission')
  } finally {
    deleting.value = false
    deletingMissionId.value = null
  }
}

const handleView3d = async (missionId: string) => {
  await authStore.ensureToken()
  const mission = displayedMissions.value.find(m => m.id === missionId)
  viewing3dMissionId.value = missionId
  viewing3dGlbSize.value = mission?.mesh_glb_size_mb ?? 0
  show3dViewer.value = true
}

const handleDownload3d = async (missionId: string) => {
  try {
    await downloadMesh(missionId)
  } catch (error) {
    useToastStore().error('Failed to download 3D model')
  }
}

// Fetch all missions when toggle activated
watch(showAllPilots, async (showAll) => {
  if (showAll && allMissions.value.length === 0) {
    loadingAll.value = true
    try { await fetchMissions() } finally { loadingAll.value = false }
  }
})

// Guard against double-registration of realtime handler
let realtimeConnected = false

function safeConnect() {
  if (realtimeConnected) return
  connectRealtimeUpdates()
  realtimeConnected = true
}

function safeDisconnect() {
  if (!realtimeConnected) return
  disconnectRealtimeUpdates()
  realtimeConnected = false
}

// Fetch missions on mount + connect WS
onMounted(() => {
  if (authStore.isAuthenticated) {
    fetchMyMissions()
    safeConnect()
  } else {
    // Unauthenticated: show all missions
    loadingAll.value = true
    fetchMissions().finally(() => { loadingAll.value = false })
  }
})

onUnmounted(() => {
  safeDisconnect()
})

// Watch for auth changes
watch(() => authStore.isAuthenticated, (isAuth) => {
  if (isAuth) {
    fetchMyMissions()
    safeConnect()
  } else {
    safeDisconnect()
  }
})
</script>
