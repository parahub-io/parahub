// Static changelog data: files under /public/changelog/ committed at release
// time (see .claude/commands/end-release.md ritual). index.json lists releases
// newest-first; each vX.Y.Z.json carries all six locales.

export interface ChangelogHighlight {
  icon?: string
  title: string
  body?: string
}

export interface ChangelogLocaleContent {
  title: string
  summary?: string
  highlights?: ChangelogHighlight[]
  notes?: string[]
}

export interface ChangelogRelease {
  version: string
  date: string
  locales: Record<string, ChangelogLocaleContent>
}

export interface ChangelogIndexEntry {
  version: string
  date: string
}

/** "v0.9.35-12-g80bd515" -> "v0.9.35"; null when no tag is present (e.g. "unknown"). */
export function parseBaseVersion(described: string | undefined): string | null {
  const m = described?.match(/^v\d+\.\d+\.\d+/)
  return m ? m[0] : null
}

/** Last release the user was shown notes for; drives WhatsNewCard. */
export const SEEN_VERSION_KEY = 'parahub_changelog_seen'

/** Stored base tag, or null when absent/corrupt (treated as "never seen"). */
export function readSeenVersion(): string | null {
  try {
    const v = localStorage.getItem(SEEN_VERSION_KEY)
    return v && /^v\d+\.\d+\.\d+$/.test(v) ? v : null
  } catch {
    return null // private mode / storage disabled
  }
}

export function markVersionSeen(version: string): void {
  try {
    localStorage.setItem(SEEN_VERSION_KEY, version)
  } catch { /* nothing to do — the card simply reappears next visit */ }
}

/** Numeric semver-ish compare of "vA.B.C" strings: negative when a < b. */
export function compareVersions(a: string, b: string): number {
  const pa = a.replace(/^v/, '').split('.').map(Number)
  const pb = b.replace(/^v/, '').split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    const d = (pa[i] || 0) - (pb[i] || 0)
    if (d !== 0) return d
  }
  return 0
}

export function useChangelog() {
  const fetchIndex = async (opts: { fresh?: boolean } = {}): Promise<ChangelogIndexEntry[]> => {
    // fresh=true busts the HTTP cache — used when a new deploy was just
    // announced over WS and the index may have grown.
    const url = opts.fresh ? `/changelog/index.json?cb=${Date.now()}` : '/changelog/index.json'
    const data = await $fetch<{ releases: ChangelogIndexEntry[] }>(url)
    return data?.releases || []
  }

  const fetchRelease = (version: string): Promise<ChangelogRelease> =>
    $fetch<ChangelogRelease>(`/changelog/${version}.json`)

  const localeContent = (release: ChangelogRelease, locale: string): ChangelogLocaleContent =>
    release.locales[locale] || release.locales.en

  return {
    fetchIndex,
    fetchRelease,
    localeContent,
    parseBaseVersion,
    compareVersions,
    readSeenVersion,
    markVersionSeen,
  }
}
