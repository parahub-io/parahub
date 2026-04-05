<template>
  <!-- Dev mode indicator bar -->
  <div v-if="isDevMode" class="fixed top-0 left-0 right-0 h-[2px] bg-[#ffe216] z-[60]"></div>
  <header class="fixed left-0 right-0 z-50 bg-neutral-100/95 dark:bg-neutral-800/95 backdrop-blur-sm safe-area-top" :class="isDevMode ? 'top-[2px]' : 'top-0'">
    <nav class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8" aria-label="Main navigation">
      <div class="flex items-center gap-1 md:gap-2 h-14 sm:h-16 md:h-20">
          <!-- Messages (authenticated) / Login (anonymous) -->
          <a
            v-if="authStore.isAuthenticated"
            :href="localePath('/chat')"
            :aria-label="$t('nav.messages')"
            @click="handleButtonClick('/chat', null, $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-path="/chat"
            class="flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/chat') || isDragHovered('/chat', null),
              'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/chat') && !isDragHovered('/chat', null)
            }"
          >
            <div class="relative">
              <MessageCircle class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
              <!-- Unread messages badge (only show after first sync to avoid stale counts) -->
              <div
                v-if="isFirstSyncCompleted && unreadCount > 0"
                class="absolute -top-1 -right-1 min-w-[18px] h-[18px] bg-error text-white text-xs font-bold rounded-full flex items-center justify-center px-1 ring-2 ring-neutral-100 dark:ring-neutral-800"
              >
                {{ unreadCount > 99 ? '99+' : unreadCount }}
              </div>
            </div>
            <span class="hidden sm:block text-xs font-medium">{{ $t('nav.messages') }}</span>
          </a>
          <a
            v-else
            :href="localePath('/login')"
            :aria-label="$t('login.submit')"
            @click="handleButtonClick('/login', null, $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-path="/login"
            class="flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/login') || isDragHovered('/login', null),
              'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/login') && !isDragHovered('/login', null)
            }"
          >
            <Lock class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
            <span class="hidden sm:block text-xs font-medium">{{ $t('login.submit') }}</span>
          </a>

          <!-- Market -->
          <a
            :href="localePath('/market')"
            :aria-label="$t('nav.market')"
            @click="handleButtonClick('/market', null, $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-path="/market"
            class="flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/market') || isDragHovered('/market', null),
              'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/market') && !isDragHovered('/market', null)
            }"
          >
            <ShoppingBag class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
            <span class="hidden sm:block text-xs font-medium">{{ $t('nav.market') }}</span>
          </a>

          <!-- Map -->
          <a
            :href="localePath('/map')"
            :aria-label="$t('nav.map')"
            @click="handleButtonClick('/map', null, $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-path="/map"
            class="flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/map') || isDragHovered('/map', null),
              'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/map') && !isDragHovered('/map', null)
            }"
          >
            <Map class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
            <span class="hidden sm:block text-xs font-medium">{{ $t('nav.map') }}</span>
          </a>

          <!-- Transit -->
          <a
            :href="localePath('/transit')"
            :aria-label="$t('nav.transit')"
            @click="handleButtonClick('/transit', null, $event)"
            @touchstart="handleDragStart"
            data-nav-button
            data-nav-path="/transit"
            class="flex-1 flex flex-col items-center justify-center group cursor-pointer py-2 rounded-2xl relative min-h-[44px]"
            :class="{
              'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/transit') || isDragHovered('/transit', null),
              'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/transit') && !isDragHovered('/transit', null)
            }"
          >
            <Bus class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
            <span class="hidden sm:block text-xs font-medium">{{ $t('nav.transit') }}</span>
          </a>

          <!-- Site Menu -->
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
                'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isSiteMenuOpen && !isMenuItemActive && !isDragHovered(null, 'site-menu')
              }"
            >
              <Menu class="w-6 h-6 sm:w-7 sm:h-7 md:w-8 md:h-8 mb-0 sm:mb-1" />
              <!-- Show active category icon instead of "Menu" text when a menu item is active -->
              <component
                v-if="isMenuItemActive && activeMenuItem"
                :is="activeMenuItem"
                class="w-4 h-4 opacity-70"
              />
              <span v-else class="hidden sm:block text-xs font-medium">{{ $t('nav.menu') || 'Menu' }}</span>
            </button>

            <!-- Site Menu Dropdown (centered, rounded bottom) -->
            <div
              v-if="isSiteMenuOpen"
              class="fixed left-1/2 -translate-x-1/2 w-full max-w-4xl bg-neutral-100 dark:bg-neutral-800 border border-t-0 border-neutral-300 dark:border-neutral-700 rounded-b-2xl z-50 shadow-lg dark:shadow-neutral-900/50"
              :style="`top: ${getSiteMenuTop()}px;`"
              @click.stop
              @pointerenter="handleMenuHoverEnter"
              @pointerleave="handleMenuHoverLeave"
            >
              <div class="px-4 sm:px-6 lg:px-8 py-4 space-y-3">

                  <!-- Profile Header (authenticated users) -->
                  <template v-if="authStore.isAuthenticated">
                    <div class="grid grid-cols-4 gap-1">
                      <!-- Avatar + Name spans 2 columns -->
                      <NuxtLink
                        :to="localePath(profilePath)"
                        @click="handleSubMenuClick(profilePath, $event)"
                        @touchstart="handleDragStart"
                        data-nav-button
                        :data-nav-path="profilePath"
                        class="col-span-2 flex items-center gap-3 px-3 py-2 h-16 rounded-lg group"
                        :class="{
                          'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isDragHovered(profilePath, null),
                          'hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isDragHovered(profilePath, null)
                        }"
                      >
                        <div class="w-10 h-10 rounded-full overflow-hidden flex-shrink-0">
                          <img v-if="avatarUrl" :src="avatarUrl" :alt="avatarInitials" class="w-full h-full object-cover" />
                          <div v-else class="w-full h-full bg-neutral-300 dark:bg-neutral-600 flex items-center justify-center">
                            <span class="text-sm font-bold text-neutral-700 dark:text-neutral-300">{{ avatarInitials }}</span>
                          </div>
                        </div>
                        <div class="flex-1 min-w-0">
                          <div class="font-semibold text-sm text-neutral-900 dark:text-neutral-100 group-hover:text-white truncate">
                            {{ authStore.activeProfile?.display_name || authStore.user?.profile?.display_name }}
                          </div>
                          <div class="text-xs text-neutral-500 dark:text-neutral-400 group-hover:text-white/80 truncate">
                            {{ authStore.activeProfile?.hna || authStore.user?.profile?.hna }}
                          </div>
                        </div>
                      </NuxtLink>
                      <!-- Wallet -->
                      <NuxtLink
                        :to="localePath('/wallet')"
                        @click="handleSubMenuClick('/wallet', $event)"
                        @touchstart="handleDragStart"
                        data-nav-button
                        data-nav-path="/wallet"
                        class="flex flex-col items-center justify-center h-16 rounded-lg"
                        :class="{
                          'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/wallet') || isDragHovered('/wallet', null),
                          'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/wallet') && !isDragHovered('/wallet', null)
                        }"
                      >
                        <Wallet class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.wallet') || 'Wallet' }}</span>
                      </NuxtLink>
                      <!-- Settings -->
                      <NuxtLink
                        :to="localePath('/profile')"
                        @click="handleSubMenuClick('/profile', $event)"
                        @touchstart="handleDragStart"
                        data-nav-button
                        data-nav-path="/profile"
                        class="flex flex-col items-center justify-center h-16 rounded-lg"
                        :class="{
                          'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/profile') || isDragHovered('/profile', null),
                          'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/profile') && !isDragHovered('/profile', null)
                        }"
                      >
                        <Settings class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('zenith.settings') }}</span>
                      </NuxtLink>
                    </div>
                  </template>

                  <!-- Guest Header -->
                  <template v-else>
                    <NuxtLink
                      :to="localePath('/login')"
                      @click="isSiteMenuOpen = false"
                      class="w-full btn-secondary gap-2 px-4 py-2.5 text-sm"
                    >
                      <Lock class="w-4 h-4" />
                      {{ $t('auth.login') || 'Login / Register' }}
                    </NuxtLink>
                  </template>

                  <div class="border-t border-neutral-200 dark:border-neutral-700"></div>

                  <!-- === Community === -->
                  <div>
                    <div class="text-[10px] uppercase tracking-wider text-neutral-400 dark:text-neutral-500 font-semibold px-1 mb-1">{{ $t('nav.section_community') || 'Community' }}</div>
                    <div class="grid grid-cols-4 gap-1">
                      <NuxtLink :to="localePath('/events')" @click="handleSubMenuClick('/events', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/events" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/events') || isDragHovered('/events', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/events') && !isDragHovered('/events', null) }">
                        <Calendar class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.events') || 'Events' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/directory')" @click="handleSubMenuClick('/directory', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/directory" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/directory') || isDragHovered('/directory', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/directory') && !isDragHovered('/directory', null) }">
                        <Book class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.directory') || 'Directory' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/governance/polls')" @click="handleSubMenuClick('/governance/polls', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/governance/polls" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/governance/polls') || isDragHovered('/governance/polls', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/governance/polls') && !isDragHovered('/governance/polls', null) }">
                        <Vote class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.governance') || 'Governance' }}</span>
                      </NuxtLink>

                      <NuxtLink v-if="authStore.isAuthenticated" :to="localePath('/condo')" @click="handleSubMenuClick('/condo', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/condo" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/condo') || isDragHovered('/condo', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/condo') && !isDragHovered('/condo', null) }">
                        <Building class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.condo') || 'Condo' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/blog')" @click="handleSubMenuClick('/blog', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/blog" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/blog') || isDragHovered('/blog', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/blog') && !isDragHovered('/blog', null) }">
                        <Newspaper class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('cms.blog') || 'Blog' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/videos')" @click="handleSubMenuClick('/videos', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/videos" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/videos') || isDragHovered('/videos', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/videos') && !isDragHovered('/videos', null) }">
                        <VideoIcon class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('videos.title') || 'Videos' }}</span>
                      </NuxtLink>

                    </div>
                  </div>

                  <!-- === Deals (auth-only) === -->
                  <div v-if="authStore.isAuthenticated">
                    <div class="text-[10px] uppercase tracking-wider text-neutral-400 dark:text-neutral-500 font-semibold px-1 mb-1">{{ $t('nav.section_deals') || 'Deals' }}</div>
                    <div class="grid grid-cols-4 gap-1">
                      <NuxtLink :to="localePath('/ads')" @click="handleSubMenuClick('/ads', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/ads" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/ads') || isDragHovered('/ads', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/ads') && !isDragHovered('/ads', null) }">
                        <div class="relative">
                          <Megaphone class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                          <div v-if="adsFeedCount > 0" class="absolute -top-1 -right-1 min-w-[16px] h-[16px] bg-error text-white text-[10px] font-bold rounded-full flex items-center justify-center px-0.5 ring-2 ring-neutral-100 dark:ring-neutral-800">
                            {{ adsFeedCount > 99 ? '99+' : adsFeedCount }}
                          </div>
                        </div>
                        <span class="text-[11px] font-medium">{{ $t('nav.ads') || 'Ads' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/contracts')" @click="handleSubMenuClick('/contracts', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/contracts" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/contracts') || isDragHovered('/contracts', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/contracts') && !isDragHovered('/contracts', null) }">
                        <FileText class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.contracts') || 'Contracts' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/shipments')" @click="handleSubMenuClick('/shipments', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/shipments" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/shipments') || isDragHovered('/shipments', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/shipments') && !isDragHovered('/shipments', null) }">
                        <PackageCheck class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.shipments') || 'Shipping' }}</span>
                      </NuxtLink>
                    </div>
                  </div>

                  <!-- === Operations (auth-only) === -->
                  <div v-if="authStore.isAuthenticated">
                    <div class="text-[10px] uppercase tracking-wider text-neutral-400 dark:text-neutral-500 font-semibold px-1 mb-1">{{ $t('nav.section_ops') || 'Operations' }}</div>
                    <div class="grid grid-cols-4 gap-1">
                      <NuxtLink :to="localePath('/iot')" @click="handleSubMenuClick('/iot', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/iot" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/iot') || isDragHovered('/iot', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/iot') && !isDragHovered('/iot', null) }">
                        <Cpu class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.iot') || 'Devices' }}</span>
                      </NuxtLink>

                      <NuxtLink :to="localePath('/energy')" @click="handleSubMenuClick('/energy', $event)" @touchstart="handleDragStart" data-nav-button data-nav-path="/energy" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative" :class="{ 'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/energy') || isDragHovered('/energy', null), 'text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/energy') && !isDragHovered('/energy', null) }">
                        <Sun class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.energy') || 'Energy' }}</span>
                      </NuxtLink>

                      <a href="https://git.parahub.io/user/login" target="_blank" rel="noopener noreferrer" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative overflow-hidden min-w-0 text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100">
                        <ExternalLink class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
                        <FolderGit class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.projects') || 'Projects' }}</span>
                      </a>

                      <NuxtLink :to="localePath('/webmail')" target="_blank" rel="noopener noreferrer" class="flex flex-col items-center justify-center group cursor-pointer py-2 h-16 rounded-lg relative overflow-hidden min-w-0 text-neutral-700 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100">
                        <ExternalLink class="absolute top-1 right-1 w-2.5 h-2.5 opacity-40" />
                        <Mail class="w-5 h-5 sm:w-6 sm:h-6 mb-0.5" />
                        <span class="text-[11px] font-medium">{{ $t('nav.webmail') || 'Webmail' }}</span>
                      </NuxtLink>

                    </div>
                  </div>

                  <div class="border-t border-neutral-200 dark:border-neutral-700"></div>

                  <!-- === Footer: About + Logout === -->
                  <div class="flex items-center">
                    <NuxtLink
                      :to="localePath('/about')"
                      @click="handleSubMenuClick('/about', $event)"
                      @touchstart="handleDragStart"
                      data-nav-button
                      data-nav-path="/about"
                      class="flex items-center gap-1.5 px-2.5 py-3.5 rounded-lg text-xs font-medium"
                      :class="{
                        'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/about') || isDragHovered('/about', null),
                        'text-neutral-600 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/about') && !isDragHovered('/about', null)
                      }"
                    >
                      <Rocket class="w-3.5 h-3.5" />
                      {{ $t('about.title') || 'About' }}
                    </NuxtLink>

                    <NuxtLink
                      v-if="authStore.user?.is_staff"
                      :to="localePath('/yellow-gate')"
                      @click="handleSubMenuClick('/yellow-gate', $event)"
                      @touchstart="handleDragStart"
                      data-nav-button
                      data-nav-path="/yellow-gate"
                      class="flex items-center gap-1.5 px-2.5 py-3.5 rounded-lg text-xs font-medium"
                      :class="{
                        'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/yellow-gate') || isDragHovered('/yellow-gate', null),
                        'text-neutral-500 dark:text-neutral-400 hover:bg-secondary-600 hover:text-white dark:hover:bg-secondary-900/30 dark:hover:text-neutral-100': !isPathActive('/yellow-gate') && !isDragHovered('/yellow-gate', null)
                      }"
                      :title="'Hive'"
                    >
                      <Bot class="w-3.5 h-3.5" />
                      <span class="hidden sm:inline">Hive</span>
                    </NuxtLink>

                    <div class="flex-1"></div>

                    <NuxtLink
                      v-if="authStore.isAuthenticated"
                      :to="localePath('/sos')"
                      @click="handleSubMenuClick('/sos', $event)"
                      @touchstart="handleDragStart"
                      data-nav-button
                      data-nav-path="/sos"
                      class="flex items-center gap-1.5 px-2.5 py-3.5 rounded-lg text-xs font-medium"
                      :class="{
                        'bg-primary text-neutral-900 dark:bg-primary dark:text-neutral-900': isPathActive('/sos') || isDragHovered('/sos', null),
                        'text-error hover:bg-error hover:text-white': !isPathActive('/sos') && !isDragHovered('/sos', null)
                      }"
                    >
                      <Shield class="w-3.5 h-3.5" />
                      SOS
                    </NuxtLink>

                    <button
                      v-if="authStore.isAuthenticated"
                      @click="openInviteModal"
                      class="flex items-center gap-1.5 px-2.5 py-3.5 rounded-lg text-xs font-medium text-success hover:bg-success hover:text-white transition-colors"
                    >
                      <UserPlus class="w-3.5 h-3.5" />
                      {{ $t('nav.invite') }}
                    </button>

                    <button
                      v-if="authStore.isAuthenticated"
                      @click="handleLogout"
                      @touchstart="handleDragStart"
                      data-nav-button
                      data-nav-action="logout"
                      class="flex items-center gap-1.5 px-2.5 py-3.5 rounded-lg text-xs font-medium transition-all"
                      :class="logoutConfirmPending
                        ? 'bg-error text-white'
                        : isDragHovered(null, 'logout')
                          ? 'bg-neutral-200 dark:bg-neutral-700'
                          : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700 hover:text-neutral-700 dark:hover:text-neutral-200'"
                    >
                      <LogOut class="w-3.5 h-3.5" />
                      {{ logoutConfirmPending ? ($t('profiles.logout_confirm') || 'Sure?') : ($t('profiles.logout') || 'Logout') }}
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
      <div class="bg-[#ffe216] py-3 flex items-center justify-center">
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

  <!-- Invite Modal -->
  <Teleport to="body">
    <div
      v-if="showInviteModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]"
      @click.self="showInviteModal = false"
    >
      <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-300 dark:border-neutral-600 p-6 max-w-md w-full mx-4">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ $t('directory.users.invite_modal.title') }}
          </h3>
          <button
            @click="showInviteModal = false"
            class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
          >
            <X class="w-6 h-6" />
          </button>
        </div>

        <div v-if="inviteData" class="space-y-4">
          <!-- QR Code -->
          <div class="flex justify-center">
            <canvas ref="inviteQRCanvas" role="img" :aria-label="$t('directory.users.invite_modal.qr_aria_label')"></canvas>
          </div>

          <!-- Invited count -->
          <div class="flex items-center justify-between bg-neutral-100 dark:bg-neutral-700/50 rounded-lg px-4 py-3">
            <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('directory.users.invite_modal.invited_count_label') }}</span>
            <span class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ inviteData.invited_count }}</span>
          </div>

          <!-- Invite URL -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('directory.users.invite_modal.invite_link_label') }}
            </label>
            <div class="flex items-center gap-2">
              <input
                :value="inviteData.invite_url"
                readonly
                class="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded text-sm font-mono"
              />
              <button
                @click="copyInviteLink"
                :class="inviteLinkCopied ? 'btn-success btn-icon' : 'btn-ghost btn-icon'"
                :title="inviteLinkCopied ? $t('directory.users.invite_modal.copied') : $t('directory.users.invite_modal.copy_button')"
              >
                <Check v-if="inviteLinkCopied" class="w-4 h-4" />
                <Copy v-else class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Status -->
          <div class="flex items-center justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ $t('directory.users.invite_modal.status_label') }}</span>
            <span :class="inviteData.is_active ? 'text-success' : 'text-error'">
              {{ inviteData.is_active ? $t('directory.users.invite_modal.active') : $t('directory.users.invite_modal.inactive') }}
            </span>
          </div>

          <!-- Actions -->
          <div class="flex gap-2 pt-4 border-t border-neutral-200 dark:border-neutral-700">
            <button
              @click="toggleInvite"
              class="flex-1"
              :class="inviteData.is_active ? 'btn-primary' : 'btn-success'"
            >
              {{ inviteData.is_active ? $t('directory.users.invite_modal.disable_button') : $t('directory.users.invite_modal.enable_button') }}
            </button>
            <button
              @click="showRegenerateConfirm = true"
              class="flex-1 btn-outline"
            >
              {{ $t('directory.users.invite_modal.regenerate_button') }}
            </button>
          </div>
        </div>

        <div v-else class="text-center py-8">
          <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
        </div>
      </div>
    </div>
  </Teleport>

  <UiConfirmModal
    v-model="showRegenerateConfirm"
    :title="$t('directory.users.invite_modal.regenerate_button')"
    :message="$t('directory.users.invite_modal.regenerate_confirm')"
    :icon="RefreshCw"
    variant="warning"
    :confirm-label="$t('directory.users.invite_modal.regenerate_button')"
    @confirm="regenerateInvite(); showRegenerateConfirm = false"
  />

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { MessageCircle, ShoppingBag, Map, Megaphone, Menu, Book, Settings, FileText, Home, Package, PackageCheck, FolderGit, Wallet, Info, Shield, LogOut, Lock, Vote, Rocket, Calendar, UserPlus, X, Copy, Check, Car, Bus, Mail, ExternalLink, Plus, Sun, Zap, ArrowRightLeft, Building, Bot, Cpu, Newspaper, Video as VideoIcon, RefreshCw } from 'lucide-vue-next'
import { useMatrixUnread } from '~/composables/useMatrixUnread'
import QRCode from 'qrcode'

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

