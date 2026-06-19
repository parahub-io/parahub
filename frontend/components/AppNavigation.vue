<template>
  <!-- Dev mode indicator bar -->
  <div v-if="isDevMode" class="fixed top-0 left-0 right-0 h-[2px] bg-primary z-[60]"></div>
  <!-- Scrim: dims the page behind the open site menu (navbar+menu stay bright at z-50).
       Sibling of <header> — its backdrop-filter creates a containing block, inset-0 inside would only cover the bar.
       Click lands outside siteMenuRef → handleClickOutside in useSiteMenu closes the menu. -->
  <div v-if="isSiteMenuOpen" class="fixed inset-0 z-40 bg-black/30 dark:bg-black/50"></div>
  <header class="fixed left-0 right-0 z-50 bg-neutral-100/95 dark:bg-neutral-800/95 backdrop-blur-sm safe-area-top" :class="isDevMode ? 'top-[2px]' : 'top-0'">
    <nav class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8" aria-label="Main navigation">
      <div class="flex items-center gap-1 md:gap-2 h-14 sm:h-16 md:h-20">
        <!-- Messages (authenticated) / Login (anonymous) -->
        <NavItem
          v-if="authStore.isAuthenticated"
          to="/chat"
          :icon="MessageCircle"
          :label="$t('nav.messages')"
          :aria-label="$t('nav.messages')"
          :badge="isFirstSyncCompleted ? unreadCount : null"
          :active="isPathActive('/chat')"
          :drag-hovered="isDragHovered('/chat', null)"
          @click="handleButtonClick('/chat', null, $event)"
          @touchstart="handleDragStart"
        />
        <NavItem
          v-else
          to="/login"
          :icon="Lock"
          :label="$t('login.submit')"
          :aria-label="$t('login.submit')"
          :active="isPathActive('/login')"
          :drag-hovered="isDragHovered('/login', null)"
          @click="handleButtonClick('/login', null, $event)"
          @touchstart="handleDragStart"
        />

        <!-- Market -->
        <NavItem
          to="/market"
          :icon="ShoppingBag"
          :label="$t('nav.market')"
          :aria-label="$t('nav.market')"
          :active="isPathActive('/market')"
          :drag-hovered="isDragHovered('/market', null)"
          @click="handleButtonClick('/market', null, $event)"
          @touchstart="handleDragStart"
        />

        <!-- Map -->
        <NavItem
          to="/map"
          :icon="Map"
          :label="$t('nav.map')"
          :aria-label="$t('nav.map')"
          :active="isPathActive('/map')"
          :drag-hovered="isDragHovered('/map', null)"
          @click="handleButtonClick('/map', null, $event)"
          @touchstart="handleDragStart"
        />

        <!-- Transit -->
        <NavItem
          to="/transit"
          :icon="Bus"
          :label="$t('nav.transit')"
          :aria-label="$t('nav.transit')"
          :active="isPathActive('/transit')"
          :drag-hovered="isDragHovered('/transit', null)"
          @click="handleButtonClick('/transit', null, $event)"
          @touchstart="handleDragStart"
        />

        <!-- Site Menu (kept inline: hover handlers, active-submenu icon swap, custom max-h) -->
        <div class="flex-1 relative" ref="siteMenuRef" @pointerenter="handleMenuHoverEnter" @pointerleave="handleMenuHoverLeave">
          <button
            :aria-label="$t('nav.menu')"
            :aria-expanded="isSiteMenuOpen"
            @click="handleButtonClick(null, 'site-menu', $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-action="site-menu"
            class="w-full h-full flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px] max-h-[44px] sm:max-h-none overflow-hidden"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isSiteMenuOpen || isMenuItemActive || isDragHovered(null, 'site-menu'),
              'text-neutral-700 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40': !isSiteMenuOpen && !isMenuItemActive && !isDragHovered(null, 'site-menu')
            }"
          >
            <Menu class="w-6 h-6 md:w-8 md:h-8 mb-0 sm:mb-1" />
            <component
              v-if="isMenuItemActive && activeMenuItem"
              :is="activeMenuItem"
              class="w-4 h-4 opacity-70"
            />
            <span v-else class="hidden sm:block text-xs font-medium">{{ $t('nav.menu') || 'Menu' }}</span>
          </button>

          <!-- Site Menu Dropdown -->
          <div
            v-if="isSiteMenuOpen"
            class="fixed w-[calc(100vw-2rem)] max-w-2xl bg-neutral-100 dark:bg-neutral-800 border border-t-0 border-neutral-300 dark:border-neutral-700 rounded-b-2xl z-50 shadow-2xl"
            :style="getSiteMenuStyle()"
            @click.stop
            @pointerenter="handleMenuHoverEnter"
            @pointerleave="handleMenuHoverLeave"
          >
            <div class="p-6 sm:p-[1.875rem] space-y-4 sm:space-y-5">

              <!-- Guest header (anon only — full-width button above the grid) -->
              <NuxtLink
                v-if="!authStore.isAuthenticated"
                :to="localePath('/login')"
                @click="isSiteMenuOpen = false"
                class="w-full btn-secondary gap-2 px-4 py-2.5 text-sm"
              >
                <Lock class="w-4 h-4" />
                {{ $t('auth.login') || 'Login / Register' }}
              </NuxtLink>

              <!-- === Account + navigation — bento grid (full width, aligns with footer pills) === -->
              <div class="grid grid-cols-4 gap-px rounded-xl overflow-hidden border border-neutral-300/70 dark:border-neutral-600/70 bg-neutral-300/70 dark:bg-neutral-600/70">
                  <!-- Profile row (authed): avatar+name (span 2) + wallet + settings -->
                  <template v-if="authStore.isAuthenticated">
                    <NuxtLink
                      :to="localePath(profilePath)"
                      @click="handleSubMenuClick(profilePath, $event)"
                      @touchstart="handleDragStart"
                      data-nav-button
                      :data-nav-path="profilePath"
                      class="col-span-2 flex items-center gap-3 px-3 py-2 min-h-[72px] overflow-hidden group"
                      :class="isDragHovered(profilePath, null)
                        ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                        : 'bg-neutral-100 dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                    >
                      <div class="w-10 h-10 rounded-full overflow-hidden flex-shrink-0">
                        <img v-if="avatarUrl" :src="avatarUrl" :alt="avatarInitials" class="w-full h-full object-cover" />
                        <div v-else class="w-full h-full bg-neutral-300 dark:bg-neutral-600 flex items-center justify-center">
                          <span class="text-sm font-bold text-neutral-700 dark:text-neutral-300">{{ avatarInitials }}</span>
                        </div>
                      </div>
                      <div class="flex-1 min-w-0">
                        <div class="font-semibold text-sm text-neutral-900 dark:text-neutral-100 truncate">
                          {{ authStore.activeProfile?.display_name || authStore.user?.profile?.display_name }}
                        </div>
                        <div class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                          {{ authStore.activeProfile?.hna || authStore.user?.profile?.hna }}
                        </div>
                      </div>
                    </NuxtLink>
                    <NavItem
                      to="/wallet"
                      :icon="Wallet"
                      :label="$t('nav.wallet') || 'Wallet'"
                      size="grid"
                      flush
                      :active="isPathActive('/wallet')"
                      :drag-hovered="isDragHovered('/wallet', null)"
                      @click="handleSubMenuClick('/wallet', $event)"
                      @touchstart="handleDragStart"
                    />
                    <NavItem
                      to="/profile"
                      :icon="Settings"
                      :label="$t('zenith.settings')"
                      size="grid"
                      flush
                      :active="isPathActive('/profile')"
                      :drag-hovered="isDragHovered('/profile', null)"
                      @click="handleSubMenuClick('/profile', $event)"
                      @touchstart="handleDragStart"
                    />
                  </template>
                  <!-- Community -->
                  <NavItem
                    to="/events"
                    :icon="Calendar"
                    :label="$t('nav.events') || 'Events'"
                    size="grid"
                    flush
                    :active="isPathActive('/events')"
                    :drag-hovered="isDragHovered('/events', null)"
                    @click="handleSubMenuClick('/events', $event)"
                    @touchstart="handleDragStart"
                  />
                  <NavItem
                    to="/directory"
                    :icon="Book"
                    :label="$t('nav.directory') || 'Directory'"
                    size="grid"
                    flush
                    :active="isPathActive('/directory')"
                    :drag-hovered="isDragHovered('/directory', null)"
                    @click="handleSubMenuClick('/directory', $event)"
                    @touchstart="handleDragStart"
                  />
                  <NavItem
                    to="/governance/polls"
                    :icon="Vote"
                    :label="$t('nav.governance') || 'Governance'"
                    size="grid"
                    flush
                    :active="isPathActive('/governance/polls')"
                    :drag-hovered="isDragHovered('/governance/polls', null)"
                    @click="handleSubMenuClick('/governance/polls', $event)"
                    @touchstart="handleDragStart"
                  />
                  <NavItem
                    v-if="authStore.isAuthenticated"
                    to="/iot"
                    :icon="Cpu"
                    :label="$t('nav.iot') || 'Devices'"
                    size="grid"
                    flush
                    :active="isPathActive('/iot')"
                    :drag-hovered="isDragHovered('/iot', null)"
                    @click="handleSubMenuClick('/iot', $event)"
                    @touchstart="handleDragStart"
                  />
                  <!-- anon: filler keeps the Community row rectangular -->
                  <div v-else class="bg-neutral-100 dark:bg-neutral-800"></div>

                  <!-- Deals + Operations (auth-only) -->
                  <template v-if="authStore.isAuthenticated">
                    <NavItem
                      to="/ads"
                      :icon="Megaphone"
                      :label="$t('nav.ads') || 'Ads'"
                      size="grid"
                      flush
                      :badge="adsFeedCount"
                      :active="isPathActive('/ads')"
                      :drag-hovered="isDragHovered('/ads', null)"
                      @click="handleSubMenuClick('/ads', $event)"
                      @touchstart="handleDragStart"
                    />
                    <NavItem
                      to="/contracts"
                      :icon="FileText"
                      :label="$t('nav.contracts') || 'Contracts'"
                      size="grid"
                      flush
                      :active="isPathActive('/contracts')"
                      :drag-hovered="isDragHovered('/contracts', null)"
                      @click="handleSubMenuClick('/contracts', $event)"
                      @touchstart="handleDragStart"
                    />
                    <NavItem
                      to="/shipments"
                      :icon="PackageCheck"
                      :label="$t('nav.shipments') || 'Shipping'"
                      size="grid"
                      flush
                      :active="isPathActive('/shipments')"
                      :drag-hovered="isDragHovered('/shipments', null)"
                      @click="handleSubMenuClick('/shipments', $event)"
                      @touchstart="handleDragStart"
                    />
                    <NavItem
                      to="/condo"
                      :icon="Building"
                      :label="$t('nav.condo') || 'Condo'"
                      size="grid"
                      flush
                      :active="isPathActive('/condo')"
                      :drag-hovered="isDragHovered('/condo', null)"
                      @click="handleSubMenuClick('/condo', $event)"
                      @touchstart="handleDragStart"
                    />

                    <NavItem
                      to="/sos"
                      :icon="Shield"
                      label="SOS"
                      size="grid"
                      flush
                      variant="sos"
                      :active="isPathActive('/sos')"
                      :drag-hovered="isDragHovered('/sos', null)"
                      @click="handleSubMenuClick('/sos', $event)"
                      @touchstart="handleDragStart"
                    />
                    <NavItem
                      to="/energy"
                      :icon="Sun"
                      :label="$t('nav.energy') || 'Energy'"
                      size="grid"
                      flush
                      :active="isPathActive('/energy')"
                      :drag-hovered="isDragHovered('/energy', null)"
                      @click="handleSubMenuClick('/energy', $event)"
                      @touchstart="handleDragStart"
                    />

                    <!-- Projects (external, kept inline: new-tab <a>; drop-target key = full URL) -->
                    <a
                      :href="PROJECTS_URL"
                      target="_blank"
                      rel="noopener noreferrer"
                      data-nav-button
                      :data-nav-path="PROJECTS_URL"
                      @click="handleSubMenuClick(PROJECTS_URL, $event)"
                      @touchstart="handleDragStart"
                      class="flex flex-col items-center justify-center group cursor-pointer py-2 aspect-[1.618] min-h-[72px] w-full relative overflow-hidden min-w-0"
                      :class="isDragHovered(PROJECTS_URL, null)
                        ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                        : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                    >
                      <ExternalLink class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
                      <FolderGit class="w-8 h-8 sm:w-10 sm:h-10 mb-1" />
                      <span class="block text-xs font-medium text-center max-w-full truncate px-0.5">{{ $t('nav.projects') || 'Projects' }}</span>
                    </a>

                    <!-- Webmail (internal but opens new tab, kept inline: NavItem has no internal+new-tab combo) -->
                    <NuxtLink
                      :to="localePath('/webmail')"
                      target="_blank"
                      rel="noopener noreferrer"
                      data-nav-button
                      data-nav-path="/webmail"
                      @click="handleSubMenuClick('/webmail', $event)"
                      @touchstart="handleDragStart"
                      class="flex flex-col items-center justify-center group cursor-pointer py-2 aspect-[1.618] min-h-[72px] w-full relative overflow-hidden min-w-0"
                      :class="isDragHovered('/webmail', null)
                        ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                        : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                    >
                      <ExternalLink class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
                      <Mail class="w-8 h-8 sm:w-10 sm:h-10 mb-1" />
                      <span class="block text-xs font-medium text-center max-w-full truncate px-0.5">{{ $t('nav.webmail') || 'Webmail' }}</span>
                    </NuxtLink>
                  </template>
                </div>

              <!-- === Footer: equal-width meta-action pills — About + Invite + Logout === -->
              <div class="flex items-center gap-1 sm:gap-1.5">
                <NavItem
                  to="/about"
                  :icon="Rocket"
                  :label="$t('about.title') || 'About'"
                  size="footer"
                  :active="isPathActive('/about')"
                  :drag-hovered="isDragHovered('/about', null)"
                  @click="handleSubMenuClick('/about', $event)"
                  @touchstart="handleDragStart"
                />

                <!-- Invite (custom handler; neutral pill like About/Logout) -->
                <button
                  v-if="authStore.isAuthenticated"
                  @click="openInviteModal"
                  @touchstart="handleDragStart"
                  data-nav-button
                  data-nav-action="invite"
                  class="flex flex-1 items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors"
                  :class="isDragHovered(null, 'invite')
                    ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                    : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                >
                  <UserPlus class="w-3.5 h-3.5" />
                  <span class="hidden sm:inline">{{ $t('nav.invite') }}</span>
                </button>

                <!-- Logout (two-tap state, custom neutral styling) -->
                <button
                  v-if="authStore.isAuthenticated"
                  @click="handleLogout"
                  @touchstart="handleDragStart"
                  data-nav-button
                  data-nav-action="logout"
                  class="flex flex-1 items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all"
                  :class="logoutConfirmPending
                    ? 'bg-error text-white'
                    : isDragHovered(null, 'logout')
                      ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                      : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                >
                  <LogOut class="w-3.5 h-3.5" />
                  <!-- label hidden on phones; the confirm prompt is forced visible so the two-tap state is never silent -->
                  <span :class="logoutConfirmPending ? 'inline' : 'hidden sm:inline'">{{ logoutConfirmPending ? ($t('profiles.logout_confirm') || 'Sure?') : ($t('profiles.logout') || 'Logout') }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </nav>
  </header>

  <!-- Drag hover label bar (bottom of screen) -->
  <Teleport to="body">
    <div
      v-if="isDragging && dragMoved && dragHoverLabel"
      class="fixed bottom-0 left-0 right-0 z-[100] pointer-events-none"
    >
      <div class="bg-primary py-3 flex items-center justify-center">
        <span class="text-lg font-bold text-neutral-900">{{ dragHoverLabel }}</span>
      </div>
    </div>
  </Teleport>

  <!-- Release Animation Beam (independent, teleported to body) -->
  <Teleport to="body">
    <div
      v-if="releaseAnimation && releaseTarget"
      class="fixed z-[100] pointer-events-none"
      :style="getBeamPosition()"
    >
      <div
        class="transition-all duration-300 ease-out"
        :class="beamAnimating ? '' : 'rounded-full'"
        :style="beamAnimating ? getBeamStyle() : `background-color: ${beamColor}; width: 12px; height: 12px; opacity: 1;`"
      ></div>
    </div>
  </Teleport>

  <InviteModal v-model="showInviteModal" />

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { MessageCircle, ShoppingBag, Map, Megaphone, Menu, Book, Settings, FileText, PackageCheck, FolderGit, Wallet, Shield, LogOut, Lock, Vote, Rocket, Calendar, UserPlus, Bus, Mail, ExternalLink, Sun, Building, Cpu } from 'lucide-vue-next'
import { useMatrixUnread } from '~/composables/useMatrixUnread'
import { getMenuItemsMap, getSubmenuPathPrefixes, makeDragLabelLookup, PROJECTS_URL } from '~/components/nav/navMenu'

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// Locale-aware path matching: strips locale prefix before comparison
function isPathActive(base: string): boolean {
  const routeName = route.name?.toString() || ''
  // @nuxtjs/i18n adds ___locale suffix to route names
  const baseName = routeName.replace(/___[a-z]{2}$/, '')
  // Convert base path to expected route name pattern
  const expectedBase = base.replace(/^\//, '').replace(/\//g, '-') || 'index'
  return baseName === expectedBase || baseName.startsWith(expectedBase + '-')
}

// Dev mode indicator (yellow bar at top). useCookie reads the cookie during SSR
// too, so the bar and the 2px header offset are in the server HTML — reading
// document.cookie in onMounted made them pop in after hydration.
// Raw decode: default decode destr's '1' into a number (see PreferencesSection).
const devModeCookie = useCookie('parahub_dev', {
  decode: (v: string) => v ? decodeURIComponent(v) : v
})
const isDevMode = computed(() => devModeCookie.value === '1')

// Matrix unread counter (global service)
const { totalUnreadCount, isFirstSyncCompleted, initialize, cleanup } = useMatrixUnread()
const unreadCount = totalUnreadCount // Use the ref directly

// Ads feed count (available unviewed ads, updated via WS)
const { feedCount: adsFeedCount, loadFeedCount: loadAdsFeedCount } = useAdsState()
const realtimeStore = useRealtimeStore()

// Invite modal: all state, API, QR generation live in <InviteModal>
const showInviteModal = ref(false)
function openInviteModal() {
  isSiteMenuOpen.value = false
  showInviteModal.value = true
}

// Site menu: hover-open/close, click-outside, ESC
const siteMenuRef = ref<HTMLElement | null>(null)
const {
  isOpen: isSiteMenuOpen,
  cancelHoverOpen,
  handleHoverEnter: handleMenuHoverEnter,
  handleHoverLeave: handleMenuHoverLeave,
  toggle: toggleSiteMenu,
} = useSiteMenu(siteMenuRef)

// Active-icon lookup for Menu button (single source: components/nav/navMenu.ts)
const menuItemsMap = getMenuItemsMap()

const activeMenuItem = computed(() => {
  for (const [pathPrefix, icon] of Object.entries(menuItemsMap)) {
    if (isPathActive(pathPrefix)) {
      return icon
    }
  }
  return null
})

// Check if any menu item is active
const isMenuItemActive = computed(() => {
  return activeMenuItem.value !== null
})

// Compute avatar initials
const avatarInitials = computed(() => {
  if (!authStore.isAuthenticated) {
    return '?'
  }
  const name = authStore.activeProfile?.display_name || authStore.user?.profile?.display_name || 'User'
  const parts = name.split(' ')
  if (parts.length >= 2) {
    return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
  }
  return name.substring(0, 2).toUpperCase()
})

// Compute avatar URL (use profile photo if available)
// Note: activeProfile doesn't include avatar_url, so we get it from user.profile
const avatarUrl = computed(() => {
  return authStore.user?.profile?.avatar_url || null
})

// Compute profile path for drag navigation
const profilePath = computed(() => {
  const hna = authStore.activeProfile?.hna || authStore.user?.profile?.hna
  if (!hna) return '/profile'
  return `/u/${hna.split('@')[0]}`
})

// Handle logout (two-tap confirm)
const logoutConfirmPending = ref(false)
let logoutConfirmTimer: ReturnType<typeof setTimeout> | null = null

async function handleLogout() {
  if (!logoutConfirmPending.value) {
    logoutConfirmPending.value = true
    logoutConfirmTimer = setTimeout(() => {
      logoutConfirmPending.value = false
      logoutConfirmTimer = null
    }, 3000)
    return
  }
  if (logoutConfirmTimer) clearTimeout(logoutConfirmTimer)
  logoutConfirmPending.value = false
  isSiteMenuOpen.value = false
  try {
    await authStore.logout()
  } catch (error) {
    console.error('Logout error:', error)
  }
  // Hard redirect ensures fresh SSR render with anonymous state
  window.location.href = '/'
}

// Touch drag selection (mobile): press → drag → release. Visual effects
// (hover highlight, bottom label bar, release beam) live in the composable.
const dragLabels = makeDragLabelLookup(t)

const {
  isDragging,
  dragMoved,
  dragHoverLabel,
  releaseAnimation,
  releaseTarget,
  beamAnimating,
  handleDragStart,
  isDragHovered,
  getBeamPosition,
  getBeamStyle,
} = useNavDragSelect({
  isSiteMenuOpen,
  cancelHoverOpen,
  submenuPathPrefixes: getSubmenuPathPrefixes(),
  onSelectPath: (path) => {
    // New-tab targets (Projects = external URL, Webmail = internal redirect page)
    if (path.startsWith('http')) {
      window.open(path, '_blank', 'noopener,noreferrer')
    } else if (path === '/webmail') {
      window.open(localePath(path), '_blank', 'noopener,noreferrer')
    } else {
      router.push(localePath(path))
    }
    isSiteMenuOpen.value = false
  },
  onSelectAction: (action) => {
    if (action === 'site-menu') toggleSiteMenu()
    else if (action === 'logout') handleLogout()
    else if (action === 'invite') openInviteModal()
  },
  resolveLabel: (path, action) => {
    if (action === 'site-menu') return t('nav.menu')
    if (action === 'logout') return t('profiles.logout')
    if (action === 'invite') return t('nav.invite')
    if (!path) return null
    if (path.startsWith('/u/')) {
      return authStore.activeProfile?.display_name || authStore.user?.profile?.display_name || 'Profile'
    }
    return dragLabels[path] || null
  },
})

onMounted(() => {
  // Initialize Matrix unread counter if user is authenticated
  if (authStore.isAuthenticated) {
    initialize()
    loadAdsFeedCount()
    realtimeStore.connect()
  }
})

// Watch for auth changes and initialize when user logs in
watch(() => authStore.isAuthenticated, (isAuth) => {
  if (isAuth) {
    initialize()
    loadAdsFeedCount()
    realtimeStore.connect()
  } else {
    cleanup()
  }
})

onUnmounted(() => {
  // Don't cleanup Matrix — keep service running for other components
  // cleanup()
})

// Handle navigation click - toggle between section and dashboard
function handleNavClick(path: string) {
  // Check if clicking on currently active section
  const active = isPathActive(path)

  if (active) {
    // "Unpress" - go back to dashboard
    router.push(localePath('/'))
  } else {
    // Navigate to the section
    router.push(localePath(path))
  }
}

// Handle button click - check if it was a drag or a normal click
function handleButtonClick(path: string | null, action: string | null, event: MouseEvent) {
  // If drag happened, prevent normal click behavior
  if (dragMoved.value) {
    event.preventDefault()
    return
  }

  // Normal click behavior
  event.preventDefault()

  if (path) {
    handleNavClick(path)
  } else if (action === 'site-menu') {
    toggleSiteMenu()
  }
}

// Handle submenu item click (from Site Menu)
function handleSubMenuClick(path: string, event: MouseEvent) {
  // If drag happened, prevent normal click behavior
  if (dragMoved.value) {
    event.preventDefault()
    return
  }

  // Normal click - let NuxtLink handle navigation
  // Close site menu after navigation
  isSiteMenuOpen.value = false
}

// Position the dropdown directly below the navbar, right edge aligned with the Menu button
function getSiteMenuStyle(): string {
  if (!process.client) return ''

  const header = document.querySelector('header')
  const top = header ? header.getBoundingClientRect().bottom - 2 : 56 // overlap 2px to kill sub-pixel gap

  // align the panel's right edge with the Menu button's right edge (siteMenuRef wraps the button)
  let right = 16 // fallback ≈ navbar px-4
  if (siteMenuRef.value) {
    right = Math.max(0, Math.round(window.innerWidth - siteMenuRef.value.getBoundingClientRect().right))
  }
  return `top: ${top}px; right: ${right}px;`
}
</script>
