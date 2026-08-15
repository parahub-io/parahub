<template>
  <!-- Dev mode indicator bar -->
  <div v-if="isDevMode" class="fixed top-0 left-0 right-0 h-[2px] bg-primary z-[60]"></div>
  <!-- Scrim: dims the page behind the open site menu (navbar+menu stay bright at z-50).
       Sibling of <header> — its backdrop-filter creates a containing block, inset-0 inside would only cover the bar.
       Click lands outside siteMenuRef → handleClickOutside in useSiteMenu closes the menu. -->
  <div v-if="isSiteMenuOpen" class="fixed inset-0 z-40 bg-black/30 dark:bg-black/50"></div>
  <!-- Docks to the thumb on phones (bottom edge), to the top on md+ pointer
       devices. Insets for both modes live in main.css § Navigation dock insets. -->
  <header class="nav-dock fixed left-0 right-0 bottom-0 md:bottom-auto z-50 bg-neutral-100/95 dark:bg-neutral-800/95 backdrop-blur-sm nav-bar-safe" :class="isDevMode ? 'md:top-[2px]' : 'md:top-0'">
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

        <!-- Transit — icon/label/target follow the last-opened section (bus ⇄ rides) -->
        <NavItem
          :to="transitTarget"
          :icon="transitSection === 'rides' ? Car : BusFront"
          :label="$t(transitSection === 'rides' ? 'nav.rides' : 'nav.transit')"
          :aria-label="$t(transitSection === 'rides' ? 'nav.rides' : 'nav.transit')"
          :active="isPathActive('/transit')"
          :drag-hovered="isDragHovered(transitTarget, null)"
          @click="handleButtonClick(transitTarget, null, $event)"
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
            <!-- Unread badge (notifications + mail) bubbles up here (kept inside the button bounds — the button is overflow-hidden, a corner-overflowing badge would be clipped) -->
            <span
              v-if="menuBadgeTotal > 0"
              class="absolute top-1 right-1 min-w-[18px] h-[18px] bg-error text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1"
              :aria-label="$t('nav.notifications') || 'Notifications'"
            >{{ menuBadgeTotal > 99 ? '99+' : menuBadgeTotal }}</span>
            <!-- Claimable-reward pill: yellow Zap chip = the FeedCard reward language
                 (money, not a count), opposite corner so it never collides with the
                 red unread badge (distinct by position AND meaning) -->
            <!-- Phones: Zap-only 18px coin (a wider amount pill would cover the
                 hamburger in the 44px dock button; the exact total sits on the
                 ads tile one tap away). sm+: full amount pill. -->
            <span
              v-if="adsFeedRewardSats > 0"
              class="absolute top-1 left-1 flex items-center justify-center gap-0.5 h-[18px] w-[18px] sm:w-auto sm:justify-start sm:px-1.5 rounded-full bg-primary text-neutral-900 text-[10px] font-bold tabular-nums ring-2 ring-neutral-100 dark:ring-neutral-800"
              :class="{ 'reward-ping': adsPing }"
              :aria-label="$t('nav.ads') || 'Ads'"
            ><Zap class="w-2.5 h-2.5 fill-current shrink-0" /><span class="hidden sm:inline">{{ adsRewardLabel }}</span></span>
          </button>

          <!-- Site Menu panel — unfolds away from whichever edge the bar is
               docked to: upward and full-bleed on phones (positioned by CSS,
               see .site-menu-panel), downward as a card on md+ (positioned by
               getSiteMenuStyle, which aligns it with the Menu button). -->
          <div
            v-if="isSiteMenuOpen"
            class="site-menu-panel fixed bottom-full left-0 right-0 md:bottom-auto md:left-auto md:right-auto md:w-[calc(100vw-2rem)] md:max-w-2xl bg-neutral-100/95 dark:bg-neutral-800/95 backdrop-blur-sm border-t md:border md:border-t-0 border-neutral-300 dark:border-neutral-700 md:rounded-b-2xl z-50 shadow-2xl"
            :style="getSiteMenuStyle()"
            @click.stop
            @pointerenter="handleMenuHoverEnter"
            @pointerleave="handleMenuHoverLeave"
          >
            <div class="p-2 sm:p-[1.875rem] space-y-3 sm:space-y-5">

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

              <!-- === Account + navigation — bento grid + footer pills = one reticle matrix === -->
              <!-- Wrapper spans grid AND footer row; it carries the reticle ticks and the
                   hover/drag tracking that positions them (see setCrossFromEl) -->
              <div class="relative" ref="bentoRef" @mouseover="handleBentoHover" @mouseleave="bentoCross = null">
              <div ref="gridRef" class="grid grid-cols-4 gap-px rounded-xl overflow-hidden border border-neutral-300/70 dark:border-neutral-600/70 bg-neutral-300/70 dark:bg-neutral-600/70">
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
                      :reward-sats="adsFeedRewardSats"
                      :reward-ping="adsPing"
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
                      <div v-if="mailUnread > 0" class="relative">
                        <Mail class="w-8 h-8 sm:w-10 sm:h-10 mb-1" />
                        <div class="absolute -top-1 -right-1 min-w-[16px] h-[16px] bg-error text-white text-[10px] font-bold rounded-full flex items-center justify-center px-0.5 ring-2 ring-neutral-100 dark:ring-neutral-800">
                          {{ mailUnread > 99 ? '99+' : mailUnread }}
                        </div>
                      </div>
                      <Mail v-else class="w-8 h-8 sm:w-10 sm:h-10 mb-1" />
                      <span class="block text-xs font-medium text-center max-w-full truncate px-0.5">{{ $t('nav.webmail') || 'Webmail' }}</span>
                    </NuxtLink>
                  </template>
                </div>

              <!-- === Footer: equal-width meta-action pills — About + Alerts + Invite + Logout === -->
              <div ref="footerRowRef" class="flex items-center gap-1 sm:gap-1.5 mt-3 sm:mt-5">
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

                <!-- Notifications feed — bell + unread badge (real-time alerting is the toast; this is the catch-up history) -->
                <NavItem
                  v-if="authStore.isAuthenticated"
                  to="/notifications"
                  :icon="Bell"
                  :label="$t('nav.notifications') || 'Alerts'"
                  size="footer"
                  :badge="notifUnread > 0 ? notifUnread : null"
                  :active="isPathActive('/notifications')"
                  :drag-hovered="isDragHovered('/notifications', null)"
                  @click="handleSubMenuClick('/notifications', $event)"
                  @touchstart="handleDragStart"
                />

                <!-- People: the way to any person — partners on open, anyone else
                     one query away. A pill, not a row of faces: the matrix keeps
                     the same geometry whatever the partner count is, and it lives
                     inside the reticle like every other action here. -->
                <button
                  v-if="authStore.isAuthenticated"
                  @click="openPeoplePicker"
                  @touchstart="handleDragStart"
                  data-nav-button
                  data-nav-action="people"
                  class="flex flex-1 items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors"
                  :class="isDragHovered(null, 'people')
                    ? 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900'
                    : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40'"
                >
                  <UserSearch class="w-3.5 h-3.5" />
                  <span class="hidden sm:inline">{{ $t('nav.find_person') }}</span>
                </button>

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

                <!-- Reticle ticks: perpendicular to the hovered zone's edges (grid OR
                     footer row — each has its own frame), pointing outward; their virtual
                     extensions cross at the targeted button's center.
                     Indigo in light theme (yellow washes out there), brand yellow in dark. -->
                <template v-if="bentoCross">
                  <span class="absolute h-px bg-secondary dark:bg-primary pointer-events-none" :style="{ left: `${bentoCross.left - CROSS_TICK}px`, top: `${bentoCross.y - 0.5}px`, width: `${CROSS_TICK}px` }"></span>
                  <span class="absolute h-px bg-secondary dark:bg-primary pointer-events-none" :style="{ left: `${bentoCross.right}px`, top: `${bentoCross.y - 0.5}px`, width: `${CROSS_TICK}px` }"></span>
                  <span class="absolute w-px bg-secondary dark:bg-primary pointer-events-none" :style="{ top: `${bentoCross.top - CROSS_TICK}px`, left: `${bentoCross.x - 0.5}px`, height: `${CROSS_TICK}px` }"></span>
                  <span class="absolute w-px bg-secondary dark:bg-primary pointer-events-none" :style="{ top: `${bentoCross.bottom}px`, left: `${bentoCross.x - 0.5}px`, height: `${CROSS_TICK}px` }"></span>
                </template>
              </div>

              <!-- Google Play — the one install path offered here. The direct APK
                   lives on /about: it stays available for anyone who wants no Google
                   account, but it is not the route to hand a first-time visitor.
                   Never shown inside the native shell: a store build pointing at an
                   install path is a Play policy risk (see PK/capacitor-system.md). -->
              <a
                v-if="showStoreRow"
                href="https://play.google.com/store/apps/details?id=io.parahub.app"
                target="_blank"
                rel="noopener"
                @click="isSiteMenuOpen = false"
                class="flex w-full items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-neutral-200 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
              >
                <Store class="w-3.5 h-3.5" />
                {{ $t('nav.google_play') }}
              </a>

            </div>
          </div>
        </div>
      </div>
    </nav>
  </header>

  <!-- Drag hover label bar — always on the edge OPPOSITE the bar, i.e. away
       from the dragging thumb, which would otherwise cover the readout. -->
  <Teleport to="body">
    <div
      v-if="isDragging && dragMoved && dragHoverLabel"
      class="fixed top-0 md:top-auto md:bottom-0 left-0 right-0 z-[100] pointer-events-none"
    >
      <div class="drag-hover-bar bg-primary px-4 flex flex-col items-center justify-center text-neutral-900">
        <span
          v-if="dragHoverIconHtml"
          class="mb-1 [&>svg]:w-8 [&>svg]:h-8 [&>img]:w-8 [&>img]:h-8 [&>img]:rounded-full [&>img]:object-cover"
          v-html="dragHoverIconHtml"
        ></span>
        <span class="text-lg font-bold leading-tight">{{ dragHoverLabel }}</span>
        <span v-if="dragHoverHint" class="text-xs font-medium opacity-75 leading-tight text-center mt-0.5">{{ dragHoverHint }}</span>
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
  <UserPickerModal v-model="showPeoplePicker" @select="goToPerson" @invite="inviteFromPicker" />

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { MessageCircle, ShoppingBag, Map, Megaphone, Menu, Book, Settings, FileText, PackageCheck, FolderGit, Wallet, Shield, LogOut, Lock, Vote, Rocket, Calendar, UserPlus, BusFront, Car, Mail, ExternalLink, Sun, Building, Cpu, Bell, Store, Zap, UserSearch } from 'lucide-vue-next'
import { isNative, isIosWeb } from '~/utils/capacitor'
import { useMatrixUnread } from '~/composables/useMatrixUnread'
import { useNotifications } from '~/composables/useNotifications'
import { getMenuItemsMap, getSubmenuPathPrefixes, makeDragLabelLookup, makeDragHintLookup, PROJECTS_URL } from '~/components/nav/navMenu'

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// Locale-aware route-name (strips the ___locale suffix @nuxtjs/i18n appends)
function currentRouteName(): string {
  return (route.name?.toString() || '').replace(/___[a-z]{2}$/, '')
}

