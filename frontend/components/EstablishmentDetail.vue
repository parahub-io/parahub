<template>
  <div class="pb-20">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-32" role="status" aria-live="polite">
      <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" aria-hidden="true" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex items-center justify-center py-32">
      <div class="text-center max-w-md mx-auto px-4">
        <AlertCircle class="w-12 h-12 text-red-500 mx-auto mb-3" />
        <h2 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('directory.establishments.empty_title') }}</h2>
        <p class="text-neutral-600 dark:text-neutral-400 mb-4 text-sm">{{ error }}</p>
        <UiButton variant="primary" size="sm" @click="navigateTo(localePath('/directory') + '#organizations')">
          {{ $t('directory.tabs.organizations') }}
        </UiButton>
      </div>
    </div>

    <!-- Content -->
    <div v-else-if="establishment" class="max-w-3xl mx-auto px-4 py-6">

      <!-- Back link -->
      <UiButton variant="ghost" size="sm" :icon="ArrowLeft" @click="goBack" class="mb-4 -ml-2">
        {{ $t('directory.tabs.organizations') }}
      </UiButton>

      <!-- Header card -->
      <div class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 sm:p-6">
        <!-- Name + verified -->
        <div class="flex items-start gap-3">
          <div class="flex-1 min-w-0">
            <h1 class="text-xl sm:text-2xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 flex-wrap">
              {{ establishment.name }}
              <BadgeCheck v-if="establishment.is_verified" class="w-5 h-5 sm:w-6 sm:h-6 text-primary flex-shrink-0" />
            </h1>

            <!-- Category + type -->
            <div class="flex items-center gap-2 mt-1 flex-wrap">
              <DemoBadge :is-demo="establishment.is_demo" />
              <span v-if="establishment.category_name" class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ establishment.category_name }}
              </span>
              <span
                v-if="establishment.organization_type"
                class="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 rounded text-xs"
              >
                {{ getTypeLabel(establishment.organization_type) }}
              </span>
              <span v-if="establishment.is_online" class="px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs">
                Online
              </span>
            </div>
          </div>

          <!-- Action buttons (owner/admin) -->
          <div class="flex items-center gap-1 shrink-0">
            <UiButton variant="ghost" size="sm" :icon="Newspaper" :to="localePath(`/org/${establishment.slug || props.id}/blog`)" class="shrink-0">
              {{ $t('cms.blog') }}
            </UiButton>
            <UiButton v-if="canManageTreasurer" variant="ghost" size="sm" :icon="Settings" :to="localePath(`/org/${establishment.slug || props.id}/manage`)" class="shrink-0">
              {{ $t('cms.manage.title') }}
            </UiButton>
            <UiButton v-if="isOwner" variant="ghost" size="sm" :icon="Pencil" :to="localePath(`/org/${establishment.slug || props.id}/edit`)" class="shrink-0">
              {{ $t('common.edit') }}
            </UiButton>
          </div>

          <!-- Rating -->
          <div v-if="establishment.rating_count > 0" class="flex-shrink-0 text-right">
            <div class="flex items-center gap-1">
              <Star class="w-5 h-5 text-yellow-500 fill-yellow-500" />
              <span class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ Number(establishment.rating_avg).toFixed(1) }}</span>
            </div>
            <span class="text-xs text-neutral-400">{{ establishment.rating_count }} {{ establishment.rating_count === 1 ? 'review' : 'reviews' }}</span>
          </div>
        </div>

        <!-- Description -->
        <p v-if="establishment.description" class="mt-3 text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">
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

        <!-- Quick info row -->
        <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm text-neutral-600 dark:text-neutral-400">
          <span v-if="establishment.member_count > 0" class="flex items-center gap-1.5">
            <Users class="w-4 h-4" />
            {{ establishment.member_count }} {{ $t('directory.organizations.members_count') }}
          </span>
          <span class="flex items-center gap-1.5">
            <Eye class="w-4 h-4" />
            {{ establishment.views_count }}
          </span>
          <span v-if="establishment.legal_entity_id" class="flex items-center gap-1.5 font-mono text-xs">
            <FileText class="w-4 h-4" />
            {{ establishment.legal_entity_id }}
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

        <!-- Action buttons -->
        <div class="mt-4 flex flex-wrap gap-2">
          <UiButton
            v-if="authStore.isAuthenticated && isJoinable && !establishment.is_member"
            variant="primary" size="sm" :loading="isJoining"
            @click="establishment.requires_terms_acceptance ? showJoinModal = true : joinEstablishment()"
          >
            {{ $t('directory.organizations.join_button') }}
          </UiButton>
          <UiButton
            v-if="establishment.terms_url"
            variant="outline" size="sm" :icon="Scale"
            :to="establishment.terms_url.startsWith('/') ? localePath(establishment.terms_url) : establishment.terms_url"
          >
            {{ $t('directory.organizations.view_terms') }}
          </UiButton>
          <UiButton
            v-if="establishment.treasury_enabled && establishment.slug"
            variant="outline" size="sm" :icon="Landmark"
            :to="localePath(`/org/${establishment.slug}/treasury`)"
          >
            {{ $t('treasury.title') }}
          </UiButton>
          <UiButton
            v-if="establishment.treasury_enabled && establishment.slug"
            variant="outline-warning" size="sm" :icon="ClipboardCheck"
            :to="localePath(`/org/${establishment.slug}/audit`)"
          >
            {{ $t('treasury.audit.title') }}
          </UiButton>
          <UiButton
            v-if="establishment.spark_address || establishment.ln_address"
            variant="success" size="sm" :icon="Wallet"
            @click="showPayModal = true"
          >
            {{ $t('directory.act_as.pay') }}
          </UiButton>
          <UiButton
            v-if="establishment.is_hub && authStore.isAuthenticated"
            variant="outline" size="sm" :icon="Package"
            :to="localePath(`/shipments?dest=${establishment.id}`)"
          >
            {{ $t('shipments.hub.send_here') }}
          </UiButton>
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
        </div>

        <!-- Utility buttons -->
        <div class="mt-3 flex flex-wrap gap-2">
          <UiButton v-if="mapCoords" variant="outline" size="sm" :icon="Navigation" @click="getDirections">
            {{ $t('directory.establishments.get_directions') }}
          </UiButton>
          <UiButton v-if="mapCoords" variant="outline" size="sm" :icon="Map" @click="openInMap">
            {{ $t('directory.establishments.view_on_map') }}
          </UiButton>
          <UiButton variant="outline" size="sm" :icon="Share2" @click="shareEstablishment">
            {{ $t('directory.establishments.share') }}
          </UiButton>
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
                  {{ $t(`directory.board.role_${bm.role.toLowerCase()}`) }}
                </span>
                <span v-if="bm.is_treasurer" class="px-1.5 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded text-xs shrink-0">
                  {{ $t('directory.act_as.treasurer') }}
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

        <!-- Treasurer info (for OWNER/ADMIN) -->
        <div v-if="canManageTreasurer" class="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <div class="flex items-center justify-between">
            <div class="text-sm text-neutral-600 dark:text-neutral-400">
              <UserCheck class="w-4 h-4 inline -mt-0.5 mr-1" />
              {{ $t('directory.act_as.treasurer') }}:
              <span v-if="treasurer" class="font-medium text-neutral-900 dark:text-neutral-100">{{ treasurer.profile_display_name || treasurer.profile_hna.split('@')[0] }}</span>
              <span v-else class="italic">{{ $t('directory.act_as.no_treasurer') }}</span>
            </div>
            <div class="flex gap-2">
              <UiButton variant="ghost" size="sm" @click="showTreasurerModal = true">
                {{ treasurer ? $t('directory.act_as.change_treasurer') : $t('directory.act_as.set_treasurer') }}
              </UiButton>
              <UiButton v-if="treasurer" variant="outline-error" size="sm" icon-only :icon="UserMinus" @click="removeTreasurer" />
            </div>
          </div>
        </div>

        <!-- Payment address (for OWNER/ADMIN/TREASURER) -->
        <div v-if="canManageTreasurer" class="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <div class="text-sm text-neutral-600 dark:text-neutral-400 mb-2">
            <Wallet class="w-4 h-4 inline -mt-0.5 mr-1" />
            {{ $t('directory.act_as.payment_address') }}
          </div>
          <div v-if="!editingPaymentAddress" class="flex items-center justify-between">
            <div class="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate max-w-[280px]">
              {{ establishment.spark_address || establishment.ln_address || $t('directory.act_as.no_payment_address') }}
            </div>
            <UiButton variant="ghost" size="sm" @click="startEditPaymentAddress" class="shrink-0 ml-2">
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

        <!-- Auditor (Fiscal Único) info (for OWNER/ADMIN) -->
        <div v-if="canManageTreasurer" class="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <div class="flex items-center justify-between">
            <div class="text-sm text-neutral-600 dark:text-neutral-400">
              <ClipboardCheck class="w-4 h-4 inline -mt-0.5 mr-1" />
              {{ $t('directory.act_as.auditor') }}:
              <span v-if="auditor" class="font-medium text-neutral-900 dark:text-neutral-100">{{ auditor.profile_hna || auditor.profile_display_name }}</span>
              <span v-else class="italic">{{ $t('directory.act_as.no_auditor') }}</span>
            </div>
            <div class="flex gap-2">
              <UiButton variant="ghost" size="sm" @click="showAuditorModal = true">
                {{ auditor ? $t('directory.act_as.change_auditor') : $t('directory.act_as.set_auditor') }}
              </UiButton>
              <UiButton v-if="auditor" variant="outline-error" size="sm" icon-only :icon="UserMinus" @click="removeAuditor" />
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

        <!-- Upload button (owner only) -->
        <div v-if="isOwner" class="mt-2">
          <label
            v-if="!isUploading"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 cursor-pointer"
          >
            <ImagePlus class="w-4 h-4" />
            {{ $t('directory.photos.add') }}
            <input type="file" accept="image/*" multiple class="hidden" @change="handlePhotoUpload" />
          </label>
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

        <!-- Address -->
        <div v-if="establishment.world_object" class="flex items-start gap-3 px-4 sm:px-6 py-3">
          <MapPin class="w-4 h-4 text-neutral-400 mt-0.5 flex-shrink-0" />
          <div class="min-w-0">
            <p class="text-sm text-neutral-900 dark:text-neutral-100">{{ establishment.world_object.full_address }}</p>
            <p v-if="establishment.floor || establishment.office_number" class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              <span v-if="establishment.floor">{{ $t('directory.establishments.floor') }} {{ establishment.floor }}</span>
              <span v-if="establishment.floor && establishment.office_number">, </span>
              <span v-if="establishment.office_number">{{ $t('directory.establishments.office') }} {{ establishment.office_number }}</span>
            </p>
          </div>
        </div>

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

      <!-- Map preview -->
      <div
        v-if="mapCoords"
        class="mt-3 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 cursor-pointer"
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
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
          <Package class="w-4 h-4 text-primary" />
          {{ $t('shipments.hub.info_title') }}
        </h2>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <!-- Accepted sizes -->
          <div v-if="establishment.hub_accepted_sizes?.length" class="col-span-2">
            <span class="text-neutral-500 dark:text-neutral-400 text-xs">{{ $t('shipments.hub.accepted_sizes') }}</span>
            <div class="flex flex-wrap gap-1.5 mt-1">
              <span
                v-for="size in establishment.hub_accepted_sizes"
                :key="size"
                class="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-lg font-medium"
              >
                {{ $t(`shipments.size.${size}`) }}
              </span>
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

      <!-- Reviews -->
      <div class="mt-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 px-4 sm:px-6 py-4">
        <EstablishmentReviews :establishment-id="props.id" />
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft, BadgeCheck, Star, Users, Eye, FileText, Scale,
  Landmark, MapPin, Phone, Mail, Globe, ExternalLink, Clock,
  AlertCircle, Wallet, UserCheck, UserMinus, ClipboardCheck, ChevronDown, Loader2,
  ImagePlus, X, ChevronLeft, ChevronRight, Camera, Pencil, Trash2,
  Grid3x3, Receipt, Vote, Package, Navigation, Map, Share2, Newspaper, Settings
} from 'lucide-vue-next'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'
import HubActivation from '~/components/HubActivation.vue'
import HubOperatorPanel from '~/components/HubOperatorPanel.vue'

const props = defineProps({
  id: { type: String, required: true }
})

const { t } = useI18n()
const router = useRouter()
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
  // WoT 2+ (is_verified_wot) or staff
  const profile = authStore.profile
  if (!profile) return false
  return profile.is_verified_wot || authStore.user?.is_staff
})

const boardMembers = computed(() => {
  const BOARD_ROLES = new Set(['OWNER', 'ADMIN'])
  return members.value.filter(m => BOARD_ROLES.has(m.role) || m.is_treasurer || m.is_auditor)
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
  if (mapCoords.value) {
    router.push(localePath(`/map?lat=${mapCoords.value.lat}&lng=${mapCoords.value.lon}&zoom=18`))
  }
}

const getDirections = () => {
  if (mapCoords.value) {
    router.push(localePath(`/map?dest_lat=${mapCoords.value.lat}&dest_lng=${mapCoords.value.lon}&zoom=15`))
  }
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
  if (window.history.length > 2) {
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
