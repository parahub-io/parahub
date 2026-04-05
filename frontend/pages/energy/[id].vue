<template>
  <div>
    <Head>
      <Title>{{ cell?.name || $t('energy.title') }} — Parahub</Title>
    </Head>

    <div class="max-w-3xl mx-auto px-4 py-6">

      <!-- Back link -->
      <NuxtLink
        :to="localePath('/energy')"
        class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 mb-4"
      >
        <ArrowLeft :size="16" />
        {{ $t('energy.title') }}
      </NuxtLink>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-16">
        <div class="animate-spin rounded-full h-10 w-10 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-white" />
      </div>

      <!-- Error -->
      <div v-else-if="!cell" class="text-center py-12">
        <p class="text-neutral-500">{{ $t('common.not_found') }}</p>
      </div>

      <template v-else>
        <!-- Header -->
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <div
                class="w-3 h-3 rounded-full flex-shrink-0"
                :class="statusDotClass"
              />
              <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
                {{ cell.name }}
              </h1>
            </div>
            <div class="flex items-center gap-3 flex-wrap text-sm">
              <span :class="statusTextClass">
                {{ $t(`energy.status.${displayStatus}`) }}
              </span>
              <span v-if="cell.current_price_eur" class="font-medium text-success-600 dark:text-success-400">
                {{ cell.current_price_eur }} €/kWh
              </span>
              <span v-if="cell.created_by_hna" class="text-neutral-400">
                {{ $t('energy.detail.created_by', { name: cell.created_by_display_name || cell.created_by_hna?.split('@')[0] }) }}
              </span>
              <NuxtLink
                v-if="cell.establishment_name"
                :to="localePath(`/directory`)"
                class="px-2 py-0.5 rounded-full text-xs bg-secondary-100 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400 hover:bg-secondary-200 dark:hover:bg-secondary-900/50 transition-colors"
              >
                {{ cell.establishment_name }}
              </NuxtLink>
            </div>
          </div>
          <!-- Owner actions -->
          <button
            v-if="isOwner"
            @click="showSettingsModal = true"
            class="p-2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            <Settings :size="18" />
          </button>
        </div>

        <!-- Mini map -->
        <div class="card overflow-hidden mb-4">
          <StaticMapPreview
            :latitude="cell.latitude"
            :longitude="cell.longitude"
            :zoom="14"
            :height="180"
          />
        </div>

        <!-- Stats row -->
        <div class="grid grid-cols-4 gap-3 mb-6">
          <div class="card p-3 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ cell.producers_count }}</div>
            <div class="text-xs text-neutral-500">{{ $t('energy.cell.producers') }}</div>
          </div>
          <div class="card p-3 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ cell.consumers_count }}</div>
            <div class="text-xs text-neutral-500">{{ $t('energy.cell.consumers') }}</div>
          </div>
          <div class="card p-3 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ cell.total_capacity_kw }}</div>
            <div class="text-xs text-neutral-500">kW</div>
          </div>
          <div class="card p-3 text-center">
            <div class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ cell.radius_km }}</div>
            <div class="text-xs text-neutral-500">km</div>
          </div>
        </div>

        <!-- Live production (if available) -->
        <div v-if="liveData && liveData.producers_online > 0" class="card p-4 mb-6 border-success-200 dark:border-success-800">
          <div class="flex items-center gap-2 mb-2">
            <Activity :size="16" class="text-success-500" />
            <span class="text-sm font-semibold text-neutral-700 dark:text-neutral-300">{{ $t('energy.detail.live_production') }}</span>
          </div>
          <div class="flex items-baseline gap-2">
            <span class="text-2xl font-bold text-success-600 dark:text-success-400">
              {{ (liveData.total_production_w / 1000).toFixed(2) }}
            </span>
            <span class="text-sm text-neutral-500">kW</span>
            <span class="ml-auto text-xs text-neutral-400">
              {{ liveData.producers_online }}/{{ liveData.producers_total }} {{ $t('energy.detail.online') }}
            </span>
          </div>
        </div>

        <!-- Description -->
        <div v-if="cell.description" class="card p-4 mb-6">
          <p class="text-sm text-neutral-600 dark:text-neutral-400 whitespace-pre-line">{{ cell.description }}</p>
        </div>

        <!-- My membership -->
        <div v-if="myMembership" class="card p-4 mb-6 border-primary/30">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Zap :size="16" class="text-primary" />
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                {{ myMembership === 'producer' ? $t('energy.role.producer') : $t('energy.role.consumer') }}
              </span>
            </div>
            <UiButton
              variant="outline"
              size="xs"
              :loading="leaving"
              @click="leaveCell"
            >
              {{ $t('energy.detail.leave') }}
            </UiButton>
          </div>
        </div>

        <!-- Shares & Distributions (cooperative investment) -->
        <SharesPanel
          :object-id="cell.establishment_id || cell.id"
          :is-owner="isOwner"
        />
        <DistributionsPanel
          :object-id="cell.establishment_id || cell.id"
          :is-owner="isOwner"
        />

        <!-- Smart Relays (consumers only) -->
        <div v-if="myMembership === 'consumer'" class="card p-4 mb-6">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
              <ToggleLeft :size="16" />
              {{ $t('energy.relay.title') }}
            </h3>
            <button
              v-if="!showRelayForm"
              @click="showRelayForm = true"
              class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
            >
              + {{ $t('energy.relay.add') }}
            </button>
          </div>

          <p class="text-xs text-neutral-400 mb-3">{{ $t('energy.relay.hint') }}</p>

          <!-- Add relay form -->
          <form v-if="showRelayForm" @submit.prevent="addRelay" class="space-y-3 mb-4 p-3 bg-neutral-50 dark:bg-neutral-800/50 rounded-lg">
            <div>
              <label class="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('energy.relay.name') }}</label>
              <input
                v-model="relayForm.name"
                required
                :placeholder="$t('energy.relay.name_placeholder')"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
              />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('energy.relay.type') }}</label>
                <select
                  v-model="relayForm.relay_type"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
                >
                  <option value="SHELLY_GEN2">Shelly Gen2+</option>
                  <option value="SHELLY_GEN1">Shelly Gen1</option>
                  <option value="TASMOTA">Tasmota</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('energy.relay.channel') }}</label>
                <input
                  v-model.number="relayForm.channel"
                  type="number"
                  min="0"
                  max="3"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
                />
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">{{ $t('energy.relay.url') }}</label>
              <input
                v-model="relayForm.url"
                required
                placeholder="http://192.168.1.50"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm font-mono focus:ring-2 focus:ring-primary focus:border-transparent outline-none text-neutral-900 dark:text-neutral-100"
              />
            </div>
            <div class="flex gap-2">
              <UiButton variant="outline" size="xs" @click="showRelayForm = false">{{ $t('common.cancel') }}</UiButton>
              <UiButton variant="primary" tag="button" type="submit" size="xs" :loading="relayAdding">{{ $t('energy.relay.add') }}</UiButton>
            </div>
          </form>

          <!-- Relay list -->
          <div v-if="relays.length" class="space-y-2">
            <div
              v-for="relay in relays"
              :key="relay.id"
              class="flex items-center gap-3 p-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700"
            >
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ relay.name }}</div>
                <div class="text-xs text-neutral-400 font-mono truncate">{{ relay.url }}</div>
                <div class="flex items-center gap-2 mt-0.5">
                  <span class="text-xs text-neutral-500">{{ relay.relay_type }}</span>
                  <span v-if="relay.last_error" class="text-xs text-red-500 truncate">{{ relay.last_error }}</span>
                  <span v-else-if="relay.last_triggered" class="text-xs text-success-500">{{ $t('energy.relay.last_ok') }}</span>
                </div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button
                  @click="testRelay(relay)"
                  :disabled="relay._testing"
                  class="p-1.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 rounded"
                  :title="$t('energy.relay.test')"
                >
                  <Wifi :size="14" :class="{ 'animate-pulse': relay._testing }" />
                </button>
                <button
                  @click="deleteRelay(relay)"
                  class="p-1.5 text-red-400 hover:text-red-600 rounded"
                  :title="$t('common.delete')"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </div>
          </div>
          <p v-else-if="!showRelayForm" class="text-xs text-neutral-400 italic">{{ $t('energy.relay.empty') }}</p>
        </div>

        <!-- Join buttons (if not member) -->
        <div v-else-if="authStore.isAuthenticated && !myMembership" class="card p-4 mb-6">
          <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3">
            {{ $t('energy.join.title') }}
          </h3>
          <div class="space-y-2">
            <button
              @click="joinRole = 'producer'"
              class="w-full text-left px-4 py-3 rounded-xl border transition-colors flex items-center gap-3"
              :class="joinRole === 'producer'
                ? 'border-primary bg-primary-50 dark:bg-primary-900/20'
                : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600'"
            >
              <Sun :size="18" class="text-warning-500 flex-shrink-0" />
              <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ $t('energy.join.as_producer') }}</span>
            </button>
            <button
              @click="joinRole = 'consumer'"
              class="w-full text-left px-4 py-3 rounded-xl border transition-colors flex items-center gap-3"
              :class="joinRole === 'consumer'
                ? 'border-primary bg-primary-50 dark:bg-primary-900/20'
                : 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600'"
            >
              <Home :size="18" class="text-secondary-500 flex-shrink-0" />
              <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ $t('energy.join.as_consumer') }}</span>
            </button>
          </div>

          <!-- Producer join form -->
          <form v-if="joinRole === 'producer'" @submit.prevent="joinAsProducer" class="mt-4 space-y-3">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.cpe_code') }} *
              </label>
              <input
                v-model="joinForm.cpe_code"
                required
                placeholder="PT0002..."
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
              />
              <p class="text-xs text-neutral-400 mt-1">{{ $t('energy.form.cpe_hint') }}</p>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('energy.form.capacity_kw') }} *
                </label>
                <input
                  v-model.number="joinForm.capacity_kw"
                  type="number"
                  step="0.1"
                  min="0.1"
                  required
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  {{ $t('energy.form.battery_kwh') }}
                </label>
                <input
                  v-model.number="joinForm.battery_kwh"
                  type="number"
                  step="0.1"
                  min="0"
                  class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.inverter_type') }}
              </label>
              <select
                v-model="joinForm.inverter_type"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
              >
                <option v-for="inv in inverterTypes" :key="inv" :value="inv">
                  {{ $t(`energy.inverter.${inv}`) }}
                </option>
              </select>
            </div>
            <UiButton
              variant="primary"
              tag="button"
              type="submit"
              :disabled="joining || !joinForm.cpe_code || !joinForm.capacity_kw"
              :loading="joining"
              class="w-full"
            >
              {{ $t('energy.join.as_producer') }}
            </UiButton>
          </form>

          <!-- Consumer join form -->
          <form v-if="joinRole === 'consumer'" @submit.prevent="joinAsConsumer" class="mt-4 space-y-3">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.cpe_code') }} *
              </label>
              <input
                v-model="joinForm.cpe_code"
                required
                placeholder="PT0002..."
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
              />
              <p class="text-xs text-neutral-400 mt-1">{{ $t('energy.form.cpe_hint') }}</p>
            </div>
            <UiButton
              variant="primary"
              tag="button"
              type="submit"
              :disabled="joining || !joinForm.cpe_code"
              :loading="joining"
              class="w-full"
            >
              {{ $t('energy.join.as_consumer') }}
            </UiButton>
          </form>
        </div>

        <!-- Members list -->
        <div v-if="members.length" class="card p-4 mb-6">
          <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-3 flex items-center gap-1.5">
            <Users :size="16" />
            {{ $t('energy.detail.members') }} ({{ members.length }})
          </h3>
          <div class="space-y-2">
            <div
              v-for="m in members"
              :key="m.profile_id"
              class="flex items-center justify-between text-sm py-1.5"
            >
              <div class="flex items-center gap-2">
                <NuxtLink
                  :to="localePath(`/u/${m.profile_hna.split('@')[0]}`)"
                  class="text-neutral-900 dark:text-neutral-100 hover:text-secondary transition-colors"
                >
                  {{ m.profile_display_name || m.profile_hna.split('@')[0] }}
                </NuxtLink>
                <span
                  class="px-1.5 py-0.5 rounded text-xs"
                  :class="m.role === 'producer'
                    ? 'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-400'
                    : 'bg-secondary-100 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400'"
                >
                  {{ $t(`energy.role.${m.role}`) }}
                </span>
              </div>
              <div class="text-xs text-neutral-400">
                <span v-if="m.capacity_kw">{{ m.capacity_kw }} kW</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Technical details -->
        <div v-if="cell.transformer_id" class="card p-4 mb-6">
          <h3 class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
            {{ $t('energy.detail.technical') }}
          </h3>
          <div class="text-sm text-neutral-500 space-y-1">
            <div>{{ $t('energy.cell.transformer') }}: <span class="text-neutral-700 dark:text-neutral-300 font-mono">{{ cell.transformer_id }}</span></div>
            <div>{{ $t('energy.cell.radius') }}: {{ cell.radius_km }} km</div>
          </div>
        </div>

        <!-- Map link -->
        <NuxtLink
          :to="`/map?energy=${cell.id}&lat=${cell.latitude}&lng=${cell.longitude}&zoom=14`"
          class="card p-4 flex items-center gap-3 hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors"
        >
          <MapPin :size="18" class="text-secondary-500" />
          <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('energy.detail.view_on_map') }}</span>
          <ChevronRight :size="16" class="ml-auto text-neutral-300 dark:text-neutral-600" />
        </NuxtLink>
      </template>
    </div>

    <!-- Settings modal (owner only) -->
    <Teleport to="body">
      <div
        v-if="showSettingsModal"
        class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
        @click.self="showSettingsModal = false"
      >
        <div class="absolute inset-0 bg-black/40" @click="showSettingsModal = false" />
        <div class="relative w-full max-w-md bg-white dark:bg-neutral-900 rounded-t-2xl sm:rounded-2xl shadow-2xl p-6 mx-0 sm:mx-4">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {{ $t('energy.detail.settings') }}
            </h2>
            <button @click="showSettingsModal = false" class="p-1 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">
              <X :size="20" />
            </button>
          </div>
          <form @submit.prevent="updateCell" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.form.description') }}
              </label>
              <textarea
                v-model="settingsForm.description"
                rows="3"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none resize-none"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('energy.detail.price_eur_kwh') }}
              </label>
              <input
                v-model.number="settingsForm.current_price_eur"
                type="number"
                step="0.01"
                min="0"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
              />
            </div>
            <div class="flex gap-3 pt-2">
              <UiButton variant="outline" class="flex-1" @click="showSettingsModal = false">
                {{ $t('common.cancel') }}
              </UiButton>
              <UiButton variant="primary" tag="button" type="submit" class="flex-1" :loading="saving">
                {{ $t('common.save') }}
              </UiButton>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ArrowLeft, Zap, MapPin, Users, Sun, Home, Settings, X, Activity, ChevronRight, ToggleLeft, Wifi, Trash2 } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'

