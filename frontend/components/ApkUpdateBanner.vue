<template>
  <UpdateCard
    :show="available && !dismissed"
    :title="$t('update.app_new_version')"
    :description="$t('update.app_description')"
    :action-label="$t('update.download')"
    :icon="Download"
    @action="download"
    @dismiss="dismiss"
  />
</template>

<script setup lang="ts">
import { Download } from 'lucide-vue-next'

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
