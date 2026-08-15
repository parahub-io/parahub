<template>
  <div class="py-6 w-full">
    <div class="w-full px-4 sm:px-6 lg:px-8">
      <div class="max-w-3xl mx-auto w-full">
    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center items-center min-h-[400px]" role="status" aria-live="polite">
      <Loader2 class="h-12 w-12 animate-spin text-neutral-400 dark:text-neutral-500" aria-hidden="true" />
      <span class="sr-only">{{ t('common.loading') }}</span>
    </div>

    <!-- Error state -->
    <UiAlert v-else-if="error" variant="error" :title="t('user_profile.not_found_title')">
      <p>{{ error }}</p>
      <NuxtLink :to="localePath('/')" class="btn-primary btn-sm mt-3 inline-flex">
        {{ t('user_profile.return_home') }}
      </NuxtLink>
    </UiAlert>

    <!-- Handle the platform holds (service agent, test fixture, reserved name).
         Not an error: the name IS taken, and saying so is what keeps this page
         consistent with the signup form. No reputation, no WoT, no actions. -->
    <div v-else-if="heldKind" class="max-w-md mx-auto text-center py-10">
      <div class="w-16 h-16 mx-auto rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
        <component :is="heldIcon" class="w-7 h-7 text-neutral-500 dark:text-neutral-400" aria-hidden="true" />
      </div>
      <h1 class="mt-4 text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {{ heldHandle }}
      </h1>
      <UiBadge variant="neutral" type="soft" size="sm" class="mt-2">
        {{ t(`user_profile.held.${heldKind}_badge`) }}
      </UiBadge>
      <p class="mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        {{ t(`user_profile.held.${heldKind}_desc`) }}
      </p>
      <NuxtLink :to="localePath('/')" class="btn-primary btn-sm mt-5 inline-flex">
        {{ t('user_profile.return_home') }}
      </NuxtLink>
    </div>

    <!-- Profile content -->
    <div v-else-if="profile" class="space-y-4">
      <!-- ========== HERO: Avatar + Identity + Badges ========== -->
      <div class="border-b border-neutral-200 dark:border-neutral-700 pb-4">
        <!-- Avatar + Name row -->
        <div class="flex items-center gap-3 sm:gap-5">
          <!-- Avatar with flip animation -->
          <div
            class="w-20 h-20 sm:w-28 sm:h-28 flex-shrink-0 perspective-500 cursor-pointer rounded-full"
            :class="{ 'cursor-default': !profile.id_photo_url }"
            @click="toggleAvatarFlip"
            :title="avatarFlipTitle"
          >
            <div
              class="relative w-full h-full transition-transform duration-500 transform-style-3d"
              :class="{ 'rotate-y-180': showIdPhoto }"
            >
              <!-- Front: Avatar -->
              <div class="absolute inset-0 backface-hidden rounded-full overflow-hidden">
                <img
                  v-if="avatarUrl"
                  :src="avatarUrl"
                  :alt="userInitials"
                  class="w-full h-full object-cover"
                />
                <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
                  <span class="text-3xl sm:text-4xl font-bold text-black">{{ userInitials }}</span>
                </div>
              </div>
              <!-- Back: ID Photo -->
              <div
                v-if="profile.id_photo_url"
                class="absolute inset-0 backface-hidden rotate-y-180 rounded-lg overflow-hidden border-2"
                :class="profile.id_photo_verified ? 'border-green-500' : 'border-amber-500'"
              >
                <img
                  v-if="idPhotoObjectUrl"
                  :src="idPhotoObjectUrl"
                  :alt="t('user_profile.id_photo')"
                  class="w-full h-full object-cover"
                />
                <div v-else class="w-full h-full flex items-center justify-center bg-neutral-100 dark:bg-neutral-800">
                  <Loader2 class="w-5 h-5 animate-spin text-neutral-400" />
                </div>
                <div
                  class="absolute top-1 right-1 rounded-full p-0.5"
                  :class="profile.id_photo_verified ? 'bg-green-500' : 'bg-amber-500'"
                >
                  <Shield v-if="profile.id_photo_verified" class="w-3 h-3 text-white" />
                  <AlertTriangle v-else class="w-3 h-3 text-white" />
                </div>
              </div>
            </div>
          </div>

          <!-- Name + HNA + Badges — unified identity block -->
          <div class="flex-1 min-w-0">
            <h1 class="text-xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100 break-words leading-tight">
              {{ profile.display_name || profile.hna }}
            </h1>
            <!-- Handle subtitle only when the H1 shows a distinct display name; when the
                 real name is gated the H1 already IS the handle, so skip the duplicate -->
            <p v-if="profile.display_name && profile.display_name !== profile.hna" class="text-neutral-500 dark:text-neutral-400 font-mono text-xs sm:text-sm mt-0.5 truncate">{{ profile.hna }}</p>

            <!-- Badges — part of identity, not a separate section. All of them go
                 through <UiBadge>: four semantic tokens (success = WoT verified,
                 warning = needs attention, secondary = standing, neutral = a fact
                 about the account), never a per-badge colour. A categorical badge
                 that needs its own identity gets a glyph, not a new hue. -->
            <div class="mt-2 flex items-center gap-1.5 flex-wrap">
              <!-- Verification Status -->
              <UiBadge v-if="profile.verifications_received_count >= 3" variant="success" type="soft" size="sm" class="gap-1">
                <Shield class="w-3.5 h-3.5" />{{ t('user_profile.verified') }}
              </UiBadge>
              <UiBadge v-else variant="neutral" type="soft" size="sm" class="gap-1.5">
                <Shield class="w-3.5 h-3.5" />{{ profile.verifications_received_count }}/3
                <span class="w-10 h-1.5 bg-neutral-300 dark:bg-neutral-600 rounded-full overflow-hidden">
                  <span
                    class="block h-full bg-neutral-500 dark:bg-neutral-400 rounded-full transition-all duration-300"
                    :style="{ width: `${(profile.verifications_received_count / 3) * 100}%` }"
                  ></span>
                </span>
              </UiBadge>

              <!-- Verification photo replaced — the verifications above were made against
                   the previous face, so say so next to them until 3 verifiers confirm it -->
              <Tooltip v-if="profile.photo_reconfirmation_needed" :text="t('user_profile.photo_reconfirmation_tooltip', { count: profile.photo_reconfirmation_count })">
                <UiBadge variant="warning" type="soft" size="sm" class="gap-1">
                  <AlertTriangle class="w-3.5 h-3.5" />{{ t('user_profile.photo_reconfirmation_badge') }} {{ profile.photo_reconfirmation_count }}/3
                </UiBadge>
              </Tooltip>

              <!-- Reputation Score — the star stays indigo: gold always means a 1–5 rating -->
              <Tooltip :text="t('user_profile.reputation_tooltip')">
                <button
                  @click="openReputationModal"
                  class="rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label="View reputation details"
                >
                  <UiBadge variant="secondary" type="soft" size="sm" class="gap-1">
                    <Star class="w-3.5 h-3.5" />{{ formatReputation(profile.reputation_score) }}
                  </UiBadge>
                </button>
              </Tooltip>

              <!-- Arbiter — a standing, so it belongs with identity rather than the counters -->
              <NuxtLink v-if="profile.is_arbiter" :to="localePath(`/arbiters/${profile.id}`)">
                <UiBadge variant="secondary" type="soft" size="sm" class="gap-1">
                  <Scale class="w-3.5 h-3.5" />{{ t('arbiter_stats.badge') }}
                </UiBadge>
              </NuxtLink>

              <!-- Supporter Badge -->
              <Tooltip v-if="profile.is_supporter" :text="$t('income.supporter_tooltip')">
                <UiBadge variant="warning" type="soft" size="sm" class="gap-1">
                  <Heart class="w-3.5 h-3.5" />{{ $t('income.supporter') }}
                </UiBadge>
              </Tooltip>

              <!-- Recurring-supporter count -->
              <Tooltip v-if="subStatus.subscriber_count > 0" :text="$t('subscriptions.supporters_tooltip')">
                <UiBadge variant="neutral" type="soft" size="sm" class="gap-1">
                  <HeartHandshake class="w-3.5 h-3.5" />{{ subStatus.subscriber_count }}
                </UiBadge>
              </Tooltip>

              <!-- Partnership Status -->
              <UiBadge v-if="authStore.isAuthenticated && partnershipStatus.they_added_me" variant="neutral" type="soft" size="sm" class="gap-1">
                <Users class="w-3.5 h-3.5" />{{ partnershipStatus.is_mutual ? t('user_profile.mutual_partner') : t('user_profile.they_added_you') }}
              </UiBadge>

              <!-- Bot Badge -->
              <UiBadge v-if="profile.is_bot" variant="neutral" type="soft" size="sm" class="gap-1">
                <Bot class="w-3.5 h-3.5" />Bot
              </UiBadge>

              <!-- Test Account Badge -->
              <UiBadge v-if="profile.is_test" variant="neutral" type="soft" size="sm" class="gap-1">
                <FlaskConical class="w-3.5 h-3.5" />Test
              </UiBadge>
            </div>

            <!-- Who vouched for this person — trust shown as faces, not a number.
                 Public by design: a verification is a signed statement and every
                 verifier is a PERSONAL profile, so the strip carries handle +
                 avatar only, never a gated display_name. The circles are rendered
                 as skeletons from the count the profile already knows, so the
                 layout never shifts when the payload lands. -->
            <button
              v-if="profile.verifications_received_count > 0 && !verificationsError"
              type="button"
              class="mt-2 flex items-center -space-x-2 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              :title="t('user_profile.verified_by')"
              :aria-label="t('user_profile.verified_by')"
              @click="showVerificationsModal('received')"
            >
              <template v-if="verifierStrip.length">
                <span
                  v-for="v in verifierStrip"
                  :key="v.id"
                  class="w-8 h-8 rounded-full ring-2 ring-white dark:ring-neutral-900 overflow-hidden bg-primary flex items-center justify-center text-xs font-semibold text-black"
                >
                  <img
                    v-if="v.verifier_avatar_url"
                    :src="v.verifier_avatar_url"
                    :alt="v.verifier_hna"
                    class="w-full h-full object-cover"
                  />
                  <template v-else>{{ (v.verifier_hna || '?')[0].toUpperCase() }}</template>
                </span>
              </template>
              <template v-else>
                <span
                  v-for="n in verifierSkeletonCount"
                  :key="`skeleton-${n}`"
                  class="w-8 h-8 rounded-full ring-2 ring-white dark:ring-neutral-900 bg-neutral-200 dark:bg-neutral-700 animate-pulse"
                ></span>
              </template>
              <span
                v-if="verifierOverflow > 0"
                class="w-8 h-8 rounded-full ring-2 ring-white dark:ring-neutral-900 bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-xs font-medium text-neutral-700 dark:text-neutral-300"
              >+{{ verifierOverflow }}</span>
            </button>
          </div>
        </div>

        <!-- Bio -->
        <p v-if="profile.bio" class="mt-3 text-sm text-neutral-700 dark:text-neutral-300">
          {{ profile.bio }}
        </p>

        <!-- New member -->
        <div v-if="!hasAnyStats && !profile.bio" class="mt-3">
          <div class="inline-flex items-center gap-1.5 px-3 py-1 bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 rounded-full text-xs text-neutral-600 dark:text-neutral-400">
            <Sprout class="w-3.5 h-3.5 text-success" />
            {{ t('user_profile.new_member') }}
          </div>
        </div>

        <!-- Page-level actions: sharing is about the page, not about a relationship
             with its owner, so it sits with the identity for every visitor instead
             of competing with the console below. Own profile also gets the tappable
             QR preview (→ large scannable code) and the way into the editor.
             Copy-link/QR/vCard all live in the share sheet, so no duplicate inline
             controls. -->
        <div class="flex items-center gap-3 mt-3">
          <button
            v-if="isOwnProfile"
            type="button"
            class="relative flex-shrink-0 rounded-lg transition hover:ring-2 hover:ring-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            :title="t('user_profile.show_qr_code')"
            :aria-label="t('user_profile.show_qr_code')"
            @click="openShareModal('qr')"
          >
            <div v-if="!ownQrGenerated" class="w-12 h-12 sm:w-16 sm:h-16 rounded-lg bg-neutral-100 dark:bg-neutral-800 animate-pulse"></div>
            <canvas v-show="ownQrGenerated" ref="ownQrCanvas" class="w-12 h-12 sm:w-16 sm:h-16 rounded-lg block" aria-hidden="true"></canvas>
          </button>
          <UiButton
            variant="ghost"
            size="sm"
            :icon="Share2"
            @click="openShareModal()"
          >
            {{ t('user_profile.share') }}
          </UiButton>
          <UiButton
            v-if="isOwnProfile"
            variant="ghost"
            size="sm"
            :icon="Pencil"
            :to="localePath('/profile')"
          >
            {{ t('user_profile.edit_profile') }}
          </UiButton>
        </div>
      </div>

      <!-- ========== Readout: what this member has actually done ==========
           One instrument cluster, not a grid of rounded rectangles: the numbers
           are data, and looking like buttons is exactly what made them compete
           with the console below. Number is the strongest text, caption is a
           mono uppercase micro-label (the market-card dialect); the cells that
           lead somewhere carry the standard primary-tint hover. -->
      <div v-if="statCells.length" class="flex flex-wrap gap-px bg-neutral-200 dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-700 rounded-xl overflow-hidden">
        <!-- Flex-wrap, not a fixed grid: cells stretch to fill whatever row they
             land on, so a count that doesn't divide by the column count can't
             leave a hairline-coloured hole at the end (same rule the tile matrix
             applies to its trailing tile). -->
        <component
          :is="statTag(cell)"
          v-for="cell in statCells"
          :key="cell.key"
          :to="cell.to"
          :type="cell.onClick ? 'button' : undefined"
          class="grow shrink basis-[88px] bg-white dark:bg-neutral-900 px-2 py-2.5 flex flex-col items-center justify-start gap-0.5"
          :class="cell.to || cell.onClick ? 'hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors' : ''"
          @click="cell.onClick?.()"
        >
          <span class="text-lg font-bold tabular-nums text-neutral-900 dark:text-neutral-100 leading-none">{{ cell.value }}</span>
          <span class="text-[9px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400 text-center leading-tight">{{ cell.label }}</span>
        </component>
      </div>

      <!-- ========== Console ==========
           One filled CTA carries the action a visitor came for; everything else
           is a tile matrix grouped by what it does to the relationship (reach /
           trust / business). Uniform tiles keep the block rectangular whatever
           a locale does to the labels — the old wrapped button rows re-broke per
           language — and nothing hides behind a disclosure any more. -->
      <div v-if="authStore.isAuthenticated && profile.id !== authStore.profile?.id" class="space-y-3">
        <UiButton variant="secondary" class="w-full" :icon="MessageCircle" :loading="messagingLoading" @click="messageUser">
          {{ t('user_profile.message') }}
        </UiButton>

        <!-- Frames sit side by side from sm up; each keeps its own column count,
             so a group never renders a hole where a tile is missing. -->
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 items-start">
          <UiTileMatrix
            v-for="group in consoleGroups"
            :key="group.id"
            :groups="[group]"
            fill="secondary"
            @pick="onConsolePick"
          />
        </div>
        <!-- Why a verifier is being asked to sign again -->
        <p v-if="canReconfirm" class="flex items-start gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <Info class="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{{ t('user_profile.reconfirm_hint') }}</span>
        </p>
        <!-- Why the verify button is disabled: target hasn't uploaded a WoT verification photo yet -->
        <p v-if="!profile.i_verified_them && canVerifyOthers && !profile.has_verification_photo" class="flex items-start gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <Info class="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{{ t('user_profile.verify_needs_photo') }}</span>
        </p>
        <!-- Why the verify button is disabled: the current user isn't allowed to verify others yet -->
        <p v-if="!profile.i_verified_them && !canVerifyOthers && verifyBlockedReason" class="flex items-start gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <Info class="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <i18n-t :keypath="verifyBlockedKey" tag="span">
            <template #link>
              <NuxtLink :to="localePath('/docs/wot')" class="text-link">{{ t('user_profile.verify_learn_more') }}</NuxtLink>
            </template>
          </i18n-t>
        </p>

        <!-- Block state notice -->
        <UiAlert v-if="profile.is_blocked_by_viewer" variant="warning" :icon="Ban" :title="t('moderation.blocked_badge')">
          {{ t('moderation.block_message') }}
        </UiAlert>

        <!-- Recurring-support status: shown to an active subscriber, with renew date + opt-out -->
        <div
          v-if="subStatus.is_subscriber && subStatus.subscription"
          class="flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-neutral-600 dark:text-neutral-400 pt-1"
        >
          <HeartHandshake class="w-3.5 h-3.5 text-secondary flex-shrink-0" />
          <span v-if="subStatus.subscription.cancelled_at">
            {{ t('subscriptions.access_until', { date: formatDateShort(subStatus.subscription.expires_at) }) }}
          </span>
          <span v-else>
            {{ t('subscriptions.renews_on', { amount: subStatus.subscription.amount_sats, date: formatDateShort(subStatus.subscription.expires_at) }) }}
          </span>
          <button
            v-if="!subStatus.subscription.cancelled_at"
            @click="cancelSupport"
            class="text-link hover:underline"
          >
            {{ t('subscriptions.cancel') }}
          </button>
        </div>
      </div>

      <!-- ========== Contact & Crypto ========== -->
      <div v-if="profile.ln_address || profile.pgp_fingerprint" class="pt-4 border-t border-neutral-200 dark:border-neutral-700 space-y-3 text-xs">
        <!-- Lightning Address -->
        <div v-if="profile.ln_address" class="flex items-center gap-2">
          <Zap class="w-4 h-4 text-amber-500 flex-shrink-0" />
          <button @click="copyLnAddress" class="inline-flex items-center gap-1.5 font-mono text-sm text-amber-600 dark:text-amber-400 hover:underline cursor-pointer">
            {{ profile.ln_address }}
            <Copy v-if="!lnAddressCopied" class="w-3.5 h-3.5" />
            <Check v-else class="w-3.5 h-3.5 text-success" />
          </button>
        </div>

        <!-- PGP keys — current key + full rotation history, full fingerprints, always visible (no toggle).
             Panels stay neutral: holding a key is a fact about the account, and the
             success token belongs to WoT verification — the badge alone says which
             key is current. -->

        <div v-if="profile.pgp_fingerprint" class="space-y-2">
          <div class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <Key class="w-4 h-4 text-neutral-500 dark:text-neutral-400 flex-shrink-0" />
            <span v-if="profile.created_at">{{ t('user_profile.pgp_verified_since') }} {{ formatDateShort(profile.created_at) }}</span>
            <span v-else>{{ t('user_profile.pgp_key_active') }}</span>
          </div>

          <div class="pl-6 space-y-1.5">
            <template v-if="visibleKeys.length">
              <div
                v-for="key in visibleKeys"
                :key="key.id"
                class="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/50 px-2.5 py-2"
              >
                <div class="flex items-center justify-between gap-2 mb-1.5">
                  <UiBadge
                    size="sm"
                    :type="key.is_active ? 'soft' : 'outline'"
                    :variant="key.is_active ? 'success' : ({ REVOKED: 'error', EXPIRED: 'neutral' }[key.action] || 'neutral')"
                  >
                    {{ key.is_active ? t('user_profile.pgp_current') : key.action }}
                  </UiBadge>
                  <span class="text-neutral-500 dark:text-neutral-400 tabular-nums">
                    {{ formatDateShort(key.valid_from) }}
                    <span v-if="key.valid_until"> – {{ formatDateShort(key.valid_until) }}</span>
                    <span v-else> – {{ t('user_profile.present') }}</span>
                  </span>
                </div>
                <div
                  class="font-mono break-all"
                  :class="key.is_active ? 'text-neutral-800 dark:text-neutral-200' : 'text-neutral-500 dark:text-neutral-400'"
                >
                  {{ key.fingerprint }}
                </div>
              </div>
            </template>
            <!-- Until the history loads (or if there is none): the current fingerprint, in full -->
            <div v-else class="font-mono bg-neutral-100 dark:bg-neutral-800 rounded-lg px-2.5 py-1.5 break-all">
              {{ profile.pgp_fingerprint }}
            </div>

            <!-- Expired/revoked keys collapse behind a toggle so they don't bury the listings below -->
            <button
              v-if="inactiveKeys.length"
              @click="showKeyHistory = !showKeyHistory"
              class="inline-flex items-center gap-1 text-link text-xs pt-0.5"
            >
              <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': showKeyHistory }" />
              {{ showKeyHistory ? t('user_profile.pgp_hide_history') : t('user_profile.pgp_show_history', { n: inactiveKeys.length }) }}
            </button>
          </div>
        </div>
      </div>

      <!-- ========== Listings (offers & seeks) — kept last so contact/crypto stays reachable without scrolling ========== -->
      <div v-if="profileItems.length" class="pt-4 border-t border-neutral-200 dark:border-neutral-700">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wide">
            {{ t('user_profile.listings') }}
          </h2>
          <NuxtLink
            v-if="profileItemsTotal > profileItems.length"
            :to="localePath(`/market?owner_id=${profile.id}`)"
            class="text-xs text-secondary hover:underline shrink-0"
          >
            {{ t('user_profile.view_all_listings') }} ({{ profileItemsTotal }})
          </NuxtLink>
        </div>
        <!-- Compact thumbnail strip (not full cards): the profile is an identity/trust
             card, so listings stay a one-row teaser; the full storefront lives at
             /market?owner_id=… behind the readout cells. SSR anchors kept for SEO. -->
        <div class="flex gap-3 overflow-x-auto pb-1">
          <NuxtLink
            v-for="it in profileItems"
            :key="it.id"
            :to="localePath(`/market/${it.slug || it.id}`)"
            class="w-24 flex-shrink-0 group"
          >
            <div class="relative w-24 h-24 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 bg-neutral-100 dark:bg-neutral-800 group-hover:border-primary transition-colors">
              <img
                v-if="it.images && it.images.length > 0"
                :src="it.images[0].url"
                :alt="it.title"
                class="w-full h-full object-cover"
                loading="lazy"
                decoding="async"
              >
              <div v-else class="w-full h-full flex items-center justify-center">
                <Package class="w-8 h-8 text-neutral-400 dark:text-neutral-500" />
              </div>
              <MarketListingType :item-type="it.item_type" size="sm" icon-only class="absolute top-1 left-1" />
            </div>
            <p class="mt-1 text-xs text-neutral-700 dark:text-neutral-300 truncate">{{ it.title }}</p>
          </NuxtLink>
        </div>
      </div>

      <!-- ========== Safety ==========
           Reporting and blocking are about the platform's relationship with an
           account, not about doing business with a person — so they stay out of
           the console and sit quietly at the end of the page, always available
           without a disclosure to open. -->
      <div
        v-if="authStore.isAuthenticated && profile.id !== authStore.profile?.id"
        class="pt-4 border-t border-neutral-200 dark:border-neutral-700 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs"
      >
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors"
          @click="showReportModal = true"
        >
          <Flag class="w-3.5 h-3.5" />{{ t('moderation.report') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 transition-colors"
          :class="profile.is_blocked_by_viewer
            ? 'text-error hover:text-error-700 dark:hover:text-error-400'
            : 'text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400'"
          :disabled="blockLoading"
          @click="toggleBlock"
        >
          <Loader2 v-if="blockLoading" class="w-3.5 h-3.5 animate-spin" />
          <Ban v-else class="w-3.5 h-3.5" />
          {{ profile.is_blocked_by_viewer ? t('moderation.unblock') : t('moderation.block') }}
        </button>
      </div>

      <!-- ========== Modals ========== -->

      <!-- Reputation Modal (6-dimension breakdown) -->
      <Modal
        v-model="showReputationModal"
        :title="t('user_profile.reputation_details_title')"
        :icon="Star"
        icon-class="text-secondary"
        size="lg"
      >
        <!-- Loading state -->
        <div v-if="reputationLoading" class="flex justify-center py-8">
          <Loader2 class="w-6 h-6 animate-spin text-neutral-400" />
        </div>

        <template v-else>
          <!-- Total score header (hidden for new users with < 2 active dimensions) -->
          <div v-if="!reputationBreakdown || reputationBreakdown.active_dimensions >= 2" class="bg-secondary-50 dark:bg-secondary-900/20 border border-secondary-200 dark:border-secondary-700 rounded-lg p-4 mb-4">
            <div class="text-center">
              <p class="text-sm text-secondary-700 dark:text-secondary-300 mb-1">{{ t('user_profile.reputation_total') }}</p>
              <p class="text-4xl font-bold text-secondary-900 dark:text-secondary-100">
                {{ reputationBreakdown ? formatReputation(reputationBreakdown.total) : formatReputation(profile.reputation_score) }}
              </p>
              <p class="text-xs text-secondary-600 dark:text-secondary-400 mt-1">/ 100</p>
            </div>
          </div>

          <!-- New user notice (shown instead of score when < 2 active dimensions) -->
          <div v-else class="bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 mb-4">
            <div class="text-center">
              <p class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ t('user_profile.reputation_score_not_yet') }}
              </p>
            </div>
          </div>

          <!-- 6 dimension bars -->
          <div class="space-y-3">
            <div v-for="dim in reputationDimensions" :key="dim.key" class="group">
              <div class="flex items-center justify-between mb-1">
                <div class="flex items-center gap-2">
                  <component :is="dim.icon" class="w-4 h-4 text-neutral-500 dark:text-neutral-400" />
                  <Tooltip :text="t(`user_profile.reputation_${dim.key}_desc`)">
                    <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300 cursor-help">
                      {{ t(`user_profile.reputation_${dim.key}`) }}
                    </span>
                  </Tooltip>
                </div>
                <span class="text-sm tabular-nums text-neutral-600 dark:text-neutral-400">
                  {{ dimensionValue(dim.key) }} / {{ dimensionMax(dim.key) }}
                </span>
              </div>
              <div class="w-full h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                <div
                  class="h-full bg-primary rounded-full transition-all duration-500"
                  :style="{ width: dimensionWidth(dim.key) }"
                ></div>
              </div>
            </div>
          </div>
        </template>

        <template #footer>
          <button
            @click="showReputationModal = false"
            class="btn-primary"
          >
            {{ t('user_profile.close') }}
          </button>
        </template>
      </Modal>

      <!-- Verifications Modal (pure display, stays inline) -->
      <Modal
        v-model="showVerificationsModalOpen"
        :title="verificationsModalType === 'received' ? t('user_profile.verifications_received') : t('user_profile.verifications_given')"
        :icon="Shield"
        icon-class="text-green-600"
        size="lg"
      >
        <!-- Loading -->
        <div v-if="verificationsLoading" class="flex justify-center py-8">
          <Loader2 class="w-6 h-6 animate-spin text-neutral-400 dark:text-neutral-500" />
        </div>

        <!-- List -->
        <div v-else-if="verificationsData.length > 0" class="space-y-3 max-h-[60vh] overflow-y-auto">
          <div
            v-for="v in verificationsData"
            :key="v.id"
            class="flex items-center justify-between p-3 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
          >
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-10 h-10 bg-primary rounded-full flex items-center justify-center text-black font-semibold flex-shrink-0 overflow-hidden">
                <img
                  v-if="verificationAvatarUrl(v)"
                  :src="verificationAvatarUrl(v)"
                  :alt="verificationDisplayHna(v)"
                  class="w-full h-full object-cover"
                />
                <template v-else>{{ verificationDisplayHna(v)?.[0]?.toUpperCase() || '?' }}</template>
              </div>
              <div class="min-w-0">
                <NuxtLink
                  :to="localePath(`/@${verificationLinkName(v)}`)"
                  class="font-medium text-neutral-900 dark:text-neutral-100 hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors truncate block"
                  @click="showVerificationsModalOpen = false"
                >
                  {{ verificationDisplayHna(v) }}
                </NuxtLink>
                <div class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ formatDateShort(v.verified_at) }}
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0 ml-2">
              <UiBadge
                size="sm"
                :variant="{ IN_PERSON: 'success', VIDEO_CALL: 'secondary', DOCUMENTS: 'neutral', VOUCHED: 'warning' }[v.verification_method] || 'neutral'"
              >
                {{ t(`user_profile.verification_method.${v.verification_method}`) }}
              </UiBadge>
              <Shield v-if="v.has_signed" class="w-3.5 h-3.5 text-green-600 dark:text-green-400" :title="t('user_profile.pgp_signed')" />
            </div>
          </div>
        </div>

        <!-- Empty -->
        <div v-else class="text-center py-8">
          <CheckCircle class="w-12 h-12 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ verificationsModalType === 'received' ? t('user_profile.no_verifications_received') : t('user_profile.no_verifications_given') }}
          </p>
        </div>

        <template #footer>
          <button
            @click="showVerificationsModalOpen = false"
            class="btn-primary"
          >
            {{ t('user_profile.close') }}
          </button>
        </template>
      </Modal>

      <!-- Extracted sub-components -->
      <UserLightningPayModal v-model="showLightningPayModal" :profile="profile" />
      <UserLightningPayModal
        v-model="showSupportModal"
        :profile="profile"
        mode="subscribe"
        :preset-amount="subStatus.subscription?.amount_sats || 5000"
        @paid="onSupportPaid"
      />
      <UserCreateInvoiceModal v-model="showCreateInvoiceModal" :profile="profile" />
      <UserShareModal v-model="showShareModal" :profile="profile" :profile-url="profileUrl" :initial-qr="shareModalInitialQr" />
      <UserPrivateNoteModal v-model="showNoteModal" :profile="profile" :cri="cri" @note-changed="privateNote = $event" />
      <UserVerifyModal v-model="showVerifyModal" :profile="profile" @verified="onVerified" />
      <UserZenithModal v-model="showZenithModal" :profile="profile" />
      <ReportModal v-model="showReportModal" :object-id="profile.id" />
      <UiConfirmModal
        v-model="showBlockConfirm"
        :title="t('moderation.block_title')"
        :message="t('moderation.block_message')"
        :confirm-label="t('moderation.block')"
        variant="warning"
        :icon="Ban"
        :loading="blockLoading"
        @confirm="doBlock"
      />

      <!-- ID photo lightbox: second click on the flipped card zooms the already-fetched
           blob to natural size; closing flips the card back to the avatar -->
      <Teleport to="body">
        <div
          v-if="showIdPhotoLightbox && idPhotoObjectUrl"
          class="fixed inset-0 z-[200] bg-black/90 flex items-center justify-center"
          @click.self="closeIdPhotoLightbox"
        >
          <button
            @click="closeIdPhotoLightbox"
            class="absolute top-4 right-4 p-2 text-white/80 hover:text-white"
            :aria-label="t('user_profile.close')"
          >
            <X class="w-6 h-6" />
          </button>
          <img
            :src="idPhotoObjectUrl"
            :alt="t('user_profile.id_photo')"
            class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
          />
          <div
            class="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-white text-sm"
            :class="profile.id_photo_verified ? 'bg-green-500' : 'bg-amber-500'"
          >
            <Shield v-if="profile.id_photo_verified" class="w-4 h-4" />
            <AlertTriangle v-else class="w-4 h-4" />
            {{ t('user_profile.id_photo') }}
          </div>
        </div>
      </Teleport>
    </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { resolveComponent } from 'vue'
