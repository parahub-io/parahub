<template>
  <div class="pb-20">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12" role="status" aria-live="polite">
      <div class="animate-spin rounded-full h-12 w-12 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-700 dark:border-t-neutral-100" aria-hidden="true" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="py-12 text-center max-w-md mx-auto px-4">
      <div class="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
        <AlertCircle class="w-8 h-8 text-red-600 dark:text-red-400" />
      </div>
      <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('directory.establishments.empty_title') }}</h2>
      <p class="text-neutral-600 dark:text-neutral-400 mb-4 text-sm">{{ error }}</p>
      <UiButton variant="primary" size="sm" @click="navigateTo(localePath('/directory') + '#organizations')">
        {{ $t('directory.tabs.organizations') }}
      </UiButton>
    </div>

    <!-- Content -->
    <div v-else-if="establishment" class="pb-6">

      <!-- Back link — neutral strip above the band (keeps the band a pure identity hero) -->
      <div class="max-w-3xl mx-auto px-4 sm:px-6 pt-4">
        <UiButton variant="ghost" size="sm" :icon="ArrowLeft" @click="goBack" class="-ml-2">
          {{ $t('directory.tabs.organizations') }}
        </UiButton>
      </div>

      <!-- Yellow header band (identity) — full-bleed, like /docs/mission. Dark text on yellow in both themes. -->
      <div class="org-header border-b border-primary/40 dark:border-primary/30">
        <div class="max-w-3xl mx-auto px-4 sm:px-6 py-5 sm:py-6">
          <!-- Name + verified + rating -->
          <div class="flex items-start gap-3">
            <!-- Logo slot: shows the logo when set; for the owner when empty, a
                 dashed placeholder nudging them to add one (links to edit form) -->
            <img
              v-if="establishment.logo_url"
              :src="establishment.logo_url"
              alt=""
              class="w-16 h-16 rounded-lg object-contain flex-shrink-0"
            />
            <NuxtLink
              v-else-if="isOwner"
              :to="localePath(`/org/${establishment.slug || props.id}/edit`)"
              :title="$t('directory.form.logo_upload')"
              class="w-16 h-16 rounded-lg border border-dashed border-neutral-900/30 hover:border-neutral-900/60 bg-white/40 hover:bg-white/70 flex flex-col items-center justify-center gap-0.5 text-neutral-900/70 hover:text-neutral-900 flex-shrink-0 transition-colors"
            >
              <ImagePlus class="w-5 h-5" />
              <span class="text-[10px] font-medium leading-none">{{ $t('directory.form.logo') }}</span>
            </NuxtLink>

            <div class="flex-1 min-w-0">
              <h1 class="text-xl sm:text-2xl font-bold text-neutral-900 flex items-center gap-2 flex-wrap">
                {{ establishment.name }}
                <BadgeCheck v-if="establishment.is_verified" class="w-5 h-5 sm:w-6 sm:h-6 text-secondary flex-shrink-0" />
              </h1>

              <!-- Category + inline meta (category · type · views · members · legal id) -->
              <div class="flex items-center gap-x-2 gap-y-1 mt-1 flex-wrap text-sm text-neutral-900/70">
                <DemoBadge :is-demo="establishment.is_demo" />
                <span v-if="establishment.category_name">{{ localizedCategoryName }}</span>
                <span
                  v-if="establishment.organization_type"
                  class="px-1.5 py-0.5 bg-white/60 text-neutral-700 rounded text-xs"
                >
                  {{ getTypeLabel(establishment.organization_type) }}
                </span>
                <span v-if="establishment.is_online" class="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs">
                  Online
                </span>
                <span v-if="establishment.member_count > 0" class="inline-flex items-center gap-1">
                  <Users class="w-3.5 h-3.5" />{{ establishment.member_count }} {{ $t('directory.organizations.members_count') }}
                </span>
                <span class="inline-flex items-center gap-1">
                  <Eye class="w-3.5 h-3.5" />{{ establishment.views_count }}
                </span>
                <span v-if="establishment.legal_entity_id" class="inline-flex items-center gap-1 font-mono text-xs">
                  <FileText class="w-3.5 h-3.5" />{{ establishment.legal_entity_id }}
                </span>
              </div>
            </div>

            <!-- Rating -->
            <div v-if="establishment.rating_count > 0" class="flex-shrink-0 text-right">
              <div class="flex items-center gap-1">
                <Star class="w-5 h-5 text-amber-600 fill-amber-600" />
                <span class="text-lg font-bold text-neutral-900">{{ Number(establishment.rating_avg).toFixed(1) }}</span>
              </div>
              <span class="text-xs text-neutral-900/60">{{ establishment.rating_count }} {{ establishment.rating_count === 1 ? 'review' : 'reviews' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Body -->
      <div class="max-w-3xl mx-auto px-4 sm:px-6 py-6">

      <!-- Header card -->
      <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 sm:p-6">

        <!-- Quick links row: public links + a single, clearly-marked owner menu -->
        <!-- (Аренда + owner menu moved into the unified action row below) -->
        <!-- Shared hidden photo input — triggered from owner menu and gallery -->
        <input v-if="isOwner" ref="photoInput" type="file" accept="image/*" multiple class="hidden" @change="handlePhotoUpload" />

        <!-- Description -->
        <p v-if="establishment.description" class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">
          {{ establishment.description }}
        </p>

        <!-- Open/Closed badge (quick glance) -->
        <div v-if="isCurrentlyOpen !== null" class="mt-3">
          <span
            v-if="isCurrentlyOpen"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-sm font-medium"
          >
            <span class="w-2 h-2 bg-green-500 rounded-full" />
            {{ $t('directory.establishments.open_now') }}
          </span>
          <span
            v-else
            class="inline-flex items-center gap-1.5 px-2.5 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-full text-sm font-medium"
          >
            <span class="w-2 h-2 bg-red-500 rounded-full" />
            {{ $t('directory.establishments.closed_now') }}
          </span>
        </div>

        <!-- Member info -->
        <div v-if="authStore.isAuthenticated && isJoinable && establishment.is_member" class="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <span class="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-sm rounded-lg font-medium">
                {{ $t('directory.organizations.member_badge') }}
              </span>
              <div class="mt-2 text-sm text-neutral-600 dark:text-neutral-400 space-y-0.5">
                <div v-if="establishment.user_membership_joined_at">
                  {{ $t('directory.organizations.member_since') }}
                  {{ formatDate(establishment.user_membership_joined_at) }}
                </div>
                <div v-if="establishment.user_membership_level">
                  {{ $t('directory.organizations.membership_level') }}:
                  {{ $t(`directory.organizations.membership_levels.${establishment.user_membership_level}`) }}
                </div>
              </div>
            </div>
            <UiButton variant="outline-error" size="sm" :disabled="isLeaving" @click="showLeaveConfirm = true">
              {{ $t('directory.organizations.leave_button') }}
            </UiButton>
          </div>
        </div>

        <!-- Unified action row: booking · public CTAs · utilities · owner menu (pushed right) -->
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <!-- Booking board -->
          <UiButton v-if="establishment.rentable_count > 0" variant="outline" size="sm" :icon="CalendarClock" :to="localePath(`/rental/org/${establishment.slug || props.id}`)">
            {{ $t('booking.board.link') }}
          </UiButton>
          <!-- Join -->
          <UiButton
            v-if="authStore.isAuthenticated && isJoinable && !establishment.is_member"
            variant="primary" size="sm" :loading="isJoining"
            @click="establishment.requires_terms_acceptance ? showJoinModal = true : joinEstablishment()"
          >
            {{ $t('directory.organizations.join_button') }}
          </UiButton>
          <!-- Pay -->
          <UiButton
            v-if="establishment.spark_address || establishment.ln_address"
            variant="success" size="sm" :icon="Wallet"
            @click="showPayModal = true"
          >
            {{ $t('directory.act_as.pay') }}
          </UiButton>
          <!-- Terms -->
          <UiButton
            v-if="establishment.terms_url"
            variant="outline" size="sm" :icon="Scale"
            :to="establishment.terms_url.startsWith('/') ? localePath(establishment.terms_url) : establishment.terms_url"
          >
            {{ $t('directory.organizations.view_terms') }}
          </UiButton>
          <!-- Treasury -->
          <UiButton
            v-if="establishment.treasury_enabled && establishment.slug"
            variant="outline" size="sm" :icon="Landmark"
            :to="localePath(`/org/${establishment.slug}/treasury`)"
          >
            {{ $t('treasury.title') }}
          </UiButton>
          <!-- Audit -->
          <UiButton
            v-if="establishment.treasury_enabled && establishment.slug"
            variant="outline-warning" size="sm" :icon="ClipboardCheck"
            :to="localePath(`/org/${establishment.slug}/audit`)"
          >
            {{ $t('treasury.audit.title') }}
          </UiButton>
          <!-- Condominium tabs -->
          <template v-if="establishment.organization_type === 'CONDOMINIUM' && establishment.slug">
            <UiButton variant="outline" size="sm" :icon="Grid3x3" :to="localePath(`/condo/${establishment.slug}/fractions`)">
              {{ $t('condo.fractions_tab') }}
            </UiButton>
            <UiButton variant="outline" size="sm" :icon="Receipt" :to="localePath(`/condo/${establishment.slug}/quotas`)">
              {{ $t('condo.quotas_tab') }}
            </UiButton>
            <UiButton v-if="canManageTreasurer" variant="outline" size="sm" :icon="Vote" :to="localePath(`/condo/${establishment.slug}/assembly`)">
              {{ $t('condo.assembly_tab') }}
            </UiButton>
          </template>

          <!-- Utilities (labelled, lighter weight) -->
          <UiButton v-if="mapCoords" variant="outline" size="sm" :icon="Navigation" @click="getDirections">
            {{ $t('directory.establishments.get_directions') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :icon="Share2" @click="shareEstablishment">
            {{ $t('directory.establishments.share') }}
          </UiButton>

          <!-- Owner / admin management menu — pushed to the right, set apart from public links -->
          <div v-if="canManageTreasurer || isOwner" ref="ownerMenuEl" class="relative ml-auto">
            <UiButton variant="outline" size="sm" :icon="ShieldCheck" @click="ownerMenuOpen = !ownerMenuOpen">
              {{ $t('directory.act_as.manage_menu') }}
              <ChevronDown class="w-4 h-4 -mr-1 transition-transform" :class="{ 'rotate-180': ownerMenuOpen }" />
            </UiButton>
            <div
              v-if="ownerMenuOpen"
              class="absolute right-0 top-full mt-1 z-30 w-56 py-1 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg"
              role="menu"
            >
              <NuxtLink
                v-if="isOwner"
                :to="localePath(`/org/${establishment.slug || props.id}/edit`)"
                class="flex items-center gap-2.5 px-3 py-2 text-sm text-neutral-700 dark:text-neutral-200 hover:bg-primary-100 dark:hover:bg-primary-900/40"
                role="menuitem"
                @click="ownerMenuOpen = false"
              >
                <Pencil class="w-4 h-4 text-neutral-400" /> {{ $t('common.edit') }}
              </NuxtLink>
              <NuxtLink
                v-if="canManageTreasurer"
                :to="localePath(`/org/${establishment.slug || props.id}/manage`)"
                class="flex items-center gap-2.5 px-3 py-2 text-sm text-neutral-700 dark:text-neutral-200 hover:bg-primary-100 dark:hover:bg-primary-900/40"
                role="menuitem"
                @click="ownerMenuOpen = false"
              >
                <LayoutTemplate class="w-4 h-4 text-neutral-400" /> {{ $t('cms.manage.title') }}
              </NuxtLink>
              <NuxtLink
                v-if="canManageTreasurer"
                :to="localePath(`/blog/create?est=${establishment.slug || props.id}`)"
                class="flex items-center gap-2.5 px-3 py-2 text-sm text-neutral-700 dark:text-neutral-200 hover:bg-primary-100 dark:hover:bg-primary-900/40"
                role="menuitem"
                @click="ownerMenuOpen = false"
              >
                <SquarePen class="w-4 h-4 text-neutral-400" /> {{ $t('directory.act_as.new_post') }}
              </NuxtLink>
              <button
                v-if="isOwner"
                type="button"
                class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-neutral-700 dark:text-neutral-200 hover:bg-primary-100 dark:hover:bg-primary-900/40"
                role="menuitem"
                @click="triggerPhotoUpload"
              >
                <ImagePlus class="w-4 h-4 text-neutral-400" /> {{ $t('directory.photos.add') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Direção (Board) — public section -->
        <div v-if="boardMembers.length > 0" class="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-1.5">
            <Users class="w-4 h-4 text-neutral-400" />
            {{ $t('directory.board.title') }}
          </h3>
          <div class="space-y-1.5">
            <div
              v-for="bm in boardMembers"
              :key="bm.profile_id"
              class="flex items-center justify-between text-sm"
            >
              <div class="flex items-center gap-2 min-w-0">
                <NuxtLink
                  :to="localePath(`/u/${bm.profile_hna.split('@')[0]}`)"
                  class="text-neutral-900 dark:text-neutral-100 font-medium hover:text-secondary truncate"
                >
                  {{ bm.profile_display_name || bm.profile_hna.split('@')[0] }}
                </NuxtLink>
                <span class="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 rounded text-xs shrink-0">
                  {{ bm.position_title || $t(`directory.board.role_${bm.role.toLowerCase()}`) }}
                </span>
                <span v-if="bm.is_auditor" class="px-1.5 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 rounded text-xs shrink-0">
                  {{ $t('directory.act_as.auditor') }}
                </span>
              </div>
              <span v-if="bm.joined_at" class="text-xs text-neutral-400 shrink-0 ml-2">
                {{ formatDate(bm.joined_at) }}
              </span>
            </div>
          </div>
        </div>

        <!-- Org management (owner/admin): treasurer · payment address · auditor — one compact block -->
        <div v-if="canManageTreasurer" class="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-1.5">
            <ShieldCheck class="w-4 h-4 text-neutral-400" />
            {{ $t('directory.act_as.manage_menu') }}
          </h3>
          <div class="space-y-2.5">
            <!-- Treasurer -->
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm text-neutral-600 dark:text-neutral-400 min-w-0">
                <UserCheck class="w-4 h-4 inline -mt-0.5 mr-1 text-neutral-400" />
                {{ $t('directory.act_as.treasurer') }}:
                <span v-if="treasurer" class="font-medium text-neutral-900 dark:text-neutral-100">{{ treasurer.profile_display_name || treasurer.profile_hna.split('@')[0] }}</span>
                <span v-else class="italic">{{ $t('directory.act_as.no_treasurer') }}</span>
              </div>
              <div class="flex gap-1 shrink-0">
                <UiButton variant="ghost" size="sm" @click="showTreasurerModal = true">
                  {{ treasurer ? $t('directory.act_as.change_treasurer') : $t('directory.act_as.set_treasurer') }}
                </UiButton>
                <UiButton v-if="treasurer" variant="outline-error" size="sm" icon-only :icon="UserMinus" @click="removeTreasurer" />
              </div>
            </div>

            <!-- Payment address -->
            <div>
              <div v-if="!editingPaymentAddress" class="flex items-center justify-between gap-3">
                <div class="text-sm text-neutral-600 dark:text-neutral-400 min-w-0 truncate">
                  <Wallet class="w-4 h-4 inline -mt-0.5 mr-1 text-neutral-400" />
                  {{ $t('directory.act_as.payment_address') }}:
                  <span class="font-mono text-xs text-neutral-500 dark:text-neutral-400">{{ establishment.spark_address || establishment.ln_address || $t('directory.act_as.no_payment_address') }}</span>
                </div>
                <UiButton variant="ghost" size="sm" class="shrink-0" @click="startEditPaymentAddress">
                  {{ $t('directory.act_as.change_treasurer') }}
                </UiButton>
              </div>
              <div v-else class="space-y-2">
                <input
                  v-model="paymentAddressInput"
                  type="text"
                  :placeholder="$t('directory.act_as.payment_address_placeholder')"
                  class="w-full text-xs border border-neutral-300 dark:border-neutral-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 font-mono"
                />
                <p class="text-[10px] text-neutral-400 dark:text-neutral-500">
                  {{ $t('directory.act_as.payment_address_help') }}
                </p>
                <div class="flex gap-2">
                  <UiButton variant="primary" size="sm" :loading="savingPaymentAddress" @click="savePaymentAddress">
                    {{ $t('treasury.audit.save') }}
                  </UiButton>
                  <UiButton variant="ghost" size="sm" @click="editingPaymentAddress = false">
                    {{ $t('treasury.audit.cancel') }}
                  </UiButton>
                </div>
              </div>
            </div>

            <!-- Auditor (Fiscal Único) -->
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm text-neutral-600 dark:text-neutral-400 min-w-0">
                <ClipboardCheck class="w-4 h-4 inline -mt-0.5 mr-1 text-neutral-400" />
                {{ $t('directory.act_as.auditor') }}:
                <span v-if="auditor" class="font-medium text-neutral-900 dark:text-neutral-100">{{ auditor.profile_hna || auditor.profile_display_name }}</span>
                <span v-else class="italic">{{ $t('directory.act_as.no_auditor') }}</span>
              </div>
              <div class="flex gap-1 shrink-0">
                <UiButton variant="ghost" size="sm" @click="showAuditorModal = true">
                  {{ auditor ? $t('directory.act_as.change_auditor') : $t('directory.act_as.set_auditor') }}
                </UiButton>
                <UiButton v-if="auditor" variant="outline-error" size="sm" icon-only :icon="UserMinus" @click="removeAuditor" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Pay modal -->
      <div v-if="showPayModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showPayModal = false">
        <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6 shadow-xl">
          <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ $t('directory.act_as.pay_to', { name: establishment.name }) }}
          </h3>
          <div v-if="establishment.spark_address" class="mb-3">
            <label class="text-xs text-neutral-500 dark:text-neutral-400 block mb-1">Spark</label>
            <div class="font-mono text-sm bg-neutral-50 dark:bg-neutral-800 p-2 rounded break-all select-all">
              {{ establishment.spark_address }}
            </div>
          </div>
          <div v-if="establishment.ln_address" class="mb-3">
            <label class="text-xs text-neutral-500 dark:text-neutral-400 block mb-1">Lightning</label>
            <div class="font-mono text-sm bg-neutral-50 dark:bg-neutral-800 p-2 rounded break-all select-all">
              {{ establishment.ln_address }}
            </div>
          </div>
          <UiButton variant="outline" class="w-full mt-4" @click="showPayModal = false">
            {{ $t('common.close') }}
          </UiButton>
        </div>
      </div>


      <!-- Join modal (terms acceptance) -->
      <div v-if="showJoinModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showJoinModal = false">
        <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-lg w-full p-6 shadow-xl">
          <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ $t('directory.organizations.join_button') }} — {{ establishment.name }}
          </h3>
          <p v-if="establishment.description" class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
            {{ establishment.description }}
          </p>
          <label class="flex items-start gap-2 cursor-pointer mb-4">
            <input v-model="acceptTerms" type="checkbox" class="mt-1 w-4 h-4 text-primary border-neutral-300 rounded focus:ring-primary" />
            <span class="text-sm text-neutral-700 dark:text-neutral-300">
              {{ $t('directory.organizations.terms_acceptance_text') }}
            </span>
          </label>
          <NuxtLink
            v-if="establishment.terms_url"
            :to="establishment.terms_url.startsWith('/') ? localePath(establishment.terms_url) : establishment.terms_url"
            target="_blank"
            class="text-link text-sm block mb-4"
          >
            {{ $t('directory.organizations.view_terms') }} →
          </NuxtLink>
          <div class="flex justify-end gap-3">
            <UiButton variant="outline" @click="showJoinModal = false">
              {{ $t('common.close') }}
            </UiButton>
            <UiButton variant="primary" size="sm" :loading="isJoining" :disabled="!acceptTerms" @click="joinEstablishment">
              {{ $t('directory.organizations.join_button') }}
            </UiButton>
          </div>
        </div>
      </div>

      <!-- Leave confirmation modal -->
      <UiConfirmModal
        v-if="showLeaveConfirm"
        :model-value="true"
        :title="$t('directory.organizations.leave_button')"
        :message="$t('directory.organizations.leave_confirm', { name: establishment.name })"
        variant="error"
        :confirm-label="$t('directory.organizations.leave_button')"
        :loading="isLeaving"
        @confirm="leaveEstablishment"
        @update:model-value="showLeaveConfirm = false"
      />

      <!-- Treasurer selection modal -->
      <div v-if="showTreasurerModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showTreasurerModal = false">
        <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6 shadow-xl">
          <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ $t('directory.act_as.set_treasurer') }}
          </h3>
          <div v-if="members.length === 0" class="text-sm text-neutral-500 py-4 text-center">
            {{ $t('directory.act_as.no_members') }}
          </div>
          <div v-else class="space-y-1 max-h-60 overflow-y-auto">
            <button
              v-for="m in members"
              :key="m.profile_id"
              type="button"
              @click="setTreasurer(m.profile_id)"
              :class="[
                'w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between',
                m.is_treasurer
                  ? 'bg-primary/10 text-secondary font-medium'
                  : 'hover:bg-neutral-50 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300'
              ]"
            >
              <span>{{ m.profile_hna || m.profile_display_name }}</span>
              <span class="text-xs text-neutral-400">{{ m.role }}</span>
            </button>
          </div>
          <UiButton variant="outline" class="w-full mt-4" @click="showTreasurerModal = false">
            {{ $t('common.close') }}
          </UiButton>
        </div>
      </div>

      <!-- Auditor selection modal -->
      <div v-if="showAuditorModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showAuditorModal = false">
        <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6 shadow-xl">
          <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ $t('directory.act_as.set_auditor') }}
          </h3>
          <div v-if="members.length === 0" class="text-sm text-neutral-500 py-4 text-center">
            {{ $t('directory.act_as.no_members') }}
          </div>
          <div v-else class="space-y-1 max-h-60 overflow-y-auto">
            <button
              v-for="m in members"
              :key="m.profile_id"
              type="button"
              @click="setAuditor(m.profile_id)"
              :class="[
                'w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between',
                m.is_auditor
                  ? 'bg-primary/10 text-secondary font-medium'
                  : 'hover:bg-neutral-50 dark:hover:bg-neutral-800 text-neutral-700 dark:text-neutral-300'
              ]"
            >
              <span>{{ m.profile_hna || m.profile_display_name }}</span>
              <span class="text-xs text-neutral-400">{{ m.role }}</span>
            </button>
          </div>
          <UiButton variant="outline" class="w-full mt-4" @click="showAuditorModal = false">
            {{ $t('common.close') }}
          </UiButton>
        </div>
      </div>

      <!-- Delete photo confirmation -->
      <UiConfirmModal
        v-if="deletePhotoTarget"
        :model-value="true"
        :title="$t('directory.photos.delete_confirm')"
        :message="$t('directory.photos.delete_confirm')"
        :icon="Trash2"
        variant="error"
        :confirm-label="$t('common.delete')"
        @confirm="deletePhoto()"
        @update:model-value="deletePhotoTarget = null"
      />

      <!-- Photos gallery -->
      <div v-if="allPhotos.length > 0 || isOwner" class="mt-3">
        <!-- Gallery grid -->
        <div v-if="allPhotos.length > 0" class="grid gap-1.5" :class="allPhotos.length >= 3 ? 'grid-cols-3' : allPhotos.length === 2 ? 'grid-cols-2' : 'grid-cols-1'">
          <div
            v-for="(photo, idx) in allPhotos"
            :key="photo.url"
            class="relative group cursor-pointer overflow-hidden rounded-lg bg-neutral-100 dark:bg-neutral-800"
            :class="allPhotos.length >= 3 && idx === 0 ? 'col-span-2 row-span-2' : ''"
            @click="openLightbox(idx)"
          >
            <img
              :src="photo.url"
              :alt="photo.caption || establishment.name"
              class="w-full h-full object-cover"
              :class="allPhotos.length >= 3 && idx === 0 ? 'aspect-square' : 'aspect-[4/3]'"
              loading="lazy"
            />
            <!-- Delete button (owner only) -->
            <button
              v-if="isOwner && photo.id"
              @click.stop="deletePhotoTarget = photo.id"
              class="absolute top-1.5 right-1.5 p-1 bg-black/60 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Upload button (owner only) — shares the single hidden file input -->
        <div v-if="isOwner" class="mt-2">
          <button
            v-if="!isUploading"
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 cursor-pointer"
            @click="triggerPhotoUpload"
          >
            <ImagePlus class="w-4 h-4" />
            {{ $t('directory.photos.add') }}
          </button>
          <span v-else class="inline-flex items-center gap-1.5 text-sm text-neutral-500">
            <Loader2 class="w-4 h-4 animate-spin" />
            {{ $t('directory.photos.uploading') }}
          </span>
        </div>
      </div>

      <!-- Lightbox -->
      <div v-if="lightboxOpen" class="fixed inset-0 bg-black/90 z-50 flex items-center justify-center" @click.self="lightboxOpen = false">
        <button @click="lightboxOpen = false" class="absolute top-4 right-4 p-2 text-white/80 hover:text-white">
          <X class="w-6 h-6" />
        </button>
        <button v-if="allPhotos.length > 1" @click="lightboxPrev" class="absolute left-4 p-2 text-white/80 hover:text-white">
          <ChevronLeft class="w-8 h-8" />
        </button>
        <img
          :src="allPhotos[lightboxIdx]?.url"
          :alt="allPhotos[lightboxIdx]?.caption || ''"
          class="max-w-[90vw] max-h-[90vh] object-contain"
        />
        <button v-if="allPhotos.length > 1" @click="lightboxNext" class="absolute right-4 p-2 text-white/80 hover:text-white">
          <ChevronRight class="w-8 h-8" />
        </button>
        <div v-if="allPhotos[lightboxIdx]?.caption" class="absolute bottom-4 text-white/80 text-sm text-center px-4">
          {{ allPhotos[lightboxIdx].caption }}
        </div>
      </div>

      <!-- Videos -->
      <ObjectVideos v-if="establishment.id" :object-id="establishment.id" :editable="isOwner" class="mt-3" />

      <!-- Contact & details -->
      <div v-if="hasContactInfo" class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 divide-y divide-neutral-100 dark:divide-neutral-800">

        <!-- Address — clickable shortcut to /map (same as the map preview below) when coords are known -->
        <component
          :is="mapCoords ? 'button' : 'div'"
          v-if="establishment.world_object"
          :type="mapCoords ? 'button' : undefined"
          class="w-full text-left flex items-start gap-3 px-4 sm:px-6 py-3"
          :class="mapCoords ? 'hover:bg-neutral-50 dark:hover:bg-neutral-800 cursor-pointer' : ''"
          style="transition: none"
          @click="mapCoords ? openInMap() : null"
        >
          <MapPin class="w-4 h-4 text-neutral-400 mt-0.5 flex-shrink-0" />
          <div class="min-w-0">
            <p class="text-sm" :class="mapCoords ? 'text-secondary' : 'text-neutral-900 dark:text-neutral-100'">{{ establishment.world_object.full_address }}</p>
            <p v-if="establishment.floor || establishment.office_number" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              <span v-if="establishment.floor">{{ $t('directory.establishments.floor') }} {{ establishment.floor }}</span>
              <span v-if="establishment.floor && establishment.office_number">, </span>
              <span v-if="establishment.office_number">{{ $t('directory.establishments.office') }} {{ establishment.office_number }}</span>
            </p>
          </div>
        </component>

        <!-- Phone -->
        <a v-if="establishment.phone" :href="`tel:${establishment.phone}`" class="flex items-center gap-3 px-4 sm:px-6 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800" style="transition: none">
          <Phone class="w-4 h-4 text-neutral-400 flex-shrink-0" />
          <span class="text-sm text-secondary">{{ establishment.phone }}</span>
        </a>

        <!-- Email -->
        <a v-if="establishment.email" :href="`mailto:${establishment.email}`" class="flex items-center gap-3 px-4 sm:px-6 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800" style="transition: none">
          <Mail class="w-4 h-4 text-neutral-400 flex-shrink-0" />
          <span class="text-sm text-secondary">{{ establishment.email }}</span>
        </a>

        <!-- Website -->
        <a v-if="establishment.website" :href="establishment.website" target="_blank" rel="noopener noreferrer" class="flex items-center gap-3 px-4 sm:px-6 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800" style="transition: none">
          <Globe class="w-4 h-4 text-neutral-400 flex-shrink-0" />
          <span class="text-sm text-secondary truncate">{{ establishment.website }}</span>
          <ExternalLink class="w-3 h-3 text-neutral-400 flex-shrink-0" />
        </a>
      </div>

      <!-- Map preview — clickable shortcut to /map (replaces the old "view on map" button) -->
      <div
        v-if="mapCoords"
        class="mt-3 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors cursor-pointer"
        @click="openInMap"
      >
        <StaticMapPreview
          :latitude="mapCoords.lat"
          :longitude="mapCoords.lon"
          :height="180"
          :zoom="15"
        />
      </div>

      <!-- Opening hours -->
      <div v-if="hasOpeningHours" class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
          <Clock class="w-4 h-4 text-neutral-400" />
          {{ $t('directory.establishments.opening_hours') }}
          <span
            v-if="isCurrentlyOpen === true"
            class="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium"
          >
            {{ $t('directory.establishments.open_now') }}
          </span>
          <span
            v-else-if="isCurrentlyOpen === false"
            class="px-2 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-full text-xs font-medium"
          >
            {{ $t('directory.establishments.closed_now') }}
          </span>
        </h2>
        <div class="space-y-1.5">
          <div v-for="(hours, day) in establishment.opening_hours" :key="day" class="flex justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400 capitalize">{{ day }}</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-mono text-xs">{{ hours }}</span>
          </div>
        </div>
      </div>

      <!-- Hub info (public, visible when is_hub) -->
      <div v-if="establishment.is_hub" class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Package class="w-4 h-4 text-neutral-400" />
            {{ $t('shipments.hub.info_title') }}
          </h2>
          <!-- Primary CTA lives with the hub details it belongs to -->
          <UiButton
            v-if="authStore.isAuthenticated"
            variant="primary" size="sm" :icon="Package"
            :to="localePath(`/shipments?dest=${establishment.id}`)"
          >
            {{ $t('shipments.hub.send_here') }}
          </UiButton>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <!-- Accepted sizes -->
          <div v-if="establishment.hub_accepted_sizes?.length" class="col-span-2">
            <span class="text-neutral-500 dark:text-neutral-400 text-xs">{{ $t('shipments.hub.accepted_sizes') }}</span>
            <div class="flex flex-wrap gap-1.5 mt-1">
              <UiBadge
                v-for="size in establishment.hub_accepted_sizes"
                :key="size"
                variant="primary"
                type="soft"
                size="sm"
              >
                {{ $t(`shipments.size.${size}`) }}
              </UiBadge>
            </div>
          </div>
          <!-- Capacity -->
          <div>
            <span class="text-neutral-500 dark:text-neutral-400 text-xs block">{{ $t('shipments.hub.capacity') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">
              {{ establishment.hub_capacity ?? $t('shipments.hub.capacity_unlimited') }}
            </span>
          </div>
          <!-- Max days -->
          <div>
            <span class="text-neutral-500 dark:text-neutral-400 text-xs block">{{ $t('shipments.hub.max_days') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">{{ establishment.hub_max_days }} {{ $t('shipments.hub.days') }}</span>
          </div>
          <!-- Storage fee -->
          <div>
            <span class="text-neutral-500 dark:text-neutral-400 text-xs block">{{ $t('shipments.storage_fee') }}</span>
            <span class="text-neutral-900 dark:text-neutral-100 font-medium">
              {{ establishment.hub_storage_fee_daily === 0 ? $t('shipments.hub.free') : `${establishment.hub_storage_fee_daily} ${$t('shipments.sats_per_day')}` }}
            </span>
          </div>
          <!-- Instructions -->
          <div v-if="establishment.hub_instructions" class="col-span-2 mt-1">
            <span class="text-neutral-500 dark:text-neutral-400 text-xs block">{{ $t('shipments.hub.instructions') }}</span>
            <p class="text-neutral-700 dark:text-neutral-300 text-sm mt-0.5">{{ establishment.hub_instructions }}</p>
          </div>
        </div>
      </div>

      <!-- Hub activation (owner/admin only) -->
      <HubActivation
        v-if="canManageTreasurer"
        :establishment-id="props.id"
        :is-hub="establishment.is_hub"
        :hub-capacity="establishment.hub_capacity"
        :hub-max-days="establishment.hub_max_days"
        :hub-storage-fee-daily-prop="establishment.hub_storage_fee_daily"
        :hub-accepted-sizes="establishment.hub_accepted_sizes"
        :hub-instructions="establishment.hub_instructions"
        :can-activate="canActivateHub"
        class="mt-3"
        @updated="fetchEstablishment"
      />

      <!-- Hub operator panel (owner/admin only, when hub is active) -->
      <HubOperatorPanel
        v-if="establishment.is_hub && canManageTreasurer"
        :establishment-id="props.id"
        class="mt-3"
      />

      <!-- Attributes / Amenities -->
      <div v-if="displayAttributes.length" class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
        <div class="flex flex-wrap gap-2">
          <template v-for="attr in displayAttributes" :key="attr.key">
            <span v-if="attr.type === 'boolean'" class="px-2 py-1 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded text-xs">
              {{ attr.label }}
            </span>
            <span v-else-if="attr.type === 'negative'" class="px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded text-xs line-through">
              {{ attr.label }}
            </span>
            <span v-else class="px-2 py-1 bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 rounded text-xs">
              {{ attr.label }}: {{ attr.value }}
            </span>
          </template>
        </div>
      </div>

      <!-- Blog: latest posts (public preview) / owner-admin invite when none published -->
      <section
        v-if="latestPosts.length > 0 || canManageTreasurer"
        class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4"
      >
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Newspaper class="w-4 h-4 text-neutral-400" />
            {{ $t('cms.blog') }}
          </h2>
          <NuxtLink
            v-if="latestPosts.length > 0"
            :to="localePath(`/org/${establishment.slug || props.id}/blog`)"
            class="text-link text-sm inline-flex items-center gap-1"
          >
            {{ $t('cms.allPosts') }}
            <ChevronRight class="w-4 h-4" />
          </NuxtLink>
        </div>

        <!-- Latest posts -->
        <div v-if="latestPosts.length > 0" class="space-y-3">
          <BlogPostCard
            v-for="post in latestPosts"
            :key="post.id"
            :post="post"
            :link-base="`/org/${establishment.slug || props.id}/blog`"
          />
        </div>

        <!-- No published posts yet — invite owner/admin to write (public sees nothing) -->
        <div v-else class="py-12 text-center">
          <Newspaper class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
          <h3 class="text-base font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
            {{ $t('cms.orgBlogInviteTitle') }}
          </h3>
          <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            {{ $t('cms.orgBlogInviteDesc') }}
          </p>
          <UiButton
            variant="primary" size="sm" :icon="SquarePen"
            :to="localePath(`/blog/create?est=${establishment.slug || props.id}`)"
          >
            {{ $t('cms.newPost') }}
          </UiButton>
        </div>
      </section>

      <!-- Reviews -->
      <div class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
        <EstablishmentReviews :establishment-id="props.id" :owner-id="establishment.owner_id" />
      </div>

      </div><!-- /body -->
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft, BadgeCheck, Star, Users, Eye, FileText, Scale,
  Landmark, MapPin, Phone, Mail, Globe, ExternalLink, Clock,
  AlertCircle, Wallet, UserCheck, UserMinus, ClipboardCheck, ChevronDown, Loader2,
  ImagePlus, X, ChevronLeft, ChevronRight, Camera, Pencil, Trash2,
  Grid3x3, Receipt, Vote, Package, Navigation, Share2, Newspaper, CalendarClock,
  LayoutTemplate, ShieldCheck, SquarePen
} from 'lucide-vue-next'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'
import HubActivation from '~/components/HubActivation.vue'
import HubOperatorPanel from '~/components/HubOperatorPanel.vue'

const props = defineProps({
  id: { type: String, required: true }
})

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()

// SSR-ready fetch (public data for SEO meta/JSON-LD)
const { data: establishment, pending: loading, error: fetchError } = await useAsyncData(
  `establishment-${props.id}`,
  () => $fetch(`/api/v1/geo/establishments/${props.id}/`)
)
const error = computed(() => {
  if (!fetchError.value) return null
  return (fetchError.value as any)?.message || 'Failed to load establishment'
})

// Latest published posts for the org blog teaser (SSR for SEO/crawl).
// Public endpoint → published only; managers with 0 published see an invite plate,
// the public sees nothing (section hidden).
const { data: latestPostsData } = await useAsyncData(
  `establishment-posts-${props.id}`,
  () => $fetch<{ items: any[]; count: number }>('/api/v1/cms/posts/', {
    params: { establishment_slug: props.id, page_size: '3' }
  })
)
const latestPosts = computed(() => latestPostsData.value?.items || [])

// Localized category label: API returns reference data in English (category_name);
// translate via the localized category tree by slug, falling back to the English name.
const { fetchCategory } = useCategories()
const localizedCategoryName = ref('')
watch(establishment, async (e) => {
  const fallback = e?.category_name || ''
  const slug = e?.category_slug
  if (!slug) { localizedCategoryName.value = fallback; return }
  try {
    const cat = await fetchCategory(slug)
    localizedCategoryName.value = cat?.name || fallback
  } catch {
    localizedCategoryName.value = fallback
  }
}, { immediate: true })

// Photos
const isUploading = ref(false)
const lightboxOpen = ref(false)
const lightboxIdx = ref(0)

const isOwner = computed(() => {
  return authStore.profile?.id && establishment.value?.owner_id === authStore.profile.id
})

const allPhotos = computed(() => {
  if (!establishment.value) return []
  const photos: Array<{ url: string; caption: string; id?: string }> = []
  // Uploaded photos first
  if (establishment.value.uploaded_photos) {
    for (const p of establishment.value.uploaded_photos) {
      photos.push({ url: p.url, caption: p.caption, id: p.id })
    }
  }
  // External URL photos
  if (establishment.value.photos) {
    for (const url of establishment.value.photos) {
      photos.push({ url, caption: '' })
    }
  }
  return photos
})

const openLightbox = (idx: number) => {
  lightboxIdx.value = idx
  lightboxOpen.value = true
}
const lightboxPrev = () => {
  lightboxIdx.value = (lightboxIdx.value - 1 + allPhotos.value.length) % allPhotos.value.length
}
const lightboxNext = () => {
  lightboxIdx.value = (lightboxIdx.value + 1) % allPhotos.value.length
}

// Owner management menu — a single, clearly-marked entry point for owner/admin
// actions, kept apart from the public quick links.
const ownerMenuOpen = ref(false)
const ownerMenuEl = ref<HTMLElement | null>(null)
const photoInput = ref<HTMLInputElement | null>(null)

const triggerPhotoUpload = () => {
  ownerMenuOpen.value = false
  photoInput.value?.click()
}

function onOwnerMenuOutside(e: MouseEvent) {
  if (ownerMenuOpen.value && ownerMenuEl.value && !ownerMenuEl.value.contains(e.target as Node)) {
    ownerMenuOpen.value = false
  }
}
function onOwnerMenuKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') ownerMenuOpen.value = false
}
onMounted(() => {
  document.addEventListener('click', onOwnerMenuOutside)
  document.addEventListener('keydown', onOwnerMenuKeydown)
})
onUnmounted(() => {
  document.removeEventListener('click', onOwnerMenuOutside)
  document.removeEventListener('keydown', onOwnerMenuKeydown)
})

const handlePhotoUpload = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files?.length) return

  isUploading.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.accessToken) return

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      // Compress with browser-image-compression if available
      let processedFile = file
      try {
        const imageCompression = (await import('browser-image-compression')).default
        processedFile = await imageCompression(file, { maxSizeMB: 2, maxWidthOrHeight: 1920 })
      } catch { /* compression not available, upload raw */ }

      const formData = new FormData()
      formData.append('image', processedFile)
      formData.append('order', String(allPhotos.value.length + i))

      await $fetch(`/api/v1/geo/establishments/${props.id}/photos/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
        body: formData,
      })
    }
    await fetchEstablishment()
  } catch (err: any) {
    console.error('Photo upload failed:', err)
  } finally {
    isUploading.value = false
    input.value = ''
  }
}

const deletePhoto = async (photoId?: string) => {
  const id = photoId || deletePhotoTarget.value
  if (!id) return
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${props.id}/photos/${id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
    deletePhotoTarget.value = null
    await fetchEstablishment()
  } catch (err: any) {
    console.error('Photo delete failed:', err)
  }
}

// Join/Leave membership
const showJoinModal = ref(false)
const showLeaveConfirm = ref(false)
const acceptTerms = ref(false)
const isJoining = ref(false)
const isLeaving = ref(false)

// Treasurer, auditor & payment
const showPayModal = ref(false)
const showTreasurerModal = ref(false)
const showAuditorModal = ref(false)
const treasurer = ref<any>(null)
const auditor = ref<any>(null)
const members = ref<any[]>([])
const userRole = ref<string | null>(null)

// Payment address editing
const editingPaymentAddress = ref(false)
const paymentAddressInput = ref('')
const savingPaymentAddress = ref(false)

const startEditPaymentAddress = () => {
  paymentAddressInput.value = establishment.value?.spark_address || ''
  editingPaymentAddress.value = true
}

const savePaymentAddress = async () => {
  savingPaymentAddress.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${props.id}/payment-address/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: { spark_address: paymentAddressInput.value.trim() }
    })
    editingPaymentAddress.value = false
    await fetchEstablishment()
  } catch (err: any) {
    console.error('Failed to save payment address:', err)
  } finally {
    savingPaymentAddress.value = false
  }
}

// Delete photo confirmation (replaces native confirm())
const deletePhotoTarget = ref<string | null>(null)

const hasOpeningHours = computed(() => {
  return establishment.value?.opening_hours && Object.keys(establishment.value.opening_hours).length > 0
})

const { isOpen: isCurrentlyOpen } = useOpeningHours(computed(() => establishment.value?.opening_hours as Record<string, string> | undefined))

const hasContactInfo = computed(() => {
  const e = establishment.value
  return e?.world_object || e?.phone || e?.email || e?.website
})

const hasCoords = computed(() => !!mapCoords.value)

// Keys that are internal metadata, not user-facing amenities
const INTERNAL_ATTR_KEYS = new Set([
  '__demo_seed', 'demo', 'import_source', 'municipality',
  'wikidata_qid', 'denomination', 'diocese', 'osm_id', 'monthly_budget',
  'addr_city', 'addr_number', 'addr_street', 'addr_postcode',
])

function formatAttrKey(key: string): string {
  const i18nKey = `directory.amenities.${key}`
  const translated = t(i18nKey)
  // If i18n returns the key itself, format the slug as readable text
  if (translated === i18nKey) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }
  return translated
}

function formatAttrValue(val: unknown): string {
  if (Array.isArray(val)) {
    return val.map(v => {
      const i18nKey = `directory.amenities.${v}`
      const translated = t(i18nKey)
      return translated === i18nKey ? String(v).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : translated
    }).join(', ')
  }
  return String(val)
}

const displayAttributes = computed(() => {
  const attrs = establishment.value?.attributes
  if (!attrs) return []
  return Object.entries(attrs)
    .filter(([key]) => !INTERNAL_ATTR_KEYS.has(key))
    .map(([key, val]) => {
      if (val === true) return { key, type: 'boolean', label: formatAttrKey(key) }
      if (val === false) return { key, type: 'negative', label: formatAttrKey(key) }
      return { key, type: 'value', label: formatAttrKey(key), value: formatAttrValue(val) }
    })
})

const JOINABLE_TYPES = new Set(['ASSOCIATION', 'COOPERATIVE', 'NGO', 'COMMUNITY', 'CONDOMINIUM'])
const isJoinable = computed(() => {
  const type = establishment.value?.organization_type
  return type && JOINABLE_TYPES.has(type)
})

const mapCoords = computed(() => {
  const e = establishment.value
  const loc = e?.location || e?.world_object?.location
  return loc ? { lat: loc.lat, lon: loc.lon } : null
})

const canManageTreasurer = computed(() => {
  return userRole.value === 'OWNER' || userRole.value === 'ADMIN'
})

const canActivateHub = computed(() => {
  // WoT 3+ (is_verified_wot) or staff
  const profile = authStore.profile
  if (!profile) return false
  return profile.is_verified_wot || authStore.user?.is_staff
})

const boardMembers = computed(() => {
  const BOARD_ROLES = new Set(['OWNER', 'ADMIN'])
  const ROLE_ORDER: Record<string, number> = { OWNER: 0, ADMIN: 1 }
  return members.value
    .filter(m => BOARD_ROLES.has(m.role) || m.is_treasurer || m.is_auditor)
    .sort((a, b) => (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9) || new Date(a.joined_at).getTime() - new Date(b.joined_at).getTime())
})

const getTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    'ASSOCIATION': t('directory.organizations.type_association'),
    'COOPERATIVE': t('directory.organizations.type_cooperative'),
    'COMPANY': t('directory.organizations.type_company'),
    'NGO': t('directory.organizations.type_ngo'),
    'COMMUNITY': t('directory.organizations.type_community'),
    'CONDOMINIUM': t('condo.title')
  }
  return labels[type] || type
}

// Client-side re-fetch with auth (for is_member, and after join/leave/treasurer mutations)
const fetchEstablishment = async () => {
  try {
    const headers: Record<string, string> = {}
    if (authStore.isAuthenticated) {
      try {
        await authStore.ensureToken()
        if (authStore.token) headers['Authorization'] = `Bearer ${authStore.token}`
      } catch (e) { /* ignore */ }
    }
    establishment.value = await $fetch(`/api/v1/geo/establishments/${props.id}/`, {
      credentials: 'include',
      headers
    })
  } catch (err: any) {
    console.error('Error fetching establishment:', err)
  }
}

const fetchTreasurer = async () => {
  try {
    const data = await $fetch(`/api/v1/geo/establishments/${props.id}/treasurer/`)
    treasurer.value = data
  } catch {
    treasurer.value = null
  }
}

const fetchMembers = async () => {
  try {
    const data = await $fetch<any[]>(`/api/v1/geo/establishments/${props.id}/members/`)
    members.value = data
  } catch {
    members.value = []
  }
}

const detectUserRole = () => {
  if (!authStore.profile) return
  const profileId = authStore.profile.id
  // Check if owner
  if (establishment.value?.owner_id === profileId) {
    userRole.value = 'OWNER'
    return
  }
  // Check membership
  const m = members.value.find(m => m.profile_id === profileId)
  if (m) {
    userRole.value = m.role
  }
}

const setTreasurer = async (profileId: string) => {
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/geo/establishments/${props.id}/treasurer/`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      credentials: 'include',
      body: { profile_id: profileId }
    })
    treasurer.value = data
    showTreasurerModal.value = false
    // Refresh establishment to get updated payment addresses
    await fetchEstablishment()
    await fetchMembers()
  } catch (err: any) {
    console.error('Failed to set treasurer:', err)
  }
}

