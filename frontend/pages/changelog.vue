<template>
  <div class="mx-auto max-w-2xl px-4 py-6 sm:px-6 lg:px-8">
    <div class="flex items-start justify-between gap-4">
      <PageHeader :title="$t('changelog.title')" :subtitle="$t('changelog.subtitle')" class="min-w-0 flex-1" />
      <img
        src="/images/para/reading.webp"
        alt=""
        aria-hidden="true"
        class="h-20 w-auto shrink-0 select-none sm:h-24"
      />
    </div>

    <div v-if="releases.length" class="mt-2">
      <div
        v-for="(release, i) in releases"
        :key="release.version"
        class="mt-8 border-t border-neutral-200 pt-8 first:mt-0 first:border-t-0 first:pt-0 dark:border-neutral-800"
      >
        <ChangelogRelease :release="release" :latest="i === 0" />
      </div>

      <div v-if="remaining > 0" class="mt-8 text-center">
        <UiButton variant="outline" size="sm" :loading="loadingMore" @click="showEarlier">
          {{ $t('changelog.show_earlier') }}
        </UiButton>
      </div>
    </div>

    <div v-else class="py-12 text-center">
      <BookOpen class="mx-auto h-12 w-12 text-neutral-400" />
      <h3 class="mt-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('changelog.empty') }}</h3>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BookOpen } from 'lucide-vue-next'
import type { ChangelogRelease as Release } from '~/composables/useChangelog'

const INITIAL_COUNT = 4

const { t } = useI18n()
const { fetchIndex, fetchRelease } = useChangelog()

useHead({ title: computed(() => t('changelog.title')) })
useSeoMeta({
  description: computed(() => t('changelog.meta_description')),
  ogTitle: computed(() => t('changelog.title')),
  ogDescription: computed(() => t('changelog.meta_description')),
})

// A missing per-release file must not blank the whole page — skip it.
const fetchReleases = (entries: { version: string }[]) =>
  Promise.all(entries.map(e => fetchRelease(e.version).catch(() => null)))
    .then(list => list.filter((r): r is Release => !!r))

const { data } = await useAsyncData('changelog', async () => {
  const index = await fetchIndex()
  const initial = await fetchReleases(index.slice(0, INITIAL_COUNT))
  return { index, initial }
})

const releases = ref<Release[]>(data.value?.initial || [])
// Count consumed index entries, not rendered releases — a skipped file must
// not leave the button loading the same slice forever.
const consumed = ref(Math.min(INITIAL_COUNT, data.value?.index.length || 0))
const remaining = computed(() => (data.value?.index.length || 0) - consumed.value)
const loadingMore = ref(false)

async function showEarlier() {
  if (!data.value) return
  loadingMore.value = true
  try {
    const rest = data.value.index.slice(consumed.value)
    consumed.value = data.value.index.length
    releases.value = [...releases.value, ...await fetchReleases(rest)]
  } finally {
    loadingMore.value = false
  }
}
</script>
