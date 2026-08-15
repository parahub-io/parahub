/**
 * Private URL surfaces — the one source of truth behind BOTH the sitemap's
 * `exclude` list (nuxt.config.ts) and the generated /robots.txt
 * (server/routes/robots.txt.ts).
 *
 * The two answer different questions and have to agree: dropping a path from the
 * sitemap only stops us ADVERTISING it, crawlers still walk in through in-app
 * links, and robots.txt is what actually keeps them out. Maintained as two lists
 * they drift — the hand-written robots.txt this replaced had missed every
 * console added since it was first written.
 *
 * A route belongs here when a signed-out visitor arriving from a search result
 * would get nothing: anything behind `middleware: 'auth'`, anything that only
 * renders with a Bearer token, every console, and every landing whose meaning
 * lives in a token (invite links, bearer notes).
 */

/** Sitemap glob syntax. Base path and `/**` are both listed where children
 *  exist — one does not imply the other. Dynamic routes come only from the app
 *  source (server/api/__sitemap__/urls.ts), so nothing here may shadow those. */
export const PRIVATE_PATHS = [
  // Sign-in, onboarding and token landings
  '/login', '/register', '/welcome', '/choose-username',
  '/auth/**', '/invite/**', '/household/join', '/t',
  // Personal account surfaces
  '/profile', '/profile/**', '/settings/**', '/notifications',
  '/wallet', '/wallet/**', '/tips', '/tips/**',
  '/contracts', '/debts', '/barter',
  '/rental', '/rental/*',  // `/rental/*/*` is the public listing page
  '/shipments', '/shipments/**', '/sos', '/sos/**',
  '/chat', '/chat-element', '/chat-fluffy', '/call', '/webmail',
  '/pgp-setup', '/pgp-test', '/seed-setup', '/seed-restore',
  // Consoles — node, staff, operator
  '/iot', '/iot/**', '/dispatch', '/dispatch/**', '/driver',
  '/moderation', '/platform/**', '/federation',
  '/wot/graph', '/mesh/graph', '/urban/validation',
  '/opensky', '/zenith', '/voice/**', '/yellow-gate',
  '/design', '/design/**',
  // Authoring and management inside otherwise public sections
  '/ads', '/ads/**',
  '/market/create', '/market/my',
  '/events/create',
  '/governance/polls/create', '/governance/delegations',
  '/blog/create',
  '/condo', '/condo/**',
  '/energy/create', '/energy/my-shares',
  '/tickets/**',
  '/org', '/org/create',
  '/org/*/manage', '/org/*/manage/**', '/org/*/edit', '/org/*/members',
  '/@*/manage', '/@*/manage/**',
]

/** Locale prefixes @nuxtjs/i18n serves the same pages under. */
export const LOCALE_PREFIXES = ['pt', 'es', 'fr', 'de', 'ru']

/** Sitemap `exclude`: every pattern, once per locale it can appear under. */
export function sitemapExcludes(): string[] {
  return PRIVATE_PATHS.flatMap(p => [p, ...LOCALE_PREFIXES.map(l => `/${l}${p}`)])
}

export type RobotsRule = { allow: boolean; path: string }

/**
 * robots.txt rules derived from the same patterns — see the mapping table in
 * the body.
 *
 * `$` and `*` are honoured by Google and Bing. A crawler that ignores them reads
 * `/x$` as a literal that matches nothing and crawls an authed page that renders
 * nothing to it — the failure direction is wasted crawl, never a blocked public
 * page. Which is why exact patterns are anchored rather than left as prefixes:
 * a bare `Disallow: /t` would take /tickets, /transit and /tips with it, and
 * `Disallow: /org` would bury every public organization page.
 */
export function robotsRules(): RobotsRule[] {
  // '/x'     exact page                  -> Disallow: /x$   (children crawlable)
  // '/x/**'  whole sub-tree              -> Disallow: /x/   (/x itself untouched)
  // '/x/*'   one level, deeper is public -> Disallow: /x/ + Allow: /x/*/
  const all = new Set(PRIVATE_PATHS)
  return PRIVATE_PATHS.flatMap((p): RobotsRule[] => {
    if (p.endsWith('/**')) return [{ allow: false, path: p.slice(0, -2) }]
    if (p.endsWith('/*')) {
      const subtree = { allow: false, path: p.slice(0, -1) }
      // A `/**` sibling means the whole sub-tree is private after all.
      if (all.has(`${p}*`)) return [subtree]
      // Longest match wins, so `/x/*/` (deeper) beats `/x/` for `/x/a/b` while
      // `/x/a` matches only the Disallow — the wildcard needs a `/` after it.
      return [subtree, { allow: true, path: `${p}/` }]
    }
    return [{ allow: false, path: `${p}$` }]
  })
}
