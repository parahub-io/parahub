<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <!-- Header -->
    <div class="docs-header border-b border-primary/40 dark:border-primary/30 py-6 sm:py-8">
      <div class="max-w-3xl mx-auto px-4 sm:px-6">
        <nav class="flex items-center gap-1.5 text-sm">
          <NuxtLink :to="localePath('/about')" class="text-neutral-900/60 dark:text-yellow-900/70 hover:text-neutral-900 dark:hover:text-yellow-900 transition-colors">
            {{ $t('about.title') }}
          </NuxtLink>
          <ChevronRight class="w-3.5 h-3.5 text-neutral-900/30 dark:text-yellow-900/40" />
          <h1 class="inline text-neutral-900 font-semibold text-lg sm:text-xl">{{ $t('docs.title') }}</h1>
        </nav>
        <p class="mt-2 text-sm text-neutral-900/60">{{ $t('docs.intro') }}</p>
      </div>
    </div>

    <!-- Section Cards -->
    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
      <div class="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-800">
        <NuxtLink
          v-for="(s, i) in sections"
          :key="s.to"
          :ref="(el: any) => { if (el?.$el) itemRefs[i] = el.$el }"
          :to="localePath(s.to)"
          class="flex items-center gap-4 p-4 sm:p-5 transition-colors group"
          :class="focusIdx === i ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-primary/15 dark:hover:bg-primary/10'"
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
    </div>

  </div>
</template>

<script setup lang="ts">
import {
  Compass, LayoutGrid, ArrowLeftRight, Scale, Cpu, ScrollText, ChevronRight,
  ShieldCheck, Shield, Zap, Wifi, Vote, Rocket, KeyRound, Megaphone, HandCoins, Globe, Landmark,
  Package, Ticket, Bus, Navigation,
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

const sections = [
  { to: '/docs/getting-started', icon: Rocket, titleKey: 'about.gettingStarted.title', descKey: 'docs.getting_started_desc' },
  { to: '/docs/mission', icon: Compass, titleKey: 'about.toc.mission', descKey: 'docs.mission_desc' },
  { to: '/docs/features', icon: LayoutGrid, titleKey: 'about.features.title', descKey: 'docs.features_desc' },
  { to: '/docs/wot', icon: ShieldCheck, titleKey: 'about.wotSystem.title', descKey: 'docs.wot_desc' },
  { to: '/docs/crypto', icon: KeyRound, titleKey: 'about.cryptoProofs.title', descKey: 'docs.crypto_desc' },
  { to: '/docs/barter', icon: ArrowLeftRight, titleKey: 'about.barterSystem.title', descKey: 'docs.barter_desc' },
  { to: '/docs/governance', icon: Vote, titleKey: 'about.governanceSystem.title', descKey: 'docs.governance_desc' },
  { to: '/docs/ads', icon: Megaphone, titleKey: 'about.adsSystem.title', descKey: 'docs.ads_desc' },
  { to: '/docs/mesh', icon: Wifi, titleKey: 'about.meshSystem.title', descKey: 'docs.mesh_desc' },
  { to: '/docs/energy', icon: Zap, titleKey: 'about.energySystem.title', descKey: 'docs.energy_desc', wip: true },
  { to: '/docs/federation', icon: Globe, titleKey: 'about.federationSystem.title', descKey: 'docs.federation_desc' },
  { to: '/docs/transparency', icon: HandCoins, titleKey: 'about.transparency.title', descKey: 'docs.transparency_desc' },
  { to: '/docs/condo', icon: Landmark, titleKey: 'about.condoSystem.title', descKey: 'docs.condo_desc', wip: true },
  { to: '/docs/phub', icon: Package, titleKey: 'about.phubSystem.title', descKey: 'docs.phub_desc' },
  { to: '/docs/sos', icon: Shield, titleKey: 'parasos.title', descKey: 'docs.parasos_desc' },
  { to: '/docs/tickets', icon: Ticket, titleKey: 'about.ticketsSystem.title', descKey: 'docs.tickets_desc' },
  { to: '/docs/transit-ops', icon: Bus, titleKey: 'about.transitOps.title', descKey: 'docs.transit_ops_desc' },
  { to: '/docs/driver', icon: Navigation, titleKey: 'about.driverMode.title', descKey: 'docs.driver_desc' },
  { to: '/docs/conduct', icon: ScrollText, titleKey: 'footer.code_of_conduct', descKey: 'docs.conduct_desc' },
  { to: '/docs/arbitration', icon: Scale, titleKey: 'about.arbitration.title', descKey: 'docs.arbitration_desc' },
  { to: '/docs/tech', icon: Cpu, titleKey: 'about.techStack.title', descKey: 'docs.tech_desc' },
]

if (import.meta.client) {
  const onKeydown = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusIdx.value = Math.min(focusIdx.value + 1, sections.length - 1)
      itemRefs[focusIdx.value]?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusIdx.value = Math.max(focusIdx.value - 1, 0)
      itemRefs[focusIdx.value]?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'ArrowRight' && focusIdx.value >= 0) {
      e.preventDefault()
      router.push(localePath(sections[focusIdx.value].to))
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

<style scoped>
.docs-header {
  background-color: var(--color-primary);
}
</style>