import {
  AlertTriangle, CheckCircle, Bitcoin, Heart, HeartHandshake, Loader2, Package, Shield, Star,
  UserPlus, UserMinus, Users, MessageCircle, Zap, FileText, Share2, MapPin, Flag, Ban,
  Copy, Check, StickyNote, Key, Bot, Phone, X, Pencil, Receipt,
  ShieldCheck, Handshake, Gift, Vote, Scale, Sprout, ChevronDown, Info,
  FlaskConical, Lock, Mic
} from 'lucide-vue-next'
import QRCode from 'qrcode'

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const subs = useSubscriptions()
const { apiErrorMessage } = useApiError()

// Get CRI (Cryptographic Resource Identifier) from route params - can be ULID or local_name
const route = useRoute()
const localePath = useLocalePath()
// The route param may arrive as a full HNA (local_name@domain) from shared
// links — profile lookups accept only ULID/local_name, so use the local part
const cri = (route.params.name as string).split('@')[0]

// SSR profile fetch (public, no auth) for SEO
const { data: profileData } = await useAsyncData(
  `profile-${cri}`,
  () => $fetch(`/api/v1/profiles/${cri}/`),
  { server: true }
)

// Public listings (offers & seeks) — shown inline so a visitor arriving from a
// market listing (clicking the seller's name) sees what else they offer/seek
// without re-running a search filter. SSR-rendered for SEO.
const { data: profileItemsData } = await useAsyncData(
  `profile-items-${cri}`,
  () => profileData.value?.id
    ? $fetch(`/api/v1/items/?owner_id=${profileData.value.id}&is_active=true&page_size=12`)
    : Promise.resolve({ items: [], count: 0 }),
  { server: true }
)
const profileItems = computed(() => profileItemsData.value?.items || [])
const profileItemsTotal = computed(() => profileItemsData.value?.count || 0)

