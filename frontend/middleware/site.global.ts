/**
 * Global middleware: detect subdomain and switch to 'site' layout.
 *
 * *.org.parahub.io / *.u.parahub.io → layout: 'site'
 * parahub.io → layout: 'default' (no change)
 */
export default defineNuxtRouteMiddleware((to) => {
  const ctx = useSiteContext()
  if (ctx.value) {
    // Force site layout for mini-site subdomains
    to.meta.layout = 'site'
  }
})
