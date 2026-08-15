<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary dark:hover:text-secondary-400 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>

    <h1 class="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('sources.title') }}</h1>
    <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed mb-8">{{ $t('sources.lead') }}</p>

    <div class="space-y-6">
      <!-- How we treat other people's data — the rule the whole page is an instance of -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Scale class="w-5 h-5 text-neutral-400" />
          {{ $t('sources.basis.title') }}
        </h2>
        <p class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ $t('sources.basis.text') }}</p>
        <p class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed mt-2">
          <i18n-t keypath="sources.basis.contact" tag="span" scope="global">
            <template #email>
              <a href="mailto:info@parahub.io" class="text-link font-mono">info&#64;parahub.io</a>
            </template>
          </i18n-t>
        </p>
      </section>

      <!-- Transit: rendered from the live feed registry, not a hand-kept list -->
      <section id="transit" class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Bus class="w-5 h-5 text-neutral-400" />
          {{ $t('sources.transit.title') }}
        </h2>
        <p v-if="feeds.length" class="text-sm text-neutral-900 dark:text-neutral-100 font-medium tabular-nums">{{ $t('sources.transit.counts', transitCounts) }}</p>
        <p v-if="feeds.length" class="text-sm text-neutral-600 dark:text-neutral-400 mt-1 mb-4">{{ $t('sources.transit.lead') }}</p>
        <TransitFeedsList v-if="feeds.length" :feeds="feeds" />
        <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('sources.transit.unavailable') }}</p>
      </section>

      <!-- Everything else: static, because these change on the scale of years -->
      <section v-for="group in groups" :key="group.id" :id="group.id" class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <component :is="group.icon" class="w-5 h-5 text-neutral-400" />
          {{ group.title }}
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700 mt-4">
          <div v-for="item in group.items" :key="item.name" class="p-3 bg-white dark:bg-neutral-800 text-sm">
            <a :href="item.url" target="_blank" rel="noopener" class="font-medium text-link">{{ item.name }}</a>
            <div class="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">{{ item.use }}</div>
            <div class="text-xs mt-1">
              <span class="text-neutral-500 dark:text-neutral-400">{{ $t('sources.license') }}:</span>
              <a
                v-if="item.licenseUrl"
                :href="item.licenseUrl"
                target="_blank"
                rel="noopener"
                class="text-link ml-1"
              >{{ item.license || $t('sources.publisher_terms') }}</a>
              <span v-else class="text-neutral-700 dark:text-neutral-300 ml-1">{{ item.license }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Member-owned data: not licensed to us by a publisher, published by its owner -->
      <section id="members" class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Users class="w-5 h-5 text-neutral-400" />
          {{ $t('sources.members.title') }}
        </h2>
        <p class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">
          <i18n-t keypath="sources.members.text" tag="span" scope="global">
            <template #terms>
              <NuxtLink :to="localePath('/about/terms')" class="text-link">{{ $t('footer.terms') }}</NuxtLink>
            </template>
          </i18n-t>
        </p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { ArrowLeft, Bus, Cloud, Map, Scale, Landmark, Users } from 'lucide-vue-next'

const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

// SSR-rendered so the registry is crawlable and citable — the collapsed client-side
// list it replaces existed for nobody but the few who expanded it.
const { data: feedsData, refresh } = await useAsyncData('data-sources-feeds', () =>
  $fetch<any[]>('/api/v1/geo/transit/feeds/').catch(() => [])
)
const feeds = computed<any[]>(() => feedsData.value || [])

// Staff-only error text rides the session cookie, which the SSR request does not carry —
// so staff re-fetch in the browser. Watched rather than called on mount: the auth store
// restores the profile asynchronously, so `is_staff` is often still undefined at mount.
if (import.meta.client) {
  watch(() => authStore.user?.is_staff, (isStaff) => {
    if (isStaff) refresh()
  }, { immediate: true })
}

const transitCounts = computed(() => {
  const agencies = new Set<string>()
  let routes = 0
  let stops = 0
  for (const f of feeds.value) {
    for (const a of f.agencies || []) agencies.add(a)
    routes += f.routes_count || 0
    stops += f.stops_count || 0
  }
  return {
    feeds: feeds.value.length,
    agencies: agencies.size,
    routes: routes.toLocaleString(locale.value),
    stops: stops.toLocaleString(locale.value),
  }
})

const groups = computed(() => [
  {
    id: 'map',
    title: t('sources.groups.map'),
    icon: Map,
    items: [
      {
        name: 'OpenStreetMap',
        url: 'https://www.openstreetmap.org/',
        use: t('sources.items.osm'),
        license: 'ODbL 1.0',
        licenseUrl: 'https://www.openstreetmap.org/copyright',
      },
      {
        name: 'GeoNames',
        url: 'https://www.geonames.org/',
        use: t('sources.items.geocoder_support'),
        license: '',
        licenseUrl: 'https://www.geonames.org/about.html',
      },
      {
        name: 'OpenAddresses',
        url: 'https://openaddresses.io/',
        use: t('sources.items.geocoder_support'),
        license: '',
        licenseUrl: 'https://openaddresses.io/',
      },
      {
        name: "Who's on First",
        url: 'https://whosonfirst.org/',
        use: t('sources.items.geocoder_support'),
        license: '',
        licenseUrl: 'https://whosonfirst.org/docs/licenses/',
      },
    ],
  },
  {
    id: 'weather',
    title: t('sources.groups.weather'),
    icon: Cloud,
    items: [
      {
        name: 'Open-Meteo',
        url: 'https://open-meteo.com/',
        use: t('sources.items.open_meteo'),
        license: 'CC BY 4.0',
        licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
      },
    ],
  },
  {
    id: 'pt',
    title: t('sources.groups.pt'),
    icon: Landmark,
    items: [
      {
        name: 'DGT — Ortofotos',
        url: 'https://www.dgterritorio.gov.pt/',
        use: t('sources.items.dgt_ortho'),
        license: 'CC BY 4.0',
        licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
      },
      {
        name: 'DGT — CAOP 2025',
        url: 'https://www.dgterritorio.gov.pt/cartografia/cartografia-tematica/caop',
        use: t('sources.items.dgt_caop'),
        license: '',
        licenseUrl: 'https://dados.gov.pt/pt/datasets/carta-administrativa-oficial-de-portugal-caop/',
      },
      {
        name: 'MuniSIG — Câmara Municipal de Caminha',
        url: 'https://sig.cm-caminha.pt/',
        use: t('sources.items.caminha_pdm'),
        license: '',
        licenseUrl: 'https://sig.cm-caminha.pt/',
      },
    ],
  },
])

useHead({ title: computed(() => t('sources.title') + ' - Parahub') })
useSeoMeta({
  description: computed(() => t('sources.meta')),
  ogTitle: computed(() => t('sources.title')),
  ogDescription: computed(() => t('sources.meta')),
  ogType: 'website',
})
</script>
