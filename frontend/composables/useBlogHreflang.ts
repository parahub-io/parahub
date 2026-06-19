/**
 * Adds hreflang <link> tags for blog post translations.
 * Tells Google which translated versions of the same post exist.
 */
export function useBlogHreflang(
  post: Ref<any>,
  linkBase: MaybeRef<string>,
) {
  const localePath = useLocalePath()

  const hreflangLinks = computed(() => {
    const p = unref(post)
    if (!p?.language || !p?.slug) return []
    const base = unref(linkBase)
    const translations: Array<{ language: string; slug: string }> = p.translations || []
    if (!translations.length) return []

    const links: Array<{ rel: string; hreflang: string; href: string }> = []

    // Self-referencing hreflang for current post
    const selfHref = `https://parahub.io${localePath(`${base}/${p.slug}`, p.language)}`
    links.push({ rel: 'alternate', hreflang: p.language, href: selfHref })

    // Each translation
    for (const tr of translations) {
      links.push({
        rel: 'alternate',
        hreflang: tr.language,
        href: `https://parahub.io${localePath(`${base}/${tr.slug}`, tr.language)}`,
      })
    }

    // x-default → English version if available, otherwise current post
    const enVersion = p.language === 'en'
      ? p
      : translations.find((t: any) => t.language === 'en')
    const defaultHref = enVersion
      ? `https://parahub.io${localePath(`${base}/${enVersion.slug}`, 'en')}`
      : selfHref
    links.push({ rel: 'alternate', hreflang: 'x-default', href: defaultHref })

    return links
  })

  useHead({ link: hreflangLinks })
}
