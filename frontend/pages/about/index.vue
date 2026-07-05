<template>
  <div>
    <!-- Yellow hero header -->
    <div class="about-header border-b border-primary-300 dark:border-primary-800 py-8 sm:py-12">
      <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center gap-4 mb-4">
          <span class="about-logo" role="img" aria-label="Parahub"></span>
          <div>
            <h1 class="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100">Parahub</h1>
            <p class="text-sm text-neutral-700 dark:text-neutral-400">{{ $t('about.hero.tagline') }}</p>
          </div>
        </div>
        <p class="text-neutral-800 dark:text-neutral-300 leading-relaxed mb-6">
          {{ $t('about.hero.subtitle') }}
        </p>

        <!-- Platform stats (human metrics only) -->
        <div v-if="platformStats.length" class="flex flex-wrap gap-x-6 gap-y-2 mb-6 text-sm">
          <div v-for="s in platformStats" :key="s.key">
            <span class="text-neutral-900 dark:text-neutral-100 font-bold text-base tabular-nums">{{ formatNumber(s.value) }}</span>
            <span class="text-neutral-700 dark:text-neutral-400 ml-1">{{ s.label }}</span>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="flex flex-wrap gap-3">
          <UiButton variant="secondary" size="sm" :to="localePath('/docs')" :icon="BookOpen">
            {{ $t('docs.title') }}
          </UiButton>
          <UiButton v-if="authStore.user?.is_staff" variant="secondary" size="sm" :to="localePath('/about/support')" :icon="Headphones">
            {{ $t('support_voice.title') }}
          </UiButton>
          <UiButton variant="secondary" size="sm" tag="a" href="/parahub.apk" download :icon="Smartphone">
            {{ $t('about.android_app') }}
          </UiButton>
        </div>
      </div>
    </div>

    <!-- Content -->
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <section id="imprint" class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <FileText class="w-5 h-5 text-neutral-400" />
          {{ $t('imprint.title') }}
        </h2>

        <div class="space-y-4 text-sm text-neutral-700 dark:text-neutral-300">
          <div>
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('imprint.operator.title') }}</h3>
            <p class="font-mono"><NuxtLink :to="localePath('/org/parahub-associacao')" class="text-link">Parahub - Associação</NuxtLink>, Portugal</p>
          </div>

          <div>
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('imprint.responsible.title') }}</h3>
            <p><NuxtLink :to="localePath('/org/parahub-associacao')" class="text-link">Parahub - Associação</NuxtLink>, {{ $t('imprint.responsible.country') }}</p>
          </div>

          <div>
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('imprint.disclaimer.title') }}</h3>
            <div class="space-y-2">
              <p><span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('imprint.disclaimer.content.title') }}:</span> {{ $t('imprint.disclaimer.content.text') }}</p>
              <p><span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('imprint.disclaimer.links.title') }}:</span> {{ $t('imprint.disclaimer.links.text') }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Contact -->
      <section id="contact" class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Mail class="w-5 h-5 text-neutral-400" />
          {{ $t('about.contact.title') }}
        </h2>

        <div v-if="!authStore.isAuthenticated" class="mb-4">
          <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('about.cta.text') }}</p>
          <NuxtLink :to="localePath('/login')" class="text-link text-sm font-medium">
            {{ $t('about.cta.start') }} &rarr;
          </NuxtLink>
        </div>

        <div class="space-y-2 text-sm">
          <div class="flex gap-3">
            <span class="text-neutral-500 dark:text-neutral-400 w-28 flex-shrink-0">{{ $t('about.contact.email') }}</span>
            <a href="mailto:info@parahub.io" class="text-link font-mono">info&#64;parahub.io</a>
          </div>
          <div class="flex gap-3">
            <span class="text-neutral-500 dark:text-neutral-400 w-28 flex-shrink-0">{{ $t('about.cta.github') }}</span>
            <a href="https://github.com/parahub-io" class="text-link font-mono" target="_blank" rel="noopener">github.com/parahub-io</a>
          </div>
          <div v-if="authStore.user?.is_staff" class="flex gap-3">
            <span class="text-neutral-500 dark:text-neutral-400 w-28 flex-shrink-0">{{ $t('about.contact.support') }}</span>
            <NuxtLink :to="localePath('/about/support')" class="text-link">{{ $t('support_voice.title') }}</NuxtLink>
          </div>
        </div>
      </section>

      <!-- Platform Services -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Server class="w-5 h-5 text-neutral-400" />
          {{ $t('about.services.title') }}
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <a
            v-for="svc in platformServices"
            :key="svc.url"
            :href="svc.url"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-3 p-3 rounded-lg border border-neutral-300 dark:border-neutral-600 hover:border-primary transition-colors group"
          >
            <component :is="svc.icon" class="w-5 h-5 text-neutral-400 group-hover:text-secondary shrink-0" />
            <div class="min-w-0">
              <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 flex items-center gap-1">
                {{ svc.name }}
                <ExternalLink class="w-3 h-3 opacity-40" />
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 truncate">{{ svc.desc }}</div>
            </div>
          </a>
        </div>
      </section>

      <!-- Cryptographic Proofs / Transparency -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <ShieldCheck class="w-5 h-5 text-neutral-400" />
          {{ $t('about.cryptoProofs.title') }}
        </h2>
        <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-4">{{ $t('about.cryptoProofs.short') }}</p>
        <div class="flex flex-wrap items-center gap-4">
          <UiButton variant="secondary" size="sm" :to="localePath('/docs/crypto')" :icon="ShieldCheck">
            {{ $t('about.cryptoProofs.verify.title') }}
          </UiButton>
          <a href="https://git.parahub.io/audit/parahub-registry" target="_blank" rel="noopener" class="text-link text-sm font-mono inline-flex items-center gap-1">
            {{ $t('about.cryptoProofs.repo.cta') }}
            <ExternalLink class="w-3.5 h-3.5 opacity-50" />
          </a>
        </div>
      </section>

      <!-- Legal links -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Scale class="w-5 h-5 text-neutral-400" />
          {{ $t('footer.legal') }}
        </h2>
        <div class="space-y-2">
          <NuxtLink :to="localePath('/about/terms')" class="text-link text-sm flex items-center gap-2">
            <ChevronRight class="w-4 h-4" />
            {{ $t('footer.terms') }}
          </NuxtLink>
          <NuxtLink :to="localePath('/about/privacy')" class="text-link text-sm flex items-center gap-2">
            <ChevronRight class="w-4 h-4" />
            {{ $t('footer.privacy') }}
          </NuxtLink>
          <NuxtLink :to="localePath('/about/code-of-conduct')" class="text-link text-sm flex items-center gap-2">
            <ChevronRight class="w-4 h-4" />
            {{ $t('codeOfConduct.title') }}
          </NuxtLink>
        </div>
      </section>

      <!-- Footer -->
      <p class="text-xs text-neutral-400 dark:text-neutral-600 font-mono">
        Parahub {{ version }} &middot; {{ buildDate }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { BookOpen, Smartphone, Headphones, FileText, Mail, Scale, ChevronRight, Server, ExternalLink, Video, Activity, ShieldCheck } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()

// SSR-prefetch stats to avoid CLS (layout shift when stats pop in after hydration)
const { data: stats } = await useAsyncData('about-stats', () =>
  $fetch('/api/v1/dashboard/stats')
)

useHead({ title: computed(() => `${t('about.hero.subtitle')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('about.meta.description')),
  ogTitle: computed(() => `${t('about.hero.subtitle')} — Parahub`),
  ogDescription: computed(() => t('about.meta.description')),
})

const platformServices = computed(() => [
  { name: t('about.services.video'), url: 'https://video.parahub.io', icon: Video, desc: t('about.services.video_desc') },
  { name: t('about.services.status'), url: 'https://status.parahub.io', icon: Activity, desc: t('about.services.status_desc') },
])

const config = useRuntimeConfig()
const version = computed(() => config.public.appVersion)
const buildDate = computed(() => {
  const date = new Date(config.public.buildDate)
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short'
  })
})

// Platform stats: show all non-zero metrics
const platformStats = computed(() => {
  if (!stats.value) return []
  return [
    { key: 'total_profiles', value: stats.value.total_profiles || 0, label: t('about.community.profiles') },
    { key: 'active_items', value: stats.value.active_items || 0, label: t('about.community.active_items') },
    { key: 'establishments', value: stats.value.establishments || 0, label: t('about.community.establishments') },
    { key: 'contracts', value: stats.value.contracts || 0, label: t('about.community.contracts') },
  ].filter(s => s.value > 0)
})

function formatNumber(n: number): string {
  if (n >= 1000) return n.toLocaleString()
  return String(n)
}

definePageMeta({
  order: 1,
})
</script>

<style scoped>
.about-header {
  background-color: var(--color-primary);
}
:root.dark .about-header {
  background-color: rgba(115, 101, 0, 0.25);
}
.about-logo {
  display: block;
  width: 3rem;
  height: 3rem;
  flex-shrink: 0;
  background-color: #000;
  -webkit-mask-image: url(/logo.svg);
  mask-image: url(/logo.svg);
  -webkit-mask-size: contain;
  mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-position: center;
  mask-position: center;
}
:root.dark .about-logo {
  background-color: #FBBF24;
}
</style>
