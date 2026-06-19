import type { Component } from 'vue'
import {
  Wallet, Settings, Calendar, Book, Vote, Building,
  Megaphone, FileText, PackageCheck, Package, Zap, Car,
  Shield, Info, Bot,
} from 'lucide-vue-next'

/**
 * Single source of truth for nav-link metadata consumed by AppNavigation
 * and useNavDragSelect. Previously this data was duplicated across three
 * inline structures: `menuItemsMap`, `submenuPathPrefixes`, and the labels
 * record inside `resolveLabel`.
 *
 * Fields:
 *   path          — exact route the nav item links to (also drag drop-target key)
 *   iconPrefix    — override prefix for Menu-button active-icon match (default: path)
 *   activeIcon    — icon shown *inside the Menu button* when this path is active;
 *                   may differ from the dropdown NavItem's icon (intentional, see /iot, /energy)
 *   labelKey      — i18n key for the drag hover-label bar
 *   inDropdown    — true if this item lives inside the dropdown (drag hovering it
 *                   keeps the menu open instead of closing it)
 */
export interface NavMenuEntry {
  path: string
  iconPrefix?: string
  activeIcon?: Component
  labelKey?: string
  inDropdown?: boolean
}

/** External Gitea link — the full URL doubles as the drag drop-target key. */
export const PROJECTS_URL = 'https://git.parahub.io/user/login'

export const NAV_MENU: NavMenuEntry[] = [
  // Top nav (visible in navbar)
  { path: '/chat', labelKey: 'nav.messages' },
  { path: '/market', labelKey: 'nav.market' },
  { path: '/map', labelKey: 'nav.map' },
  { path: '/transit', labelKey: 'nav.transit' },

  // Dropdown: profile row
  { path: '/u/', inDropdown: true }, // dynamic — drag label resolved from display_name
  { path: '/wallet', activeIcon: Wallet, labelKey: 'nav.wallet', inDropdown: true },
  { path: '/profile', activeIcon: Settings, labelKey: 'zenith.settings', inDropdown: true },

  // Dropdown: bento grid rows 2-4 (visual order, rows are NOT thematic groups)
  { path: '/events', activeIcon: Calendar, labelKey: 'nav.events', inDropdown: true },
  { path: '/directory', activeIcon: Book, labelKey: 'nav.directory', inDropdown: true },
  { path: '/governance/polls', iconPrefix: '/governance', activeIcon: Vote, labelKey: 'nav.governance', inDropdown: true },
  { path: '/iot', activeIcon: Package, labelKey: 'nav.iot', inDropdown: true },
  { path: '/ads', activeIcon: Megaphone, labelKey: 'nav.ads', inDropdown: true },
  { path: '/contracts', activeIcon: FileText, labelKey: 'nav.contracts', inDropdown: true },
  { path: '/shipments', activeIcon: PackageCheck, labelKey: 'nav.shipments', inDropdown: true },
  { path: '/condo', activeIcon: Building, labelKey: 'nav.condo', inDropdown: true },
  { path: '/sos', activeIcon: Shield, labelKey: 'parasos.title', inDropdown: true },
  { path: '/energy', activeIcon: Zap, labelKey: 'nav.energy', inDropdown: true },
  { path: PROJECTS_URL, labelKey: 'nav.projects', inDropdown: true }, // external new-tab, no active-icon
  { path: '/webmail', labelKey: 'nav.webmail', inDropdown: true }, // internal new-tab, no active-icon

  // Dropdown: footer pills
  { path: '/about', activeIcon: Info, labelKey: 'about.title', inDropdown: true },
  { path: '/yellow-gate', activeIcon: Bot, inDropdown: true }, // "Hive" — no i18n key, not rendered in dropdown (Menu active-icon only)

  // Subpath-only (no navbar link of its own — lights Menu icon when user is on /transit/rides)
  { path: '/transit/rides', activeIcon: Car, labelKey: 'nav.rides' },
]

/** Path-prefix → active-icon for Menu-button active-state display. */
export function getMenuItemsMap(): Record<string, Component> {
  const out: Record<string, Component> = {}
  for (const e of NAV_MENU) {
    if (e.activeIcon) out[e.iconPrefix ?? e.path] = e.activeIcon
  }
  return out
}

/** Paths that live inside the dropdown (used by drag: keep menu open when hovering). */
export function getSubmenuPathPrefixes(): string[] {
  return NAV_MENU.filter(e => e.inDropdown).map(e => e.path)
}

/** Build drag-bar label lookup. Caller passes t() so i18n stays reactive. */
export function makeDragLabelLookup(t: (key: string) => string): Record<string, string> {
  const map: Record<string, string> = {}
  for (const e of NAV_MENU) {
    if (e.labelKey) map[e.path] = t(e.labelKey)
  }
  return map
}