// State
const profile = ref(profileData.value)
const loading = ref(!profileData.value)
const error = ref(null)

// SEO meta (reactive, works with SSR data)
useSeoMeta({
  title: () => profile.value?.display_name
    ? `${profile.value.display_name} - Parahub`
    : t('user_profile.title') + ' - Parahub',
  ogTitle: () => profile.value?.display_name || t('user_profile.title'),
  description: () => t('user_profile.meta_description', { hna: profile.value?.hna || 'user' }),
  ogDescription: () => t('user_profile.meta_description', { hna: profile.value?.hna || 'user' }),
  ogImage: () => profile.value?.avatar_url
    ? `https://parahub.io${profile.value.avatar_url}`
    : 'https://parahub.io/og-image.jpg',
  ogType: 'profile',
  twitterCard: 'summary',
})

// Person JSON-LD
useHead({
  script: computed(() => {
    if (!profile.value) return []
    const p = profile.value as any
    const jsonLd: Record<string, any> = {
      '@context': 'https://schema.org',
      '@type': 'Person',
      'name': p.display_name || p.hna,
      'url': `https://parahub.io/@${cri}`,
    }
    if (p.avatar_url) jsonLd.image = `https://parahub.io${p.avatar_url}`
    return [{ type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd) }]
  })
})
const partnershipStatus = ref({
  i_added_them: false,
  they_added_me: false,
  is_mutual: false
})
const addingPartner = ref(false)
const messagingLoading = ref(false)
const callingLoading = ref(false)
const showIdPhoto = ref(false)
// id_photo is private — fetched as an authed blob (the API returns a gated
// /id-photo/ endpoint URL only to the owner or WoT-verified viewers)
const idPhotoObjectUrl = ref<string | null>(null)
const publicPGPHistory = ref<any[]>([])
// PGP key list: current key shown by default, expired/revoked keys collapsed behind a toggle
const showKeyHistory = ref(false)
const activeKey = computed(() => publicPGPHistory.value.find(k => k.is_active) || null)
const inactiveKeys = computed(() => publicPGPHistory.value.filter(k => !k.is_active))
const visibleKeys = computed(() => showKeyHistory.value ? publicPGPHistory.value : (activeKey.value ? [activeKey.value] : []))

