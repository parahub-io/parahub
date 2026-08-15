<template>
  <!-- Mini-site subdomain: show site home -->
  <BlogSiteHome v-if="siteCtx" />

  <!-- Unauthenticated or SSR: show landing page -->
  <!-- Use !isAuthenticated (not a check-complete gate) to avoid unmount/remount during auth check -->
  <TheLanding v-else-if="isSSR || !authStore.isAuthenticated" />

  <!-- Authenticated: the map is the home screen — brief blank while redirecting -->
  <div v-else class="min-h-full"></div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'

definePageMeta({
  order: 0,
})

const authStore = useAuthStore()
const { t } = useI18n()
const localePath = useLocalePath()

// Mini-site subdomain detection
const siteCtx = useSiteContext()

// SSR always renders landing page (crawlers are anonymous)
const isSSR = import.meta.server

// Landing SEO for anonymous users / crawlers (skip on subdomain — site layout handles it)
if (!siteCtx.value) {
  useSeoMeta({
    title: () => authStore.isAuthenticated ? undefined : t('landing.seo.title'),
    ogTitle: () => authStore.isAuthenticated ? undefined : t('landing.seo.title'),
    description: () => authStore.isAuthenticated ? undefined : t('landing.seo.description'),
    ogDescription: () => authStore.isAuthenticated ? undefined : t('landing.seo.description'),
    twitterCard: 'summary_large_image',
  })
}

// Authenticated home is the map: `/` only serves the landing (anon) and
// mini-site homes; logged-in visitors are forwarded to /map.
onMounted(async () => {
  if (siteCtx.value) return

  await authStore.ensureSession()

  if (authStore.isAuthenticated) {
    await navigateTo(localePath('/map'), { replace: true })
    return
  }

  // Watch for auth state change (e.g. after OAuth login redirect back)
  const unwatch = watch(() => authStore.isAuthenticated, async (isAuth) => {
    if (isAuth) {
      unwatch()
      await navigateTo(localePath('/map'), { replace: true })
    }
  })
})
</script>