const route = useRoute()
const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const toastStore = useToastStore()

const cellId = route.params.id as string

const cell = ref<any>(null)
const members = ref<any[]>([])
const liveData = ref<any>(null)
const loading = ref(true)
const joining = ref(false)
const leaving = ref(false)
const saving = ref(false)
const showSettingsModal = ref(false)
const joinRole = ref<'producer' | 'consumer' | null>(null)

// Smart relays
const relays = ref<any[]>([])
const showRelayForm = ref(false)
const relayAdding = ref(false)
const relayForm = ref({ name: '', relay_type: 'SHELLY_GEN2', url: '', channel: 0 })

const joinForm = ref({
  cpe_code: '',
  capacity_kw: null as number | null,
  battery_kwh: null as number | null,
  inverter_type: 'OTHER',
})

const settingsForm = ref({
  description: '',
  current_price_eur: null as number | null,
})

const inverterTypes = ['SOLARMAN', 'FRONIUS', 'GROWATT', 'SMA', 'SHELLY', 'OTHER']

const myMembership = computed(() => {
  if (!authStore.profile) return null
  const pid = authStore.profile.id
  const m = members.value.find(m => m.profile_id === pid)
  return m?.role || null
})

const isOwner = computed(() => {
  if (!authStore.profile || !cell.value) return false
  return cell.value.created_by_hna === authStore.profile.hna
})