// Convert a base path to its expected route-name pattern (/market/my → market-my)
function routeNameFor(base: string): string {
  return base.replace(/^\//, '').replace(/\//g, '-') || 'index'
}

// Locale-aware path matching: true on the path itself or any of its subpaths
function isPathActive(base: string): boolean {
  const baseName = currentRouteName()
  const expectedBase = routeNameFor(base)
  return baseName === expectedBase || baseName.startsWith(expectedBase + '-')
}

// Exact match — the path itself, not its subpaths
function isExactPath(base: string): boolean {
  return currentRouteName() === routeNameFor(base)
}

// Transit nav button follows the last-opened section (public transit ⇄ shared
// rides): mode choice is sticky, so the button targets the user's tool
// directly and swaps icon/label to match. Visiting any transit route updates
// the memory (immediate: true also covers the SSR render, so direct /rides
// visits paint the Car icon without a hydration mismatch).
const { section: transitSection, remember: rememberTransitSection } = useTransitSection()
const transitTarget = computed(() => (transitSection.value === 'rides' ? '/transit/rides' : '/transit'))

watch(() => currentRouteName(), (name) => {
  if (name === 'transit-rides' || name.startsWith('transit-rides-')) rememberTransitSection('rides')
  else if (name === 'transit' || name.startsWith('transit-')) rememberTransitSection('transit')
}, { immediate: true })

// Dev mode indicator (yellow bar at top). useCookie reads the cookie during
// SSR too, so on per-request renders the bar and the 2px header offset are in
// the server HTML (no pop-in). But client-side useCookie reads document.cookie
// at setup — before hydration — while SWR-cached routes serve a cookie-less
// cached shell: hydrating straight from the cookie made the bar a guaranteed
// hydration mismatch for dev-cookie holders on every cached page. Hydrate
// from the payload value instead (always matches the served HTML), then
// reconcile with the live cookie after mount; on cached shells the bar pops
// in post-mount, which is the only honest option there.
// Raw decode: default decode destr's '1' into a number (see AdvancedPreferencesSection).
const devModeCookie = useCookie('parahub_dev', {
  decode: (v: string) => v ? decodeURIComponent(v) : v
})
const devModeHydrated = useState('dev-mode-bar', () => devModeCookie.value === '1')
onMounted(() => { devModeHydrated.value = devModeCookie.value === '1' })
const isDevMode = computed(() => devModeHydrated.value)

// The store row is only for someone who can act on it: not the native shell
// (already installed), and not iOS (there is no iOS build — /about states the
// platform situation instead). Both checks need the client, so resolve after
// mount and let SSR agree with the first client render; the menu is `v-if`-gated
// behind a user click, so the row is never mid-flight when this settles.
const showStoreRow = ref(false)
onMounted(() => { showStoreRow.value = !isNative() && !isIosWeb() })

// Matrix unread counter (global service)
const { totalUnreadCount, isFirstSyncCompleted, initialize, cleanup } = useMatrixUnread()
const unreadCount = totalUnreadCount // Use the ref directly

// In-app notification feed — unread count drives the bell badge
const {
  unreadCount: notifUnread,
  init: initNotifications,
  cleanup: cleanupNotifications,
} = useNotifications()

// Webmail unseen count — badge on the menu tile; bubbles up to the menu
// button together with the notifications count (both live inside the menu)
const { unseenCount: mailUnread, refresh: refreshMailUnread, reset: resetMailUnread } = useMailUnread()
const menuBadgeTotal = computed(() => notifUnread.value + mailUnread.value)

// Ads claimable-reward total (sats across unviewed ads, updated via WS)
const { feedRewardSats: adsFeedRewardSats, feedRewardPulse: adsFeedRewardPulse, loadFeedCount: loadAdsFeedCount } = useAdsState()
const adsRewardLabel = computed(() =>
  adsFeedRewardSats.value >= 10000 ? `${Math.floor(adsFeedRewardSats.value / 1000)}k` : String(adsFeedRewardSats.value))
// One-shot ping when a live refetch raises the claimable total (page-load
// fetches don't bump the pulse — see useAdsState)
const adsPing = ref(false)
let adsPingTimer: ReturnType<typeof setTimeout> | null = null
watch(adsFeedRewardPulse, () => {
  adsPing.value = false
  requestAnimationFrame(() => { adsPing.value = true })
  if (adsPingTimer) clearTimeout(adsPingTimer)
  adsPingTimer = setTimeout(() => { adsPing.value = false }, 800)
})
// Browser-paid ad payouts: pays queued rewards from this account's wallet
// (WS-triggered + one post-login sweep). No-op unless work is queued.
const { init: initAdsPayer, cleanup: cleanupAdsPayer } = useAdsPayer()
const realtimeStore = useRealtimeStore()

// Invite modal: all state, API, QR generation live in <InviteModal>
const showInviteModal = ref(false)
function openInviteModal() {
  isSiteMenuOpen.value = false
  showInviteModal.value = true
}

// People picker: partners when it opens, anyone else one query away. It only
// ever LEADS to `/@name` — the profile console is the single place where
// anything is done to a person. Nothing is fetched until it is opened.
const showPeoplePicker = ref(false)
function openPeoplePicker() {
  isSiteMenuOpen.value = false
  showPeoplePicker.value = true
}
// "Nobody found → invite them": the picker's empty state hands the invite back
// here. One overlay closes before the next opens — <Modal>'s close cleanup
// (body scroll, Esc trap) is global state, and watcher order across two
// instances is mount order, not call order, so a same-tick swap is a coin flip.
async function inviteFromPicker() {
  showPeoplePicker.value = false
  await nextTick()
  showInviteModal.value = true
}

function goToPerson(person: { hna: string }) {
  const localName = (person.hna || '').split('@')[0]
  if (localName) navigateTo(localePath(`/@${localName}`))
}

// Virtual keyboard tracking — collapses the bottom dock while typing
useVirtualKeyboard()

// Site menu: hover-open/close, click-outside, ESC
const siteMenuRef = ref<HTMLElement | null>(null)
const {
  isOpen: isSiteMenuOpen,
  cancelHoverOpen,
  handleHoverEnter: handleMenuHoverEnter,
  handleHoverLeave: handleMenuHoverLeave,
  toggle: toggleSiteMenu,
} = useSiteMenu(siteMenuRef)

// Reticle crosshair over the menu: two independent frames — the bento grid
// and the footer pill row each get their own reticle, ticks hugging that
// zone's edges (so footer hovers flip the top ticks down to just above the
// row). Driven by mouse hover AND by the touch drag-select gesture.
const CROSS_TICK = 5 // tick length in px; thickness is 1px (matches the frame border)
const bentoRef = ref<HTMLElement | null>(null)
const gridRef = ref<HTMLElement | null>(null)
const footerRowRef = ref<HTMLElement | null>(null)
// x/y = target center; left/right/top/bottom = the hovered zone's edges (wrapper coords)
const bentoCross = ref<{ x: number; y: number; left: number; right: number; top: number; bottom: number } | null>(null)

function setCrossFromEl(el: HTMLElement) {
  if (!bentoRef.value) return
  const zoneEl = gridRef.value?.contains(el) ? gridRef.value
    : footerRowRef.value?.contains(el) ? footerRowRef.value : null
  if (!zoneEl) return
  const wrap = bentoRef.value.getBoundingClientRect()
  const zone = zoneEl.getBoundingClientRect()
  const rect = el.getBoundingClientRect()
  bentoCross.value = {
    x: rect.left - wrap.left + rect.width / 2,
    y: rect.top - wrap.top + rect.height / 2,
    left: zone.left - wrap.left,
    right: zone.right - wrap.left,
    top: zone.top - wrap.top,
    bottom: zone.bottom - wrap.top,
  }
}

function handleBentoHover(e: MouseEvent) {
  const cell = (e.target as HTMLElement).closest?.('[data-nav-button]') as HTMLElement | null
  // Ignore hovers over the 1px gap hairlines — keep the last position, clear only on frame leave
  if (!cell || !bentoRef.value?.contains(cell)) return
  setCrossFromEl(cell)
}

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
  return `/@${hna.split('@')[0]}`
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
  window.location.href = localePath('/')
}

