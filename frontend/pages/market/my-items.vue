<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('market.my_items.title') }}</h1>
            <p class="text-neutral-600 dark:text-neutral-400 mt-1">{{ $t('market.my_items.subtitle') }}</p>
          </div>

          <UiButton size="sm" :icon="Plus" :to="localePath('/market/create')">
            {{ $t('market.create_listing') }}
          </UiButton>
        </div>

        <!-- Filters -->
        <div class="mt-4">
          <UiTabs
            :model-value="filterStatus"
            :tabs="statusTabs"
            variant="pills"
            @update:model-value="filterStatus = $event; fetchMyItems()"
          />
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
        <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin" aria-hidden="true"></div>
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <!-- Items grid -->
      <div v-else-if="items.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div
          v-for="item in items"
          :key="item.id"
          class="card overflow-hidden relative"
        >
          <!-- Status badge -->
          <div class="absolute top-2 right-2 z-10">
            <span
              :class="item.is_active ? 'bg-green-500' : 'bg-neutral-400'"
              class="px-2 py-1 text-xs font-medium text-white rounded-full"
            >
              {{ $t(item.is_active ? 'market.my_items.status_active' : 'market.my_items.status_hidden') }}
            </span>
          </div>

          <!-- Item image -->
          <div
            @click="viewItem(item)"
            class="cursor-pointer"
          >
            <div v-if="item.images && item.images.length > 0" class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700">
              <img :src="item.images[0].url" :alt="item.title" class="w-full h-full object-cover">
            </div>
            <div v-else class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
              <Package class="w-12 h-12 text-neutral-400" />
            </div>
          </div>

          <!-- Item content -->
          <div class="p-4">
            <!-- Type badge -->
            <div class="mb-2">
              <span
                :class="item.item_type === 'CREDIT' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200'"
                class="text-xs font-medium px-2 py-1 rounded"
              >
                {{ $t(item.item_type === 'CREDIT' ? 'market.type.credit' : 'market.type.debit') }}
              </span>
            </div>

            <!-- Title -->
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-1 line-clamp-2">
              {{ item.title }}
            </h3>

            <!-- Description -->
            <p class="text-sm text-neutral-600 dark:text-neutral-400 line-clamp-2 mb-3">
              {{ item.description || $t('market.item.no_description') }}
            </p>

            <!-- Price -->
            <div class="mb-3">
              <div v-if="item.pricing_options && item.pricing_options.length > 0" class="text-sm">
                <div
                  v-for="(opt, idx) in item.pricing_options.slice(0, 2)"
                  :key="idx"
                  class="font-semibold text-neutral-900 dark:text-neutral-100"
                >
                  {{ formatPricingOption(opt) }}
                </div>
              </div>
              <div v-else class="font-semibold text-green-600 dark:text-green-400">
                {{ $t('market.pricing.free') }}
              </div>
            </div>

            <!-- Actions -->
            <div class="flex gap-2 mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700">
              <UiButton variant="outline" size="sm" :icon="Edit" class="flex-1" @click="editItem(item)">
                {{ $t('market.actions.edit') }}
              </UiButton>
              <UiButton
                :variant="item.is_active ? 'outline-warning' : 'success'"
                size="sm"
                :icon="item.is_active ? EyeOff : Eye"
                @click="toggleActive(item)"
              >
                {{ $t(item.is_active ? 'market.actions.hide' : 'market.actions.activate') }}
              </UiButton>
              <UiButton variant="outline-error" size="sm" :icon="Trash2" @click="confirmDelete(item)">
                {{ $t('market.actions.delete') }}
              </UiButton>
            </div>

            <div class="mt-2 text-xs text-neutral-500">
              {{ formatDate(item.created_at) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-else class="text-center py-12">
        <img src="/images/para/pointing.png" alt="Para" class="mx-auto h-32 w-auto mb-6" />
        <h3 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
          {{ $t('market.my_items.empty_title') }}
        </h3>
        <p class="text-neutral-600 dark:text-neutral-400 mb-6">
          {{ $t('market.my_items.empty_description') }}
        </p>
        <UiButton :to="localePath('/market/create')">
          {{ $t('market.create_listing') }}
        </UiButton>
      </div>
    </div>

    <!-- Edit Modal -->
    <div v-if="editingItem" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        <div @click="editingItem = null" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

        <div class="relative inline-block w-full max-w-2xl px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
          <div class="absolute top-0 right-0 pt-4 pr-4">
            <button @click="editingItem = null" class="text-neutral-400 hover:text-neutral-500" :aria-label="$t('common.close')">
              <X class="w-6 h-6" aria-hidden="true" />
            </button>
          </div>

          <div class="sm:flex sm:items-start">
            <div class="w-full">
              <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100 mb-4">
                {{ $t('market.edit_modal.title') }}
              </h3>

              <form @submit.prevent="updateItem" class="space-y-4">
                <!-- Title -->
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('market.edit_modal.title_label') }}
                  </label>
                  <input
                    v-model="editForm.title"
                    type="text"
                    required
                    maxlength="255"
                    class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  >
                </div>

                <!-- Description -->
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('market.edit_modal.description_label') }}
                  </label>
                  <textarea
                    v-model="editForm.description"
                    rows="3"
                    maxlength="5000"
                    class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                  ></textarea>
                </div>

                <!-- Pricing Options -->
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    {{ $t('market.edit_modal.pricing_label') }}
                  </label>
                  <div class="space-y-3">
                    <div
                      v-for="(opt, index) in editForm.pricing_options"
                      :key="index"
                      class="p-3 border border-neutral-300 dark:border-neutral-600 rounded-lg"
                    >
                      <div class="flex justify-between items-start mb-2">
                        <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                          {{ $t('market.edit_modal.pricing_option_number', { number: index + 1 }) }}
                        </div>
                        <button
                          type="button"
                          @click="editForm.pricing_options.splice(index, 1)"
                          class="text-red-500 hover:text-red-700"
                        >
                          <X class="w-4 h-4" />
                        </button>
                      </div>

                      <!-- Type selector -->
                      <div class="grid grid-cols-3 gap-2 mb-2">
                        <label class="text-xs">
                          <input
                            v-model="opt.type"
                            type="radio"
                            :name="`edit-type-${index}`"
                            value="sale"
                            class="mr-1"
                          >
                          {{ $t('market.edit_modal.pricing_type_sale') }}
                        </label>
                        <label class="text-xs">
                          <input
                            v-model="opt.type"
                            type="radio"
                            :name="`edit-type-${index}`"
                            value="rent"
                            class="mr-1"
                          >
                          {{ $t('market.edit_modal.pricing_type_rent') }}
                        </label>
                        <label class="text-xs">
                          <input
                            v-model="opt.type"
                            type="radio"
                            :name="`edit-type-${index}`"
                            value="free"
                            class="mr-1"
                          >
                          {{ $t('market.pricing.free') }}
                        </label>
                      </div>

                      <!-- Amount and currency (if not free) -->
                      <div v-if="opt.type !== 'free'" class="grid grid-cols-2 gap-2 mb-2">
                        <input
                          v-model.number="opt.amount"
                          type="number"
                          step="0.01"
                          min="0"
                          :placeholder="$t('market.edit_modal.amount_placeholder')"
                          class="px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                        >
                        <select
                          v-model="opt.currency"
                          class="px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                        >
                          <option value="EUR">EUR</option>
                          <option value="USD">USD</option>
                          <option value="RUB">RUB</option>
                          <option value="BTC">BTC</option>
                        </select>
                      </div>

                      <!-- Unit (e.g. kg, hour, day, pcs) -->
                      <div v-if="opt.type !== 'free'" class="mb-2">
                        <input
                          v-model="opt.unit"
                          type="text"
                          list="edit-unit-presets"
                          :placeholder="$t('market.edit_modal.unit_placeholder')"
                          maxlength="50"
                          class="w-full px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                        />
                      </div>

                      <!-- Note -->
                      <input
                        v-model="opt.note"
                        type="text"
                        maxlength="100"
                        :placeholder="$t('market.edit_modal.note_placeholder')"
                        class="w-full px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-700"
                      >
                    </div>

                    <button
                      type="button"
                      @click="editForm.pricing_options.push({ type: 'sale', amount: null, currency: 'EUR', unit: '', note: '' })"
                      class="w-full px-3 py-2 border-2 border-dashed border-neutral-300 dark:border-neutral-600 rounded-lg hover:border-primary text-sm text-neutral-600 dark:text-neutral-400"
                    >
                      {{ $t('market.edit_modal.add_pricing_option') }}
                    </button>
                    <datalist id="edit-unit-presets">
                      <option value="kg" /><option value="g" /><option value="t" />
                      <option value="l" /><option value="ml" />
                      <option value="m" /><option value="m²" /><option value="m³" />
                      <option value="pcs" /><option value="шт" />
                      <option value="pair" /><option value="box" /><option value="set" />
                      <option value="hour" /><option value="day" /><option value="week" />
                      <option value="month" /><option value="year" />
                      <option value="session" /><option value="project" />
                      <option value="page" /><option value="consultation" />
                    </datalist>
                  </div>
                </div>

                <!-- Location -->
                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('market.edit_modal.location_label') }}
                  </label>
                  <div class="grid grid-cols-2 gap-3">
                    <input
                      v-model.number="editForm.location.latitude"
                      type="number"
                      step="0.000001"
                      min="-90"
                      max="90"
                      :placeholder="$t('market.edit_modal.latitude_placeholder')"
                      class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                    >
                    <input
                      v-model.number="editForm.location.longitude"
                      type="number"
                      step="0.000001"
                      min="-180"
                      max="180"
                      :placeholder="$t('market.edit_modal.longitude_placeholder')"
                      class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700"
                    >
                  </div>
                </div>

                <!-- Submit buttons -->
                <div class="space-y-3 pt-4">
                  <UiButton type="submit" :loading="updating" class="w-full">
                    {{ updating ? $t('market.edit_modal.saving') : $t('market.edit_modal.save') }}
                  </UiButton>
                  <UiButton type="button" variant="outline" class="w-full" @click="editingItem = null">
                    {{ $t('market.edit_modal.cancel') }}
                  </UiButton>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <UiConfirmModal
      :model-value="!!deletingItem"
      @update:model-value="!$event && (deletingItem = null)"
      :title="$t('market.delete_modal.title')"
      :message="deletingItem ? $t('market.delete_modal.confirm_message', { title: deletingItem.title }) : ''"
      :icon="Trash2"
      variant="error"
      :confirm-label="$t('market.delete_modal.delete')"
      :cancel-label="$t('market.delete_modal.cancel')"
      :loading="deleting"
      @confirm="deleteItem"
    />

    <!-- View Modal -->
    <div v-if="viewingItem" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        <div @click="viewingItem = null" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

        <div class="relative inline-block w-full max-w-2xl px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
          <div class="absolute top-0 right-0 pt-4 pr-4">
            <button @click="viewingItem = null" class="text-neutral-400 hover:text-neutral-500" :aria-label="$t('common.close')">
              <X class="w-6 h-6" aria-hidden="true" />
            </button>
          </div>

          <div class="sm:flex sm:items-start">
            <div class="w-full">
              <!-- Image gallery -->
              <div v-if="viewingItem.images && viewingItem.images.length > 0" class="mb-4">
                <div class="w-full aspect-video bg-neutral-200 dark:bg-neutral-700 rounded-lg overflow-hidden mb-2">
                  <img :src="viewingItem.images[0].url" :alt="viewingItem.title" class="w-full h-full object-cover">
                </div>
                <div v-if="viewingItem.images.length > 1" class="grid grid-cols-4 gap-2">
                  <div
                    v-for="(img, idx) in viewingItem.images.slice(1)"
                    :key="img.id"
                    class="aspect-square bg-neutral-200 dark:bg-neutral-700 rounded overflow-hidden"
                  >
                    <img :src="img.url" :alt="`${viewingItem.title} ${idx + 1}`" class="w-full h-full object-cover">
                  </div>
                </div>
              </div>

              <div class="flex items-start justify-between mb-4">
                <span
                  :class="viewingItem.type === 'CREDIT' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-secondary-100 text-secondary-800 dark:bg-secondary-900 dark:text-secondary-200'"
                  class="text-xs font-medium px-2 py-1 rounded"
                >
                  {{ $t(viewingItem.type === 'CREDIT' ? 'market.type.credit' : 'market.type.debit') }}
                </span>
                <span
                  :class="viewingItem.is_active ? 'bg-green-500' : 'bg-neutral-400'"
                  class="px-2 py-1 text-xs font-medium text-white rounded-full"
                >
                  {{ $t(viewingItem.is_active ? 'market.my_items.status_active' : 'market.my_items.status_hidden') }}
                </span>
              </div>

              <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
                {{ viewingItem.title }}
              </h3>

              <p class="text-neutral-600 dark:text-neutral-400 mb-4 whitespace-pre-wrap">
                {{ viewingItem.description || $t('market.detail_modal.no_description') }}
              </p>

              <div class="mb-4">
                <span class="text-sm text-neutral-500 dark:text-neutral-400 block mb-2">{{ $t('market.detail_modal.price_label') }}:</span>
                <div v-if="viewingItem.pricing_options && viewingItem.pricing_options.length > 0" class="space-y-1">
                  <div
                    v-for="(opt, idx) in viewingItem.pricing_options"
                    :key="idx"
                    class="font-semibold text-neutral-900 dark:text-neutral-100"
                  >
                    {{ formatPricingOption(opt) }}
                    <span v-if="opt.note" class="text-sm text-neutral-500 ml-2">({{ opt.note }})</span>
                  </div>
                </div>
                <div v-else class="font-semibold text-green-600 dark:text-green-400">
                  {{ $t('market.pricing.free') }}
                </div>
              </div>

              <div class="border-t border-neutral-200 dark:border-neutral-700 pt-4">
                <div class="text-sm text-neutral-500 dark:text-neutral-400 mb-2">
                  {{ $t('market.detail_modal.posted') }}: {{ formatDate(viewingItem.created_at) }}
                </div>
                <div class="flex gap-3 mt-4">
                  <UiButton class="flex-1" :icon="Edit" @click="editItem(viewingItem); viewingItem = null">
                    {{ $t('market.actions.edit') }}
                  </UiButton>
                  <UiButton variant="outline" class="flex-1" :icon="viewingItem.is_active ? EyeOff : Eye" @click="toggleActive(viewingItem); viewingItem = null">
                    {{ $t(viewingItem.is_active ? 'market.actions.hide' : 'market.actions.activate') }}
                  </UiButton>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'