// Dev mode indicator (yellow bar at top)
const isDevMode = ref(false)
onMounted(() => {
  if (typeof document !== 'undefined') {
    isDevMode.value = document.cookie.includes('parahub_dev=1')
  }
})

// Matrix unread counter (global service)
const { totalUnreadCount, isFirstSyncCompleted, initialize, cleanup } = useMatrixUnread()
const unreadCount = totalUnreadCount // Use the ref directly

// Ads feed count (available unviewed ads, updated via WS)
const { feedCount: adsFeedCount, loadFeedCount: loadAdsFeedCount } = useAdsState()
const realtimeStore = useRealtimeStore()

// Invite modal state
const showInviteModal = ref(false)
const inviteData = ref<any>(null)
const showRegenerateConfirm = ref(false)
const inviteQRCanvas = ref<HTMLCanvasElement | null>(null)
const inviteLinkCopied = ref(false)

watch(showInviteModal, async (isOpen) => {
  if (isOpen) {
    await loadInviteData()
  }
})

const loadInviteData = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const response = await $fetch('/api/v1/partners/invite/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    inviteData.value = response

    await nextTick()
    if (inviteQRCanvas.value) {
      await generateInviteQR()
    }
  } catch (error) {
    console.error('Failed to load invite data:', error)
  }
}