const removeTreasurer = async () => {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${props.id}/treasurer/`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })
    treasurer.value = null
    await fetchEstablishment()
    await fetchMembers()
  } catch (err: any) {
    console.error('Failed to remove treasurer:', err)
  }
}

const fetchAuditor = async () => {
  try {
    const data = await $fetch(`/api/v1/geo/establishments/${props.id}/auditor/`)
    auditor.value = data
  } catch {
    auditor.value = null
  }
}

const setAuditor = async (profileId: string) => {
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/geo/establishments/${props.id}/auditor/`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      credentials: 'include',
      body: { profile_id: profileId }
    })
    auditor.value = data
    showAuditorModal.value = false
    await fetchMembers()
  } catch (err: any) {
    console.error('Failed to set auditor:', err)
  }
}

const removeAuditor = async () => {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${props.id}/auditor/`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })
    auditor.value = null
    await fetchMembers()
  } catch (err: any) {
    console.error('Failed to remove auditor:', err)
  }
}

const joinEstablishment = async () => {
  isJoining.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.accessToken) return
    await $fetch(`/api/v1/geo/establishments/${props.id}/join/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: { terms_accepted: true }
    })
    showJoinModal.value = false
    acceptTerms.value = false
    await fetchEstablishment()
    await fetchMembers()
    detectUserRole()
  } catch (err: any) {
    console.error('Failed to join:', err)
  } finally {
    isJoining.value = false
  }
}

