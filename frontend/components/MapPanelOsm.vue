<template>
  <div>
    <!-- Feature image preview -->
    <MapFeatureImage
      :image-url="featureImageUrl"
      :alt="featureTitle"
      :can-upload="canUploadFeatureImage"
      :building-geometry="featureBuildingGeometry"
      :building-levels="featureBuildingLevels"
      :poi-class="featurePoiClass"
      @upload="onFeatureImageUpload"
      class="flex-shrink-0"
    />

    <div class="px-4 pt-2 space-y-4">

    <!-- Building address (shown above establishments only if title is the name, not the address itself) -->
    <div v-if="!selectedEstablishment && !showCreateForm && establishments.length > 0 && buildingFullAddress && buildingFullAddress !== featureTitle" class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400 pb-2 border-b border-neutral-200 dark:border-neutral-700">
      <MapPin :size="14" class="flex-shrink-0" />
      <span>{{ buildingFullAddress }}</span>
    </div>

    <!-- Establishments List (prioritized - shown first) -->
    <div v-if="!selectedEstablishment && !showCreateForm && establishments.length > 0" class="space-y-2">
      <div
        v-for="est in establishments"
        :key="est.id"
        class="bg-white dark:bg-neutral-800 rounded-lg p-4 cursor-pointer border border-neutral-200 dark:border-neutral-700 hover:border-primary transition-colors"
        @click="showEstablishmentDetails(est.id)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1 flex items-center gap-2">
              {{ est.name }}
              <ShieldCheck v-if="est.is_verified" :size="16" class="text-secondary-600 flex-shrink-0" />
            </h3>
            <p v-if="est.category_name" class="text-sm text-neutral-600 dark:text-neutral-400 mb-2 flex items-center gap-1">
              <span v-if="est.category_icon" class="text-base">{{ est.category_icon }}</span>
              {{ est.category_name }}
            </p>
            <a
              v-if="est.phone"
              :href="`tel:${est.phone}`"
              class="text-link text-sm flex items-center gap-1"
              @click.stop
            >
              <Phone :size="14" />
              {{ est.phone }}
            </a>
          </div>
          <ChevronRight :size="20" class="text-neutral-400 dark:text-neutral-500 flex-shrink-0 mt-1" />
        </div>
      </div>

      <!-- Add organization button -->
      <UiButton variant="outline" size="md" :icon="Plus" class="w-full mt-4" @click="showCreateForm = true">
        {{ $t('map.panel.add_organization') }}
      </UiButton>
    </div>

    <!-- Establishment Details (Beautiful Design) -->
    <div v-else-if="selectedEstablishment" class="space-y-4">
      <!-- Header - minimalist with yellow background -->
      <div class="p-4 bg-primary dark:bg-primary-700">
        <div class="flex items-start justify-between gap-3 mb-3">
          <div class="flex items-start gap-3 flex-1 min-w-0">
            <div v-if="selectedEstablishment.category_icon" class="flex-shrink-0 text-4xl">
              {{ selectedEstablishment.category_icon }}
            </div>
            <div class="flex-1 min-w-0">
              <p v-if="selectedEstablishment.category_name" class="text-xs text-neutral-500 dark:text-neutral-700 mb-1">
                {{ selectedEstablishment.category_name }}
              </p>
              <h3 class="text-xl font-bold text-neutral-900 dark:text-neutral-900 flex items-center gap-2">
                {{ selectedEstablishment.name }}
                <ShieldCheck v-if="selectedEstablishment.is_verified" :size="18" class="text-secondary-600" />
              </h3>
              <div v-if="selectedEstablishment.rating_count > 0" class="flex items-center gap-1 mt-0.5">
                <span class="text-sm font-semibold text-neutral-800">★ {{ Number(selectedEstablishment.rating_avg).toFixed(1) }}</span>
                <span class="text-xs text-neutral-600">({{ selectedEstablishment.rating_count }})</span>
              </div>
            </div>
          </div>
          <UiButton
            v-if="selectedEstablishment.owner_id === authStore.profile?.id"
            variant="ghost"
            size="sm"
            icon-only
            :icon="Edit"
            class="flex-shrink-0 text-neutral-800 dark:text-neutral-800 hover:bg-neutral-900/10 dark:hover:bg-neutral-900/20"
            :title="$t('map.panel.edit_organization')"
            @click="startEdit"
          />
        </div>
      </div>

      <!-- Photos gallery (compact) -->
      <div v-if="establishmentPhotos.length > 0" class="grid grid-cols-3 gap-1">
        <div
          v-for="(photo, idx) in establishmentPhotos.slice(0, 6)"
          :key="photo.url"
          class="relative cursor-pointer overflow-hidden rounded bg-neutral-100 dark:bg-neutral-800 aspect-square"
          @click="panelLightboxIdx = idx; panelLightboxOpen = true"
        >
          <img :src="photo.url" :alt="photo.caption || ''" class="w-full h-full object-cover" loading="lazy" />
        </div>
      </div>

      <!-- Panel lightbox -->
      <div v-if="panelLightboxOpen" class="fixed inset-0 bg-black/90 z-[60] flex items-center justify-center" @click.self="panelLightboxOpen = false">
        <button @click="panelLightboxOpen = false" class="absolute top-4 right-4 p-2 text-white/80 hover:text-white" :aria-label="t('common.close')">
          <X :size="24" aria-hidden="true" />
        </button>
        <button v-if="establishmentPhotos.length > 1" @click="panelLightboxIdx = (panelLightboxIdx - 1 + establishmentPhotos.length) % establishmentPhotos.length" class="absolute left-4 p-2 text-white/80 hover:text-white" aria-label="Previous image">
          <ChevronLeft :size="32" aria-hidden="true" />
        </button>
        <img :src="establishmentPhotos[panelLightboxIdx]?.url" :alt="establishmentPhotos[panelLightboxIdx]?.caption || 'Photo'" class="max-w-[90vw] max-h-[90vh] object-contain" />
        <button v-if="establishmentPhotos.length > 1" @click="panelLightboxIdx = (panelLightboxIdx + 1) % establishmentPhotos.length" class="absolute right-4 p-2 text-white/80 hover:text-white" aria-label="Next image">
          <ChevronRight :size="32" aria-hidden="true" />
        </button>
      </div>

      <!-- Tabs -->
      <UiTabs v-model="activeTab" :tabs="establishmentTabs" class="px-1" />

      <!-- Info tab -->
      <template v-if="activeTab === 'info'">
      <div v-if="selectedEstablishment.description"
           class="border-l-4 pl-4 py-1 border-primary dark:border-primary-700">
        <p class="text-neutral-700 dark:text-neutral-300 text-sm leading-relaxed">
          {{ selectedEstablishment.description }}
        </p>
      </div>

      <div class="space-y-2">
        <div v-if="selectedEstablishment.world_object"
             class="border-l-4 border-transparent hover:border-primary bg-neutral-50 dark:bg-neutral-800 p-3">
          <div class="flex items-start gap-3">
            <MapPin :size="18" class="flex-shrink-0 text-neutral-600 dark:text-neutral-400 mt-0.5" />
            <div class="flex-1 min-w-0">
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('map.panel.address') }}</p>
              <p class="text-sm text-neutral-900 dark:text-neutral-100 font-medium">
                {{ selectedEstablishment.world_object.full_address }}
                <span v-if="selectedEstablishment.floor || selectedEstablishment.office_number" class="block text-neutral-600 dark:text-neutral-400 font-normal mt-0.5">
                  <span v-if="selectedEstablishment.floor">{{ $t('map.panel.floor') }} {{ selectedEstablishment.floor }}</span>
                  <span v-if="selectedEstablishment.floor && selectedEstablishment.office_number">, </span>
                  <span v-if="selectedEstablishment.office_number">{{ $t('map.panel.office') }} {{ selectedEstablishment.office_number }}</span>
                </span>
              </p>
            </div>
          </div>
        </div>

        <a v-if="selectedEstablishment.phone"
           :href="`tel:${selectedEstablishment.phone}`"
           class="block border-l-4 border-transparent hover:border-primary bg-neutral-50 dark:bg-neutral-800 p-3">
          <div class="flex items-center gap-3">
            <Phone :size="18" class="flex-shrink-0 text-neutral-600 dark:text-neutral-400" />
            <div class="flex-1 min-w-0">
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">{{ $t('map.panel.phone') }}</p>
              <p class="text-sm text-neutral-900 dark:text-neutral-100 font-medium">{{ selectedEstablishment.phone }}</p>
            </div>
          </div>
        </a>

        <a v-if="selectedEstablishment.email"
           :href="`mailto:${selectedEstablishment.email}`"
           class="block border-l-4 border-transparent hover:border-primary bg-neutral-50 dark:bg-neutral-800 p-3">
          <div class="flex items-center gap-3">
            <Mail :size="18" class="flex-shrink-0 text-neutral-600 dark:text-neutral-400" />
            <div class="flex-1 min-w-0">
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">{{ $t('map.panel.email') }}</p>
              <p class="text-sm text-neutral-900 dark:text-neutral-100 font-medium truncate">{{ selectedEstablishment.email }}</p>
            </div>
          </div>
        </a>

        <a v-if="selectedEstablishment.website"
           :href="selectedEstablishment.website"
           target="_blank"
           class="block border-l-4 border-transparent hover:border-primary bg-neutral-50 dark:bg-neutral-800 p-3">
          <div class="flex items-center gap-3">
            <ExternalLink :size="18" class="flex-shrink-0 text-neutral-600 dark:text-neutral-400" />
            <div class="flex-1 min-w-0">
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">{{ $t('map.panel.website') }}</p>
              <p class="text-sm text-neutral-900 dark:text-neutral-100 font-medium truncate">{{ selectedEstablishment.website }}</p>
            </div>
          </div>
        </a>
      </div>

      <!-- Opening Hours -->
      <div v-if="selectedEstablishment.opening_hours && Object.keys(selectedEstablishment.opening_hours).length > 0"
           class="bg-neutral-50 dark:bg-neutral-800 p-3">
        <div class="flex items-center gap-2 mb-2">
          <Clock :size="18" class="text-neutral-600 dark:text-neutral-400" />
          <h4 class="font-semibold text-neutral-900 dark:text-neutral-100 text-sm">{{ $t('map.panel.opening_hours') }}</h4>
          <UiBadge v-if="establishmentOpenStatus === true" variant="success" type="soft" size="sm">
            {{ $t('directory.establishments.open_now') }}
          </UiBadge>
          <UiBadge v-else-if="establishmentOpenStatus === false" variant="error" type="soft" size="sm">
            {{ $t('directory.establishments.closed_now') }}
          </UiBadge>
        </div>
        <div class="space-y-1">
          <div v-for="(hours, day) in selectedEstablishment.opening_hours" :key="day"
               class="flex justify-between items-center py-1 text-sm">
            <span class="font-medium text-neutral-600 dark:text-neutral-400 capitalize">{{ day }}</span>
            <span class="font-semibold text-neutral-900 dark:text-neutral-100">{{ hours }}</span>
          </div>
        </div>
      </div>
      </template>

      <!-- Reviews tab -->
      <template v-else-if="activeTab === 'reviews'">
        <EstablishmentReviews
          :establishment-id="selectedEstablishment.id"
          :owner-id="selectedEstablishment.owner_id"
        />
      </template>
    </div>

    <!-- Create/Edit Form -->
    <div v-else-if="showCreateForm" class="space-y-4">
      <button
        @click="cancelForm"
        class="flex items-center gap-2 text-neutral-500 hover:text-primary transition text-sm font-medium"
      >
        <ChevronRight :size="16" class="rotate-180" />
        {{ $t('map.panel.back_to_list') }}
      </button>

      <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100">
        {{ editMode ? $t('map.panel.edit_organization') : $t('map.panel.create_organization') }}
      </h3>

      <form @submit.prevent="createEstablishment" class="space-y-3">
        <div>
          <label for="est-name" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.name_required') }}</label>
          <input id="est-name" v-model="formData.name" type="text" required
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
            :placeholder="$t('map.panel.name_placeholder')" />
        </div>
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.category') }}</label>
          <CategorySelect v-model="formData.category_id" mode="leaf" domain="directory" :placeholder="$t('map.panel.category_placeholder')" />
        </div>
        <div>
          <label for="est-description" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.description') }}</label>
          <textarea id="est-description" v-model="formData.description" rows="3"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
            :placeholder="$t('map.panel.description_placeholder')" />
        </div>
        <div>
          <label for="est-phone" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.phone') }}</label>
          <input id="est-phone" v-model="formData.phone" type="tel"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
            :placeholder="$t('map.panel.phone_placeholder')" />
        </div>
        <div>
          <label for="est-email" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.email') }}</label>
          <input id="est-email" v-model="formData.email" type="email"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
            :placeholder="$t('map.panel.email_placeholder')" />
        </div>
        <div>
          <label for="est-website" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.website') }}</label>
          <input id="est-website" v-model="formData.website" type="url"
            class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
            :placeholder="$t('map.panel.website_placeholder')" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label for="est-floor" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.floor_label') }}</label>
            <input id="est-floor" v-model="formData.floor" type="text"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
              placeholder="1" />
          </div>
          <div>
            <label for="est-office" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('map.panel.office_label') }}</label>
            <input id="est-office" v-model="formData.office_number" type="text"
              class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100"
              placeholder="12А" />
          </div>
        </div>
        <div class="flex gap-2 pt-2">
          <UiButton variant="outline" class="flex-1" @click="cancelForm">{{ $t('map.panel.cancel') }}</UiButton>
          <UiButton variant="secondary" tag="button" type="submit" class="flex-1" :disabled="!formData.name" :loading="creatingEstablishment">
            {{ editMode ? $t('map.panel.save') : $t('map.panel.create') }}
          </UiButton>
        </div>
      </form>
    </div>

    <!-- Empty building - show add button -->
    <div v-else-if="!selectedEstablishment && !showCreateForm && establishments.length === 0 && feature?.sourceLayer === 'building'" class="py-12 text-center">
      <Building2 class="w-12 h-12 mx-auto text-neutral-400 dark:text-neutral-600 mb-3" aria-hidden="true" />
      <h3 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('map.panel.no_organizations_yet') }}
      </h3>
      <UiButton variant="secondary" size="md" :icon="Plus" @click="showCreateForm = true">
        {{ $t('map.panel.add_first_organization') }}
      </UiButton>
    </div>

    <!-- OSM Properties -->
    <div v-if="hasProperties && (showOsmData || (establishments.length === 0 && feature?.sourceLayer !== 'building'))" class="space-y-2">
      <div
        v-for="(value, key) in readableProperties"
        :key="key"
        class="flex justify-between items-center py-2 border-b border-neutral-200 dark:border-neutral-700 last:border-0"
      >
        <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ translateKey(key) }}</span>
        <component
          :is="getPropertyComponent(key)"
          :value="value"
          :property-key="key"
          @click="handlePropertyClick(key, value)"
          :class="getPropertyClasses(key)"
        >
          {{ formatValue(value) }}
        </component>
      </div>
    </div>

    <!-- Compact Action Buttons -->
    <div class="flex gap-2 border-t border-neutral-200 dark:border-neutral-700 pt-4">
      <UiButton
        v-if="establishments.length > 0 && hasProperties"
        :variant="showOsmData ? 'secondary' : 'outline'"
        size="sm"
        :icon="ChevronDown"
        class="flex-1"
        @click="showOsmData = !showOsmData"
      >
        {{ showOsmData ? $t('map.panel.hide_details') : $t('map.panel.details_toggle') }}
      </UiButton>

      <UiButton
        :variant="showDebug ? 'secondary' : 'outline'"
        size="sm"
        :icon="Code"
        class="flex-1"
        @click="showDebug = !showDebug"
      >
        {{ $t('map.panel.raw_data') }}
      </UiButton>

      <UiButton variant="outline" size="sm" :icon="ExternalLink" class="flex-1" @click="openInOSM">
        OSM
      </UiButton>
    </div>

    <!-- Raw Data Content (collapsible) -->
    <div v-if="showDebug" class="mt-3">
      <div v-if="osmData" class="bg-neutral-900 text-warning-400 rounded-lg p-3 text-xs overflow-x-auto">
        <pre class="font-mono">{{ JSON.stringify(osmData, null, 2) }}</pre>
      </div>
      <div v-else class="bg-neutral-900 text-success-400 rounded-lg p-3 text-xs overflow-x-auto">
        <pre class="font-mono">{{ JSON.stringify(feature, null, 2) }}</pre>
      </div>
    </div>

    <!-- Claim ownership -->
    <div v-if="featureWorldObjectId && !featureOwnerId && authStore.isAuthenticated" class="mt-3">
      <UiButton variant="secondary" size="sm" :icon="ShieldCheck" :loading="claimingObject" @click="claimWorldObject">
        {{ t('map.panel.claim_ownership') }}
      </UiButton>
    </div>
    <div v-else-if="featureOwnerId" class="mt-3 text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-1">
      <ShieldCheck :size="12" />
      {{ t('map.panel.owned_by', { name: featureOwnerName }) }}
    </div>

    <!-- Comments section -->
    <div v-if="osmData?.data?.osm_id" class="mt-4 pt-3 border-t border-neutral-200 dark:border-neutral-700">
      <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2 flex items-center gap-1.5">
        <MessageSquare :size="14" />
        {{ t('map.panel.comments') }}
        <span v-if="featureComments.length" class="text-xs font-normal text-neutral-500">({{ featureComments.length }})</span>
      </h3>

      <div v-if="featureComments.length" class="space-y-2 mb-3">
        <div v-for="c in featureComments" :key="c.id" class="bg-neutral-50 dark:bg-neutral-800 rounded-lg px-3 py-2">
          <div class="flex justify-between items-start">
            <span class="text-xs font-medium text-neutral-700 dark:text-neutral-300">{{ c.author_name }}</span>
            <div class="flex items-center gap-1">
              <span class="text-xs text-neutral-400">{{ formatCommentTime(c.created_at) }}</span>
              <button v-if="c.author_id === authStore.profile?.id" @click="deleteComment(c.id)" class="text-neutral-400 hover:text-red-500 transition ml-1">
                <X :size="12" />
              </button>
            </div>
          </div>
          <p class="text-sm text-neutral-800 dark:text-neutral-200 mt-0.5 whitespace-pre-line">{{ c.text }}</p>
        </div>
      </div>

      <div v-if="authStore.isAuthenticated" class="flex gap-2">
        <input v-model="newCommentText" type="text" maxlength="2000" :placeholder="t('map.panel.add_comment')"
          class="flex-1 px-3 py-1.5 text-sm bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          @keyup.enter="submitComment" />
        <UiButton variant="secondary" size="sm" :icon="Send" icon-only :disabled="!newCommentText.trim()" @click="submitComment" />
      </div>
    </div>

    <!-- Contracts section -->
    <div v-if="featureWorldObjectId" class="mt-4 pt-3 border-t border-neutral-200 dark:border-neutral-700">
      <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2 flex items-center gap-1.5">
        <FileText :size="14" />
        {{ t('map.panel.contracts') }}
        <span v-if="featureContracts.length" class="text-xs font-normal text-neutral-500">({{ featureContracts.length }})</span>
      </h3>
      <div v-if="featureContracts.length" class="space-y-1.5 mb-3">
        <div v-for="c in featureContracts" :key="c.id" class="bg-neutral-50 dark:bg-neutral-800 rounded-lg px-3 py-2 flex items-center justify-between">
          <div class="min-w-0">
            <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200 truncate block">{{ c.title }}</span>
            <span class="text-xs text-neutral-500">{{ c.creator_name }} & {{ c.partner_name }}</span>
          </div>
          <UiBadge :variant="contractStatusVariant(c.status)" type="soft" size="sm" class="flex-shrink-0 ml-2">
            {{ c.status }}
          </UiBadge>
        </div>
      </div>
      <UiButton v-if="authStore.isAuthenticated" variant="secondary" size="sm" :icon="FileText"
        @click="navigateTo(localePath(`/contracts?world_object=${featureWorldObjectId}`))">
        {{ t('map.panel.new_contract') }}
      </UiButton>
    </div>

    <!-- Activity feed -->
    <MapFeatureActivity
      v-if="featureWorldObjectId"
      :world-object-id="featureWorldObjectId"
      class="mt-4 pt-3 border-t border-neutral-200 dark:border-neutral-700"
    />

    </div> <!-- Close px-4 inner wrapper -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, ChevronDown, ChevronRight, ChevronLeft, Phone, ShieldCheck, ExternalLink, Code, Plus, Edit, MessageSquare, Send, MapPin, Mail, Clock, FileText, Building2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import CategorySelect from '~/components/CategorySelect.vue'