import { Plus, Package, Edit, Trash2, Eye, EyeOff, X } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth'
})

const { t: $t, locale } = useI18n()

const authStore = useAuthStore()
const localePath = useLocalePath()
const { showSuccess, showError } = useNotification()
const { formatPricingOption } = usePricingFormat()

// State
const items = ref([])
const loading = ref(false)
const filterStatus = useTabSync(['all', 'active', 'inactive'])
const statusTabs = computed(() => [
  { id: 'all', label: $t('market.my_items.filter_all') },
  { id: 'active', label: $t('market.my_items.filter_active') },
  { id: 'inactive', label: $t('market.my_items.filter_inactive') },
])
const editingItem = ref(null)
const deletingItem = ref(null)
const viewingItem = ref(null)
const updating = ref(false)
const deleting = ref(false)

const editForm = ref({
  title: '',
  description: '',
  pricing_options: [],
  location: {
    latitude: null,
    longitude: null
  }
})

// Fetch user's items
const fetchMyItems = async () => {
  loading.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    // Get current user's ID
    const profile = await $fetch('/api/v1/profiles/me/', {
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })

    const params = new URLSearchParams({
      owner_id: profile.id
    })

    // Add status filter
    if (filterStatus.value === 'active') {
      params.append('is_active', 'true')
    } else if (filterStatus.value === 'inactive') {
      params.append('is_active', 'false')
    }

    const response = await $fetch(`/api/v1/items/?${params}`, {
      headers: { Authorization: `Bearer ${authStore.accessToken}` },
      credentials: 'include'
    })

    items.value = Array.isArray(response) ? response : (response.items || response.results || [])
  } catch (error) {
    console.error('Failed to fetch items:', error)
    showError($t('market.notifications.load_error'))
  } finally {
    loading.value = false
  }
}

