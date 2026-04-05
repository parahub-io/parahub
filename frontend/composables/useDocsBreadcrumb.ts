/**
 * Adds BreadcrumbList JSON-LD structured data for docs pages.
 * Usage: useDocsBreadcrumb('Getting Started', '/docs/getting-started')
 */
export function useDocsBreadcrumb(pageTitle: string, pagePath: string) {
  useHead({
    script: [
      {
        type: 'application/ld+json',
        innerHTML: JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            {
              '@type': 'ListItem',
              position: 1,
              name: 'Parahub',
              item: 'https://parahub.io',
            },
            {
              '@type': 'ListItem',
              position: 2,
              name: 'Docs',
              item: 'https://parahub.io/docs',
            },
            {
              '@type': 'ListItem',
              position: 3,
              name: pageTitle,
              item: `https://parahub.io${pagePath}`,
            },
          ],
        }),
      },
    ],
  })
}
