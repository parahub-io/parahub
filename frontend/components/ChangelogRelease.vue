<template>
  <article>
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <UiBadge variant="secondary" type="soft" size="sm">{{ release.version }}</UiBadge>
      <UiBadge v-if="latest" variant="primary" type="soft" size="sm">{{ $t('changelog.latest') }}</UiBadge>
      <time :datetime="release.date" class="text-xs text-neutral-500 dark:text-neutral-400">{{ formattedDate }}</time>
    </div>

    <template v-if="compact">
      <p class="mt-2 text-xs font-semibold text-neutral-900 dark:text-neutral-100">{{ content.title }}</p>
      <ul v-if="content.highlights?.length" class="mt-1.5 space-y-1">
        <li
          v-for="(h, i) in content.highlights"
          :key="i"
          class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400"
        >
          <component :is="iconFor(h.icon)" class="h-3.5 w-3.5 shrink-0 text-secondary dark:text-secondary-400" />
          <span>{{ h.title }}</span>
        </li>
      </ul>
    </template>

    <template v-else>
      <h2 class="mt-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ content.title }}</h2>
      <p v-if="content.summary" class="mt-1 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
        {{ content.summary }}
      </p>
      <ul v-if="content.highlights?.length" class="mt-4 space-y-3">
        <li v-for="(h, i) in content.highlights" :key="i" class="flex gap-3">
          <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary-50 text-secondary dark:bg-secondary-900/30 dark:text-secondary-400">
            <component :is="iconFor(h.icon)" class="h-4 w-4" />
          </span>
          <div class="min-w-0">
            <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ h.title }}</p>
            <p v-if="h.body" class="mt-0.5 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">{{ h.body }}</p>
          </div>
        </li>
      </ul>
      <div v-if="content.notes?.length" class="mt-4">
        <p class="text-xs font-medium uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
          {{ $t('changelog.also') }}
        </p>
        <ul class="mt-2 space-y-1.5">
          <li
            v-for="(note, i) in content.notes"
            :key="i"
            class="flex gap-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400"
          >
            <span class="mt-2 h-1 w-1 shrink-0 rounded-full bg-neutral-400 dark:bg-neutral-500" />
            <span>{{ note }}</span>
          </li>
        </ul>
      </div>
    </template>
  </article>
</template>

<script setup lang="ts">
import type { FunctionalComponent } from 'vue'
import {
  AtSign, Bus, Calendar, Clock, Eye, Gift, Home, Landmark, Languages, LayoutGrid,
  Megaphone, Plane, Printer, Scale, Share2, Shield, ShieldCheck, Smartphone,
  Sparkles, Users, Video, Vote, Wallet, Wifi, Wind, Zap
} from 'lucide-vue-next'
import type { ChangelogRelease } from '~/composables/useChangelog'

const props = defineProps<{
  release: ChangelogRelease
  compact?: boolean
  latest?: boolean
}>()

const { locale } = useI18n()
const { localeContent } = useChangelog()

const content = computed(() => localeContent(props.release, locale.value))

const formattedDate = computed(() =>
  new Date(props.release.date).toLocaleDateString(locale.value, {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
)

const ICONS: Record<string, FunctionalComponent> = {
  'at-sign': AtSign,
  'bus': Bus,
  'calendar': Calendar,
  'clock': Clock,
  'eye': Eye,
  'gift': Gift,
  'home': Home,
  'landmark': Landmark,
  'languages': Languages,
  'layout-grid': LayoutGrid,
  'megaphone': Megaphone,
  'plane': Plane,
  'printer': Printer,
  'scale': Scale,
  'share-2': Share2,
  'shield': Shield,
  'shield-check': ShieldCheck,
  'smartphone': Smartphone,
  'users': Users,
  'video': Video,
  'vote': Vote,
  'wallet': Wallet,
  'wifi': Wifi,
  'wind': Wind,
  'zap': Zap
}

const iconFor = (name?: string) => (name && ICONS[name]) || Sparkles
</script>
