<template>
  <div class="min-h-screen flex flex-col" :style="cssVars">
    <!-- Site Navigation -->
    <nav class="sticky top-0 z-50 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-14 sm:h-16">
          <!-- Site name / logo -->
          <NuxtLink :to="siteHomeUrl" class="flex items-center gap-2 min-w-0">
            <img
              v-if="site?.logo_url"
              :src="site.logo_url"
              alt=""
              class="w-8 h-8 rounded-full object-cover shrink-0"
            />
            <div
              v-else
              class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm shrink-0"
              :style="{ background: site?.accent_color || '#F5C518', color: accentTextColor }"
            >
              {{ siteInitial }}
            </div>
            <span class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 truncate">
              {{ siteName }}
            </span>
          </NuxtLink>

          <!-- Nav links (desktop) -->
          <div class="hidden sm:flex items-center gap-1">
            <NuxtLink
              v-for="item in navItems"
              :key="item.slug"
              :to="localePath(item.to)"
              class="px-3 py-1.5 text-sm font-medium rounded-lg transition-colors"
              :class="isNavActive(item.to) ? '' : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
              :style="isNavActive(item.to) ? { background: 'var(--site-accent)', color: accentTextColor } : {}"
            >
              {{ item.label }}
            </NuxtLink>
          </div>

          <!-- Mobile menu toggle -->
          <button
            @click="mobileNav = !mobileNav"
            class="sm:hidden p-2 text-neutral-600 dark:text-neutral-400"
          >
            <component :is="mobileNav ? XIcon : MenuIcon" class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Mobile nav -->
      <div v-if="mobileNav" class="sm:hidden border-t border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-4 py-2 space-y-1">
        <NuxtLink
          v-for="item in navItems"
          :key="item.slug"
          :to="localePath(item.to)"
          @click="mobileNav = false"
          class="block px-3 py-2 text-sm font-medium rounded-lg"
          :class="isNavActive(item.to) ? '' : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800'"
          :style="isNavActive(item.to) ? { background: 'var(--site-accent)', color: accentTextColor } : {}"
        >
          {{ item.label }}
        </NuxtLink>
      </div>
    </nav>

    <!-- Hero section -->
    <div
      v-if="site?.hero_image_url || site?.hero_text_html"
      class="relative"
    >
      <img
        v-if="site.hero_image_url"
        :src="site.hero_image_url"
        alt=""
        class="w-full h-48 sm:h-64 object-cover"
      />
      <div
        v-if="site.hero_text_html"
        class="bg-white/90 dark:bg-neutral-900/90 backdrop-blur-sm"
        :class="site.hero_image_url ? 'absolute inset-x-0 bottom-0 px-6 py-4' : 'px-6 py-8'"
      >
        <div class="max-w-4xl mx-auto prose dark:prose-invert prose-sm" v-html="site.hero_text_html" />
      </div>
    </div>

    <!-- Main content -->
    <main class="flex-1">
      <slot />
    </main>

  </div>
</template>

<script setup lang="ts">
import { Menu as MenuIcon, X as XIcon } from 'lucide-vue-next'

const { t, te } = useI18n()
const route = useRoute()
const localePath = useLocalePath()

const siteCtx = useSiteContext()

const site = useState<any>('siteData', () => null)
const loading = ref(true)

const mobileNav = ref(false)

// Fetch site data
async function fetchSite() {
  if (!siteCtx.value) return
  try {
    const params: Record<string, string> = siteCtx.value.type === 'custom'
      ? { domain: siteCtx.value.slug }
      : { slug: siteCtx.value.slug, type: siteCtx.value.type }
    site.value = await $fetch<any>('/api/v1/cms/sites/resolve/', { params })
  } catch {
    // Site not found — show empty shell
  } finally {
    loading.value = false
  }
}

if (import.meta.server || !site.value) {
  await fetchSite()
}

const siteName = computed(() => {
  if (!site.value) return siteCtx.value?.slug || ''
  return site.value.establishment_name || site.value.profile_name || siteCtx.value?.slug || ''
})

const siteInitial = computed(() => {
  const name = siteName.value
  return name ? name[0].toUpperCase() : '?'
})

// Pick readable text color (black/white) against the site's accent background —
// raw accent color as text (or as a light background tint) is unreadable for
// light accents, same "text-primary is unreadable" rule as PK/design-system.md
const accentTextColor = computed(() => {
  const hex = (site.value?.accent_color || '#F5C518').replace('#', '')
  const r = parseInt(hex.substring(0, 2), 16)
  const g = parseInt(hex.substring(2, 4), 16)
  const b = parseInt(hex.substring(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.5 ? '#000000' : '#ffffff'
})

// Set page title to site/org name
useHead(computed(() => ({
  title: siteName.value || undefined,
})))

const siteHomeUrl = computed(() => localePath('/'))

// Build nav items from nav_sections + pages
interface NavItem {
  slug: string
  label: string
  to: string
}

const navItems = computed<NavItem[]>(() => {
  if (!site.value) return []

  const items: NavItem[] = []

  // Home
  items.push({ slug: 'home', label: te('common.home') ? t('common.home') : 'Home', to: '/' })

  // Built-in sections from nav_sections
  const sections = (site.value.nav_sections || []).sort((a: any, b: any) => a.order - b.order)
  const sectionLabels: Record<string, string> = {
    blog: t('cms.site.sectionBlog'),
    gallery: t('cms.site.sectionGallery'),
    items: t('cms.site.sectionItems'),
    contact: t('cms.site.sectionContact'),
  }
  const sectionRoutes: Record<string, string> = {
    blog: '/blog/',
    gallery: '/blog/?tag=galeria',
    items: '/items/',
    contact: '/contact/',
  }
  for (const s of sections) {
    if (sectionLabels[s.type]) {
      items.push({ slug: s.type, label: sectionLabels[s.type], to: sectionRoutes[s.type] })
    }
  }

  // Custom pages with show_in_nav (homepage is reachable via "Home" already, exclude it here)
  const pages = (site.value.nav_pages || []).filter((p: any) => !p.is_homepage)
  for (const p of pages) {
    items.push({ slug: p.slug, label: p.title, to: `/${p.slug}` })
  }

  // Sort by order (sections already ordered, pages by their order field)
  return items
})

function isNavActive(to: string) {
  const localizedTo = localePath(to)
  if (to === '/') return route.path === localizedTo
  // Strip trailing slash for comparison
  const base = localizedTo.endsWith('/') ? localizedTo.slice(0, -1) : localizedTo
  return route.path === localizedTo || route.path === base || route.path.startsWith(base + '/')
}

// CSS custom properties for accent color
const cssVars = computed(() => ({
  '--site-accent': site.value?.accent_color || '#F5C518',
}))
</script>