// Touch drag selection (mobile): press → drag → release. Visual effects
// (hover highlight, bottom label bar, release beam) live in the composable.
const dragLabels = makeDragLabelLookup(t)

const {
  isDragging,
  dragMoved,
  dragHoverLabel,
  currentHoverTarget,
  releaseAnimation,
  releaseTarget,
  beamAnimating,
  handleDragStart,
  isDragHovered,
  getBeamPosition,
  getBeamStyle,
  hapticSelect,
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
    else if (action === 'people') openPeoplePicker()
  },
  resolveLabel: (path, action) => {
    if (action === 'site-menu') return t('nav.menu')
    if (action === 'logout') return t('profiles.logout')
    if (action === 'invite') return t('nav.invite')
    if (action === 'people') return t('nav.find_person')
    if (!path) return null
    if (path.startsWith('/@')) {
      return authStore.activeProfile?.display_name || authStore.user?.profile?.display_name || 'Profile'
    }
    return dragLabels[path] || null
  },
})

// Touch drag drives the same reticle: follow the dragged-over button while it
// is inside the menu matrix, clear as soon as the drag leaves it or ends
watch(currentHoverTarget, (el) => {
  if (el && bentoRef.value?.contains(el)) setCrossFromEl(el)
  else bentoCross.value = null
})