// Modals
const showVerifyModal = ref(false)
const showReputationModal = ref(false)
const reputationBreakdown = ref<any>(null)
const reputationLoading = ref(false)
const showLightningPayModal = ref(false)
const showSupportModal = ref(false)
const showCreateInvoiceModal = ref(false)
const showShareModal = ref(false)
// When opened from the inline QR preview, the share sheet starts on the large QR;
// every other trigger opens it copy-link-first.
const shareModalInitialQr = ref(false)
const openShareModal = (view?: 'qr') => {
  shareModalInitialQr.value = view === 'qr'
  showShareModal.value = true
}
const showNoteModal = ref(false)
const showVerificationsModalOpen = ref(false)
const verificationsModalType = ref<'received' | 'given'>('received')
const verificationsLoading = ref(false)
const verificationsData = ref<any[]>([])
// Public verifications payload, fetched once and shared by the verifier strip
// and the modal. `verificationsError` hides the strip rather than leaving it
// pulsing forever when the fetch fails.
const verificationsCache = ref<{ received: any[], given: any[] } | null>(null)
const verificationsError = ref(false)
let verificationsRequest: Promise<{ received: any[], given: any[] }> | null = null

const verifierStrip = computed(() => (verificationsCache.value?.received || []).slice(0, 7))
const verifierSkeletonCount = computed(() => Math.min(profile.value?.verifications_received_count || 0, 7))
const verifierOverflow = computed(() => Math.max(0, (profile.value?.verifications_received_count || 0) - 7))
const showZenithModal = ref(false)

