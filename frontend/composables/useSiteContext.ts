/**
 * Detect mini-site context from Host header.
 *
 * Subdomains:
 *   {slug}.org.parahub.io → type='org', slug
 *   {name}.u.parahub.io  → type='u', slug
 *
 * Custom domains:
 *   cafe-central.pt → type='custom', slug=domain
 *
 * Returns null on main domain (parahub.io).
 */

interface SiteContext {
  type: 'org' | 'u' | 'custom'
  slug: string
}

export function useSiteContext(): Ref<SiteContext | null> {
  const ctx = useState<SiteContext | null>('siteContext', () => null)

  if (import.meta.server) {
    const event = useRequestEvent()
    const host = event?.node?.req?.headers?.host || ''
    ctx.value = parseSiteHost(host)
  }

  if (import.meta.client && !ctx.value) {
    ctx.value = parseSiteHost(window.location.host)
  }

  return ctx
}

function parseSiteHost(host: string): SiteContext | null {
  // Remove port
  const hostname = host.split(':')[0]

  // Main domain — not a mini-site
  if (hostname === 'parahub.io' || hostname === 'www.parahub.io' || hostname === 'localhost') {
    return null
  }

  // Match {slug}.org.parahub.io
  const orgMatch = hostname.match(/^([a-z0-9-]+)\.org\.parahub\.io$/)
  if (orgMatch) {
    return { type: 'org', slug: orgMatch[1] }
  }

  // Match {name}.u.parahub.io
  const userMatch = hostname.match(/^([a-z0-9-]+)\.u\.parahub\.io$/)
  if (userMatch) {
    return { type: 'u', slug: userMatch[1] }
  }

  // Any other *.parahub.io subdomain (e.g. energia.parahub.io) — not a mini-site
  if (hostname.endsWith('.parahub.io')) {
    return null
  }

  // Custom domain (anything else)
  return { type: 'custom', slug: hostname }
}
