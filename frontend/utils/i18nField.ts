/**
 * Pick the best string for the active locale from an authoritative {lang: text} i18n map,
 * falling back to the base (source-language) string.
 *
 * Shared substrate for DB-text i18n (curated civic polls now; market MT cache later).
 * Authoritative maps are small (<=6 langs) and shipped whole, so the client resolves —
 * switching the UI language re-renders instantly with no refetch. An empty/absent map
 * (user-authored content) transparently falls back to the base field.
 */
export function pickI18n(
  i18n: Record<string, string> | null | undefined,
  base: string,
  locale: string,
): string {
  const v = i18n?.[locale]
  return v ? v : base
}
