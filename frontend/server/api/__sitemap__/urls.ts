import { defineSitemapEventHandler } from '#imports'

type SitemapUrl = { loc: string; lastmod?: string }

export default defineSitemapEventHandler(async () => {
  const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

  // Each dynamic source is fetched independently so one backend hiccup never
  // wipes the other's URLs out of the sitemap. New surfaces (e.g. transit
  // stops) slot in as another entry below.
  async function fetchSource(path: string): Promise<SitemapUrl[]> {
    try {
      const data = await $fetch<SitemapUrl[]>(`${backendUrl}${path}`)
      return data.map((item) => ({
        // Canonical (default-locale) URL only — one entry per page, NOT expanded
        // across locales. Every page emits a full hreflang cluster + self-canonical
        // in its <head> (app.vue → useLocaleHead), so Google discovers and indexes
        // each language from there. This keeps the sitemap flat (≈90k, not ≈540k ×
        // 6 locales) and sidesteps @nuxtjs/sitemap's i18n-chunking phantom-404 bug.
        loc: item.loc,
        ...(item.lastmod ? { lastmod: item.lastmod } : {}),
      }))
    } catch (e) {
      console.warn(`[sitemap] Failed to fetch ${path}:`, (e as Error).message)
      return []
    }
  }

  const groups = await Promise.all([
    fetchSource('/api/v1/cms/sitemap-urls/'),              // blog posts, mini-sites, org/user blog indexes
    fetchSource('/api/v1/geo/transit/sitemap-urls/'),      // canonical transit route pages (one per line)
    fetchSource('/api/v1/geo/transit/stop-sitemap-urls/'), // transit stop pages (one per physical boarding point)
  ])
  return groups.flat()
})
