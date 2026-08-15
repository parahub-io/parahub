<script setup lang="ts">
import {
  ArrowLeft, Clock, ExternalLink, HandCoins, IdCard, Landmark,
  Percent, ShoppingBag, Users, Zap,
} from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  key: 'wallet-exchange',
})

const { t, tm, rt } = useI18n()
const localePath = useLocalePath()

useSeoMeta({
  title: t('wallet.exchangePage.title') + ' - Parahub',
  ogTitle: t('wallet.exchangePage.title') + ' - Parahub',
})

const direction = useTabSync(['sell', 'buy'])

const tabs = computed(() => [
  { id: 'sell', label: t('wallet.exchangePage.tabSell') },
  { id: 'buy', label: t('wallet.exchangePage.tabBuy') },
])

// One card per route. Steps come from the locale as arrays (`$tm`), one array per
// direction — the meta (cost/time/id) is direction-independent.
const ROUTES = [
  { key: 'kraken', icon: Landmark, links: [{ label: 'kraken.com', url: 'https://www.kraken.com' }] },
  { key: 'bringin', icon: Zap, links: [{ label: 'bringin.app', url: 'https://bringin.app' }] },
  { key: 'p2p', icon: Users, links: [
    { label: 'robosats.org', url: 'https://robosats.org' },
    { label: 'mostro.network', url: 'https://mostro.network' },
  ] },
  { key: 'cash', icon: HandCoins, links: [{ label: 'vexl.it', url: 'https://vexl.it' }] },
]

const routes = computed(() => ROUTES.map(r => ({
  ...r,
  name: t(`wallet.exchangePage.routes.${r.key}.name`),
  what: t(`wallet.exchangePage.routes.${r.key}.what`),
  cost: t(`wallet.exchangePage.routes.${r.key}.cost`),
  time: t(`wallet.exchangePage.routes.${r.key}.time`),
  id: t(`wallet.exchangePage.routes.${r.key}.id`),
  note: t(`wallet.exchangePage.routes.${r.key}.note`),
  steps: (tm(`wallet.exchangePage.routes.${r.key}.${direction.value}`) as unknown[]).map(s => rt(s as string)),
})))

const spendItems = computed(() => (tm('wallet.exchangePage.spend') as unknown[]).map(s => rt(s as string)))
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink
      :to="localePath('/wallet')"
      class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 mb-4"
    >
      <ArrowLeft class="w-4 h-4" /> {{ $t('wallet.title') }}
    </NuxtLink>

    <h1 class="text-2xl sm:text-3xl font-bold mb-2 text-neutral-900 dark:text-neutral-100">
      {{ $t('wallet.exchangePage.title') }}
    </h1>
    <p class="text-neutral-600 dark:text-neutral-400 mb-6">{{ $t('wallet.exchangePage.lead') }}</p>

    <UiTabs v-model="direction" :tabs="tabs" full-width class="mb-5" />

    <div class="space-y-4">
      <div v-for="route in routes" :key="route.key" class="card p-4">
        <div class="flex items-start gap-3">
          <div class="w-10 h-10 rounded-full bg-secondary-100 dark:bg-secondary-900 flex items-center justify-center shrink-0">
            <component :is="route.icon" class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
          </div>
          <div class="min-w-0 flex-1">
            <h2 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ route.name }}</h2>
            <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ route.what }}</p>
          </div>
        </div>

        <div class="flex flex-wrap gap-1.5 mt-3">
          <UiBadge variant="neutral" size="sm" class="gap-1">
            <Percent class="w-3 h-3" aria-hidden="true" />{{ route.cost }}
          </UiBadge>
          <UiBadge variant="neutral" size="sm" class="gap-1">
            <Clock class="w-3 h-3" aria-hidden="true" />{{ route.time }}
          </UiBadge>
          <UiBadge variant="neutral" size="sm" class="gap-1">
            <IdCard class="w-3 h-3" aria-hidden="true" />{{ route.id }}
          </UiBadge>
        </div>

        <ol class="mt-3 space-y-2 list-decimal pl-5 text-sm text-neutral-800 dark:text-neutral-200 marker:text-neutral-400 marker:font-medium">
          <li v-for="(step, idx) in route.steps" :key="route.key + '-' + idx" class="leading-relaxed">{{ step }}</li>
        </ol>

        <p class="mt-3 text-xs text-neutral-500 dark:text-neutral-400">{{ route.note }}</p>

        <div class="flex flex-wrap gap-x-4 gap-y-1 mt-3">
          <a
            v-for="link in route.links"
            :key="link.url"
            :href="link.url"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1 text-sm text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300"
          >
            {{ link.label }}<ExternalLink class="w-3.5 h-3.5" aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>

    <!-- Not converting at all -->
    <div class="card p-4 mt-4">
      <div class="flex items-start gap-3">
        <div class="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center shrink-0">
          <ShoppingBag class="w-5 h-5 text-neutral-700 dark:text-primary-200" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <h2 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('wallet.exchangePage.spendTitle') }}</h2>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('wallet.exchangePage.spendLead') }}</p>
        </div>
      </div>
      <ul class="mt-3 space-y-2 list-disc pl-5 text-sm text-neutral-800 dark:text-neutral-200 marker:text-neutral-400">
        <li v-for="(item, idx) in spendItems" :key="'spend-' + idx" class="leading-relaxed">{{ item }}</li>
      </ul>
      <a
        href="https://www.bitrefill.com/pt/en/"
        target="_blank"
        rel="noopener"
        class="inline-flex items-center gap-1 mt-3 text-sm text-secondary dark:text-secondary-400 hover:text-secondary-700 dark:hover:text-secondary-300"
      >
        bitrefill.com<ExternalLink class="w-3.5 h-3.5" aria-hidden="true" />
      </a>
    </div>

    <p class="mt-6 text-xs text-neutral-400 dark:text-neutral-500">{{ $t('wallet.exchangePage.disclaimer') }}</p>
  </div>
</template>
