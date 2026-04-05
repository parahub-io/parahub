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
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('about.features.title') }}</h1>
        </nav>
      </div>
    </div>

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-6">
      <div v-for="group in groups" :key="group.labelKey">
        <div class="text-xs font-semibold text-neutral-400 dark:text-neutral-500 uppercase tracking-wider px-2 mb-1">
          {{ $t(group.labelKey) }}
        </div>
        <div class="space-y-0.5">
          <component
            :is="f.to ? NuxtLink : f.href ? 'a' : 'div'"
            v-for="f in group.items"
            :key="f.key"
            :to="f.to"
            :href="!f.to ? f.href : undefined"
            :target="(!f.to && f.href) ? '_blank' : undefined"
            :rel="(!f.to && f.href) ? 'noopener' : undefined"
            class="flex items-center gap-3 px-2 py-2 rounded-lg"
            :class="(f.to || f.href) ? 'hover:bg-neutral-50 dark:hover:bg-neutral-900 group cursor-pointer' : ''"
          >
            <component :is="f.icon" class="w-4 h-4 flex-shrink-0" :class="(f.to || f.href) ? 'text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300' : 'text-neutral-300 dark:text-neutral-600'" />
            <div class="flex-1 text-neutral-700 dark:text-neutral-300 leading-relaxed text-sm">
              <span class="font-medium text-neutral-900 dark:text-neutral-100" :class="(f.to || f.href) ? 'group-hover:text-secondary dark:group-hover:text-secondary-400' : ''">{{ $t(`about.features.${f.key}.title`) }}</span>
              <span v-if="f.wip" class="ml-1.5 text-xs px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded">{{ $t('docs.wip') }}</span>
              <span class="text-neutral-400 dark:text-neutral-500"> &mdash; </span>
              <span class="text-neutral-600 dark:text-neutral-400">{{ $t(`about.features.${f.key}.desc`) }}</span>
            </div>
            <button v-if="f.href && f.to" class="p-1 -m-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors flex-shrink-0" :title="f.href.replace('https://', '')" @click.stop.prevent="window.open(f.href, '_blank')">
              <ExternalLink class="w-3.5 h-3.5 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400" />
            </button>
            <ExternalLink v-else-if="f.href" class="w-3.5 h-3.5 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
            <ChevronRight v-else-if="f.to" class="w-3.5 h-3.5 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
          </component>
        </div>
      </div>
      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { resolveComponent } from 'vue'
import {
  Store, ArrowLeftRight, ShieldCheck, Users, Zap, MapPin, Wifi, Scale,
  Vote, Megaphone, CalendarDays, Receipt, Building2, FileSignature,
  Bot, Camera, Radio, Brain, Video, Globe, ChevronRight, ExternalLink, Bus, Car,
  Wallet, PiggyBank, Heart, LayoutDashboard, Ticket, Package, Navigation,
  Home, Landmark, Server, Bell,
} from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.features.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.features_desc')),
  ogTitle: computed(() => `${t('about.features.title')} — Parahub`),
  ogDescription: computed(() => t('docs.features_desc')),
})
useDocsBreadcrumb(t('about.features.title'), '/docs/features')

const NuxtLink = resolveComponent('NuxtLink')

const groups = [
  {
    labelKey: 'docs.group_trade',
    items: [
      { key: 'marketplace', icon: Store },
      { key: 'barter', icon: ArrowLeftRight, to: '/docs/barter', href: 'https://troca.parahub.io' },
      { key: 'payments', icon: Zap },
      { key: 'wallet', icon: Wallet },
      { key: 'debts', icon: Receipt },
      { key: 'contracts', icon: FileSignature, href: 'https://contratos.parahub.io' },
      { key: 'treasury', icon: PiggyBank, to: '/docs/transparency', wip: true },
      { key: 'income', icon: Heart, to: '/docs/transparency' },
    ],
  },
  {
    labelKey: 'docs.group_trust',
    items: [
      { key: 'reputation', icon: Users, to: '/docs/wot' },
      { key: 'crypto', icon: ShieldCheck, to: '/docs/crypto' },
      { key: 'arbitration', icon: Scale, to: '/docs/arbitration', wip: true },
    ],
  },
  {
    labelKey: 'docs.group_community',
    items: [
      { key: 'events', icon: CalendarDays, href: 'https://eventos.parahub.io' },
      { key: 'ads', icon: Megaphone, to: '/docs/ads' },
      { key: 'governance', icon: Vote, to: '/docs/governance', href: 'https://democracia.parahub.io' },
      { key: 'condo', icon: Landmark, to: '/docs/condo', href: 'https://condominios.parahub.io', wip: true },
      { key: 'sos', icon: Bell, href: 'https://sos.parahub.io' },
    ],
  },
  {
    labelKey: 'docs.group_infrastructure',
    items: [
      { key: 'maps', icon: MapPin },
      { key: 'property', icon: Home },
      { key: 'directory', icon: Building2, href: 'https://directorio.parahub.io' },
      { key: 'transit', icon: Bus, href: 'https://transporte.parahub.io' },
      { key: 'logistics', icon: Package, wip: true },
      { key: 'driver', icon: Navigation },
      { key: 'carpool', icon: Car, href: 'https://boleias.parahub.io', wip: true },
      { key: 'tickets', icon: Ticket, wip: true },
      { key: 'dispatch', icon: LayoutDashboard },
      { key: 'mesh', icon: Wifi, to: '/docs/mesh' },
      { key: 'energy', icon: Zap, to: '/docs/energy', href: 'https://energia.parahub.io', wip: true },
      { key: 'federation', icon: Globe, to: '/docs/federation' },
    ],
  },
  {
    labelKey: 'docs.group_advanced',
    items: [
      { key: 'presence', icon: Radio },
      { key: 'zenith', icon: Bot },
      { key: 'ha', icon: Server, wip: true },
      { key: 'opensky', icon: Camera },
      { key: 'psycho', icon: Brain },
      { key: 'jitsi', icon: Video },
    ],
  },
]

definePageMeta({ order: 2 })
</script>

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
</style>