import EstablishmentReviews from '~/components/EstablishmentReviews.vue'
import MapFeatureImage from '~/components/MapFeatureImage.vue'
import MapFeatureActivity from '~/components/MapFeatureActivity.vue'
import { checkIsOpen } from '~/composables/useOpeningHours'

const router = useRouter()
const localePath = useLocalePath()
const { t, locale } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const props = defineProps<{
  feature: any
  clickCoordinates: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'search-location', value: any): void
  (e: 'establishment-selected', id: string | null): void
  (e: 'osm-resolved', data: { osmId: number }): void
  (e: 'update:title', title: string): void
  (e: 'update:subtitle', subtitle: string): void
  (e: 'update:has-selected-establishment', val: boolean): void
}>()

// ======== State ========
const showDebug = ref(false)
const showOsmData = ref(false)
const osmData = ref<any>(null)
const loadingOsmData = ref(false)

// Establishments
const establishments = ref<any[]>([])
const loadingEstablishments = ref(false)
const selectedEstablishment = ref<any>(null)
const activeTab = ref('info')
const panelLightboxOpen = ref(false)
const panelLightboxIdx = ref(0)
const showCreateForm = ref(false)
const creatingEstablishment = ref(false)
const editMode = ref(false)
const editingEstablishmentId = ref<string | null>(null)
const formData = ref({
  name: '', description: '', category_id: '', phone: '', email: '', website: '', floor: '', office_number: '', opening_hours: {} as any,
})

