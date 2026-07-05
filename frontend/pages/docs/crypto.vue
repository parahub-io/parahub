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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.cryptoProofs.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">

      <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ $t('about.cryptoProofs.intro') }}</p>

      <!-- Live anchoring status -->
      <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg p-5 space-y-4">
        <div class="flex items-center gap-2">
          <ShieldCheck class="w-4 h-4 text-neutral-500" />
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.live.title') }}</h3>
        </div>

        <div v-if="anchoringLoading" class="flex items-center gap-2 text-sm text-neutral-400 dark:text-neutral-500">
          <span class="w-4 h-4 rounded-full border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-700 dark:border-t-neutral-100 animate-spin"></span>
        </div>
        <template v-else-if="anchoring?.enabled">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{{ anchoring.keys_published }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.keys') }}</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{{ anchoring.proofs_anchored }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.anchored') }}</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{{ anchoring.batches_confirmed }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.confirmed') }}</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">{{ anchoring.proofs_pending }}</div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.pending') }}</div>
            </div>
          </div>

          <div v-if="anchoring.latest_batch" class="text-sm text-neutral-600 dark:text-neutral-400 flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 border-t border-neutral-100 dark:border-neutral-800">
            <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ $t('about.cryptoProofs.live.latest') }}:</span>
            <span v-if="anchoring.latest_batch.bitcoin_block" class="inline-flex items-center gap-1 text-neutral-700 dark:text-neutral-300">
              <Bitcoin class="w-3.5 h-3.5 text-yellow-500" />{{ $t('about.cryptoProofs.live.block', { block: anchoring.latest_batch.bitcoin_block }) }}
            </span>
            <span v-else class="inline-flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
              <Clock class="w-3.5 h-3.5" />{{ $t('about.cryptoProofs.live.awaiting') }}
            </span>
            <span class="text-neutral-300 dark:text-neutral-600">·</span>
            <code class="font-mono text-xs">{{ $t('about.cryptoProofs.live.commit', { hash: anchoring.latest_batch.git_commit_hash.slice(0, 10) }) }}</code>
          </div>
          <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.none') }}</p>
        </template>
        <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('about.cryptoProofs.live.disabled') }}</p>
      </div>

      <!-- PGP + OTS cards -->
      <div class="grid sm:grid-cols-2 gap-4">
        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg p-5 space-y-3">
          <div class="flex items-center gap-2">
            <KeyRound class="w-4 h-4 text-neutral-500" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.pgp.title') }}</h3>
          </div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.pgp.text') }}</p>
          <ul class="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
            <li v-for="p in ['point1','point2','point3']" :key="p" class="flex items-start gap-2">
              <span class="text-neutral-400 mt-0.5 flex-shrink-0">—</span>
              <span>{{ $t(`about.cryptoProofs.pgp.${p}`) }}</span>
            </li>
          </ul>
        </div>

        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg p-5 space-y-3">
          <div class="flex items-center gap-2">
            <Bitcoin class="w-4 h-4 text-neutral-500" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.ots.title') }}</h3>
          </div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.ots.text') }}</p>
          <ul class="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
            <li v-for="p in ['point1','point2','point3']" :key="p" class="flex items-start gap-2">
              <span class="text-neutral-400 mt-0.5 flex-shrink-0">—</span>
              <span>{{ $t(`about.cryptoProofs.ots.${p}`) }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Public audit repository -->
      <div class="p-5 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg space-y-3">
        <div class="flex items-center gap-2">
          <FolderGit2 class="w-4 h-4 text-neutral-500" />
          <h3 class="font-semibold text-neutral-900 dark:text-white">{{ $t('about.cryptoProofs.repo.title') }}</h3>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.repo.text') }}</p>
        <UiButton tag="a" :href="REPO_URL" target="_blank" rel="noopener" variant="secondary" size="sm" :icon="ExternalLink">
          {{ $t('about.cryptoProofs.repo.cta') }}
        </UiButton>
      </div>

      <!-- Export section -->
      <div class="p-5 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg space-y-3">
        <div class="flex items-center gap-2">
          <FileDown class="w-4 h-4 text-neutral-500" />
          <h3 class="font-semibold text-neutral-900 dark:text-white">{{ $t('about.cryptoProofs.export.title') }}</h3>
        </div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.export.text') }}</p>
        <div class="text-sm text-neutral-500 dark:text-neutral-500 font-medium">{{ $t('about.cryptoProofs.export.contains') }}</div>
        <ul class="space-y-1 text-sm text-neutral-600 dark:text-neutral-400 font-mono">
          <li v-for="i in ['item1','item2','item3','item4']" :key="i" class="flex items-start gap-2">
            <span class="text-yellow-500 flex-shrink-0">›</span>
            <span>{{ $t(`about.cryptoProofs.export.${i}`) }}</span>
          </li>
        </ul>
      </div>

      <!-- Verify section -->
      <div class="space-y-3">
        <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('about.cryptoProofs.verify.title') }}</h3>
        <div class="space-y-2">
          <div v-for="(step, i) in ['step1','step2','step3']" :key="step" class="flex gap-3 items-start">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 text-xs flex items-center justify-center font-mono mt-0.5">{{ i + 1 }}</span>
            <code class="text-sm text-neutral-700 dark:text-neutral-300 font-mono leading-relaxed">{{ $t(`about.cryptoProofs.verify.${step}`) }}</code>
          </div>
        </div>
      </div>

      <!-- Legal note -->
      <div class="p-4 border-l-4 border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-900 rounded-r-lg">
        <div class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">{{ $t('about.cryptoProofs.legal.title') }}</div>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t('about.cryptoProofs.legal.text') }}</p>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, KeyRound, Bitcoin, FileDown, ShieldCheck, Clock, FolderGit2, ExternalLink } from 'lucide-vue-next'

const REPO_URL = 'https://git.parahub.io/audit/parahub-registry'

const { t } = useI18n()
const localePath = useLocalePath()

// Live anchoring status — fetched client-side so it reflects the backend the
// request actually routes to (dev-slot cookie aware); fail-soft on error.
const anchoring = ref<any>(null)
const anchoringLoading = ref(true)
onMounted(async () => {
  try {
    anchoring.value = await $fetch('/api/v1/audit/anchoring')
  } catch {
    anchoring.value = null
  } finally {
    anchoringLoading.value = false
  }
})
useHead({ title: computed(() => `${t('about.cryptoProofs.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.crypto_desc')),
  ogTitle: computed(() => `${t('about.cryptoProofs.title')} — Parahub`),
  ogDescription: computed(() => t('docs.crypto_desc')),
})
useDocsBreadcrumb(t('about.cryptoProofs.title'), '/docs/crypto')

definePageMeta({ order: 2 })
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
</style>