const generateInviteQR = async () => {
  if (!inviteData.value || !inviteQRCanvas.value) return

  try {
    const isDark = document.documentElement.classList.contains('dark')

    await QRCode.toCanvas(inviteQRCanvas.value, inviteData.value.invite_url, {
      width: 256,
      margin: 2,
      color: {
        dark: isDark ? '#FFFFFF' : '#000000',
        light: isDark ? '#374151' : '#FFFFFF'
      }
    })
  } catch (error) {
    console.error('Failed to generate invite QR code:', error)
  }
}

const toggleInvite = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const response = await $fetch('/api/v1/partners/invite/toggle/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: { active: !inviteData.value.is_active }
    })

    inviteData.value = response
  } catch (error) {
    console.error('Failed to toggle invite:', error)
  }
}

const regenerateInvite = async () => {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return

    const response = await $fetch('/api/v1/partners/invite/regenerate/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    inviteData.value = response

    await nextTick()
    if (inviteQRCanvas.value) {
      await generateInviteQR()
    }
  } catch (error) {
    console.error('Failed to regenerate invite:', error)
  }
}

const copyInviteLink = async () => {
  try {
    await navigator.clipboard.writeText(inviteData.value.invite_url)
    inviteLinkCopied.value = true
    setTimeout(() => { inviteLinkCopied.value = false }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}

const openInviteModal = () => {
  isSiteMenuOpen.value = false
  showInviteModal.value = true
}

// Menu states
const isSiteMenuOpen = ref(false)
const siteMenuRef = ref<HTMLElement | null>(null)
let menuHoverOpenTimer: ReturnType<typeof setTimeout> | null = null
let menuHoverCloseTimer: ReturnType<typeof setTimeout> | null = null
let menuOpenedByHover = false

function cancelHoverOpen() {
  if (menuHoverOpenTimer) {
    clearTimeout(menuHoverOpenTimer)
    menuHoverOpenTimer = null
  }
}

function handleMenuHoverEnter(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  if (menuHoverCloseTimer) {
    clearTimeout(menuHoverCloseTimer)
    menuHoverCloseTimer = null
  }
  // Delay open slightly so touchstart can cancel it on hybrid devices
  cancelHoverOpen()
  menuHoverOpenTimer = setTimeout(() => {
    menuHoverOpenTimer = null
    menuOpenedByHover = true
    isSiteMenuOpen.value = true
  }, 80)
}

function handleMenuHoverLeave(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  cancelHoverOpen()
  if (!menuOpenedByHover) return
  if (menuHoverCloseTimer) clearTimeout(menuHoverCloseTimer)
  menuHoverCloseTimer = setTimeout(() => {
    isSiteMenuOpen.value = false
    menuOpenedByHover = false
    menuHoverCloseTimer = null
  }, 200)
}

// Touch drag selection state
const isDragging = ref(false)
const dragStartTarget = ref<HTMLElement | null>(null)
const currentHoverTarget = ref<HTMLElement | null>(null)
const dragMoved = ref(false) // Track if drag actually moved
const releaseAnimation = ref(false) // Track release animation state
const releaseTarget = ref<{ path: string | null, action: string | null, rect: DOMRect | null } | null>(null)
const beamAnimating = ref(false) // Track when beam animation starts (for CSS transition)

// Check animation preference from active profile
const animationEnabled = computed(() => {
  const value = authStore.activeProfile?.animation_enabled
  return value !== false
})

// Get beam color based on theme
const beamColor = computed(() => {
  if (process.client) {
    const isDark = document.documentElement.classList.contains('dark')
    return isDark ? '#ffe216' : '#ff0000' // Yellow for dark, red for light
  }
  return '#ffe216'
})

// Menu items mapping: path prefix → icon component
const menuItemsMap = {
  '/shipments': PackageCheck,
  '/iot': Package,
  '/directory': Book,
  '/events': Calendar,
  '/ads': Megaphone,
  '/contracts': FileText,
  '/sos': Shield,
  '/wallet': Wallet,
  '/governance': Vote,
  '/transit/rides': Car,
  '/energy': Zap,
  '/condo': Building,
  '/profile': Settings,
  '/about': Info,
  '/yellow-gate': Bot,
  '/videos': VideoIcon,
}

// Get active menu item (icon component) based on current route
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

// Label for the bottom drag-hover bar
const dragHoverLabel = computed(() => {
  if (!isDragging.value || !dragMoved.value || !currentHoverTarget.value) return null

  const path = currentHoverTarget.value.getAttribute('data-nav-path')
  const action = currentHoverTarget.value.getAttribute('data-nav-action')

  if (action === 'site-menu') return t('nav.menu')
  if (action === 'logout') return t('profiles.logout')

  if (path) {
    if (path.startsWith('/u/')) {
      return authStore.activeProfile?.display_name || authStore.user?.profile?.display_name || 'Profile'
    }
    const labels: Record<string, string> = {
      '/chat': t('nav.messages'),
      '/market': t('nav.market'),
      '/map': t('nav.map'),
      '/ads': t('nav.ads'),
      '/directory': t('nav.directory'),
      '/events': t('nav.events'),
      '/contracts': t('nav.contracts'),
      '/shipments': t('nav.shipments'),
      '/iot': t('nav.iot'),
      '/sos': t('parasos.title'),
      '/wallet': t('nav.wallet'),
      '/governance/polls': t('nav.governance'),
      '/transit/rides': t('nav.rides'),
      '/transit': t('nav.transit'),

      '/profile': t('zenith.settings'),
      '/about': t('about.title'),
    }
    return labels[path] || null
  }

  return null
})

// Toggle menus
function toggleSiteMenu() {
  isSiteMenuOpen.value = !isSiteMenuOpen.value
  menuOpenedByHover = false
}

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

// Handle clicks outside menus
function handleClickOutside(event: MouseEvent) {
  if (siteMenuRef.value && !siteMenuRef.value.contains(event.target as Node)) {
    isSiteMenuOpen.value = false
  }
}

// ESC closes dropdown menu
function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isSiteMenuOpen.value) {
    isSiteMenuOpen.value = false
  }
}