// Recurring support (subscription) status for this profile
const subStatus = ref<any>({ subscriber_count: 0, is_subscriber: false, subscription: null })
const subscribing = ref(false)

// Private note (for button amber styling, updated via @note-changed)
const privateNote = ref('')

// Verification permissions (for v-if on button)
const canVerifyOthers = ref(false)
// Why the current user can't verify others ('not_personal' | 'no_pgp' | 'not_verified' | null)
const verifyBlockedReason = ref<string | null>(null)
const verifyBlockedKey = computed(() => {
  if (verifyBlockedReason.value === 'not_personal') return 'user_profile.verify_blocked_not_personal'
  if (verifyBlockedReason.value === 'no_pgp') return 'user_profile.verify_blocked_no_pgp'
  return 'user_profile.verify_blocked_not_verified'
})

// This viewer verified the profile before it replaced its verification photo:
// the signature stands, but it attests to a face that is no longer on file.
// Signing again over the new photo is what clears the pending round.
const canReconfirm = computed(() => Boolean(
  profile.value?.i_verified_them
  && profile.value?.photo_reconfirmation_needed
  && profile.value?.has_verification_photo
  && canVerifyOthers.value
))

// Zenith status (for v-if on button)
const zenithStatus = ref({
  enabled: false,
  can_ask: false,
  reason: null as string | null
})

// Lightning Address copy
const lnAddressCopied = ref(false)

// Own profile detection
const isOwnProfile = computed(() => {
  return authStore.isAuthenticated && profile.value?.id === authStore.profile?.id
})

// Own profile QR
const ownQrCanvas = ref<HTMLCanvasElement | null>(null)
const ownQrGenerated = ref(false)

const hasAnyStats = computed(() => {
  if (!profile.value) return false
  const p = profile.value as any
  return (p.items_credit_count > 0 || p.items_debit_count > 0 ||
    p.verifications_received_count > 0 || p.verifications_given_count > 0 ||
    p.invited_count > 0 || p.contracts_active_count > 0 || p.contracts_completed_count > 0 ||
    p.debts_active_count > 0 || p.debts_settled_count > 0 || p.is_arbiter ||
    p.rentable_count > 0)
})

