<template>
  <UpdateCard
    :show="newVersionAvailable && !dismissed"
    :title="$t('update.new_version')"
    :description="$t('update.description')"
    :action-label="$t('update.refresh')"
    :icon="RefreshCw"
    @action="reload"
    @dismiss="dismissed = true"
  >
    <div v-if="releases.length" class="mt-2.5">
      <button
        type="button"
        class="flex items-center gap-1 text-xs font-medium text-secondary hover:underline dark:text-secondary-400"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <ChevronDown class="h-3.5 w-3.5 transition-transform" :class="{ '-rotate-180': expanded }" />
        {{ $t('update.whats_new') }}
      </button>
      <div v-if="expanded" class="mt-2 max-h-56 space-y-4 overflow-y-auto pr-1">
        <ChangelogRelease v-for="r in releases" :key="r.version" :release="r" compact />
        <NuxtLink
          :to="localePath('/changelog')"
          class="inline-block pb-1 text-xs font-medium text-secondary hover:underline dark:text-secondary-400"
        >
          {{ $t('update.full_changelog') }}
        </NuxtLink>
      </div>
    </div>
  </UpdateCard>
</template>

<script setup lang="ts">
import { RefreshCw, ChevronDown } from 'lucide-vue-next'
import type { ChangelogRelease as Release } from '~/composables/useChangelog'

const newVersionAvailable = useState('newVersionAvailable', () => false)
const dismissed = ref(false)
const expanded = ref(false)
const releases = ref<Release[]>([])

const localePath = useLocalePath()
const config = useRuntimeConfig()
const { fetchIndex, fetchRelease, parseBaseVersion, compareVersions, markVersionSeen } = useChangelog()

// When a deploy is announced, check whether it crossed a tagged release:
// compare our build's base tag against a fresh copy of the changelog index
// and load the notes for every release we don't have yet (newest first).
watch(newVersionAvailable, async (available) => {
  if (!available || releases.value.length) return
  const base = parseBaseVersion(config.public.appVersion as string)
  if (!base) return
  try {
    const index = await fetchIndex({ fresh: true })
    const newer = index
      .filter(e => compareVersions(e.version, base) > 0)
      .slice(0, 3)
    const loaded = await Promise.all(newer.map(e => fetchRelease(e.version).catch(() => null)))
    releases.value = loaded.filter((r): r is Release => !!r)
  } catch {
    // Notes are a bonus — the refresh prompt works without them.
  }
})

const reload = () => {
  // These notes were already offered here, so the post-reload WhatsNewCard
  // would only repeat them.
  if (releases.value.length) markVersionSeen(releases.value[0].version)
  window.location.reload()
}
</script>