onMounted(() => {
  // Initialize Matrix unread counter if user is authenticated
  if (authStore.isAuthenticated) {
    initialize()
    loadAdsFeedCount()
    realtimeStore.connect()
  }

  // Add click outside listener
  if (process.client) {
    document.addEventListener('click', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)

    // Add global drag handlers (touch only)
    document.addEventListener('touchmove', handleDragMove, { passive: false })
    document.addEventListener('touchend', handleDragEnd)
    document.addEventListener('touchcancel', handleDragEnd)
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

// Profile switcher state
const showCreateProfileDialog = ref(false)
const newProfileForm = ref({
  local_name: '',
  display_name: '',
})
const creatingProfile = ref(false)
const createProfileError = ref('')

// Fetch manageable profiles when site menu opens
watch(isSiteMenuOpen, async (isOpen) => {
  if (isOpen) {
    if (authStore.isAuthenticated && authStore.user?.profile) {
      try {
        await authStore.fetchManageableProfiles()
      } catch (e) {
        // ignore
      }
    }
  }
})

async function handleSwitchProfile(profileId: string) {
  const currentId = authStore.activeProfile?.id || authStore.user?.profile?.id
  if (profileId === currentId) return
  try {
    await authStore.switchProfile(profileId)
    isSiteMenuOpen.value = false
  } catch (error: any) {
    console.error('Failed to switch profile:', error)
  }
}

function getProfileTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    'PERSONAL': t('profiles.personal') || 'Personal',
    'PSEUDONYMOUS': t('profiles.pseudonymous') || 'Pseudonymous'
  }
  return labels[type] || type
}

async function handleCreateProfileSubmit() {
  creatingProfile.value = true
  createProfileError.value = ''
  try {
    const data: any = {
      local_name: newProfileForm.value.local_name,
      display_name: newProfileForm.value.display_name
    }
    await authStore.createProfile(data)
    showCreateProfileDialog.value = false
    newProfileForm.value = { local_name: '', display_name: '' }
  } catch (error: any) {
    createProfileError.value = error.data?.message || error.message || 'Failed to create profile'
  } finally {
    creatingProfile.value = false
  }
}

onUnmounted(() => {
  // Don't cleanup - keep service running for other components
  // cleanup()

  // Remove click outside listener
  if (process.client) {
    document.removeEventListener('click', handleClickOutside)
    document.removeEventListener('keydown', handleKeyDown)

    // Remove global drag handlers (touch only)
    document.removeEventListener('touchmove', handleDragMove)
    document.removeEventListener('touchend', handleDragEnd)
    document.removeEventListener('touchcancel', handleDragEnd)
  }
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

// Touch drag selection handlers
function getNavButton(element: HTMLElement | null): HTMLElement | null {
  if (!element) return null
  if (element.hasAttribute('data-nav-button')) return element
  return element.closest('[data-nav-button]') as HTMLElement | null
}

function handleDragStart(event: MouseEvent | TouchEvent) {
  // Only enable drag mode on touch devices
  if (event instanceof MouseEvent) return

  // Cancel any pending hover-open (touch on hybrid device fires pointerenter:mouse first)
  cancelHoverOpen()

  const target = event.target as HTMLElement
  const navButton = getNavButton(target)

  if (!navButton) return

  // Don't prevent default yet - let it be a normal click if no drag happens
  isDragging.value = true
  dragMoved.value = false
  dragStartTarget.value = navButton
  currentHoverTarget.value = navButton

  // DON'T open/close menus on touchstart - only when drag actually moves
  // This allows normal tap to work without immediately closing menus
}

function handleDragMove(event: MouseEvent | TouchEvent) {
  if (!isDragging.value) return

  // Mark that drag has moved
  if (!dragMoved.value) {
    dragMoved.value = true
    event.preventDefault() // Now prevent default since we're dragging

    // Open menu on first move if drag started on menu button
    const startAction = dragStartTarget.value?.getAttribute('data-nav-action')
    if (startAction === 'site-menu') {
      isSiteMenuOpen.value = true
    }
  }

  event.preventDefault()

  // Get coordinates from touch or mouse event
  let clientX: number, clientY: number
  if (event instanceof TouchEvent) {
    const touch = event.touches[0]
    clientX = touch.clientX
    clientY = touch.clientY
  } else {
    clientX = event.clientX
    clientY = event.clientY
  }

  // Find element under cursor/finger
  const elementUnder = document.elementFromPoint(clientX, clientY) as HTMLElement
  const navButton = getNavButton(elementUnder)

  // Update hover target if it changed (skip null gaps between buttons to prevent flicker)
  if (navButton !== currentHoverTarget.value && navButton !== null) {
    currentHoverTarget.value = navButton

    // Open/close menus when hovering different buttons
    if (navButton) {
      const action = navButton.getAttribute('data-nav-action')
      const path = navButton.getAttribute('data-nav-path')

      if (action === 'site-menu') {
        isSiteMenuOpen.value = true
      } else if (path) {
        // Check if this is a submenu item (all items in site menu)
        const siteSubmenuPaths = ['/iot', '/directory', '/events', '/contracts', '/governance/polls', '/wallet', '/sos', '/profile', '/u/', '/about', '/yellow-gate', '/ads', '/shipments', '/energy', '/condo', '/webmail', '/videos']
        const isSiteSubmenuItem = siteSubmenuPaths.some(p => path.startsWith(p))

        if (isSiteSubmenuItem) {
          // Keep site menu open when hovering submenu items
        } else {
          // Close menu when hovering main nav buttons (chat, iot, map, ads)
          isSiteMenuOpen.value = false
        }
      }
    }
  }
}

function handleDragEnd(event: MouseEvent | TouchEvent) {
  if (!isDragging.value) return

  // Only handle if drag actually moved
  if (dragMoved.value) {
    event.preventDefault()

    // Only activate if we released on a valid nav button
    if (currentHoverTarget.value) {
      const path = currentHoverTarget.value.getAttribute('data-nav-path')
      const action = currentHoverTarget.value.getAttribute('data-nav-action')

      // Start release animation (background only, doesn't block action)
      // Save element rect BEFORE navigation (element might disappear after)
      const rect = currentHoverTarget.value.getBoundingClientRect()

      // Set releaseTarget FIRST before checking isVerticalBeam()
      releaseTarget.value = { path, action, rect }

      releaseAnimation.value = true
      beamAnimating.value = false // Start as dot

      // Trigger animation after small delay (allows initial dot to render first)
      setTimeout(() => {
        beamAnimating.value = true
      }, 10)

      // Execute action IMMEDIATELY (don't wait for animation)
      if (path) {
        // Navigate to path (includes submenu items)
        router.push(localePath(path))
        // Close menu after navigation
        isSiteMenuOpen.value = false
      } else if (action) {
        // Handle special buttons (Site Menu, Logout)
        if (action === 'site-menu') {
          toggleSiteMenu()
        } else if (action === 'logout') {
          handleLogout()
        }
      }

      // Clear animation after it completes
      setTimeout(() => {
        releaseAnimation.value = false
        releaseTarget.value = null
      }, 300)
    }
  }

  // Reset drag state
  isDragging.value = false
  dragStartTarget.value = null
  currentHoverTarget.value = null
  dragMoved.value = false
}

// Check if button is currently hovered during drag
function isDragHovered(buttonPath: string | null, buttonAction: string | null): boolean {
  if (!isDragging.value || !currentHoverTarget.value) return false

  const currentPath = currentHoverTarget.value.getAttribute('data-nav-path')
  const currentAction = currentHoverTarget.value.getAttribute('data-nav-action')

  return (buttonPath && currentPath === buttonPath) || (buttonAction && currentAction === buttonAction)
}

// Determine if beam should be vertical (all items now use vertical beam)
function isVerticalBeam(): boolean {
  return true
}

// Get beam starting position based on saved rect
function getBeamPosition(): string {
  if (!releaseTarget.value?.rect) return 'top: 0; left: 0;'

  const rect = releaseTarget.value.rect

  if (isVerticalBeam()) {
    // Vertical beam - start from bottom center of button, go down
    return `top: ${rect.bottom + 40}px; left: ${rect.left + rect.width / 2}px;`
  } else {
    // Horizontal beam - start from left center of button, go left
    return `top: ${rect.top + rect.height / 2}px; left: ${rect.left - 12}px;`
  }
}

// Get beam animated style (becomes beam with opacity 0)
function getBeamStyle(): string {
  if (isVerticalBeam()) {
    return `width: 2px; height: 100vh; opacity: 0; background-color: ${beamColor.value};`
  } else {
    return `width: 100vw; height: 2px; opacity: 0; background-color: ${beamColor.value};`
  }
}

// Get Site Menu position (directly below main navbar)
function getSiteMenuTop(): number {
  if (!process.client) return 0

  // Get header element (navbar container)
  const header = document.querySelector('header')
  if (!header) return 56 // fallback to navbar height (mobile h-14)

  const rect = header.getBoundingClientRect()
  return rect.bottom - 2 // overlap 2px to eliminate sub-pixel gap
}
</script>