// Feature image
const featureImageUrlOverride = ref<string | null>(null)
const featurePhotoUrl = ref<string | null>(null)

// Ownership
const featureWorldObjectId = ref<string | null>(null)
const featureOwnerId = ref<string | null>(null)
const featureOwnerName = ref('')
const claimingObject = ref(false)

// Comments
const featureComments = ref<Array<{ id: string; object_id: string; text: string; author_id: string; author_name: string; created_at: string }>>([])
const newCommentText = ref('')

// Contracts
const featureContracts = ref<Array<{ id: string; title: string; status: string; creator_name: string; partner_name: string; created_at: string }>>([])

// ======== Computed ========

const osmId = computed(() => osmData.value?.data?.osm_id || props.feature?.properties?.osm_id || props.feature?.properties?.id)

const osmType = computed(() => {
  const sourceTable = osmData.value?.data?.source_table
  if (!sourceTable) return null
  if (sourceTable.includes('_point')) return 'node'
  // imposm3 stores relation-derived geometries (multipolygons) with a negative
  // osm_id; positive ids are ways. Without this, a building that is an OSM
  // relation links to the way of the same number (e.g. an unrelated street).
  if (sourceTable.includes('_polygon') || sourceTable.includes('_linestring')) {
    return Number(osmId.value) < 0 ? 'relation' : 'way'
  }
  return 'way'
})

