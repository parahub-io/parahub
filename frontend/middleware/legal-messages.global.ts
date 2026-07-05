/**
 * Lazily merges the heavy `legal.json` locale namespaces (about/terms/privacy/
 * manifest/imprint, 70-115KB per locale) only on the routes that render them.
 * The file is excluded from the i18n `files` list in nuxt.config, which keeps
 * it out of every locale bundle; `about.title` — the only key used by global
 * components — lives in common.json.
 */
const needsLegal = (baseName: string) =>
  baseName === 'manifest' || baseName.startsWith('docs') || baseName.startsWith('about')

// The client app is a singleton, so remember which locales are merged. The
// server builds a fresh i18n instance per request — merge unconditionally.
const mergedOnClient = new Set<string>()

export default defineNuxtRouteMiddleware(async (to) => {
  // Localized route names look like `docs-crypto___ru`; the suffix is the
  // target locale of the navigation (already correct during locale switches,
  // when $i18n.locale may not have flipped yet).
  const [baseName = '', localeFromName] = String(to.name ?? '').split('___')
  if (!needsLegal(baseName)) return

  const i18n = useNuxtApp().$i18n as any
  const locale: string = localeFromName || i18n.locale.value
  if (import.meta.client && mergedOnClient.has(locale)) return

  const messages = await import(`../locales/${locale}/legal.json`)
  i18n.mergeLocaleMessage(locale, messages.default ?? messages)
  if (import.meta.client) mergedOnClient.add(locale)
})