const displayStatus = computed(() => {
  if (!cell.value) return 'OFFLINE'
  if (cell.value.producers_count === 0 && cell.value.status !== 'OFFLINE') return 'WAITING'
  return cell.value.status
})

const statusDotClass = computed(() => ({
  'bg-success-500': displayStatus.value === 'GREEN',
  'bg-warning-400': displayStatus.value === 'YELLOW' || displayStatus.value === 'WAITING',
  'bg-error-400': displayStatus.value === 'RED',
  'bg-neutral-300 dark:bg-neutral-600': displayStatus.value === 'OFFLINE',
}))

const statusTextClass = computed(() => ({
  'text-success-600 dark:text-success-400': displayStatus.value === 'GREEN',
  'text-warning-600 dark:text-warning-400': displayStatus.value === 'YELLOW' || displayStatus.value === 'WAITING',
  'text-error-500': displayStatus.value === 'RED',
  'text-neutral-400': displayStatus.value === 'OFFLINE',
}))

const authHeaders = async () => {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

const fetchCell = async () => {
  try {
    cell.value = await $fetch(`/api/v1/energy/cells/${cellId}/`)
    settingsForm.value.description = cell.value.description || ''
    settingsForm.value.current_price_eur = cell.value.current_price_eur
  } catch {
    cell.value = null
  }
}

const fetchMembers = async () => {
  try {
    members.value = await $fetch(`/api/v1/energy/cells/${cellId}/members/`)
  } catch {
    members.value = []
  }
}

const fetchLive = async () => {
  try {
    liveData.value = await $fetch(`/api/v1/energy/cells/${cellId}/live/`)
  } catch {
    liveData.value = null
  }
}

const joinAsProducer = async () => {
  if (!joinForm.value.cpe_code || !joinForm.value.capacity_kw) return
  joining.value = true
  try {
    const headers = await authHeaders()
    await $fetch(`/api/v1/energy/cells/${cellId}/join/producer/`, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: {
        cpe_code: joinForm.value.cpe_code,
        capacity_kw: joinForm.value.capacity_kw,
        battery_kwh: joinForm.value.battery_kwh || undefined,
        inverter_type: joinForm.value.inverter_type,
      },
    })
    toastStore.success(t('energy.detail.joined'))
    joinRole.value = null
    await Promise.all([fetchCell(), fetchMembers()])
  } catch (err: any) {
    const msg = err?.data?.detail || err?.data?.message || t('common.error')
    toastStore.error(msg)
  } finally {
    joining.value = false
  }
}

