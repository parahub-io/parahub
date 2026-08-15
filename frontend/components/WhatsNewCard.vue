<template>
  <UpdateCard
    :show="releases.length > 0 && !dismissed && !newVersionAvailable"
    :title="$t('update.whats_new')"
    :description="$t('update.updated_description')"
    :dismiss-label="$t('update.got_it')"
    @dismiss="dismissed = true"
  >
    <div class="mt-2.5 max-h-56 space-y-4 overflow-y-auto pr-1">
      <ChangelogRelease v-for="r in releases" :key="r.version" :release="r" compact />
      <NuxtLink
        :to="localePath('/changelog')"
        class="inline-block pb-1 text-xs font-medium text-secondary hover:underline dark:text-secondary-400"
      >
        {{ $t('update.full_changelog') }}
      </NuxtLink>
    </div>
  </UpdateCard>
</template>

<script setup lang="ts">
import type { ChangelogRelease as Release } from '~/composables/useChangelog'

// Catch-up counterpart of UpdateBanner: that one needs the user to be online
// when the deploy is announced over WS, this one greets everyone who was away
// while releases happened. Same notes, no refresh button — whoever loads this
// page is already running the new build.
const newVersionAvailable = useState('newVersionAvailable', () => false)
const dismissed = ref(false)
const releases = ref<Release[]>([])

const localePath = useLocalePath()
const config = useRuntimeConfig()
const {
  fetchIndex, fetchRelease, parseBaseVersion, compareVersions, readSeenVersion, markVersionSeen,
} = useChangelog()

onMounted(async () => {
  const base = parseBaseVersion(config.public.appVersion as string)
  if (!base) return

  const seen = readSeenVersion()
  // Nothing to catch up on: either this browser has never been here (a
  // first-time visitor gets no release notes) or it is already up to date.
  if (!seen || compareVersions(base, seen) <= 0) {
    markVersionSeen(base)
    return
  }

  try {
    const index = await fetchIndex({ fresh: true })
    const missed = index
      .filter(e => compareVersions(e.version, seen) > 0 && compareVersions(e.version, base) <= 0)
      .slice(0, 3)
    const loaded = await Promise.all(missed.map(e => fetchRelease(e.version).catch(() => null)))
    releases.value = loaded.filter((r): r is Release => !!r)
    // Marked once the notes are in hand, not on dismiss: the card is shown
    // exactly once per release and a reload never brings it back. A failed
    // fetch leaves the marker alone so the next visit retries.
    markVersionSeen(base)
  } catch { /* no notes, no card */ }
})
</script>
