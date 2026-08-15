<template>
  <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
    <div
      v-for="feed in feeds"
      :key="feed.id"
      class="p-3 bg-white dark:bg-neutral-800 text-sm"
    >
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span class="w-2 h-2 rounded-full flex-shrink-0" :class="dotClass(feed)" aria-hidden="true" />
        <a
          :href="primaryUrl(feed)"
          target="_blank"
          rel="noopener"
          class="font-medium text-link truncate"
        >{{ feed.name }}</a>
        <!-- A feed can be several files (NYC borough zips, two Madrid lots) — one link plus a count -->
        <span v-if="extraUrlCount(feed)" class="text-xs text-neutral-400 dark:text-neutral-500" :title="feed.url">+{{ extraUrlCount(feed) }}</span>
        <span class="text-xs text-neutral-500 dark:text-neutral-400 ml-auto">{{ statusLabel(feed) }}</span>
        <UiBadge v-if="feed.has_realtime" variant="success" type="soft" size="sm">{{ $t('transit.feeds.realtime') }}</UiBadge>
      </div>

      <div class="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-neutral-600 dark:text-neutral-400 tabular-nums">
        <span>{{ $t('transit.feeds.routes') }}: <strong>{{ feed.routes_count }}</strong></span>
        <span>{{ $t('transit.feeds.stops') }}: <strong>{{ feed.stops_count }}</strong></span>
        <span>{{ $t('transit.feeds.trips') }}: <strong>{{ feed.trips_count }}</strong></span>
        <span v-if="feed.last_imported_at">{{ $t('transit.feeds.imported') }}: {{ importedOn(feed.last_imported_at) }}</span>
      </div>

      <div v-if="feed.agencies.length" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {{ operatorNames(feed).join(', ') }}
      </div>

      <!-- We mirror these feeds verbatim, so their terms are published with them. A publisher
           who states none is a fact about the publisher, not our error — hence neutral ink. -->
      <div class="mt-1 text-xs">
        <template v-if="feed.license">
          <span class="text-neutral-500 dark:text-neutral-400">{{ $t('transit.feeds.license') }}:</span>
          <a
            v-if="feed.license_url"
            :href="feed.license_url"
            target="_blank"
            rel="noopener"
            class="text-link ml-1"
          >{{ feed.license }}</a>
          <span v-else class="text-neutral-700 dark:text-neutral-300 ml-1">{{ feed.license }}</span>
          <span v-if="feed.attribution" class="text-neutral-500 dark:text-neutral-400"> · {{ feed.attribution }}</span>
        </template>
        <span v-else class="text-neutral-500 dark:text-neutral-400">{{ $t('transit.feeds.license_missing') }}</span>
      </div>

      <!-- Error text names an operator's broken endpoint — the API only sends it to staff -->
      <template v-if="feed.last_error">
        <div
          v-if="expandedError === feed.id"
          class="mt-2 p-2 bg-error/10 dark:bg-error/20 text-error dark:text-red-300 rounded text-xs font-mono break-all"
        >{{ feed.last_error }}</div>
        <button
          v-else
          @click="expandedError = feed.id"
          class="mt-1 text-xs text-error hover:underline"
        >{{ $t('transit.feeds.show_error') }}</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Feed {
  id: string
  name: string
  url: string
  is_active: boolean
  has_error: boolean
  last_error: string
  has_realtime: boolean
  last_imported_at: string | null
  license: string
  license_url: string
  attribution: string
  agencies: string[]
  routes_count: number
  stops_count: number
  trips_count: number
}

defineProps<{ feeds: Feed[] }>()

const { t, locale } = useI18n()
const expandedError = ref<string | null>(null)

function dotClass(feed: Feed): string {
  if (!feed.is_active) return 'bg-neutral-400'
  return feed.has_error ? 'bg-warning' : 'bg-success'
}

function statusLabel(feed: Feed): string {
  if (!feed.is_active) return t('transit.feeds.inactive')
  return feed.has_error ? t('transit.feeds.error') : t('transit.feeds.active')
}

// A feed can carry several GTFS agency rows under one operator name (Carris
// Metropolitana ships four); the reader wants the operator, not the row count.
function operatorNames(feed: Feed): string[] {
  return [...new Set(feed.agencies || [])]
}

function feedUrls(feed: Feed): string[] {
  return (feed.url || '').split(/\s+/).filter(Boolean)
}

function primaryUrl(feed: Feed): string {
  return feedUrls(feed)[0] || feed.url
}

function extraUrlCount(feed: Feed): number {
  return Math.max(0, feedUrls(feed).length - 1)
}

// Fixed UTC date, not a relative "3h ago": the list renders on the server too, and a
// clock-based string would differ between the SSR pass and hydration.
function importedOn(iso: string): string {
  return new Intl.DateTimeFormat(locale.value, { timeZone: 'UTC', dateStyle: 'medium' }).format(new Date(iso))
}
</script>
