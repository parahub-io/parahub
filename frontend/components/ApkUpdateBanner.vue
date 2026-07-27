<template>
  <Teleport to="body">
    <Transition name="apk-update-banner">
      <div
        v-if="available && !dismissed"
        class="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-3 px-4 py-2.5 rounded-lg shadow-lg border bg-secondary-50 dark:bg-secondary-900 border-secondary-300 dark:border-secondary-700"
      >
        <Download class="w-4 h-4 text-secondary dark:text-secondary-400 flex-shrink-0" />
        <span class="text-sm text-secondary-800 dark:text-secondary-200">
          {{ $t('update.app_new_version') }}
        </span>
        <button
          @click="download"
          class="btn-secondary px-3 py-1 text-xs rounded-md"
        >
          {{ $t('update.download') }}
        </button>
        <button
          @click="dismiss"
          class="text-secondary-400 hover:text-secondary dark:hover:text-secondary-300 transition-colors"
          :aria-label="$t('common.cancel')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { Download, X } from 'lucide-vue-next'

const available = useState('apkUpdateAvailable', () => false)
const version = useState('apkUpdateVersion', () => 0)
const dismissed = ref(false)

const download = async () => {
  // System browser handles the download; tapping the finished download runs
  // the package installer, which updates in place (same signing key).
  const { Browser } = await import('@capacitor/browser')
  await Browser.open({ url: `${window.location.origin}/parahub.apk` })
}

const dismiss = () => {
  try {
    localStorage.setItem('apk_update_dismissed', String(version.value))
  } catch { /* private mode */ }
  dismissed.value = true
}
</script>

<style scoped>
.apk-update-banner-enter-active,
.apk-update-banner-leave-active {
  transition: all 0.3s ease;
}

.apk-update-banner-enter-from,
.apk-update-banner-leave-to {
  opacity: 0;
  transform: translate(-50%, 100%);
}
</style>