// Drag-bar teaser line for the hovered target
const dragHints = makeDragHintLookup(t)
const dragHoverHint = computed(() => {
  if (!isDragging.value || !dragMoved.value || !currentHoverTarget.value) return null
  const action = currentHoverTarget.value.getAttribute('data-nav-action')
  if (action) return t(`nav.hint.${action === 'site-menu' ? 'menu' : action}`)
  const path = currentHoverTarget.value.getAttribute('data-nav-path')
  if (!path) return null
  if (path.startsWith('/@')) return dragHints['/@']
  return dragHints[path] || null
})

// Drag-bar icon: clone the hovered button's own graphic (lucide svg, or the
// avatar img on the profile tile) — no icon map to keep in sync. Corner
// ExternalLink minis are skipped via :not(.absolute).
const dragHoverIconHtml = computed(() => {
  if (!isDragging.value || !dragMoved.value || !currentHoverTarget.value) return null
  const gfx = currentHoverTarget.value.querySelector('svg:not(.absolute), img')
  return gfx ? gfx.outerHTML : null
})

// Returning from the webmail tab (or Custom Tab in the native app): the SSO
// credentials endpoint drops the server-side count cache on webmail entry, so
// this refetch gets a fresh IMAP count and the badge clears right away
const refreshMailOnVisible = () => {
  if (document.visibilityState === 'visible') refreshMailUnread()
}