const enrichedProperties = computed(() => {
  const tileProps = props.feature?.properties || {}
  if (!osmData.value?.data) return tileProps

  const apiData = osmData.value.data
  const merged = { ...tileProps }

  if (apiData.address) {
    merged.address_housenumber = apiData.address.housenumber
    merged.address_street = apiData.address.street
    merged.address_block = apiData.address.block_number
  }
  if (apiData.name && !merged.name) merged.name = apiData.name
  if (apiData.building) merged.building = apiData.building
  if (apiData.buildinglevels) merged.building_levels = apiData.buildinglevels
  if (apiData.buildingheight) merged.building_height = apiData.buildingheight
  if (apiData.material) merged.material = apiData.material
  if (apiData.colour) merged.colour = apiData.colour
  if (apiData.tags) Object.assign(merged, apiData.tags)

  return merged
})

const buildingFullAddress = computed(() => {
  const enriched = enrichedProperties.value || {}
  const parts: string[] = []
  if (enriched.address_street) parts.push(enriched.address_street)
  if (enriched.address_housenumber) parts.push(enriched.address_housenumber)
  return parts.join(' ')
})

const hasProperties = computed(() => enrichedProperties.value && Object.keys(enrichedProperties.value).length > 0)

const establishmentOpenStatus = computed(() => {
  const est = selectedEstablishment.value as any
  if (!est?.opening_hours) return null
  return checkIsOpen(est.opening_hours)
})

