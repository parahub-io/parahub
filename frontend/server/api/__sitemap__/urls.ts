import { defineSitemapEventHandler } from '#imports'

export default defineSitemapEventHandler(async () => {
  const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

  try {
    const data = await $fetch<Array<{ loc: string; lastmod?: string }>>(
      `${backendUrl}/api/v1/cms/sitemap-urls/`
    )

    return data.map((item) => ({
      loc: item.loc,
      ...(item.lastmod ? { lastmod: item.lastmod } : {}),
    }))
  } catch (e) {
    // Don't break sitemap if backend is unreachable
    console.warn('[sitemap] Failed to fetch CMS URLs:', (e as Error).message)
    return []
  }
})
