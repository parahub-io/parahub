// https://nuxt.com/docs/api/configuration/nuxt-config
import { execSync } from 'child_process'

function getGitVersion(): string {
  try {
    return execSync('git describe --tags --always', { encoding: 'utf-8' }).trim()
  } catch {
    return 'unknown'
  }
}

export default defineNuxtConfig({
  devtools: { enabled: true },
  buildDir: process.env.NUXT_BUILD_DIR || '.nuxt',
  
  // Hybrid architecture: SSR for public pages, SPA for interactive sections
  ssr: true,
  
  // Modules
  modules: [
    '@pinia/nuxt',
    '@nuxtjs/tailwindcss',
    '@nuxtjs/color-mode',
    '@nuxtjs/i18n',
    '@nuxtjs/sitemap',
    // Chunk ONLY the default-locale sitemap. Our app sources emit canonical
    // (default-locale) URLs — server/api/__sitemap__/urls.ts no longer sets
    // _i18nTransform — so @nuxtjs/sitemap's i18n auto-map files every dynamic app
    // URL (≈87k transit stops + ≈3k routes + CMS) into the default locale's
    // sitemap (en-US); the other locale sitemaps hold only their static localized
    // pages. en-US therefore blows past Google's 50k-URL / 50MB per-file limit and
    // must split into `<key>-<n>.xml` files referenced from sitemap_index.xml.
    //
    // It MUST be only this one sitemap. The module derives a sitemap's chunkCount
    // from the UNFILTERED resolved URL set (sitemap-index.js:133) while serving
    // FILTERS entries by `_sitemap` (sitemap.js:239). Those two agree only for the
    // sitemap the flat URLs actually belong to — the default locale. Chunking any
    // other locale would count ≈90k yet serve only its handful of static pages,
    // producing phantom chunks that 404. runtimeConfig is frozen at runtime, so
    // stamp `chunks` at build (modules:done, after the sitemap module populated
    // runtimeConfig.sitemap with `.sitemaps` + `.autoI18n`).
    (_inlineOptions: unknown, nuxt: any) => {
      nuxt.hook('modules:done', () => {
        const sm = nuxt.options.runtimeConfig?.sitemap
        const sitemaps = sm?.sitemaps
        const autoI18n = sm?.autoI18n
        if (!sitemaps) return
        // Sitemap keys are locale.language ('en-US'); the default-locale one holds
        // all the flat app URLs. Derive it; fall back to the known key if needed.
        const defaultKey = autoI18n?.locales?.find(
          (l: any) => l.code === autoI18n.defaultLocale,
        )?._sitemap || 'en-US'
        const cfg = sitemaps[defaultKey]
        if (cfg && typeof cfg === 'object') cfg.chunks = 45000
        else console.warn(`[sitemap] default-locale sitemap "${defaultKey}" not found; large sitemap left un-chunked (will exceed 50k limit)`)
      })
    },
  ],

  i18n: {
    baseUrl: 'https://parahub.io',
    defaultLocale: 'en',
    strategy: 'prefix_except_default',
    locales: (() => {
      const files = [
        'ads.json', 'barter.json', 'call.json', 'code-of-conduct.json',
        'common.json', 'contracts.json', 'debts.json', 'directory.json',
        'energy.json', 'events.json', 'governance.json', 'help.json',
        'home.json', 'invite.json', 'iot.json', 'landing.json',
        // legal.json is deliberately NOT listed — it is merged on demand by
        // middleware/legal-messages.global.ts on /docs, /about and /manifest
        'map.json', 'market.json', 'mesh.json',
        'messages.json', 'opensky.json', 'personality.json', 'profile.json',
        'projects.json', 'rides.json', 'transit.json', 'treasury.json',
        'wallet.json', 'zenith.json', 'federation.json', 'dispatch.json', 'tickets.json',
        'transit_manage.json', 'shipments.json', 'income.json', 'subscriptions.json', 'vera.json',
        'voice_chat.json', 'support_voice.json', 'condo.json', 'ha.json', 'property.json', 'parasos.json',
        'cms.json', 'videos.json', 'booking.json', 'notifications.json',
        'wot.json', 'civic.json',
      ]
      return [
        { code: 'en', language: 'en-US', name: 'English', files: files.map(f => `en/${f}`) },
        { code: 'pt', language: 'pt-PT', name: 'Português', files: files.map(f => `pt/${f}`) },
        { code: 'es', language: 'es-ES', name: 'Español', files: files.map(f => `es/${f}`) },
        { code: 'fr', language: 'fr-FR', name: 'Français', files: files.map(f => `fr/${f}`) },
        { code: 'de', language: 'de-DE', name: 'Deutsch', files: files.map(f => `de/${f}`) },
        { code: 'ru', language: 'ru-RU', name: 'Русский', files: files.map(f => `ru/${f}`) },
      ]
    })(),
    langDir: '../locales',
    lazy: true,
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'preferred_language',
      redirectOn: 'root',
      alwaysRedirect: false,
    },
    compilation: {
      strictMessage: false,
      escapeHtml: false,
    },
  },

  site: {
    url: 'https://parahub.io',
  },

  sitemap: {
    // The auto app-source endpoint (server/api/__sitemap__/urls.ts) is NOT picked
    // up under @nuxtjs/i18n multi-sitemaps, so register it explicitly — without
    // this, every dynamic URL it returns (transit routes, CMS posts/pages) is
    // silently absent from the sitemap. Its entries carry _i18nTransform so the
    // module expands each into all locales with hreflang (see the handler).
    sources: ['/api/__sitemap__/urls'],
    exclude: (() => {
      const privatePaths = [
        '/login', '/register', '/welcome', '/choose-username',
        '/auth/**', '/invite/**',
        '/profile/**', '/settings/**',
        '/chat', '/chat-element', '/chat-fluffy',
        '/wallet', '/contracts',
        '/opensky', '/zenith', '/call', '/webmail',
        '/design', '/design/**',
        '/barter', '/iot',
        '/pgp-setup', '/pgp-test', '/seed-setup', '/seed-restore',
        '/ads/campaigns/**', '/ads/campaigns', '/ads/history', '/ads/settings',
        '/market/create', '/market/my',
        '/events/create',
        '/governance/polls/create',
        '/tickets/**',
        '/voice/**',
        '/blog/create',
        '/org/*/manage/**', '/org/*/edit',
        '/u/*/manage/**',
      ]
      const locales = ['pt', 'es', 'fr', 'de', 'ru']
      const withLocales = privatePaths.flatMap(p =>
        [p, ...locales.map(l => `/${l}${p}`)]
      )
      return withLocales
    })(),
  },

  // Color mode configuration
  colorMode: {
    classSuffix: '',
    preference: 'system', // default value
    fallback: 'light', // fallback value if not system preference found
    storageKey: 'nuxt-color-mode'
  },
  
  // CSS configuration
  css: [
    '~/assets/css/fonts.css',
    '~/assets/css/main.css'
  ],
  
  // App configuration - keep defaults neutral, localized in app.vue
  app: {
    head: {
      titleTemplate: '%s',
      title: 'Parahub',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'description', content: 'Open-source civic platform for P2P trade, Lightning payments, encrypted messaging, community governance, and transit maps.' }
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
        { rel: 'manifest', href: '/site.webmanifest' },
        // Inter is self-hosted (assets/css/fonts.css + public/webfonts/inter/;
        // /fonts/* is taken — nginx serves MapLibre glyph PBFs there).
        // Preload only the latin subset: every locale's ASCII text uses it;
        // other subsets arrive on demand via unicode-range.
        { rel: 'preload', as: 'font', type: 'font/woff2', href: '/webfonts/inter/inter-latin.woff2', crossorigin: 'anonymous' }
      ]
    }
  },
  
  // Runtime configuration
  runtimeConfig: {
    public: {
      apiBase: '/api/v1',
      traccarUrl: 'https://traccar.parahub.io',
      traccarPublicHost: process.env.TRACCAR_PUBLIC_HOST || '',
      wsUrl: process.env.NODE_ENV === 'development' ? 'ws://localhost:8000' : 'wss://parahub.io',
      breezApiKey: process.env.NUXT_PUBLIC_BREEZ_API_KEY || '',
      // Version info (build-time)
      appVersion: getGitVersion(),
      buildDate: new Date().toISOString()
    }
  },
  
  // Build configuration
  build: {
    transpile: ['openpgp', '@breeztech/breez-sdk-spark']
  },

  // Vite configuration for Node.js polyfills (bip39) and WASM (breez-sdk-spark)
  vite: {
    define: {
      'process.env': {},
      global: 'globalThis',
      // Dev-slot builds only (0restart-dev sets NUXT_OUTPUT_DIR=.output-devN):
      // make Vue print WHICH node mismatched instead of the bare "Hydration
      // completed but contains mismatches" — costs a little bundle size, so
      // production builds keep the default (false).
      __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: JSON.stringify(
        (process.env.NUXT_OUTPUT_DIR || '').includes('dev')
      )
    },
    resolve: {
      alias: {
        buffer: 'buffer/'
      }
    },
    optimizeDeps: {
      include: ['buffer'],
      exclude: ['@breeztech/breez-sdk-spark']
    }
  },
  
  // SWR cache for public read-mostly pages: the rendered HTML is served from
  // the Nitro cache and revalidated in the background, so the ~90k transit
  // URLs and blog/about pages stop paying a full Vue SSR per hit.
  // - varies: ['host'] because mini-sites (org/u subdomains, custom domains)
  //   render DIFFERENT content on the same paths (site.global.ts middleware).
  // - /blog/[slug] is deliberately NOT cached: its SSR forwards cookies
  //   (staff demo posts, subscribers_only gating) — a cached render would
  //   serve one viewer's variant to everyone.
  // - Cached pages still self-correct fast: e.g. the stop page re-fetches its
  //   schedule in onMounted, so a stale-cached shell updates on hydration.
  routeRules: (() => {
    // en has no prefix (strategy: prefix_except_default), others are prefixed
    const localePrefixes = ['', '/pt', '/es', '/fr', '/de', '/ru']
    const swrByHost = (maxAge: number) => ({
      cache: { swr: true, maxAge, varies: ['host'] }
    })
    const rules: Record<string, any> = {}
    for (const p of localePrefixes) {
      rules[`${p}/transit/stop/**`] = swrByHost(3600)
      rules[`${p}/transit/route/**`] = swrByHost(3600)
      rules[`${p}/blog`] = swrByHost(600)
      rules[`${p}/about`] = swrByHost(3600)
      rules[`${p}/about/**`] = swrByHost(3600)
    }
    return rules
  })(),

  hooks: {
    // deck.gl/loaders.gl load via dynamic import on the 3D toggle
    // (useMap3DTiles) — without this, Nuxt still emits <link rel="prefetch">
    // for their ~1.1MB of chunks to every map visitor. Keep them strictly
    // on-demand.
    //
    // Name-matching alone is not enough: vue-bundle-renderer expands a
    // dynamic import's static-import closure when emitting hints, and rollup
    // splits deck.gl internals into anonymous shared chunks (manifest keys
    // like `_Cs9bfT2v.js`) whose per-file flags stay true — so ~190K of
    // loaders.gl still got preloaded on /map. Sweep the whole closure: a
    // chunk is swept only when ALL its static importers are swept, so shared
    // chunks the map page (or any other static graph) genuinely imports keep
    // their hints.
    'build:manifest'(manifest) {
      const seed = /deck\.gl|loaders\.gl|useMap3DTiles/
      const swept = new Set(Object.keys(manifest).filter(k => seed.test(k)))
      const importers = new Map<string, string[]>()
      for (const [key, entry] of Object.entries(manifest)) {
        for (const dep of entry.imports || []) {
          if (!importers.has(dep)) importers.set(dep, [])
          importers.get(dep)!.push(key)
        }
      }
      let grew = true
      while (grew) {
        grew = false
        for (const [dep, froms] of importers) {
          if (swept.has(dep) || !manifest[dep]) continue
          if (froms.every(k => swept.has(k))) {
            swept.add(dep)
            grew = true
          }
        }
      }
      for (const key of swept) {
        manifest[key].prefetch = false
        manifest[key].preload = false
      }
    },
  },

  // Server-side rendering routes (public pages)
  nitro: {
    // Allow custom output directory via env (for parallel dev/prod builds)
    output: {
      dir: process.env.NUXT_OUTPUT_DIR || '.output'
    },
    prerender: {
      routes: []
    }
  },
  
  // Development server
  devServer: {
    port: 3000,
    host: '0.0.0.0'
  }
})