const joinAsConsumer = async () => {
  if (!joinForm.value.cpe_code) return
  joining.value = true
  try {
    const headers = await authHeaders()
    await $fetch(`/api/v1/energy/cells/${cellId}/join/consumer/`, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: { cpe_code: joinForm.value.cpe_code },
    })
    toastStore.success(t('energy.detail.joined'))
    joinRole.value = null
    await Promise.all([fetchCell(), fetchMembers()])
  } catch (err: any) {
    const msg = err?.data?.detail || err?.data?.message || t('common.error')
    toastStore.error(msg)
  } finally {
    joining.value = false
  }
}

const leaveCell = async () => {
  leaving.value = true
  try {
    const headers = await authHeaders()
    await $fetch(`/api/v1/energy/cells/${cellId}/leave/`, {
      method: 'POST',
      credentials: 'include',
      headers,
    })
    toastStore.success(t('energy.detail.left'))
    await Promise.all([fetchCell(), fetchMembers()])
  } catch (err: any) {
    toastStore.error(err?.data?.detail || t('common.error'))
  } finally {
    leaving.value = false
  }
}

const updateCell = async () => {
  saving.value = true
  try {
    const headers = await authHeaders()
    await $fetch(`/api/v1/energy/cells/${cellId}/`, {
      method: 'PATCH',
      credentials: 'include',
      headers,
      body: {
        description: settingsForm.value.description,
        current_price_eur: settingsForm.value.current_price_eur,
      },
    })
    toastStore.success(t('common.saved'))
    showSettingsModal.value = false
    await fetchCell()
  } catch (err: any) {
    toastStore.error(err?.data?.detail || t('common.error'))
  } finally {
    saving.value = false
  }
}