// Edit item
const editItem = (item) => {
  editingItem.value = item
  editForm.value = {
    title: item.title,
    description: item.description || '',
    pricing_options: item.pricing_options?.length > 0
      ? JSON.parse(JSON.stringify(item.pricing_options))
      : [{ type: 'sale', amount: null, currency: 'EUR', unit: '', note: '' }],
    location: {
      latitude: item.location?.coordinates?.[1] || null,
      longitude: item.location?.coordinates?.[0] || null
    }
  }
}

// Update item
const updateItem = async () => {
  updating.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    // Clean pricing options
    const cleanPricingOptions = editForm.value.pricing_options
      .filter(opt => {
        if (opt.type === 'free') return true
        if (!opt.amount || opt.amount <= 0) return false
        return true
      })
      .map(opt => {
        const cleaned = { type: opt.type }
        if (opt.type !== 'free') {
          cleaned.amount = opt.amount
          cleaned.currency = opt.currency
        }
        if (opt.unit) {
          cleaned.unit = opt.unit
        }
        if (opt.note) {
          cleaned.note = opt.note
        }
        return cleaned
      })

    const payload = {
      title: editForm.value.title,
      description: editForm.value.description,
      pricing_options: cleanPricingOptions,
      expected_version: editingItem.value.version
    }

    if (editForm.value.location.latitude && editForm.value.location.longitude) {
      payload.location = editForm.value.location
    }

    await $fetch(`/api/v1/items/${editingItem.value.id}/`, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`,
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      body: payload
    })

    showSuccess($t('market.notifications.updated'))
    useState('marketDirty', () => false).value = true
    editingItem.value = null
    await fetchMyItems()
  } catch (error) {
    console.error('Failed to update item:', error)
    showError($t('market.notifications.update_error'))
  } finally {
    updating.value = false
  }
}

// Toggle active status
const toggleActive = async (item) => {
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    if (item.is_active) {
      // Deactivate
      await $fetch(`/api/v1/items/${item.id}/deactivate/`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authStore.accessToken}`
        },
        credentials: 'include'
      })
      showSuccess($t('market.notifications.hidden'))
    } else {
      // Activate (update with is_active: true)
      await $fetch(`/api/v1/items/${item.id}/`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${authStore.accessToken}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: { is_active: true, expected_version: item.version }
      })
      showSuccess($t('market.notifications.activated'))
    }

    await fetchMyItems()
  } catch (error) {
    console.error('Failed to toggle item status:', error)
    showError($t('market.notifications.status_error'))
  }
}

