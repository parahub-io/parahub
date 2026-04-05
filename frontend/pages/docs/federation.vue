<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <div class="docs-header border-b border-primary/40 dark:border-primary/30 py-6 sm:py-8">
      <div class="max-w-3xl mx-auto px-4 sm:px-6">
        <nav class="flex items-center gap-1.5 text-sm">
          <NuxtLink :to="localePath('/about')" class="text-neutral-900/60 hover:text-neutral-900 transition-colors">
            {{ $t('about.title') }}
          </NuxtLink>
          <ChevronRight class="w-3.5 h-3.5 text-neutral-900/30" />
          <NuxtLink :to="localePath('/docs')" class="text-neutral-900/60 hover:text-neutral-900 transition-colors">
            {{ $t('docs.title') }}
          </NuxtLink>
          <ChevronRight class="w-3.5 h-3.5 text-neutral-900/30" />
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.federationSystem.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section space-y-8">

        <p class="text-base">{{ $t('about.federationSystem.intro') }}</p>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.federationSystem.why.title') }}</h3>
          <p>{{ $t('about.federationSystem.why.text') }}</p>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.federationSystem.git.title') }}</h3>
          <p class="mb-3">{{ $t('about.federationSystem.git.text') }}</p>
          <pre class="bg-neutral-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto font-mono leading-relaxed">parahub-registry/
├── node.json                  # Node manifest (PGP key, capabilities)
├── nodes/                     # Known peers
│   └── para.sh.json
├── organizations/             # Public organization records
│   └── 01K7M4MD.json
├── verifications/             # Cross-node WoT verifications
│   └── alice__bob.json
├── migrations/                # Profile migration records
│   └── 2026-03-08_norn.json
└── pgp-keyring/               # PGP public keys</pre>
        </div>

        <!-- Three layers -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('federation.node.title') }}</h3>
          <div class="grid sm:grid-cols-3 gap-3 text-sm">
            <div class="border border-secondary-200 dark:border-secondary-900 rounded-lg p-4 bg-secondary-50 dark:bg-secondary-900/30">
              <div class="font-mono font-semibold text-secondary-700 dark:text-secondary-300 mb-2">Git</div>
              <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">State layer. Signed JSON records, append-only, verifiable history.</p>
            </div>
            <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 bg-neutral-50 dark:bg-neutral-900">
              <div class="font-mono font-semibold text-neutral-700 dark:text-neutral-300 mb-2">WebSocket</div>
              <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">Signal layer. Real-time inter-node notifications.</p>
            </div>
            <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 bg-neutral-50 dark:bg-neutral-900">
              <div class="font-mono font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Matrix</div>
              <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">Communication layer. E2E encrypted messaging between nodes.</p>
            </div>
          </div>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.federationSystem.migration.title') }}</h3>
          <p>{{ $t('about.federationSystem.migration.text') }}</p>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.federationSystem.search.title') }}</h3>
          <p>{{ $t('about.federationSystem.search.text') }}</p>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.federationSystem.wot.title') }}</h3>
          <p>{{ $t('about.federationSystem.wot.text') }}</p>
        </div>

      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.federationSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.federation_desc')),
  ogTitle: computed(() => `${t('about.federationSystem.title')} — Parahub`),
  ogDescription: computed(() => t('docs.federation_desc')),
})
useDocsBreadcrumb(t('about.federationSystem.title'), '/docs/federation')

definePageMeta({ order: 2 })
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
