<template>
  <div class="py-6 w-full">
    <div class="w-full px-4 sm:px-6 lg:px-8">
      <div class="max-w-3xl mx-auto w-full">
    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center items-center min-h-[400px]" role="status" aria-live="polite">
      <Loader2 class="h-12 w-12 animate-spin text-primary" aria-hidden="true" />
      <span class="sr-only">{{ t('common.loading') }}</span>
    </div>

    <!-- Error state -->
    <UiAlert v-else-if="error" variant="error" :title="t('user_profile.not_found_title')">
      <p>{{ error }}</p>
      <NuxtLink :to="localePath('/')" class="btn-primary btn-sm mt-3 inline-flex">
        {{ t('user_profile.return_home') }}
      </NuxtLink>
    </UiAlert>

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
            :title="profile.id_photo_url ? t('user_profile.click_to_flip') : ''"
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

            <!-- Badges — part of identity, not a separate section -->
            <div class="mt-2 flex items-center gap-1.5 flex-wrap">
        <!-- Verification Status -->
        <div v-if="profile.verifications_received_count >= 3" class="flex items-center gap-1 px-2.5 py-1 bg-success-50 dark:bg-success-950/30 border border-success-300 dark:border-success-700 rounded-full text-xs">
          <Shield class="w-3.5 h-3.5 text-success" />
          <span class="font-semibold text-success-700 dark:text-success-400">{{ t('user_profile.verified') }}</span>
        </div>
        <div v-else class="flex items-center gap-2 px-2.5 py-1 bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 rounded-full text-xs">
          <Shield class="w-3.5 h-3.5 text-neutral-400" />
          <span class="font-medium text-neutral-600 dark:text-neutral-400">{{ profile.verifications_received_count }}/3</span>
          <div class="w-12 h-1.5 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
            <div
              class="h-full bg-neutral-400 dark:bg-neutral-500 rounded-full transition-all duration-300"
              :style="{ width: `${(profile.verifications_received_count / 3) * 100}%` }"
            ></div>
          </div>
        </div>

        <!-- Reputation Score -->
        <Tooltip :text="t('user_profile.reputation_tooltip')">
          <button
            @click="openReputationModal"
            class="flex items-center gap-1 px-2.5 py-1 bg-secondary-50 dark:bg-secondary-950/30 border border-secondary-200 dark:border-secondary-800 rounded-full text-xs hover:bg-secondary-100 dark:hover:bg-secondary-900/40 transition-colors"
            aria-label="View reputation details"
          >
            <Star class="w-3.5 h-3.5 text-secondary" />
            <span class="font-semibold text-secondary-700 dark:text-secondary-400">{{ formatReputation(profile.reputation_score) }}</span>
          </button>
        </Tooltip>

        <!-- Supporter Badge -->
        <Tooltip v-if="profile.is_supporter" :text="$t('income.supporter_tooltip')">
          <div class="flex items-center gap-1 px-2.5 py-1 bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-700 rounded-full text-xs">
            <Heart class="w-3.5 h-3.5 text-amber-500" />
            <span class="font-semibold text-amber-700 dark:text-amber-400">{{ $t('income.supporter') }}</span>
          </div>
        </Tooltip>

        <!-- Recurring-supporter count -->
        <Tooltip v-if="subStatus.subscriber_count > 0" :text="$t('subscriptions.supporters_tooltip')">
          <div class="flex items-center gap-1 px-2.5 py-1 bg-rose-50 dark:bg-rose-950/30 border border-rose-300 dark:border-rose-700 rounded-full text-xs">
            <HeartHandshake class="w-3.5 h-3.5 text-rose-500" />
            <span class="font-semibold text-rose-700 dark:text-rose-400">{{ subStatus.subscriber_count }}</span>
          </div>
        </Tooltip>

        <!-- Partnership Status -->
        <div v-if="authStore.isAuthenticated && partnershipStatus.they_added_me" class="flex items-center gap-1 px-2.5 py-1 bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 rounded-full text-xs">
          <Users class="w-3.5 h-3.5 text-neutral-500 dark:text-neutral-400" />
          <span class="font-medium text-neutral-700 dark:text-neutral-300">
            {{ partnershipStatus.is_mutual ? t('user_profile.mutual_partner') : t('user_profile.they_added_you') }}
          </span>
        </div>

        <!-- Bot Badge -->
        <div v-if="profile.is_bot" class="flex items-center gap-1 px-2.5 py-1 bg-blue-50 dark:bg-blue-950/30 border border-blue-300 dark:border-blue-700 rounded-full text-xs">
          <Bot class="w-3.5 h-3.5 text-blue-500" />
          <span class="font-semibold text-blue-700 dark:text-blue-400">Bot</span>
        </div>

        <!-- Test Account Badge -->
        <div v-if="profile.is_test" class="flex items-center gap-1 px-2.5 py-1 bg-orange-50 dark:bg-orange-950/30 border border-orange-300 dark:border-orange-700 rounded-full text-xs">
          <FlaskConical class="w-3.5 h-3.5 text-orange-500" />
          <span class="font-semibold text-orange-700 dark:text-orange-400">Test</span>
        </div>
            </div>
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

        <!-- Share my profile (own profile): a tappable QR preview (→ large scannable
             code) next to one Share button. Copy-link/QR/vCard all live in the share
             sheet, so no duplicate inline controls. -->
        <div v-if="isOwnProfile" class="flex items-center gap-3 mt-3">
          <button
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
        </div>
      </div>

      <!-- ========== Stats ========== -->
      <div v-if="hasAnyStats">
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <NuxtLink v-if="profile.items_credit_count > 0" :to="localePath(`/market?owner_id=${profile.id}&type=CREDIT`)" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <Package class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.items_credit_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.offers') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.items_debit_count > 0" :to="localePath(`/market?owner_id=${profile.id}&type=DEBIT`)" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <ShoppingBag class="w-4 h-4 text-amber-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.items_debit_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.seeks') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.rentable_count > 0" :to="localePath(`/rental/u/${profile.hna?.split('@')[0] || profile.id}`)" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <CalendarClock class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.rentable_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('booking.board.link') }}</span></span>
          </NuxtLink>
          <button v-if="profile.verifications_received_count > 0" @click="showVerificationsModal('received')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors text-left">
            <CheckCircle class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.verifications_received_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.verified_by') }}</span></span>
          </button>
          <button v-if="profile.verifications_given_count > 0" @click="showVerificationsModal('given')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors text-left">
            <UserCheck class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.verifications_given_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.verified_others') }}</span></span>
          </button>
          <div v-if="profile.invited_count > 0" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg">
            <UserPlus class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.invited_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.invited') }}</span></span>
          </div>
          <NuxtLink v-if="profile.contracts_active_count > 0" :to="localePath('/contracts?status=SIGNED')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <FileText class="w-4 h-4 text-neutral-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.contracts_active_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.contracts_active') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.contracts_completed_count > 0" :to="localePath('/contracts?status=COMPLETED')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <CheckCircle class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.contracts_completed_count }}</strong> <span class="text-success-600 dark:text-success-400">{{ t('user_profile.contracts_completed') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.debts_active_count > 0" :to="localePath('/wallet/debts')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <Bitcoin class="w-4 h-4 text-warning flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.debts_active_count }}</strong> <span class="text-warning-600 dark:text-warning-400">{{ t('user_profile.debts_active') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.debts_settled_count > 0" :to="localePath('/wallet/debts')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <CheckCircle class="w-4 h-4 text-neutral-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.debts_settled_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.debts_settled') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.is_arbiter" :to="localePath(`/arbiters/${profile.id}`)" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <Scale class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm font-medium text-secondary-700 dark:text-secondary-400">{{ t('arbiter_stats.badge') }}</span>
          </NuxtLink>
        </div>
      </div>

      <!-- ========== Actions ========== -->
      <div v-if="authStore.isAuthenticated && profile.id !== authStore.profile?.id" class="space-y-2">
        <!-- Primary action row -->
        <div class="flex flex-wrap gap-2">
          <UiButton variant="secondary" size="sm" class="flex-1 min-w-0" :icon="MessageCircle" :loading="messagingLoading" @click="messageUser">
            {{ t('user_profile.message') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :icon="Phone" :loading="callingLoading" @click="callUser">
            {{ t('user_profile.call') }}
          </UiButton>
          <UiButton
            :variant="partnershipStatus.i_added_them ? 'outline-error' : 'outline'"
            size="sm"
            :icon="partnershipStatus.i_added_them ? UserMinus : UserPlus"
            :loading="addingPartner"
            @click="togglePartner"
          >
            {{ partnershipStatus.i_added_them ? t('user_profile.remove_from_partners') : t('user_profile.add_to_partners') }}
          </UiButton>
        </div>
        <!-- Secondary actions -->
        <div class="flex flex-wrap gap-2">
          <UiButton v-if="!profile.i_verified_them && canVerifyOthers && profile.has_verification_photo" variant="outline-success" size="sm" :icon="ShieldCheck" @click="showVerifyModal = true">
            {{ t('user_profile.verify_button') }}
          </UiButton>
          <UiButton v-else-if="!profile.i_verified_them && canVerifyOthers" variant="outline-success" size="sm" :icon="ShieldCheck" disabled>
            {{ t('user_profile.verify_button') }}
          </UiButton>
          <UiButton v-else-if="!profile.i_verified_them && !canVerifyOthers && verifyBlockedReason" variant="outline-success" size="sm" :icon="ShieldCheck" disabled>
            {{ t('user_profile.verify_button') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="Zap" @click="showLightningPayModal = true">
            {{ t('user_profile.send_lightning') }}
          </UiButton>
          <UiButton
            v-if="profile.ln_address || profile.spark_address"
            :variant="subStatus.is_subscriber ? 'outline-error' : 'ghost'"
            size="sm"
            :icon="Heart"
            @click="showSupportModal = true"
          >
            {{ subStatus.is_subscriber ? t('subscriptions.supporting') : t('subscriptions.support_monthly_btn') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="Share2" @click="openShareModal()">
            {{ t('user_profile.share') }}
          </UiButton>
          <UiButton v-if="zenithStatus.can_ask" variant="ghost" size="sm" :icon="Bot" @click="showZenithModal = true">
            {{ t('zenith.ask_zenith') }}
          </UiButton>
          <button @click="showMoreActions = !showMoreActions" class="btn-ghost btn-sm text-neutral-500 dark:text-neutral-400">
            <ChevronDown class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showMoreActions }" />
            {{ t('user_profile.more') }}
          </button>
        </div>
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
              <NuxtLink :to="localePath('/docs/wot')" class="text-primary hover:underline">{{ t('user_profile.verify_learn_more') }}</NuxtLink>
            </template>
          </i18n-t>
        </p>
        <div v-if="showMoreActions" class="flex flex-wrap gap-2">
          <UiButton variant="ghost" size="sm" :icon="FileText" @click="navigateTo(localePath(`/contracts?partner=${profile.id}`))">
            {{ t('user_profile.create_contract') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="Bitcoin" @click="navigateTo(localePath(`/wallet/debts?partner=${profile.id}`))">
            {{ t('user_profile.record_debt') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="FileText" @click="showCreateInvoiceModal = true">
            {{ t('user_profile.create_invoice') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="StickyNote" class="relative" @click="showNoteModal = true">
            {{ t('user_profile.private_note') }}
            <span v-if="privateNote" class="absolute -top-0.5 -right-0.5 w-2 h-2 bg-primary rounded-full"></span>
          </UiButton>
        </div>

        <!-- Recurring-support status: shown to an active subscriber, with renew date + opt-out -->
        <div
          v-if="subStatus.is_subscriber && subStatus.subscription"
          class="flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-neutral-600 dark:text-neutral-400 pt-1"
        >
          <HeartHandshake class="w-3.5 h-3.5 text-rose-500 flex-shrink-0" />
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

      <!-- Share — anonymous visitors only (own profile shares from the hero, members from the action row) -->
      <div v-else-if="!authStore.isAuthenticated">
        <UiButton variant="ghost" size="sm" :icon="Share2" @click="openShareModal()">
          {{ t('user_profile.share') }}
        </UiButton>
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

        <!-- PGP keys — current key + full rotation history, full fingerprints, always visible (no toggle) -->
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
                class="rounded-lg border px-2.5 py-2"
                :class="key.is_active
                  ? 'bg-success-50 dark:bg-success-950/30 border-success-300 dark:border-success-700'
                  : 'bg-neutral-50 dark:bg-neutral-800/50 border-neutral-200 dark:border-neutral-700'"
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
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <MarketItemCard v-for="it in profileItems" :key="it.id" :item="it" />
        </div>
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
                  {{ reputationBreakdown ? parseFloat(reputationBreakdown[dim.key]).toFixed(1) : '0.0' }} / {{ dim.max }}
                </span>
              </div>
              <div class="w-full h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                <div
                  class="h-full bg-primary rounded-full transition-all duration-500"
                  :style="{ width: reputationBreakdown ? `${Math.min((parseFloat(reputationBreakdown[dim.key]) / dim.max) * 100, 100)}%` : '0%' }"
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
          <Loader2 class="w-6 h-6 animate-spin text-primary" />
        </div>

        <!-- List -->
        <div v-else-if="verificationsData.length > 0" class="space-y-3 max-h-[60vh] overflow-y-auto">
          <div
            v-for="v in verificationsData"
            :key="v.id"
            class="flex items-center justify-between p-3 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
          >
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-10 h-10 bg-primary rounded-full flex items-center justify-center text-black font-semibold flex-shrink-0">
                {{ verificationDisplayHna(v)?.[0]?.toUpperCase() || '?' }}
              </div>
              <div class="min-w-0">
                <NuxtLink
                  :to="localePath(`/u/${verificationDisplayHna(v)}`)"
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
      <UserVerifyModal v-model="showVerifyModal" :profile="profile" @verified="fetchProfile" />
      <UserZenithModal v-model="showZenithModal" :profile="profile" />
    </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  AlertTriangle, CheckCircle, Bitcoin, Heart, HeartHandshake, Loader2, Package, Shield, ShoppingBag, Star,
  UserPlus, UserMinus, Users, MessageCircle, UserCheck, Zap, FileText, Share2, MapPin, Flag,
  Copy, Check, StickyNote, Key, Bot, Phone,
  ShieldCheck, Handshake, Gift, Vote, Scale, Sprout, ChevronDown, Info, CalendarClock
} from 'lucide-vue-next'
import QRCode from 'qrcode'

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()
const subs = useSubscriptions()

// Get CRI (Cryptographic Resource Identifier) from route params - can be ULID or local_name
const route = useRoute()
const localePath = useLocalePath()
const cri = route.params.name as string

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
    : Promise.resolve({ items: [], total: 0 }),
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
      'url': `https://parahub.io/u/${cri}`,
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

// Actions
const showMoreActions = ref(false)

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

// Computed
const profileUrl = computed(() => {
  if (typeof window !== 'undefined') {
    return `${window.location.origin}/u/${cri}`
  }
  return `https://parahub.io/u/${cri}`
})

const userInitials = computed(() => {
  if (!profile.value) return 'U'
  const hna = profile.value.hna || ''
  const parts = hna.split('@')
  const name = parts[0] || 'U'
  return name.charAt(0).toUpperCase()
})

const avatarUrl = computed(() => profile.value?.avatar_url || null)

// Fetch profile on mount (re-fetch with auth for partnership-gated fields)
onMounted(async () => {
  if (authStore.isAuthenticated) {
    // Always re-fetch with auth to get partnership-gated fields
    await fetchProfile()
    await checkPartnershipStatus()
    await checkVerificationPermissions()
    await checkZenithStatus()
  } else if (!profileData.value) {
    // SSR fetch failed or no data — fetch client-side
    await fetchProfile()
  }

  // Generate QR code after mount (DOM + canvas ref guaranteed ready)
  if (isOwnProfile.value) {
    await generateOwnQRCode()
  }

  // PGP key history is public + short — load it eagerly so the current key
  // and rotation history render in full without an extra click
  if (profile.value?.pgp_fingerprint) {
    loadPGPHistory()
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

// Toggle avatar flip to show ID photo
const toggleAvatarFlip = () => {
  if (profile.value?.id_photo_url) {
    showIdPhoto.value = !showIdPhoto.value
  }
}

// Fetch the gated id_photo as an authed blob → object URL for <img>.
// The endpoint re-checks auth server-side (owner or WoT-verified); on 403/404
// we simply leave the flip empty.
const loadIdPhoto = async (url: string) => {
  if (!import.meta.client || !authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    const res = await fetch(url, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (res.ok) {
      if (idPhotoObjectUrl.value) URL.revokeObjectURL(idPhotoObjectUrl.value)
      idPhotoObjectUrl.value = URL.createObjectURL(await res.blob())
    }
  } catch (err) {
    console.error('Failed to load ID photo:', err)
  }
}

watch(() => profile.value?.id_photo_url, (url) => {
  if (url) loadIdPhoto(url)
  else if (idPhotoObjectUrl.value) {
    URL.revokeObjectURL(idPhotoObjectUrl.value)
    idPhotoObjectUrl.value = null
  }
})

onBeforeUnmount(() => {
  if (idPhotoObjectUrl.value) URL.revokeObjectURL(idPhotoObjectUrl.value)
})

// Reputation breakdown dimensions config
const reputationDimensions = [
  { key: 'identity', icon: ShieldCheck, max: 25 },
  { key: 'commerce', icon: Handshake, max: 15 },
  { key: 'community', icon: Users, max: 20 },
  { key: 'contribution', icon: Gift, max: 15 },
  { key: 'governance', icon: Vote, max: 15 },
  { key: 'reliability', icon: CheckCircle, max: 10 },
]

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
    toastStore.error(t('user_profile.message_user_error'))
  } finally {
    messagingLoading.value = false
  }
}

// Stub functions with toast
const showMapStub = () => {
  toastStore.info(t('user_profile.map_coming_soon'), t('user_profile.feature_coming_soon'))
}

const showReportStub = () => {
  toastStore.info(t('user_profile.report_coming_soon'), t('user_profile.feature_coming_soon'))
}

const showVerificationsModal = async (type: 'received' | 'given') => {
  verificationsModalType.value = type
  verificationsData.value = []
  verificationsLoading.value = true
  showVerificationsModalOpen.value = true

  try {
    const res = await $fetch<{ received: any[], given: any[] }>(`/api/v1/wot/profile/${profile.value.id}/`)
    verificationsData.value = type === 'received' ? res.received : res.given
  } catch (err) {
    console.error('Failed to fetch verifications:', err)
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
