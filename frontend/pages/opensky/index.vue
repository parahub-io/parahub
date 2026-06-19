<template>
  <div class="mx-auto px-4 sm:px-6 lg:px-8 py-6 max-w-6xl">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div class="mr-4">
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('opensky.title') }}
        </h1>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          {{ $t('opensky.subtitle') }}
        </p>
      </div>

      <UiButton
        v-if="authStore.isAuthenticated"
        variant="primary"
        size="sm"
        :icon="Upload"
        class="min-h-[44px] shrink-0"
        @click="appendMissionId = undefined; showUploadModal = true"
      >
        {{ $t('opensky.upload_mission') }}
      </UiButton>
      <UiButton
        v-else
        variant="primary"
        size="sm"
        :to="localePath('/auth/login')"
        class="min-h-[44px] shrink-0"
      >
        {{ $t('opensky.login_to_upload') }}
      </UiButton>
    </div>

    <!-- Stats Cards -->
    <OpenSkyStatsCards :stats="stats" class="mb-6" />

    <!-- Missions -->
    <OpenSkyMyMissions @add-photos="openAddPhotos" />

    <!-- Upload Modal -->
    <Modal v-model="showUploadModal" :title="appendMissionId ? $t('opensky.add_photos_title', 'Add Photos to Mission') : $t('opensky.upload_title')" size="lg">
      <OpenSkyUploadForm :mission-id="appendMissionId" @uploaded="onMissionUploaded" @close="showUploadModal = false" />
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { Upload } from 'lucide-vue-next'

// Page meta
definePageMeta({
  middleware: 'auth',
})

useHead({
  title: 'OpenSky - Aerial Imagery'
})

const authStore = useAuthStore()
const localePath = useLocalePath()
const { stats, fetchStats } = useOpenSky()

const showUploadModal = ref(false)
const appendMissionId = ref<string | undefined>()

const openAddPhotos = (missionId: string) => {
  appendMissionId.value = missionId
  showUploadModal.value = true
}

const onMissionUploaded = (mission: any) => {
  appendMissionId.value = undefined
  fetchStats()
}

onMounted(() => {
  fetchStats()
})
</script>