// ===== Readout cells =====
// One list instead of eleven near-identical blocks in the template: a cell is a
// number, its caption, and (usually) where it leads. Zero-valued facts stay out
// — an empty counter is noise on an identity card.
const NuxtLinkComponent = resolveComponent('NuxtLink')
const statTag = (cell: { to?: string; onClick?: () => void }) =>
  cell.to ? NuxtLinkComponent : (cell.onClick ? 'button' : 'div')

const statCells = computed(() => {
  const p = profile.value as any
  if (!p) return []
  const handle = p.hna?.split('@')[0] || p.id
  const cells: Array<{ key: string; value: number; label: string; to?: string; onClick?: () => void }> = []

  if (p.items_credit_count > 0) cells.push({ key: 'offers', value: p.items_credit_count, label: t('user_profile.offers'), to: localePath(`/market?owner_id=${p.id}&type=CREDIT`) })
  if (p.items_debit_count > 0) cells.push({ key: 'seeks', value: p.items_debit_count, label: t('user_profile.seeks'), to: localePath(`/market?owner_id=${p.id}&type=DEBIT`) })
  if (p.rentable_count > 0) cells.push({ key: 'rental', value: p.rentable_count, label: t('user_profile.stat_rental'), to: localePath(`/rental/u/${handle}`) })
  if (p.verifications_received_count > 0) cells.push({ key: 'verified_by', value: p.verifications_received_count, label: t('user_profile.verified_by'), onClick: () => showVerificationsModal('received') })
  if (p.verifications_given_count > 0) cells.push({ key: 'verified_others', value: p.verifications_given_count, label: t('user_profile.verified_others'), onClick: () => showVerificationsModal('given') })
  if (p.invited_count > 0) cells.push({ key: 'invited', value: p.invited_count, label: t('user_profile.invited') })
  if (p.invited_verified_count > 0) cells.push({ key: 'rooted', value: p.invited_verified_count, label: t('user_profile.invited_rooted') })
  if (p.contracts_active_count > 0) cells.push({ key: 'contracts_active', value: p.contracts_active_count, label: t('user_profile.contracts_active'), to: localePath('/contracts?status=SIGNED') })
  if (p.contracts_completed_count > 0) cells.push({ key: 'contracts_completed', value: p.contracts_completed_count, label: t('user_profile.contracts_completed'), to: localePath('/contracts?status=COMPLETED') })
  if (p.debts_active_count > 0) cells.push({ key: 'debts_active', value: p.debts_active_count, label: t('user_profile.debts_active'), to: localePath('/wallet/debts') })
  if (p.debts_settled_count > 0) cells.push({ key: 'debts_settled', value: p.debts_settled_count, label: t('user_profile.debts_settled'), to: localePath('/wallet/debts') })

  return cells
})

// ===== Console =====
// The verify tile always occupies its slot, in whatever state the viewer is in:
// a missing tile can't explain itself, and the reasons under the frame need
// something to point at.
const verifyTile = computed(() => {
  const p = profile.value as any
  if (canReconfirm.value) return { id: 'verify', icon: ShieldCheck, label: t('user_profile.tile_reconfirm'), tone: 'warning' as const }
  if (p?.i_verified_them) return { id: 'verify', icon: ShieldCheck, label: t('user_profile.tile_verified_by_you'), tone: 'success' as const, disabled: true }
  if (canVerifyOthers.value && p?.has_verification_photo) return { id: 'verify', icon: ShieldCheck, label: t('user_profile.tile_verify'), tone: 'success' as const }
  return { id: 'verify', icon: ShieldCheck, label: t('user_profile.tile_verify'), disabled: true }
})

const consoleGroups = computed(() => {
  const p = profile.value as any
  if (!p) return []
  const handle = p.hna?.split('@')[0] || p.id

  const contact: any[] = [
    { id: 'call', icon: Phone, label: t('user_profile.call'), loading: callingLoading.value },
    { id: 'voice', icon: Mic, label: t('user_profile.voice_note'), to: localePath(`/talk/${handle}`) },
  ]
  if (zenithStatus.value.can_ask) contact.push({ id: 'zenith', icon: Bot, label: 'Zenith' })

  const trust: any[] = [
    {
      id: 'partner',
      icon: partnershipStatus.value.i_added_them ? UserMinus : UserPlus,
      label: partnershipStatus.value.i_added_them ? t('user_profile.tile_partner_added') : t('user_profile.tile_partner_add'),
      active: partnershipStatus.value.i_added_them,
      loading: addingPartner.value,
    },
    verifyTile.value,
    { id: 'note', icon: StickyNote, label: t('user_profile.tile_note'), dot: Boolean(privateNote.value) },
  ]

  const business: any[] = [{ id: 'lightning', icon: Zap, label: 'Lightning' }]
  if (p.ln_address || p.spark_address) {
    business.push({
      id: 'support',
      icon: Heart,
      label: subStatus.value.is_subscriber ? t('user_profile.tile_supporting') : t('user_profile.tile_support'),
      active: subStatus.value.is_subscriber,
    })
  }
  business.push(
    { id: 'invoice', icon: Receipt, label: t('user_profile.tile_invoice') },
    { id: 'contract', icon: FileText, label: t('user_profile.tile_contract') },
    { id: 'debt', icon: Bitcoin, label: t('user_profile.tile_debt') },
  )

  // Column count per frame so the last row always fills: 4 tiles read as 2×2,
  // everything else as rows of three (the matrix widens a trailing tile itself).
  return [
    { id: 'contact', label: t('user_profile.group_contact'), items: contact, cols: contact.length },
    { id: 'trust', label: t('user_profile.group_trust'), items: trust, cols: 3 },
    { id: 'business', label: t('user_profile.group_business'), items: business, cols: business.length === 4 ? 2 : 3 },
  ]
})

const onConsolePick = (id: string) => {
  switch (id) {
    case 'call': callUser(); break
    case 'zenith': showZenithModal.value = true; break
    case 'partner': togglePartner(); break
    case 'verify': showVerifyModal.value = true; break
    case 'note': showNoteModal.value = true; break
    case 'lightning': showLightningPayModal.value = true; break
    case 'support': showSupportModal.value = true; break
    case 'invoice': showCreateInvoiceModal.value = true; break
    case 'contract': navigateTo(localePath(`/contracts?partner=${profile.value.id}`)); break
    case 'debt': navigateTo(localePath(`/wallet/debts?partner=${profile.value.id}`)); break
  }
}

// Computed
const profileUrl = computed(() => {
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/@${cri}`
  }
  return `https://parahub.io/@${cri}`
})

const userInitials = computed(() => {
  if (!profile.value) return 'U'
  const hna = profile.value.hna || ''
  const parts = hna.split('@')
  const name = parts[0] || 'U'
  return name.charAt(0).toUpperCase()
})

const avatarUrl = computed(() => profile.value?.avatar_url || null)

// A handle the platform holds — the API answers with a stripped stub carrying
// only `account_kind` ('bot' | 'test' | 'reserved'), never member data.
const heldKind = computed<string | null>(() => profile.value?.account_kind || null)
const heldHandle = computed(() => `@${(profile.value?.hna || '').split('@')[0]}`)
const heldIcon = computed(() => ({ bot: Bot, test: FlaskConical, reserved: Lock }[heldKind.value as string] || Lock))

// Fetch profile on mount (re-fetch with auth for partnership-gated fields)
onMounted(async () => {
  if (authStore.isAuthenticated) {
    // Always re-fetch with auth to get partnership-gated fields
    await fetchProfile()
    // A held handle carries no member data — partnership/verification/zenith
    // lookups have nothing to work with
    if (heldKind.value) return
    await checkPartnershipStatus()
    await checkVerificationPermissions()
    await checkZenithStatus()
  } else if (!profileData.value) {
    // SSR fetch failed or no data — fetch client-side
    await fetchProfile()
  }
  if (heldKind.value) return

  // Generate QR code after mount (DOM + canvas ref guaranteed ready)
  if (isOwnProfile.value) {
    await generateOwnQRCode()
  }

  // PGP key history is public + short — load it eagerly so the current key
  // and rotation history render in full without an extra click
  if (profile.value?.pgp_fingerprint) {
    loadPGPHistory()
  }

  // Verifier faces render right under the badges — load them with the page
  // instead of waiting for the modal to be opened
  if (profile.value?.verifications_received_count > 0) {
    loadVerifications().catch(() => {})
  }

  // Recurring-support count (public) + viewer's own status (if signed in)
  loadSubStatus()
})

