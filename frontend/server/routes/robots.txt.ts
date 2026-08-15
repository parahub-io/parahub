import { LOCALE_PREFIXES, robotsRules } from '~~/shared/private-paths'

/**
 * /robots.txt, generated from shared/private-paths.ts so it can never drift
 * from the sitemap's exclusion list. Replaces a hand-maintained public/robots.txt
 * (a static file there would win over this route, so it must stay deleted).
 *
 * Sitemaps of the per-feature landing subdomains are listed too: they are served
 * by their own nginx roots, and a crawler that only ever fetches parahub.io/robots.txt
 * would otherwise never learn they exist.
 */
const SITEMAPS = [
  'https://parahub.io/sitemap.xml',
  'https://boleias.parahub.io/sitemap.xml',
  'https://condominios.parahub.io/sitemap.xml',
  'https://contratos.parahub.io/sitemap.xml',
  'https://democracia.parahub.io/sitemap.xml',
  'https://directorio.parahub.io/sitemap.xml',
  'https://energia.parahub.io/sitemap.xml',
  'https://eventos.parahub.io/sitemap.xml',
  'https://mesh.parahub.io/sitemap.xml',
  'https://sos.parahub.io/sitemap.xml',
  'https://transporte.parahub.io/sitemap.xml',
  'https://troca.parahub.io/sitemap.xml',
]

export default defineEventHandler((event) => {
  const rules = robotsRules()
  const render = (prefix: string) =>
    rules.map(r => `${r.allow ? 'Allow' : 'Disallow'}: ${prefix}${r.path}`).join('\n')

  const body = [
    '# Generated from shared/private-paths.ts — edit that list, not this output.',
    '',
    'User-agent: *',
    'Allow: /',
    '',
    '# Private surfaces',
    render(''),
    // The same pages answer under every locale prefix, and each prefix is a
    // distinct URL to a crawler.
    ...LOCALE_PREFIXES.map(l => `\n# ${l}\n${render(`/${l}`)}`),
    '',
    ...SITEMAPS.map(s => `Sitemap: ${s}`),
    '',
  ].join('\n')

  setResponseHeader(event, 'Content-Type', 'text/plain; charset=utf-8')
  setResponseHeader(event, 'Cache-Control', 'public, max-age=3600')
  return body
})