const establishmentPhotos = computed(() => {
  const est = selectedEstablishment.value as any
  if (!est) return []
  const photos: Array<{ url: string; caption: string }> = []
  if (est.uploaded_photos) {
    for (const p of est.uploaded_photos) photos.push({ url: p.url, caption: p.caption || '' })
  }
  if (est.photos) {
    for (const url of est.photos) photos.push({ url, caption: '' })
  }
  return photos
})

const establishmentTabs = computed(() => [
  { id: 'info', label: t('map.panel.tab_info') },
  { id: 'reviews', label: t('map.panel.tab_reviews'), badge: selectedEstablishment.value?.rating_count > 0 ? selectedEstablishment.value.rating_count : undefined },
])

// ======== Feature image computeds ========

const featureImageUrl = computed<string | null>(() => featureImageUrlOverride.value || featurePhotoUrl.value)

const canUploadFeatureImage = computed(() => authStore.isAuthenticated)

const featureBuildingGeometry = computed<number[][][] | null>(() => {
  const geom = props.feature?.geometry
  if (!geom) return null
  if (geom.type === 'Polygon' && geom.coordinates?.length > 0) return geom.coordinates
  if (geom.type === 'MultiPolygon' && geom.coordinates?.[0]?.length > 0) return geom.coordinates[0]
  return null
})

const featureBuildingLevels = computed<number | null>(() => {
  const enriched = enrichedProperties.value || {}
  const levels = enriched.building_levels || props.feature?.properties?.building_levels
  return levels ? Number(levels) : null
})

const featurePoiClass = computed<string | null>(() => {
  if (featureBuildingGeometry.value) return null
  const tileProps = props.feature?.properties || {}
  return tileProps.subclass || tileProps.class || null
})

// ======== Title/subtitle (emitted to orchestrator) ========

function localizedName(tileProps: any, enriched: any): string | null {
  const lang = locale.value
  if (tileProps[`name_${lang}`]) return tileProps[`name_${lang}`]
  if (enriched[`name:${lang}`]) return enriched[`name:${lang}`]
  if (lang !== 'en' && tileProps.name_latin) return tileProps.name_latin
  return null
}

const featureTitle = computed(() => {
  if (!props.feature) return ''
  if (selectedEstablishment.value) return selectedEstablishment.value.name
  if (establishments.value.length > 0) {
    const tileProps = props.feature.properties || {}
    const enriched = enrichedProperties.value || {}
    const localized = localizedName(tileProps, enriched)
    if (localized) return localized
    if (enriched.name) return enriched.name
    if (osmData.value?.data?.name) return osmData.value.data.name
    if (tileProps.name) return tileProps.name
    return enriched.address_street && enriched.address_housenumber
      ? `${enriched.address_street} ${enriched.address_housenumber}` : 'Building'
  }
  const tileProps = props.feature.properties || {}
  const enriched = enrichedProperties.value || {}

  const localized = localizedName(tileProps, enriched)
  if (localized) return localized
  if (enriched.name) return enriched.name
  if (osmData.value?.data?.name) return osmData.value.data.name
  if (tileProps.name) return tileProps.name

  const layer = props.feature.sourceLayer || ''

  if (layer === 'transportation' || layer === 'transportation_name') {
    const highway = enriched.highway || tileProps.class
    if (highway) {
      const roadTranslated = t(`map.panel.road_types.${highway}`)
      if (!roadTranslated.includes('map.panel')) return roadTranslated
    }
    return t('map.panel.layer_types.transportation')
  }

  if (tileProps.class || tileProps.type) {
    const cls = tileProps.subclass || tileProps.class || tileProps.type
    const translated = t(`map.panel.poi_classes.${cls}`)
    if (!translated.includes('map.panel')) return translated
    return cls
  }

  if (layer === 'building') {
    const addr = enriched.address_street && enriched.address_housenumber
      ? `${enriched.address_street} ${enriched.address_housenumber}` : null
    if (addr) return addr
    const buildingType = enriched.building || tileProps.building || 'yes'
    const translated = t(`map.panel.building_types.${buildingType}`)
    return translated.includes('map.panel') ? t('map.panel.building_types.yes') : translated
  }

  const layerTranslated = t(`map.panel.layer_types.${layer}`)
  if (!layerTranslated.includes('map.panel')) return enriched.name || layerTranslated

  return enriched.name || ''
})