// ── Relays ───────────────────────────────────────────────────────────────────

const fetchRelays = async () => {
  try {
    const headers = await authHeaders()
    relays.value = await $fetch<any[]>('/api/v1/energy/my/relays/', {
      credentials: 'include',
      headers,
    })
  } catch {
    relays.value = []
  }
}

const addRelay = async () => {
  relayAdding.value = true
  try {
    const headers = await authHeaders()
    await $fetch('/api/v1/energy/my/relays/', {
      method: 'POST',
      credentials: 'include',
      headers,
      body: relayForm.value,
    })
    toastStore.success(t('energy.relay.added'))
    showRelayForm.value = false
    relayForm.value = { name: '', relay_type: 'SHELLY_GEN2', url: '', channel: 0 }
    await fetchRelays()
  } catch (err: any) {
    toastStore.error(err?.data?.detail || t('common.error'))
  } finally {
    relayAdding.value = false
  }
}

const testRelay = async (relay: any) => {
  relay._testing = true
  try {
    const headers = await authHeaders()
    const result = await $fetch<any>(`/api/v1/energy/relays/${relay.id}/test/`, {
      method: 'POST',
      credentials: 'include',
      headers,
    })
    if (result.ok) {
      toastStore.success(`${relay.name}: ${result.info}`)
      relay.last_error = ''
    } else {
      toastStore.error(`${relay.name}: ${result.error}`)
      relay.last_error = result.error
    }
  } catch (err: any) {
    toastStore.error(err?.data?.detail || t('common.error'))
  } finally {
    relay._testing = false
  }
}

const deleteRelay = async (relay: any) => {
  try {
    const headers = await authHeaders()
    await $fetch(`/api/v1/energy/relays/${relay.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers,
    })
    relays.value = relays.value.filter(r => r.id !== relay.id)
  } catch (err: any) {
    toastStore.error(err?.data?.detail || t('common.error'))
  }
}

onMounted(async () => {
  await Promise.all([fetchCell(), fetchMembers(), fetchLive()])
  loading.value = false
  // Fetch relays after we know membership
  if (authStore.isAuthenticated) await fetchRelays()
})
</script>
