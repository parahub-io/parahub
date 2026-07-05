<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <!-- Top progress bar: instant feedback on navigation while the next page's
         data resolves (pairs with useListData's Suspense-blocking fetch). -->
    <NuxtLoadingIndicator color="#4E4EC8" :height="3" />
    <NuxtLayout>
      <!-- This prop OVERRIDES definePageMeta keepalive (Nuxt: props.keepalive ?? route.meta.keepalive),
           so ALL pages are KeepAlive-cached (LRU max 10). Per-page keepalive:true/false in definePageMeta
           is a no-op. Stateful pages (forms, listeners, map markers) must clean up / re-sync in
           onActivated/onDeactivated — onMounted/onUnmounted do not fire on cached navigation. -->
      <NuxtPage :keepalive="{ max: 10 }" />
    </NuxtLayout>

    <!-- Global Toast Notifications -->
    <ClientOnly>
      <Toast />
    </ClientOnly>

    <!-- Version update banner (driven by WebSocket feed:system) -->
    <ClientOnly>
      <UpdateBanner />
    </ClientOnly>

    <!-- Incoming Call Banner -->
    <ClientOnly>
      <IncomingCallBanner />
    </ClientOnly>
  </div>
</template>

<script setup>
// Global app setup
import { useColorMode } from '#imports'

// Set up color mode
const colorMode = useColorMode()

const { locale } = useI18n()
const route = useRoute()
const head = useLocaleHead({ addSeoAttributes: true })

useHead({
  htmlAttrs: computed(() => ({
    lang: head.value.htmlAttrs?.lang || locale.value,
    dir: head.value.htmlAttrs?.dir,
  })),
  link: computed(() => [
    ...(head.value.link || []),
  ]),
  meta: computed(() => [
    ...(head.value.meta || []),
  ]),
  script: [
    {
      src: '/plausible/js/script.file-downloads.outbound-links.js',
      defer: true,
      'data-domain': 'parahub.io',
      'data-api': '/plausible/api/event',
    },
    {
      type: 'application/ld+json',
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@graph': [
          {
            '@type': ['Organization', 'NGO'],
            '@id': 'https://parahub.io/#organization',
            name: 'Parahub',
            url: 'https://parahub.io',
            logo: 'https://parahub.io/logo.svg',
            description: 'Open-source civic platform for P2P trade, Lightning payments, encrypted messaging, community governance, and transit maps.',
            foundingDate: '2026',
            areaServed: 'Worldwide',
            sameAs: ['https://github.com/parahub-io'],
          },
          {
            '@type': 'WebSite',
            '@id': 'https://parahub.io/#website',
            name: 'Parahub',
            url: 'https://parahub.io',
            publisher: { '@id': 'https://parahub.io/#organization' },
            potentialAction: {
              '@type': 'SearchAction',
              target: 'https://parahub.io/market?q={search_term_string}',
              'query-input': 'required name=search_term_string',
            },
          },
        ],
      }),
    },
  ],
})

useSeoMeta({
  title: 'Parahub — open-source civic platform without middlemen',
  ogTitle: 'Parahub — open-source civic platform without middlemen',
  description: 'Open-source civic platform for P2P trade, Lightning payments, encrypted messaging, governance, and transit maps. Zero commissions. Join free.',
  ogDescription: 'Open-source civic platform for P2P trade, Lightning payments, encrypted messaging, governance, and transit maps. Zero commissions. Join free.',
  ogImage: 'https://parahub.io/og-image.jpg',
  ogSiteName: 'Parahub',
  twitterCard: 'summary_large_image',
  // No twitterTitle/twitterDescription here: they would pin every sub-page's X
  // card to the generic site copy (X does NOT fall back to og: when present).
  // Omitting them lets each page's ogTitle/ogDescription drive the X card; the
  // homepage still gets correct copy via its own ogTitle/ogDescription above.
  twitterImage: 'https://parahub.io/og-image.jpg',
  ogType: 'website',
  ogUrl: computed(() => `https://parahub.io${route.path}`),
})

// Global error handling
onErrorCaptured((error) => {
  console.error('Global error:', error)
  // Here you could send error to logging service
})
</script>

<style>
/* Global styles are imported via nuxt.config.ts */

/* Prevent horizontal scroll globally */
html, body {
  overflow-x: hidden;
  max-width: 100vw;
}
</style>