const featureType = computed(() => {
  if (!props.feature) return ''
  if (selectedEstablishment.value) return selectedEstablishment.value.category_name || 'Организация'
  if (establishments.value.length > 0) return t('map.panel.organizations_count', { count: establishments.value.length }, establishments.value.length)

  const layer = props.feature.sourceLayer || ''
  const tileProps = props.feature.properties || {}

  if (layer === 'poi') {
    const subclass = tileProps.subclass
    const cls = tileProps.class
    if (subclass) { const sub = t(`map.panel.poi_classes.${subclass}`); if (!sub.includes('map.panel')) return sub }
    if (cls) { const main = t(`map.panel.poi_classes.${cls}`); if (!main.includes('map.panel')) return main }
    if (cls) return cls.charAt(0).toUpperCase() + cls.slice(1).replace(/_/g, ' ')
  }

  if (layer === 'transportation' || layer === 'transportation_name') {
    const enriched = enrichedProperties.value || {}
    const highway = enriched.highway || tileProps.class
    if (highway) { const r = t(`map.panel.road_types.${highway}`); if (!r.includes('map.panel')) return r }
    return t('map.panel.layer_types.transportation')
  }

  const translated = t(`map.panel.layer_types.${layer}`)
  return translated.includes('map.panel') ? '' : translated
})

// Emit title/subtitle to orchestrator
watch(featureTitle, (val) => emit('update:title', val), { immediate: true })
watch(featureType, (val) => emit('update:subtitle', val), { immediate: true })
watch(selectedEstablishment, (val) => emit('update:has-selected-establishment', !!val), { immediate: true })

// ======== Readable properties ========

const readableProperties = computed(() => {
  const enriched = enrichedProperties.value || {}
  const filtered: Record<string, any> = {}
  const usefulKeys = [
    'name', 'building', 'building_levels', 'building_height',
    'address_street', 'address_housenumber',
    'material', 'colour', 'landuse', 'natural',
    'waterway', 'leisure', 'amenity',
    'shop', 'tourism', 'craft', 'office', 'healthcare',
    'cuisine', 'opening_hours', 'phone', 'website',
    'operator', 'brand', 'wheelchair',
    'highway', 'surface', 'lanes', 'maxspeed', 'ref',
    'oneway', 'lit', 'sidewalk', 'cycleway', 'bridge', 'tunnel'
  ]
  for (const key of usefulKeys) {
    if (enriched[key] !== undefined && enriched[key] !== null && enriched[key] !== '') {
      filtered[key] = enriched[key]
    }
  }
  if (filtered.name && filtered.name === featureTitle.value) delete filtered.name
  return filtered
})

const formatValue = (value: any) => {
  if (value === null || value === undefined) return 'N/A'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'number') return value.toLocaleString()
  return String(value)
}

const translateKey = (key: string) => {
  const path = `map.panel.properties.${key}`
  const translated = t(path)
  return translated !== path ? translated : key
}

const getPropertyComponent = (key: string) => {
  const interactiveKeys = ['address_street', 'address_housenumber', 'building', 'building_levels']
  return interactiveKeys.includes(key) ? 'button' : 'span'
}

const getPropertyClasses = (key: string) => {
  const interactiveKeys = ['address_street', 'address_housenumber', 'building', 'building_levels']
  if (interactiveKeys.includes(key)) return 'text-sm font-medium text-secondary-600 hover:text-secondary-800 hover:underline cursor-pointer'
  return 'text-sm font-medium text-neutral-900 dark:text-neutral-100'
}