const fetchProfile = async () => {
  loading.value = true
  error.value = null

  try {
    const fetchOptions: any = {}

    if (authStore.isAuthenticated) {
      await authStore.ensureToken()

      if (authStore.token) {
        fetchOptions.credentials = 'include'
        fetchOptions.headers = {
          'Authorization': `Bearer ${authStore.token}`
        }
      }
    }

    const response = await $fetch(`/api/v1/profiles/${cri}/`, fetchOptions)
    profile.value = response
  } catch (err: any) {
    console.error('Failed to fetch profile:', err)
    error.value = err.statusCode === 404
      ? t('user_profile.not_found_desc_404')
      : t('user_profile.not_found_desc_error')
  } finally {
    loading.value = false
  }
}

const checkPartnershipStatus = async () => {
  try {
    await authStore.ensureToken()
    const response = await $fetch(`/api/v1/partners/status/${cri}/`, {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    partnershipStatus.value = response
  } catch (err) {
    console.error('Failed to check partnership status:', err)
  }
}

const checkVerificationPermissions = async () => {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/wot/my-status/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    canVerifyOthers.value = response.can_verify_others
    verifyBlockedReason.value = response.verify_blocked_reason ?? null
  } catch (err) {
    console.error('Failed to check verification permissions:', err)
    canVerifyOthers.value = false
    verifyBlockedReason.value = null
  }
}

const togglePartner = async () => {
  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login'))
    return
  }

  addingPartner.value = true
  try {
    await authStore.ensureToken()

    if (partnershipStatus.value.i_added_them) {
      await $fetch(`/api/v1/partners/${cri}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`
        }
      })
      toastStore.success(t('user_profile.partner_removed_success'))
    } else {
      await $fetch(`/api/v1/partners/add/${cri}/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${authStore.token}`
        }
      })
      toastStore.success(t('user_profile.partner_added_success'))
    }

    await checkPartnershipStatus()
  } catch (err: any) {
    console.error('Failed to toggle partner:', err)
    toastStore.error(err.data?.error || t('user_profile.partner_toggle_failed'))
  } finally {
    addingPartner.value = false
  }
}

// First click flips avatar → ID photo; second click zooms it in a lightbox.
// Closing the lightbox flips the card back to the avatar.
const showIdPhotoLightbox = ref(false)

const avatarFlipTitle = computed(() => {
  if (!profile.value?.id_photo_url) return ''
  return showIdPhoto.value && idPhotoObjectUrl.value
    ? t('user_profile.click_to_enlarge')
    : t('user_profile.click_to_flip')
})

const toggleAvatarFlip = () => {
  const url = profile.value?.id_photo_url
  if (!url) return
  if (showIdPhoto.value && idPhotoObjectUrl.value) {
    showIdPhotoLightbox.value = true
    return
  }
  showIdPhoto.value = !showIdPhoto.value
  // Fetched on intent, never on page load: every fetch of someone else's ID photo
  // is written to their access log, so merely opening the profile must not appear
  // there — and a private photo shouldn't travel to a viewer who never asked.
  if (showIdPhoto.value && !idPhotoObjectUrl.value) loadIdPhoto(url)
}

const closeIdPhotoLightbox = () => {
  showIdPhotoLightbox.value = false
  showIdPhoto.value = false
}

// Lightbox a11y: Esc close + body scroll lock. The overlay is Teleport'd to
// <body> so it escapes the page stacking context and covers the fixed navbar.
const onIdPhotoLightboxKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') closeIdPhotoLightbox()
}
watch(showIdPhotoLightbox, (open) => {
  if (open) {
    window.addEventListener('keydown', onIdPhotoLightboxKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    window.removeEventListener('keydown', onIdPhotoLightboxKeydown)
    document.body.style.overflow = ''
  }
})

// Fetch the gated id_photo as an authed blob → object URL for <img>.
// The endpoint re-checks auth server-side (owner or WoT-verified); a refusal or a
// network error flips the card back rather than leaving the spinner running
// forever — the next click retries.
const loadIdPhoto = async (url: string) => {
  if (!import.meta.client || !authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    const res = await fetch(url, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (!res.ok) throw new Error(`ID photo fetch failed: ${res.status}`)
    if (idPhotoObjectUrl.value) URL.revokeObjectURL(idPhotoObjectUrl.value)
    idPhotoObjectUrl.value = URL.createObjectURL(await res.blob())
  } catch (err) {
    console.error('Failed to load ID photo:', err)
    showIdPhoto.value = false
  }
}

// Drop a loaded blob if the photo goes away (owner deleted it, viewer lost access
// on re-fetch). Loading is click-driven — see toggleAvatarFlip.
watch(() => profile.value?.id_photo_url, (url) => {
  if (!url && idPhotoObjectUrl.value) {
    URL.revokeObjectURL(idPhotoObjectUrl.value)
    idPhotoObjectUrl.value = null
  }
})

onBeforeUnmount(() => {
  if (idPhotoObjectUrl.value) URL.revokeObjectURL(idPhotoObjectUrl.value)
  window.removeEventListener('keydown', onIdPhotoLightboxKeydown)
  document.body.style.overflow = ''
})

// Reputation breakdown dimensions config. `max` is only a fallback for the
// pre-fetch render — the ceilings ship with the breakdown response.
const reputationDimensions = [
  { key: 'identity', icon: ShieldCheck, max: 25 },
  { key: 'commerce', icon: Handshake, max: 15 },
  { key: 'community', icon: Users, max: 20 },
  { key: 'contribution', icon: Gift, max: 15 },
  { key: 'governance', icon: Vote, max: 15 },
  { key: 'reliability', icon: CheckCircle, max: 10 },
]

const dimensionMax = (key: string) => {
  const fromApi = reputationBreakdown.value?.maxima?.[key]
  return fromApi ?? reputationDimensions.find(d => d.key === key)?.max ?? 0
}

// Reliability sits at a neutral 5.0 until there is a commitment to measure —
// show that as "no data" rather than a half-filled bar.
const dimensionHasData = (key: string) =>
  key !== 'reliability' || reputationBreakdown.value?.reliability_has_data !== false

const dimensionValue = (key: string) => {
  if (!reputationBreakdown.value) return '0.0'
  if (!dimensionHasData(key)) return '—'
  return parseFloat(reputationBreakdown.value[key]).toFixed(1)
}

const dimensionWidth = (key: string) => {
  if (!reputationBreakdown.value || !dimensionHasData(key)) return '0%'
  const max = dimensionMax(key)
  if (!max) return '0%'
  return `${Math.min((parseFloat(reputationBreakdown.value[key]) / max) * 100, 100)}%`
}

// Fetch reputation breakdown when modal opens
const fetchReputationBreakdown = async () => {
  if (!profile.value?.id || reputationBreakdown.value) return
  reputationLoading.value = true
  try {
    const response = await $fetch(`/api/v1/wot/reputation-breakdown/${profile.value.id}/`)
    reputationBreakdown.value = response
  } catch (err) {
    console.error('Failed to fetch reputation breakdown:', err)
  } finally {
    reputationLoading.value = false
  }
}

const openReputationModal = () => {
  showReputationModal.value = true
  fetchReputationBreakdown()
}

// Format reputation score
const formatReputation = (score: number) => {
  const n = Number(score)
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return Number.isInteger(n) ? n.toString() : Math.round(n).toString()
}

// Format date for PGP history
const formatDateShort = (dateString: string) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return 'N/A'
  return new Intl.DateTimeFormat('en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }).format(date)
}

// Load public PGP key history (auto-loaded on mount; fails silently — the
// full current fingerprint stays visible as a fallback)
const loadPGPHistory = async () => {
  try {
    const response = await $fetch(`/api/v1/profiles/${cri}/keys/history/`)
    publicPGPHistory.value = response || []
  } catch (error) {
    console.error('Failed to load PGP history:', error)
  }
}

// Actions
const callUser = () => {
  if (!profile.value?.id) {
    toastStore.error(t('user_profile.call_user_error'))
    return
  }

  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login'))
    return
  }

  navigateTo({
    path: localePath('/call'),
    query: {
      target: profile.value.id
    }
  })
}

const messageUser = async () => {
  if (!profile.value?.account_id || !profile.value?.id) {
    toastStore.error(t('user_profile.message_user_error_missing_info'))
    return
  }

  if (!authStore.isAuthenticated) {
    navigateTo(localePath('/login'))
    return
  }

  messagingLoading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        target_account_id: profile.value.account_id
      }
    })

    if (response.success && response.room_id) {
      navigateTo({
        path: localePath('/chat'),
        query: {
          room_id: response.room_id
        }
      })
    } else {
      toastStore.error(response.error || t('user_profile.message_user_error'))
    }
  } catch (error) {
    console.error('Failed to create DM:', error)
    toastStore.error(apiErrorMessage(error, 'moderation.error_codes', t('user_profile.message_user_error')))
  } finally {
    messagingLoading.value = false
  }
}