const leaveEstablishment = async () => {
  isLeaving.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.accessToken) return
    await $fetch(`/api/v1/geo/establishments/${props.id}/leave/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` }
    })
    showLeaveConfirm.value = false
    await fetchEstablishment()
    await fetchMembers()
    detectUserRole()
  } catch (err: any) {
    console.error('Failed to leave:', err)
  } finally {
    isLeaving.value = false
  }
}

const formatDate = (dateString: string) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'long', day: 'numeric' }).format(date)
}

// SEO meta tags
useSeoMeta({
  title: () => establishment.value?.name ? `${establishment.value.name} - Parahub` : t('directory.title'),
  ogTitle: () => establishment.value?.name || t('directory.title'),
  description: () => establishment.value?.description?.slice(0, 160) || t('directory.meta_description'),
  ogDescription: () => establishment.value?.description?.slice(0, 160) || t('directory.meta_description'),
  ogImage: () => establishment.value?.logo_url || '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// JSON-LD LocalBusiness structured data
const _baseUrl = useRuntimeConfig().public.siteUrl || 'https://parahub.io'
useHead({
  script: computed(() => {
    if (!establishment.value) return []
    const baseUrl = _baseUrl
    const est = establishment.value

    const jsonLd: Record<string, any> = {
      '@context': 'https://schema.org',
      '@type': 'LocalBusiness',
      'name': est.name,
      'url': `${baseUrl}/org/${est.slug || est.id}`,
    }
    if (est.description) jsonLd.description = est.description
    if (est.logo_url) jsonLd.image = est.logo_url
    if (est.phone) jsonLd.telephone = est.phone
    if (est.email) jsonLd.email = est.email
    if (est.website) jsonLd.sameAs = est.website

    // Address
    if (est.world_object?.full_address) {
      jsonLd.address = {
        '@type': 'PostalAddress',
        'streetAddress': est.world_object.full_address,
      }
    }

    // Geo
    const loc = est.location || est.world_object?.location
    if (loc) {
      jsonLd.geo = {
        '@type': 'GeoCoordinates',
        'latitude': loc.lat,
        'longitude': loc.lon,
      }
    }

    // Rating
    if (est.rating_count > 0) {
      jsonLd.aggregateRating = {
        '@type': 'AggregateRating',
        'ratingValue': Number(est.rating_avg).toFixed(1),
        'reviewCount': est.rating_count,
      }
    }

    return [{ type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd) }]
  })
})

const openInMap = () => {
  if (!mapCoords.value) return
  // Center on the org AND open its panel: establishmentId drives MapView's feature
  // restore → MapPanelOsm.showEstablishmentDetails; layer=building prefers the
  // footprint under the point so the native org panel opens.
  const q = new URLSearchParams({
    lat: String(mapCoords.value.lat),
    lng: String(mapCoords.value.lon),
    zoom: '17',
    establishmentId: String(establishment.value?.id || props.id),
    layer: 'building',
    // Remember where we came from so the map's back button returns to this org
    // page instead of dumping the user into the building's tenant list.
    returnTo: route.fullPath,
  })
  router.push(localePath(`/map?${q.toString()}`))
}

const getDirections = () => {
  if (!mapCoords.value) return
  // Hand the destination to /map, which opens the directions panel pre-filled
  // (the map reads dest_lat/dest_lng/dest_name — see MapView applyDirectionsFromQuery).
  const q = new URLSearchParams({
    dest_lat: String(mapCoords.value.lat),
    dest_lng: String(mapCoords.value.lon),
    dest_name: establishment.value?.name || establishment.value?.world_object?.full_address || '',
    zoom: '15',
    returnTo: route.fullPath,
  })
  router.push(localePath(`/map?${q.toString()}`))
}

const shareEstablishment = async () => {
  const url = window.location.href
  const title = establishment.value?.name || ''
  if (navigator.share) {
    try {
      await navigator.share({ title, url })
    } catch { /* user cancelled */ }
  } else {
    try {
      await navigator.clipboard.writeText(url)
      const { useToastStore } = await import('~/stores/toast')
      useToastStore().success(t('directory.establishments.share_copied'))
    } catch { /* clipboard failed */ }
  }
}

const goBack = () => {
  // Browser-back only when the previous history entry is the organizations
  // directory itself (preserves its filters/scroll). Otherwise — arrived from the
  // map, a profile, search, or an external/direct link — go to the directory
  // directly so the "Organizations" label always lands on the organizations list,
  // not wherever the user happened to come from. router history state is the
  // reliable in-app signal (document.referrer stays empty across SPA navigation).
  const back = router.options.history.state.back
  if (typeof back === 'string' && /\/directory(\?|#|$)/.test(back)) {
    router.back()
  } else {
    navigateTo(localePath('/directory') + '#organizations')
  }
}

onMounted(async () => {
  // Re-fetch with auth on client (for is_member, membership data)
  await fetchEstablishment()
  await Promise.all([fetchTreasurer(), fetchAuditor(), fetchMembers()])
  detectUserRole()
})
</script>

<style scoped>
/* Yellow identity band — same treatment as the docs header (/docs/mission). */
.org-header {
  background-color: var(--color-primary);
}
</style>
