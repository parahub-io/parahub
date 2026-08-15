<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader root :title="$t('docs.title')" :subtitle="$t('docs.intro')" />

    <!-- Group jump chips -->
    <div class="max-w-3xl mx-auto px-4 sm:px-6 pt-4 sm:pt-6">
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="g in groups"
          :key="g.id"
          type="button"
          class="px-2.5 py-1 text-xs rounded-full border border-neutral-200 dark:border-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          @click="scrollToGroup(g.id)"
        >
          {{ $t(g.labelKey) }}
        </button>
      </div>
    </div>

    <!-- Grouped section lists -->
    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-4 sm:py-6 space-y-6">
      <section v-for="g in groups" :id="`group-${g.id}`" :key="g.id" class="scroll-mt-4">
        <div class="text-xs font-semibold text-neutral-400 dark:text-neutral-500 uppercase tracking-wider px-2 mb-1">
          {{ $t(g.labelKey) }}
        </div>
        <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-800">
          <NuxtLink
            v-for="s in g.items"
            :key="s.to"
            :ref="(el: any) => { if (el?.$el) itemRefs[s.idx] = el.$el }"
            :to="localePath(s.to)"
            class="flex items-center gap-4 p-4 sm:p-5 transition-colors group"
            :class="focusIdx === s.idx ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-primary-100 dark:hover:bg-primary-900/40'"
          >
            <component :is="s.icon" class="w-5 h-5 text-neutral-400 group-hover:text-neutral-700 dark:group-hover:text-neutral-200 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
                {{ $t(s.titleKey) }}
                <span v-if="s.wip" class="text-xs font-normal px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded">{{ $t('docs.wip') }}</span>
              </div>
              <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                {{ $t(s.descKey) }}
              </div>
            </div>
            <ChevronRight class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
          </NuxtLink>
        </div>
      </section>
    </div>

  </div>
</template>