const handlePropertyClick = (key: string, value: any) => {
  if (key === 'address_street') { emit('search-location', value); emit('close') }
  else if (key === 'address_housenumber') { toastStore.info(`You are already at house number ${value}`); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  else if (key === 'building') {
    const map: Record<string, string> = { residential: 'real-estate', apartments: 'real-estate', commercial: 'commercial-real-estate', office: 'commercial-real-estate', retail: 'commercial-real-estate', house: 'real-estate' }
    router.push(localePath(`/market?category=${map[value] || 'real-estate'}`))
  }
  else if (key === 'building_levels') { toastStore.info(`This building has ${value} floor${value > 1 ? 's' : ''}`) }
}

const openInOSM = () => {
  if (osmId.value && osmType.value) {
    window.open(`https://www.openstreetmap.org/${osmType.value}/${Math.abs(osmId.value)}`, '_blank')
    return
  }
  if (!props.clickCoordinates) return
  window.open(`https://www.openstreetmap.org/#map=18/${props.clickCoordinates.lat}/${props.clickCoordinates.lng}`, '_blank')
}

// ======== Data fetching ========

async function fetchOsmDataByCoordinates(lat: number, lon: number, layer: string) {
  if (!lat || !lon) return
  loadingOsmData.value = true
  osmData.value = null
  try {
    const params = new URLSearchParams({ lat: lat.toString(), lon: lon.toString(), radius: '10' })
    if (layer) params.append('layer', layer)
    const response = await fetch(`/api/v1/geo/osm/at-point?${params}`)
    if (!response.ok) return
    const data = await response.json()
    if (data.features && data.features.length > 0) {
      let selectedFeature = data.features[0]
      if (data.features.length > 1) {
        const lineStringFeature = data.features.find((f: any) => f.geometry_type === 'LineString')
        if (lineStringFeature) selectedFeature = lineStringFeature
      }
      osmData.value = { found: true, data: selectedFeature }
    }
  } catch (error) {
    console.error('Error fetching OSM data:', error)
  } finally {
    loadingOsmData.value = false
  }
}

async function fetchOsmData(id: number, layer: string) {
  if (!id) return
  loadingOsmData.value = true
  osmData.value = null
  try {
    const response = await fetch(`/api/v1/geo/osm/${id}?layer=${layer || ''}`)
    if (!response.ok) return
    osmData.value = await response.json()
  } catch (error) {
    console.error('Error fetching OSM data:', error)
  } finally {
    loadingOsmData.value = false
  }
}

async function fetchEstablishments(lat: number, lon: number) {
  if (!lat || !lon) return
  loadingEstablishments.value = true
  establishments.value = []
  try {
    const params = new URLSearchParams({ lat: lat.toString(), lon: lon.toString(), radius_km: '0.05' })
    const response = await fetch(`/api/v1/geo/establishments/?${params}`)
    if (!response.ok) return
    const data = await response.json()
    if (data.items && data.items.length > 0) {
      establishments.value = data.items
      if ((window as any)._pendingEstablishmentId) {
        const estId = (window as any)._pendingEstablishmentId
        setTimeout(() => { showEstablishmentDetails(estId); delete (window as any)._pendingEstablishmentId }, 100)
      }
    }
  } catch (error) {
    console.error('Error fetching establishments:', error)
  } finally {
    loadingEstablishments.value = false
  }
}

async function fetchWorldObjectPhoto(xenoSource: string, xenoId: string) {
  try {
    const wo = await $fetch<{ id: string } | null>(`/api/v1/geo/world-objects/resolve/?xeno_source=${encodeURIComponent(xenoSource)}&xeno_id=${encodeURIComponent(xenoId)}`)
    if (wo?.id) {
      const photos = await $fetch<Array<{ url: string }>>(`/api/v1/core/photos/?object_id=${wo.id}`)
      if (photos.length > 0) featurePhotoUrl.value = photos[0]!.url
    }
  } catch { /* No WorldObject yet */ }
}

async function fetchComments(objectId: string) {
  try { featureComments.value = await $fetch(`/api/v1/core/comments/?object_id=${objectId}`) }
  catch { featureComments.value = [] }
}

async function fetchWorldObjectContracts(objectId: string) {
  try { featureContracts.value = await $fetch(`/api/v1/geo/world-objects/${objectId}/contracts/`) }
  catch { featureContracts.value = [] }
}

// ======== Actions ========

async function claimWorldObject() {
  if (!featureWorldObjectId.value) return
  claimingObject.value = true
  try {
    await authStore.ensureToken()
    const resp = await $fetch<{ owner_id: string; owner_name: string }>(`/api/v1/geo/world-objects/${featureWorldObjectId.value}/claim/`, {
      method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    featureOwnerId.value = resp.owner_id
    featureOwnerName.value = resp.owner_name
    toastStore.success(t('map.panel.claimed'))
  } catch (err: any) {
    toastStore.error(err?.data?.error || 'Failed to claim')
  } finally { claimingObject.value = false }
}

async function submitComment() {
  const text = newCommentText.value.trim()
  if (!text || !authStore.isAuthenticated) return
  if (!osmData.value?.data?.osm_id || !osmType.value) return
  try {
    await authStore.ensureToken()
    const xenoId = `${osmType.value}/${Math.abs(osmData.value.data.osm_id)}`
    const wo = await $fetch<{ id: string }>('/api/v1/geo/world-objects/', {
      method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { xeno_source: 'osm', xeno_id: xenoId, latitude: props.clickCoordinates?.lat || null, longitude: props.clickCoordinates?.lng || null },
    })
    const comment = await $fetch<any>('/api/v1/core/comments/', {
      method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { object_id: wo.id, text },
    })
    featureComments.value.push(comment)
    newCommentText.value = ''
  } catch (err: any) { toastStore.error(err?.data?.error || 'Failed to post comment') }
}

async function deleteComment(commentId: string) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/core/comments/${commentId}/`, {
      method: 'DELETE', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    featureComments.value = featureComments.value.filter(c => c.id !== commentId)
  } catch (err: any) { toastStore.error(err?.data?.error || 'Failed to delete comment') }
}

function contractStatusVariant(status: string): 'warning' | 'success' | 'error' | 'neutral' {
  if (status === 'PENDING_PARTNER') return 'warning'
  if (status === 'SIGNED' || status === 'COMPLETED') return 'success'
  if (status === 'DISPUTED') return 'error'
  return 'neutral'
}

function formatCommentTime(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

async function onFeatureImageUpload(file: File) {
  if (!authStore.isAuthenticated) { toastStore.error(t('map.panel.error_auth_required')); return }
  if (!osmData.value?.data?.osm_id || !osmType.value) { toastStore.error('Cannot identify this map feature'); return }
  try {
    await authStore.ensureToken()
    const xenoId = `${osmType.value}/${Math.abs(osmData.value.data.osm_id)}`
    const worldObjResponse = await $fetch<{ id: string; created: boolean }>('/api/v1/geo/world-objects/', {
      method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        xeno_source: 'osm', xeno_id: xenoId,
        latitude: props.clickCoordinates?.lat || null, longitude: props.clickCoordinates?.lng || null,
        full_address: enrichedProperties.value?.address_street ? `${enrichedProperties.value.address_street} ${enrichedProperties.value.address_housenumber || ''}`.trim() : '',
      },
    })
    const formDataObj = new FormData()
    formDataObj.append('image', file)
    formDataObj.append('object_id', worldObjResponse.id)
    formDataObj.append('order', '0')
    const photoResponse = await $fetch<{ id: string; url: string }>('/api/v1/core/photos/', {
      method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: formDataObj,
    })
    featureImageUrlOverride.value = photoResponse.url
    toastStore.success(t('map.panel.photo_uploaded'))
  } catch (err: any) {
    console.error('Photo upload failed:', err)
    toastStore.error(err?.data?.error || 'Failed to upload photo')
  }
}

// ======== Establishments CRUD ========

const showEstablishmentDetails = async (id: string) => {
  try {
    selectedEstablishment.value = await $fetch(`/api/v1/geo/establishments/${id}/`)
    emit('establishment-selected', id)
  } catch (error) { console.error('Error loading establishment:', error) }
}

function backToList() {
  selectedEstablishment.value = null
  activeTab.value = 'info'
  emit('establishment-selected', null)
}

const startEdit = () => {
  if (!selectedEstablishment.value) return
  formData.value = {
    name: selectedEstablishment.value.name || '', description: selectedEstablishment.value.description || '',
    category_id: selectedEstablishment.value.category_id || '', phone: selectedEstablishment.value.phone || '',
    email: selectedEstablishment.value.email || '', website: selectedEstablishment.value.website || '',
    floor: selectedEstablishment.value.floor || '', office_number: selectedEstablishment.value.office_number || '',
    opening_hours: selectedEstablishment.value.opening_hours || {},
  }
  editMode.value = true
  editingEstablishmentId.value = selectedEstablishment.value.id
  selectedEstablishment.value = null
  showCreateForm.value = true
}

const cancelForm = () => {
  showCreateForm.value = false
  editMode.value = false
  editingEstablishmentId.value = null
  formData.value = { name: '', description: '', category_id: '', phone: '', email: '', website: '', floor: '', office_number: '', opening_hours: {} }
}

const createEstablishment = async () => {
  if (!authStore.isAuthenticated) { toastStore.error(t('map.panel.error_auth_required')); return }
  creatingEstablishment.value = true
  try {
    await authStore.ensureToken()
    let buildingId = null
    if (osmData.value?.data?.osm_id && props.clickCoordinates) {
      let detectedCountry = 'PT'
      let detectedCity = 'Unknown'
      try {
        const coords = `${props.clickCoordinates.lat.toFixed(6)},${props.clickCoordinates.lng.toFixed(6)}`
        const geoResult = await $fetch<any>(`/api/v1/geo/geocode/search?q=${coords}&limit=1`)
        const feat = geoResult?.features?.[0]?.properties
        if (feat) {
          if (feat.country_a) detectedCountry = (feat.country_code || feat.country_a?.slice(0, 2) || 'PT').toUpperCase()
          detectedCity = feat.locality || feat.localadmin || feat.region || 'Unknown'
        }
      } catch (e) { console.warn('Reverse geocode failed, using defaults', e) }

      const buildingResponse = await $fetch<any>('/api/v1/geo/buildings/', {
        method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` },
        body: {
          osm_way_id: osmData.value.data.osm_id,
          location: { latitude: props.clickCoordinates.lat, longitude: props.clickCoordinates.lng },
          country: detectedCountry, city: detectedCity,
          full_address: `${enrichedProperties.value.address_street || ''} ${enrichedProperties.value.address_housenumber || ''}`.trim() || 'Unknown',
          street: enrichedProperties.value.address_street || '', house_number: enrichedProperties.value.address_housenumber || '',
          building_type: enrichedProperties.value.building || 'yes',
        },
      })
      buildingId = buildingResponse.id
    }

    const body = {
      world_object_id: buildingId, name: formData.value.name, description: formData.value.description || '',
      category_id: formData.value.category_id || null, phone: formData.value.phone || '',
      email: formData.value.email || '', website: formData.value.website || '',
      floor: formData.value.floor || '', office_number: formData.value.office_number || '',
    }

    if (editMode.value && editingEstablishmentId.value) {
      await $fetch(`/api/v1/geo/establishments/${editingEstablishmentId.value}/`, {
        method: 'PUT', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` }, body,
      })
    } else {
      await $fetch('/api/v1/geo/establishments/', {
        method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${authStore.token}` }, body,
      })
    }
    const wasEditMode = editMode.value
    if (props.clickCoordinates) await fetchEstablishments(props.clickCoordinates.lat, props.clickCoordinates.lng)
    cancelForm()
    toastStore.success(wasEditMode ? t('map.panel.success_updated') : t('map.panel.success_created'))
  } catch (error: any) {
    let errorMsg = error.data?.detail || error.data?.message || error.message || t('map.panel.error_creating')
    if (errorMsg.includes('WoT') || errorMsg.includes('verification')) errorMsg = t('map.panel.error_wot_required')
    toastStore.error(errorMsg)
  } finally { creatingEstablishment.value = false }
}