// Confirm delete
const confirmDelete = (item) => {
  deletingItem.value = item
}

// Delete item
const deleteItem = async () => {
  deleting.value = true
  try {
    await authStore.ensureToken()

    if (!authStore.accessToken) {
      showError($t('market.notifications.login_required_action'))
      return
    }

    await $fetch(`/api/v1/items/${deletingItem.value.id}/`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${authStore.accessToken}`
      },
      credentials: 'include'
    })

    showSuccess($t('market.notifications.deleted'))
    useState('marketDirty', () => false).value = true
    deletingItem.value = null
    await fetchMyItems()
  } catch (error) {
    console.error('Failed to delete item:', error)
    const errorMsg = error.response?._data?.error || $t('market.notifications.delete_error')
    showError(errorMsg)
  } finally {
    deleting.value = false
  }
}

// View item details
const viewItem = (item) => {
  viewingItem.value = item
}


// Format date
const formatDate = (dateString) => {
  const date = new Date(dateString)
  const now = new Date()
  const diff = Math.floor((now - date) / 1000)

  if (diff < 60) return $t('market.time.just_now')
  if (diff < 3600) return $t('market.time.minutes_ago', { n: Math.floor(diff / 60) })
  if (diff < 86400) return $t('market.time.hours_ago', { n: Math.floor(diff / 3600) })
  if (diff < 604800) return $t('market.time.days_ago', { n: Math.floor(diff / 86400) })

  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(() => {
  fetchMyItems()
})
</script>

