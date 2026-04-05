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
        'legal.json', 'map.json', 'market.json', 'mesh.json',
        'messages.json', 'opensky.json', 'personality.json', 'profile.json',
        'projects.json', 'rides.json', 'transit.json', 'treasury.json',
        'wallet.json', 'zenith.json', 'federation.json', 'dispatch.json', 'tickets.json',
        'transit_manage.json', 'shipments.json', 'income.json', 'vera.json',
        'voice_chat.json', 'support_voice.json', 'condo.json', 'ha.json', 'property.json', 'parasos.json',
        'cms.json', 'videos.json',
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
    exclude: (() => {
      const privatePaths = [
        '/login', '/register', '/welcome', '/choose-username',
        '/auth/**', '/invite/**',
        '/profile/**', '/settings/**',
        '/chat', '/chat-element', '/chat-fluffy',
        '/wallet', '/contracts',
        '/opensky', '/zenith', '/call', '/webmail',
        '/design',
        '/barter', '/iot',
        '/pgp-setup', '/pgp-test', '/seed-setup', '/seed-restore',
        '/ads/campaigns/**', '/ads/campaigns', '/ads/history', '/ads/settings',
        '/market/create', '/market/my-items',
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
        // Inter font from Google Fonts - as per DESIGN.md
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: 'anonymous' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' }
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
      global: 'globalThis'
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