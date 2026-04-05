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
                  :src="profile.id_photo_url"
                  :alt="t('user_profile.id_photo')"
                  class="w-full h-full object-cover"
                />
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
            <p class="text-neutral-500 dark:text-neutral-400 font-mono text-xs sm:text-sm mt-0.5 truncate">{{ profile.hna }}</p>

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

        <!-- QR Code (own profile) -->
        <div v-if="isOwnProfile" class="flex items-center gap-3 mt-3">
          <div class="relative flex-shrink-0">
            <div v-if="!ownQrGenerated" class="w-11 h-11 sm:w-16 sm:h-16 rounded-lg bg-neutral-100 dark:bg-neutral-800 animate-pulse"></div>
            <canvas v-show="ownQrGenerated" ref="ownQrCanvas" class="w-11 h-11 sm:w-16 sm:h-16 rounded-lg" role="img" :aria-label="$t('user_profile.qr_aria_label')"></canvas>
          </div>
          <UiButton
            variant="ghost"
            size="sm"
            :icon="linkCopied ? Check : ClipboardCopy"
            @click="copyProfileLink"
          >
            {{ t('user_profile.copy_link') }}
          </UiButton>
        </div>
      </div>

      <!-- ========== Stats ========== -->
      <div v-if="hasAnyStats" class="rounded-xl overflow-hidden bg-neutral-200 dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-700">
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-px">
          <NuxtLink v-if="profile.items_credit_count > 0" :to="`/market?owner_id=${profile.id}&type=CREDIT`" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <Package class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.items_credit_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.offers') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.items_debit_count > 0" :to="`/market?owner_id=${profile.id}&type=DEBIT`" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <ShoppingBag class="w-4 h-4 text-amber-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.items_debit_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.seeks') }}</span></span>
          </NuxtLink>
          <button v-if="profile.verifications_received_count > 0" @click="showVerificationsModal('received')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors text-left">
            <CheckCircle class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.verifications_received_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.verified_by') }}</span></span>
          </button>
          <button v-if="profile.verifications_given_count > 0" @click="showVerificationsModal('given')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors text-left">
            <UserCheck class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.verifications_given_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.verified_others') }}</span></span>
          </button>
          <div v-if="profile.invited_count > 0" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900">
            <UserPlus class="w-4 h-4 text-secondary flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.invited_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.invited') }}</span></span>
          </div>
          <NuxtLink v-if="profile.contracts_active_count > 0" :to="localePath('/contracts?status=SIGNED')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <FileText class="w-4 h-4 text-neutral-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.contracts_active_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.contracts_active') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.contracts_completed_count > 0" :to="localePath('/contracts?status=COMPLETED')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <CheckCircle class="w-4 h-4 text-success flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.contracts_completed_count }}</strong> <span class="text-success-600 dark:text-success-400">{{ t('user_profile.contracts_completed') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.debts_active_count > 0" :to="localePath('/wallet/debts')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <Bitcoin class="w-4 h-4 text-warning flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.debts_active_count }}</strong> <span class="text-warning-600 dark:text-warning-400">{{ t('user_profile.debts_active') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.debts_settled_count > 0" :to="localePath('/wallet/debts')" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
            <CheckCircle class="w-4 h-4 text-neutral-500 flex-shrink-0" />
            <span class="text-sm"><strong class="text-neutral-900 dark:text-neutral-100">{{ profile.debts_settled_count }}</strong> <span class="text-neutral-500 dark:text-neutral-400">{{ t('user_profile.debts_settled') }}</span></span>
          </NuxtLink>
          <NuxtLink v-if="profile.is_arbiter" :to="localePath(`/arbiters/${profile.id}`)" class="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors">
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
          <UiButton v-if="!profile.i_verified_them && canVerifyOthers" variant="outline" size="sm" :icon="Shield" @click="showVerifyModal = true">
            {{ t('user_profile.verify_button') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="Zap" @click="showLightningPayModal = true">
            {{ t('user_profile.send_lightning') }}
          </UiButton>
          <UiButton variant="ghost" size="sm" :icon="Share2" @click="showShareModal = true">
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
      </div>

      <!-- Share only (non-authenticated or own profile) -->
      <div v-else>
        <UiButton variant="ghost" size="sm" :icon="Share2" @click="showShareModal = true">
          {{ t('user_profile.share') }}
        </UiButton>
      </div>

      <!-- ========== Contact & Crypto ========== -->
      <div v-if="profile.ln_address || profile.pgp_fingerprint" class="pt-4 border-t border-neutral-200 dark:border-neutral-700 space-y-2 text-xs">
        <!-- Lightning Address -->
        <div v-if="profile.ln_address" class="flex items-center gap-2">
          <Zap class="w-4 h-4 text-amber-500 flex-shrink-0" />
          <button @click="copyLnAddress" class="inline-flex items-center gap-1.5 font-mono text-sm text-amber-600 dark:text-amber-400 hover:underline cursor-pointer">
            {{ profile.ln_address }}
            <Copy v-if="!lnAddressCopied" class="w-3.5 h-3.5" />
            <Check v-else class="w-3.5 h-3.5 text-success" />
          </button>
        </div>

        <!-- PGP -->
        <div v-if="profile.pgp_fingerprint" class="flex items-center gap-2">
          <Key class="w-4 h-4 text-neutral-500 dark:text-neutral-400 flex-shrink-0" />
          <span class="text-sm text-neutral-600 dark:text-neutral-400">
            <span v-if="profile.created_at">{{ t('user_profile.pgp_verified_since') }} {{ formatDateShort(profile.created_at) }}</span>
            <span v-else>{{ t('user_profile.pgp_key_active') }}</span>
          </span>
          <button @click="showPGPAdvanced = !showPGPAdvanced" class="text-link text-xs ml-1">
            {{ showPGPAdvanced ? t('user_profile.hide_advanced') : t('user_profile.show_advanced') }}
          </button>
        </div>

        <!-- PGP Advanced -->
        <div v-if="showPGPAdvanced && profile.pgp_fingerprint" class="pl-6 space-y-2">
          <div class="font-mono text-xs bg-neutral-200 dark:bg-neutral-700 rounded px-2 py-1 break-all">
            {{ profile.pgp_fingerprint }}
          </div>
          <button v-if="!showPublicPGPHistory" @click="loadPGPHistory" class="text-link text-xs">
            {{ t('user_profile.view_history') }}
          </button>
          <div v-if="showPublicPGPHistory">
            <div v-if="publicPGPHistoryLoading" class="text-center py-2">
              <Loader2 class="w-4 h-4 animate-spin mx-auto" />
            </div>
            <div v-else-if="publicPGPHistory.length > 0" class="space-y-2">
              <div
                v-for="key in publicPGPHistory"
                :key="key.id"
                class="p-2 rounded border text-xs"
                :class="key.is_active
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700'
                  : 'bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-600'"
              >
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span class="font-mono" :class="key.is_active ? 'text-green-700 dark:text-green-300' : 'text-neutral-600 dark:text-neutral-400'">
                    {{ key.fingerprint.substring(0, 16) }}...
                  </span>
                  <UiBadge size="sm" :variant="{ CREATED: 'success', REVOKED: 'error', EXPIRED: 'warning' }[key.action] || 'neutral'">
                    {{ key.action }}
                  </UiBadge>
                </div>
                <div class="text-neutral-600 dark:text-neutral-400">
                  {{ formatDateShort(key.valid_from) }}
                  <span v-if="key.valid_until"> - {{ formatDateShort(key.valid_until) }}</span>
                  <span v-else> - {{ t('user_profile.present') }}</span>
                  <span class="text-neutral-500"> ({{ key.validity_days }}d)</span>
                </div>
              </div>
            </div>
          </div>
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
                  :to="`/u/${verificationDisplayHna(v)}`"
                  class="font-medium text-neutral-900 dark:text-neutral-100 hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors truncate block"
                  @click="showVerificationsModalOpen = false"
                >
                  {{ verificationDisplayHna(v) }}
                </NuxtLink>
                <div class="text-xs text-neutral-500 dark:text-neutral-400">
                  {{ formatDateShort(v.verified_at) }}
                </div>
                <div v-if="v.notes" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 truncate">
                  {{ v.notes }}
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
      <UserCreateInvoiceModal v-model="showCreateInvoiceModal" :profile="profile" />
      <UserShareModal v-model="showShareModal" :profile="profile" :profile-url="profileUrl" />
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
  AlertTriangle, CheckCircle, Bitcoin, Heart, Loader2, Package, Shield, ShoppingBag, Star,
  UserPlus, UserMinus, Users, MessageCircle, UserCheck, Zap, FileText, Share2, MapPin, Flag,
  Copy, Check, StickyNote, Key, Bot, Phone, ClipboardCopy,
  ShieldCheck, Handshake, Gift, Vote, Scale, Sprout, ChevronDown
} from 'lucide-vue-next'
import QRCode from 'qrcode'

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

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
const showPGPAdvanced = ref(false)
const showPublicPGPHistory = ref(false)
const showIdPhoto = ref(false)
const publicPGPHistory = ref([])
const publicPGPHistoryLoading = ref(false)

// Actions
const showMoreActions = ref(false)

// Modals
const showVerifyModal = ref(false)
const showReputationModal = ref(false)
const reputationBreakdown = ref<any>(null)
const reputationLoading = ref(false)
const showLightningPayModal = ref(false)
const showCreateInvoiceModal = ref(false)
const showShareModal = ref(false)
const showNoteModal = ref(false)
const showVerificationsModalOpen = ref(false)
const verificationsModalType = ref<'received' | 'given'>('received')
const verificationsLoading = ref(false)
const verificationsData = ref<any[]>([])
const showZenithModal = ref(false)

// Private note (for button amber styling, updated via @note-changed)
const privateNote = ref('')

// Verification permissions (for v-if on button)
const canVerifyOthers = ref(false)

// Zenith status (for v-if on button)
const zenithStatus = ref({
  enabled: false,
  can_ask: false,
  reason: null as string | null
})

// Lightning Address copy
const lnAddressCopied = ref(false)

// Own profile link copy
const linkCopied = ref(false)

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
    p.debts_active_count > 0 || p.debts_settled_count > 0 || p.is_arbiter)
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
  } catch (err) {
    console.error('Failed to check verification permissions:', err)
    canVerifyOthers.value = false
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

// Load public PGP key history
const loadPGPHistory = async () => {
  showPublicPGPHistory.value = true
  publicPGPHistoryLoading.value = true
  try {
    const response = await $fetch(`/api/v1/profiles/${cri}/keys/history/`)
    publicPGPHistory.value = response || []
  } catch (error) {
    console.error('Failed to load PGP history:', error)
    toastStore.error(t('user_profile.pgp_history_load_failed'))
  } finally {
    publicPGPHistoryLoading.value = false
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

// Own profile link copy
const copyProfileLink = async () => {
  try {
    await navigator.clipboard.writeText(profileUrl.value)
    linkCopied.value = true
    toastStore.success(t('user_profile.link_copied'))
    setTimeout(() => { linkCopied.value = false }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
    toastStore.error(t('user_profile.link_copy_failed'))
  }
}

// Generate QR code for own profile (shown inline, not in modal)
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

// Generate own profile QR when isOwnProfile changes (e.g., login while viewing profile)
watch(isOwnProfile, async (isOwn) => {
  if (isOwn) {
    await generateOwnQRCode()
  }
})
</script>

<style scoped>
.btn-ghost {
  @apply px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 bg-transparent hover:bg-neutral-200 dark:hover:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded-lg transition-colors;
}

.btn-ghost:disabled {
  @apply opacity-50 cursor-not-allowed hover:bg-transparent dark:hover:bg-transparent;
}

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