<script setup lang="ts">
import {
  Compass, LayoutGrid, ArrowLeftRight, Scale, Cpu, ScrollText, ChevronRight,
  ShieldCheck, Shield, Zap, Wifi, Vote, Rocket, KeyRound, Megaphone, HandCoins, Globe, Landmark,
  Package, Ticket, Bus, Navigation, Car, Store, CalendarCheck, HeartHandshake, Building2,
  Wallet, MessageCircle, Newspaper, Plug, Home, Printer, Wind,
  Map, BusFront, FileSignature, CalendarDays, Plane,
} from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
const router = useRouter()
useHead({ title: computed(() => `${t('docs.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('docs.intro')),
  ogTitle: computed(() => `${t('docs.title')} — Parahub`),
  ogDescription: computed(() => t('docs.intro')),
})

const focusIdx = ref(-1)
const itemRefs: Record<number, HTMLElement> = {}

const rawGroups = [
  {
    id: 'start',
    labelKey: 'docs.group_start',
    items: [
      { to: '/docs/getting-started', icon: Rocket, titleKey: 'about.gettingStarted.title', descKey: 'docs.getting_started_desc' },
      { to: '/docs/mission', icon: Compass, titleKey: 'about.toc.mission', descKey: 'docs.mission_desc' },
      { to: '/docs/features', icon: LayoutGrid, titleKey: 'about.features.title', descKey: 'docs.features_desc' },
    ],
  },
  {
    id: 'trust',
    labelKey: 'docs.group_trust',
    items: [
      { to: '/docs/wot', icon: ShieldCheck, titleKey: 'about.wotSystem.title', descKey: 'docs.wot_desc' },
      { to: '/docs/crypto', icon: KeyRound, titleKey: 'about.cryptoProofs.title', descKey: 'docs.crypto_desc' },
      { to: '/docs/contracts', icon: FileSignature, titleKey: 'about.contractsSystem.title', descKey: 'docs.contracts_desc' },
      { to: '/docs/arbitration', icon: Scale, titleKey: 'about.arbitration.title', descKey: 'docs.arbitration_desc' },
      { to: '/docs/conduct', icon: ScrollText, titleKey: 'footer.code_of_conduct', descKey: 'docs.conduct_desc' },
      { to: '/docs/sos', icon: Shield, titleKey: 'parasos.title', descKey: 'docs.parasos_desc' },
    ],
  },
  {
    id: 'trade',
    labelKey: 'docs.group_trade',
    items: [
      { to: '/docs/marketplace', icon: Store, titleKey: 'about.marketplaceSystem.title', descKey: 'docs.marketplace_desc' },
      { to: '/docs/barter', icon: ArrowLeftRight, titleKey: 'about.barterSystem.title', descKey: 'docs.barter_desc' },
      { to: '/docs/rental', icon: CalendarCheck, titleKey: 'about.rentalSystem.title', descKey: 'docs.rental_desc' },
      { to: '/docs/wallet', icon: Wallet, titleKey: 'about.walletSystem.title', descKey: 'docs.wallet_desc' },
      { to: '/docs/tips', icon: Printer, titleKey: 'about.tipsSystem.title', descKey: 'docs.tips_desc' },
      { to: '/docs/tickets', icon: Ticket, titleKey: 'about.ticketsSystem.title', descKey: 'docs.tickets_desc' },
      { to: '/docs/subscriptions', icon: HeartHandshake, titleKey: 'about.subscriptionsSystem.title', descKey: 'docs.subscriptions_desc' },
      { to: '/docs/ads', icon: Megaphone, titleKey: 'about.adsSystem.title', descKey: 'docs.ads_desc' },
      { to: '/docs/phub', icon: Package, titleKey: 'about.phubSystem.title', descKey: 'docs.phub_desc' },
    ],
  },
  {
    id: 'community',
    labelKey: 'docs.group_community',
    items: [
      { to: '/docs/governance', icon: Vote, titleKey: 'about.governanceSystem.title', descKey: 'docs.governance_desc' },
      { to: '/docs/transparency', icon: HandCoins, titleKey: 'about.transparency.title', descKey: 'docs.transparency_desc' },
      { to: '/docs/communication', icon: MessageCircle, titleKey: 'about.communicationSystem.title', descKey: 'docs.communication_desc' },
      { to: '/docs/events', icon: CalendarDays, titleKey: 'about.eventsSystem.title', descKey: 'docs.events_desc' },
      { to: '/docs/blog', icon: Newspaper, titleKey: 'about.cmsSystem.title', descKey: 'docs.blog_desc' },
      { to: '/docs/condo', icon: Landmark, titleKey: 'about.condoSystem.title', descKey: 'docs.condo_desc', wip: true },
    ],
  },
  {
    id: 'city',
    labelKey: 'docs.group_city',
    items: [
      { to: '/docs/maps', icon: Map, titleKey: 'about.mapsSystem.title', descKey: 'docs.maps_desc' },
      { to: '/docs/opensky', icon: Plane, titleKey: 'about.openskySystem.title', descKey: 'docs.opensky_desc' },
      { to: '/docs/transit', icon: BusFront, titleKey: 'about.transitSystem.title', descKey: 'docs.transit_desc' },
      { to: '/docs/directory', icon: Building2, titleKey: 'about.directorySystem.title', descKey: 'docs.directory_desc' },
      { to: '/docs/transit-ops', icon: Bus, titleKey: 'about.transitOps.title', descKey: 'docs.transit_ops_desc' },
      { to: '/docs/driver', icon: Navigation, titleKey: 'about.driverMode.title', descKey: 'docs.driver_desc' },
      { to: '/docs/carpool', icon: Car, titleKey: 'about.carpoolSystem.title', descKey: 'docs.carpool_desc', wip: true },
    ],
  },
  {
    id: 'home',
    labelKey: 'docs.group_home',
    items: [
      { to: '/docs/property', icon: Home, titleKey: 'about.propertySystem.title', descKey: 'docs.property_desc' },
      { to: '/docs/smart-home', icon: Plug, titleKey: 'about.smartHomeSystem.title', descKey: 'docs.smart_home_desc' },
      { to: '/docs/stations', icon: Wind, titleKey: 'about.stationsSystem.title', descKey: 'docs.stations_desc' },
      { to: '/docs/energy', icon: Zap, titleKey: 'about.energySystem.title', descKey: 'docs.energy_desc', wip: true },
    ],
  },
  {
    id: 'platform',
    labelKey: 'docs.group_platform',
    items: [
      { to: '/docs/mesh', icon: Wifi, titleKey: 'about.meshSystem.title', descKey: 'docs.mesh_desc' },
      { to: '/docs/federation', icon: Globe, titleKey: 'about.federationSystem.title', descKey: 'docs.federation_desc' },
      { to: '/docs/tech', icon: Cpu, titleKey: 'about.techStack.title', descKey: 'docs.tech_desc' },
    ],
  },
]

let flatIdx = 0
const groups = rawGroups.map(g => ({
  ...g,
  items: g.items.map(it => ({ ...it, idx: flatIdx++ })),
}))
const flatSections = groups.flatMap(g => g.items)

const scrollToGroup = (id: string) => {
  document.getElementById(`group-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

if (import.meta.client) {
  const onKeydown = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusIdx.value = Math.min(focusIdx.value + 1, flatSections.length - 1)
      itemRefs[focusIdx.value]?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusIdx.value = Math.max(focusIdx.value - 1, 0)
      itemRefs[focusIdx.value]?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'ArrowRight' && focusIdx.value >= 0) {
      e.preventDefault()
      router.push(localePath(flatSections[focusIdx.value].to))
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      router.push(localePath('/about'))
    }
  }
  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}

definePageMeta({
  order: 2,
})
</script>