// Stub functions with toast
const showMapStub = () => {
  toastStore.info(t('user_profile.map_coming_soon'), t('user_profile.feature_coming_soon'))
}

// --- Report & block (Play UGC policy) ---
const showReportModal = ref(false)
const showBlockConfirm = ref(false)
const blockLoading = ref(false)

const toggleBlock = () => {
  if (profile.value?.is_blocked_by_viewer) {
    doUnblock()
  } else {
    showBlockConfirm.value = true
  }
}

const doBlock = async () => {
  blockLoading.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/profiles/${profile.value.id}/block/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    profile.value.is_blocked_by_viewer = true
    showBlockConfirm.value = false
    toastStore.success(t('moderation.blocked_toast'))
  } catch (error) {
    console.error('Failed to block:', error)
    toastStore.error(t('moderation.block_error'))
  } finally {
    blockLoading.value = false
  }
}

const doUnblock = async () => {
  blockLoading.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/profiles/${profile.value.id}/block/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    profile.value.is_blocked_by_viewer = false
    toastStore.success(t('moderation.unblocked_toast'))
  } catch (error) {
    console.error('Failed to unblock:', error)
    toastStore.error(t('moderation.block_error'))
  } finally {
    blockLoading.value = false
  }
}

// One fetch of the public verifications payload feeds both the verifier strip
// and this modal — the strip loads it on mount, so opening the modal is instant.
const loadVerifications = () => {
  if (verificationsCache.value) return Promise.resolve(verificationsCache.value)
  if (!verificationsRequest) {
    verificationsRequest = $fetch<{ received: any[], given: any[] }>(`/api/v1/wot/profile/${profile.value.id}/`)
      .then((res) => {
        verificationsCache.value = { received: res.received || [], given: res.given || [] }
        return verificationsCache.value
      })
      .catch((err) => {
        console.error('Failed to fetch verifications:', err)
        verificationsError.value = true
        throw err
      })
      .finally(() => { verificationsRequest = null })
  }
  return verificationsRequest
}

const showVerificationsModal = async (type: 'received' | 'given') => {
  verificationsModalType.value = type
  showVerificationsModalOpen.value = true

  if (verificationsCache.value) {
    verificationsData.value = type === 'received' ? verificationsCache.value.received : verificationsCache.value.given
    return
  }

  verificationsData.value = []
  verificationsLoading.value = true
  try {
    const res = await loadVerifications()
    verificationsData.value = type === 'received' ? res.received : res.given
  } catch {
    // logged in loadVerifications
  } finally {
    verificationsLoading.value = false
  }
}

const verificationDisplayHna = (v: any) => {
  if (verificationsModalType.value === 'received') {
    return v.verifier_hna || v.verifier_cri
  }
  return v.verified_user_hna || v.verified_user_id
}

const verificationAvatarUrl = (v: any) => (
  verificationsModalType.value === 'received' ? v.verifier_avatar_url : v.verified_user_avatar_url
)

// A fresh signature adds a face to the strip, so the cached payload has to go
const onVerified = async () => {
  verificationsCache.value = null
  verificationsError.value = false
  await fetchProfile()
  if (profile.value?.verifications_received_count > 0) {
    loadVerifications().catch(() => {})
  }
}

// Profile link target: local part of the HNA (ULID fallbacks pass through as-is)
const verificationLinkName = (v: any) => verificationDisplayHna(v)?.split('@')[0]

// Lightning Address copy
const copyLnAddress = async () => {
  if (!profile.value?.ln_address) return
  try {
    await navigator.clipboard.writeText(profile.value.ln_address)
    lnAddressCopied.value = true
    toastStore.success(t('user_profile.ln_address_copied'))
    setTimeout(() => { lnAddressCopied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

// Generate QR code for own profile (inline preview; the large scannable code lives in the share sheet)
const generateOwnQRCode = async () => {
  await nextTick()
  if (ownQrCanvas.value) {
    try {
      const isDark = document.documentElement.classList.contains('dark')
      await QRCode.toCanvas(ownQrCanvas.value, profileUrl.value, {
        width: 80,
        margin: 1,
        color: {
          dark: isDark ? '#FFFFFF' : '#000000',
          light: isDark ? '#171717' : '#FFFFFF'
        }
      })
      ownQrGenerated.value = true
    } catch (err) {
      console.error('Failed to generate own QR code:', err)
    }
  }
}

// Zenith status check
const checkZenithStatus = async () => {
  if (!profile.value) return
  try {
    await authStore.ensureToken()
    const response = await $fetch(`/api/v1/zenith/status/${profile.value.id}`, {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    }) as any
    zenithStatus.value = response
  } catch (err) {
    console.error('Failed to check Zenith status:', err)
  }
}

// ===== Recurring support (subscription) =====

// Public subscriber count + (if signed in) the viewer's own status. Non-fatal.
const loadSubStatus = async () => {
  if (!profile.value?.id) return
  try {
    subStatus.value = await subs.getStatus(profile.value.id)
  } catch (err) {
    console.error('Failed to load subscription status:', err)
  }
}

// The pay modal reports a successful payment → record (or renew) the subscription.
const onSupportPaid = async (e: { amountSats: number; paymentHash: string }) => {
  if (subscribing.value || !profile.value?.id) return
  subscribing.value = true
  try {
    await subs.subscribe(profile.value.id, e.amountSats, e.paymentHash)
    toastStore.success(t('subscriptions.toast_subscribed', { name: profile.value.display_name || profile.value.hna }))
    await loadSubStatus()
  } catch (err: any) {
    console.error('Failed to record subscription:', err)
    toastStore.error(err.data?.detail || t('subscriptions.toast_failed'))
  } finally {
    subscribing.value = false
  }
}

const cancelSupport = async () => {
  const id = subStatus.value?.subscription?.id
  if (!id) return
  try {
    await subs.cancel(id)
    toastStore.success(t('subscriptions.toast_cancelled'))
    await loadSubStatus()
  } catch (err) {
    console.error('Failed to cancel subscription:', err)
    toastStore.error(t('subscriptions.toast_failed'))
  }
}

// Generate own profile QR when isOwnProfile changes (e.g., login while viewing profile)
watch(isOwnProfile, async (isOwn) => {
  if (isOwn) {
    await generateOwnQRCode()
  }
})
</script>

<style scoped>
/* 3D Flip Animation */
.perspective-500 {
  perspective: 500px;
}

.transform-style-3d {
  transform-style: preserve-3d;
}

.backface-hidden {
  backface-visibility: hidden;
}

.rotate-y-180 {
  transform: rotateY(180deg);
}
</style>