// ======== Watchers ========

watch(() => [props.feature, props.clickCoordinates] as const, ([newFeature, coords]) => {
  osmData.value = null
  establishments.value = []
  selectedEstablishment.value = null
  activeTab.value = 'info'
  featureImageUrlOverride.value = null
  featurePhotoUrl.value = null
  featureComments.value = []
  featureContracts.value = []
  newCommentText.value = ''
  featureWorldObjectId.value = null
  featureOwnerId.value = null
  featureOwnerName.value = ''

  if (!newFeature) return

  if (coords?.lat && coords?.lng && newFeature?.sourceLayer === 'building') {
    fetchEstablishments(coords.lat, coords.lng)
  }

  if (newFeature?.properties?.osm_id) {
    fetchOsmData(newFeature.properties.osm_id, newFeature.sourceLayer)
  } else if (coords?.lat && coords?.lng) {
    fetchOsmDataByCoordinates(coords.lat, coords.lng, newFeature.sourceLayer)
  }
}, { immediate: true })

watch(osmData, (newOsmData) => {
  if (newOsmData?.data?.osm_id && osmType.value) {
    emit('osm-resolved', { osmId: newOsmData.data.osm_id })
    const xenoId = `${osmType.value}/${Math.abs(newOsmData.data.osm_id)}`
    fetchWorldObjectPhoto('osm', xenoId)
    $fetch<{ id: string; owner_id?: string; owner_name?: string }>(`/api/v1/geo/world-objects/resolve/?xeno_source=osm&xeno_id=${encodeURIComponent(xenoId)}`)
      .then(wo => {
        if (wo?.id) {
          featureWorldObjectId.value = wo.id
          featureOwnerId.value = wo.owner_id || null
          featureOwnerName.value = wo.owner_name || ''
          fetchComments(wo.id)
          fetchWorldObjectContracts(wo.id)
        }
      })
      .catch(() => {})
  }
})

watch(establishments, (newEstablishments) => {
  if (newEstablishments.length === 1 && !selectedEstablishment.value && !showCreateForm.value) {
    showEstablishmentDetails(newEstablishments[0].id)
  }
})

// Expose backToList for orchestrator's header
defineExpose({ backToList })
</script>