onMounted(() => {
  // Initialize Matrix unread counter if user is authenticated
  if (authStore.isAuthenticated) {
    initialize()
    loadAdsFeedCount()
    realtimeStore.connect()
    initNotifications()
    initAdsPayer()
    refreshMailUnread()
  }
  document.addEventListener('visibilitychange', refreshMailOnVisible)
})

// Watch for auth changes and initialize when user logs in
watch(() => authStore.isAuthenticated, (isAuth) => {
  if (isAuth) {
    initialize()
    loadAdsFeedCount()
    realtimeStore.connect()
    initNotifications()
    initAdsPayer()
    refreshMailUnread()
  } else {
    cleanup()
    cleanupNotifications()
    cleanupAdsPayer()
    resetMailUnread()
  }
})

// Re-check mail on every menu open (server caches the IMAP count 60s)
watch(isSiteMenuOpen, (open) => {
  if (open) refreshMailUnread()
})

onUnmounted(() => {
  // Don't cleanup Matrix — keep service running for other components
  // cleanup()
  document.removeEventListener('visibilitychange', refreshMailOnVisible)
})

// Handle navigation click — re-tapping the section you're already in is
// per-section: Market toggles its two views, Transit returns to its home,
// Messages "unpress" to the map (the home screen), Map re-tap is a no-op.
function handleNavClick(path: string) {
  // Confirm-pulse fires only when the tap actually changes the screen
  const go = (p: string) => {
    hapticSelect()
    router.push(localePath(p))
  }

  // Not on this section yet — just navigate there
  if (!isPathActive(path)) {
    go(path)
    return
  }

  // Already in this section — re-tap behavior depends on which one
  if (path === '/market') {
    // Toggle between the marketplace and the user's own items;
    // from a detail/create subpage, the first tap returns to the list
    go(isExactPath('/market') ? '/market/my' : '/market')
  } else if (path === '/transit' || path === '/transit/rides') {
    // Return to the section's home (e.g. from a ride detail or a stop page).
    // `path` is the remembered target, which route-tracking keeps in sync
    // with the section the user is currently inside.
    if (!isExactPath(path)) go(path)
  } else if (path === '/map') {
    // The map is home — from a subpage return to it, on the map itself do nothing
    if (!isExactPath(path)) go(path)
  } else {
    // Messages: "unpress" back to the map home
    go('/map')
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
  hapticSelect() // screen change committed
  isSiteMenuOpen.value = false
}

// Top-dock (md+) only: hang the panel directly below the navbar with its right
// edge on the Menu button's. The bottom dock needs no JS — `bottom: 100%` in
// .site-menu-panel puts the panel on the bar's top edge, full-bleed.
function getSiteMenuStyle(): string {
  if (!process.client) return ''
  if (window.innerWidth < 768) return ''

  const header = document.querySelector('header')
  const top = header ? header.getBoundingClientRect().bottom - 2 : 80 // overlap 2px to kill sub-pixel gap

  // align the panel's right edge with the Menu button's right edge (siteMenuRef wraps the button)
  let right = 16 // fallback ≈ navbar px-4
  if (siteMenuRef.value) {
    right = Math.max(0, Math.round(window.innerWidth - siteMenuRef.value.getBoundingClientRect().right))
  }
  return `top: ${top}px; right: ${right}px;`
}
</script>

<style scoped>
/* The strip stays flush to the physical edge (edge-to-edge WebView), but its
   content must clear whatever system bar overlays that edge — the notch when
   it rides the top (phones, where the nav bar took the bottom), the Android
   gesture bar when it rides the bottom (md+). */
.drag-hover-bar {
  padding-top: calc(0.75rem + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)));
  padding-bottom: 0.75rem;
}
@media (min-width: 768px) {
  .drag-hover-bar {
    padding-top: 0.75rem;
    padding-bottom: calc(0.75rem + var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)));
  }
}

/* Phones: the menu unfolds upward off the bar's top edge (`bottom: 100%`),
   capped to the free band above it so a tall menu scrolls instead of running
   off screen. The bar's backdrop-filter makes it the containing block for
   this fixed panel, which is exactly what `bottom: 100%` needs. */
.site-menu-panel {
  max-height: calc(100dvh - var(--nav-inset-bottom) - var(--nav-inset-top) - 0.5rem);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

/* Keyboard up: the bottom dock slides off so the field keeps the band
   (see useVirtualKeyboard + main.css § Navigation dock insets). */
.nav-dock {
  transition: transform 0.18s ease-out;
}
@media (max-width: 767px) {
  :root.kb-open .nav-dock {
    transform: translateY(100%);
    pointer-events: none;
  }
}

/* One-shot pulse for the claimable-reward pill (NavItem carries its own copy) */
@keyframes reward-ping {
  0% { transform: scale(1); }
  35% { transform: scale(1.35); }
  100% { transform: scale(1); }
}
.reward-ping {
  animation: reward-ping 0.7s cubic-bezier(0.22, 1, 0.36, 1);
}
</style>
