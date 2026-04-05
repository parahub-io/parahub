<template>
  <div class="w-full space-y-6">
    <!-- Section 1: Earnings -->
    <div class="rounded-lg border border-yellow-300 p-4 space-y-4" style="background-color: #FFE216;">
      <div>
        <h3 class="text-sm font-semibold text-neutral-900">{{ $t('ads.sections.earnings.title') }}</h3>
        <p class="text-xs text-neutral-700 mt-0.5">{{ $t('ads.sections.earnings.description') }}</p>
      </div>

      <!-- Stats row -->
      <div class="grid grid-cols-3 gap-3">
        <div class="bg-white/60 rounded-lg p-3 text-center">
          <p class="text-xl font-bold text-neutral-900">{{ earnings.total_views }}</p>
          <p class="text-xs text-neutral-600">{{ $t('ads.profile.total_views') }}</p>
        </div>
        <div class="bg-white/60 rounded-lg p-3 text-center">
          <p class="text-xl font-bold text-neutral-900">{{ earnings.total_earned_sats }}</p>
          <p class="text-xs text-neutral-600">{{ $t('ads.profile.total_earned') }}</p>
        </div>
        <div class="bg-white/60 rounded-lg p-3 text-center">
          <p class="text-xl font-bold text-neutral-900">{{ earnings.avg_per_view_sats.toFixed(1) }}</p>
          <p class="text-xs text-neutral-600">{{ $t('ads.profile.avg_per_view') }}</p>
        </div>
      </div>

      <!-- Min reward slider -->
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-sm text-neutral-900">
            {{ $t('ads.profile.min_reward') }}
          </label>
          <span class="text-sm font-semibold text-neutral-900">{{ targeting.min_reward_sats }} sats</span>
        </div>
        <input
          v-model.number="targeting.min_reward_sats"
          @change="saveTargeting"
          type="range"
          min="1"
          max="500"
          step="1"
          class="w-full accent-neutral-900"
          :aria-label="$t('ads.profile.min_reward')"
        />
        <div class="flex gap-2 flex-wrap">
          <button
            v-for="preset in [5, 10, 50, 100]"
            :key="preset"
            type="button"
            @click="targeting.min_reward_sats = preset; saveTargeting()"
            class="px-2.5 py-1 text-xs rounded-full border border-neutral-400 bg-white/50 hover:bg-white/80 text-neutral-800 transition-colors"
            :class="targeting.min_reward_sats === preset ? 'border-neutral-700 font-semibold' : ''"
          >
            {{ preset }} sats
          </button>
        </div>
        <p class="text-xs text-neutral-600">{{ $t('ads.profile.min_reward_help') }}</p>
      </div>
    </div>

    <!-- Section 2: About You -->
    <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 space-y-4">
      <div>
        <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.settings.about_you') }}</h3>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('ads.settings.about_you_desc') }}</p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Gender -->
        <div>
          <label class="block text-xs font-medium text-neutral-500 dark:text-neutral-400 mb-1">
            {{ $t('ads.profile.gender') }}
          </label>
          <select
            v-model="targeting.gender"
            @change="saveTargeting"
            class="w-full px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100"
          >
            <option value="any">{{ $t('ads.profile.gender_any') }}</option>
            <option value="male">{{ $t('ads.profile.gender_male') }}</option>
            <option value="female">{{ $t('ads.profile.gender_female') }}</option>
          </select>
        </div>

        <!-- Birth date -->
        <div>
          <label class="block text-xs font-medium text-neutral-500 dark:text-neutral-400 mb-1">
            {{ $t('ads.profile.birth_date') }}
          </label>
          <input
            v-model="targeting.birth_date"
            @change="saveTargeting"
            type="date"
            class="w-full px-3 py-1.5 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100"
          />
        </div>
      </div>

      <!-- Children ages -->
      <div>
        <label class="block text-xs font-medium text-neutral-500 dark:text-neutral-400 mb-2">
          {{ $t('ads.sections.children.title') }}
        </label>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="age in allChildrenAges"
            :key="age.id"
            type="button"
            @click="toggleChildrenAge(age.id, age.name)"
            class="px-3 py-1.5 rounded-full border text-sm transition-colors"
            :class="selectedChildrenAges.includes(age.id)
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400'"
          >
            {{ getChildrenAgeLabel(age.name) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Section 3: Interests (chip cloud) -->
    <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 space-y-4">
      <div>
        <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.profile.interests') }}</h3>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('ads.profile.interests_help') }}</p>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          v-for="interest in allInterests"
          :key="interest.id"
          type="button"
          @click="toggleInterest(interest.id)"
          class="px-3 py-1.5 rounded-full border text-sm transition-colors"
          :class="selectedInterests.includes(interest.id)
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400'"
        >
          {{ $t(`ads.interests.${interest.slug}`, interest.name) }}
        </button>
      </div>
    </div>

    <!-- Section 4: Skills -->
    <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 space-y-4">
      <div>
        <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.sections.skills.title') }}</h3>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('ads.sections.skills.description') }}</p>
      </div>

      <div class="space-y-0.5 max-h-[26rem] overflow-y-auto pr-1">
        <div
          v-for="skill in allSkills"
          :key="skill.id"
          class="flex items-center justify-between py-1.5 px-2 rounded hover:bg-neutral-50 dark:hover:bg-neutral-700"
        >
          <span class="text-sm text-neutral-800 dark:text-neutral-200 min-w-0 mr-3 truncate">
            {{ $t(`ads.skills.${skill.slug}`, skill.name) }}
          </span>
          <div class="flex gap-0.5 flex-shrink-0"
            @mouseleave="skillHover = null"
          >
            <button
              v-for="lvl in 5"
              :key="lvl"
              @click="setSkillRating(skill.id, lvl)"
              @mouseenter="skillHover = { id: skill.id, level: lvl }"
              class="p-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
              :title="$t(`ads.skill_levels.l${lvl}`)"
              :aria-label="$t(`ads.skill_levels.l${lvl}`)"
            >
              <Star
                class="w-4 h-4 transition-colors"
                :class="isStarActive(skill.id, lvl)
                  ? 'text-amber-400 fill-amber-400'
                  : 'text-neutral-300 dark:text-neutral-600'"
              />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 5: Locations (unified map) -->
    <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 space-y-4">
      <div>
        <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.profile.locations_title') }}</h3>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('ads.settings.locations_desc') }}</p>
      </div>

      <!-- Unified map UI -->
      <div v-if="locations.length > 0" class="space-y-3">
        <!-- Slot selector tabs -->
        <div class="flex gap-2">
          <button
            v-for="(loc, idx) in locations"
            :key="idx"
            type="button"
            @click="activeSlot = idx"
            class="px-3 py-1.5 text-sm rounded-full border transition-colors"
            :class="activeSlot === idx
              ? 'border-primary bg-primary/10 text-primary font-medium'
              : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400'"
          >
            <span :style="{ color: SLOT_COLORS[idx] }">●</span>
            {{ $t(`ads.profile.location_${loc.label.toLowerCase()}`) }}
          </button>
        </div>

        <!-- Unified map -->
        <div
          ref="unifiedMapEl"
          class="w-full h-[250px] rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600"
        />
        <p class="text-xs text-neutral-400">{{ $t('ads.profile.click_map_to_set') }}</p>

        <!-- Location entries -->
        <div class="space-y-2">
          <div
            v-for="(loc, idx) in locations"
            :key="idx"
            class="flex items-center gap-2 p-2 rounded-lg border transition-colors"
            :class="activeSlot === idx
              ? 'border-primary/30 bg-primary/5'
              : 'border-neutral-200 dark:border-neutral-700'"
          >
            <span class="text-sm" :style="{ color: SLOT_COLORS[idx] }">●</span>
            <select
              v-model="loc.label"
              @change="onLabelChange(idx); saveLocations()"
              class="px-2 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100"
            >
              <option value="Home">{{ $t('ads.profile.location_home') }}</option>
              <option value="Work">{{ $t('ads.profile.location_work') }}</option>
              <option value="Other">{{ $t('ads.profile.location_other') }}</option>
            </select>
            <span v-if="loc.latitude !== null" class="text-xs text-neutral-500 font-mono flex-1 truncate">
              {{ loc.latitude.toFixed(5) }}, {{ loc.longitude.toFixed(5) }}
            </span>
            <span v-else class="text-xs text-neutral-400 flex-1">—</span>
            <button @click="removeLocation(idx)" class="text-neutral-400 hover:text-red-500 flex-shrink-0">
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <!-- Add location button -->
      <button
        v-if="locations.length < 3"
        type="button"
        @click="addLocation"
        class="w-full py-2 border border-dashed border-neutral-300 dark:border-neutral-600 rounded-lg text-sm text-neutral-500 dark:text-neutral-400 hover:border-secondary hover:text-secondary transition-colors"
      >
        + {{ $t('ads.profile.add_location') }}
      </button>
      <p v-if="locations.length >= 3" class="text-xs text-neutral-400 text-center">
        {{ $t('ads.profile.max_locations') }}
      </p>
    </div>

    <!-- Save confirmation toast -->
    <Transition
      enter-active-class="transition ease-out duration-300"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
      <div
        v-if="saved"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-lg shadow-lg text-sm font-medium bg-green-600 text-white"
      >
        {{ $t('ads.sections.targeting.saved') }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { X, Star } from 'lucide-vue-next'
import { useMapStore } from '~/stores/map'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const colorMode = useColorMode()
const mapStore = useMapStore()
const { loadAdsProfile } = useAdsState()

const allInterests = ref<any[]>([])
const allSkills = ref<any[]>([])
const allChildrenAges = ref<any[]>([])


const skillHover = ref<{ id: string; level: number } | null>(null)

function isStarActive(skillId: string, lvl: number): boolean {
  if (skillHover.value?.id === skillId) return lvl <= skillHover.value.level
  return lvl <= (skillRatings.value[skillId] || 0)
}

const targeting = ref({ gender: 'any', birth_date: null as string | null, min_reward_sats: 10 })
const selectedInterests = ref<string[]>([])
const skillRatings = ref<Record<string, number>>({})
const selectedChildrenAges = ref<string[]>([])
const earnings = ref({ total_views: 0, total_earned_sats: 0, avg_per_view_sats: 0 })
const saved = ref(false)

// Unified location map
const SLOT_COLORS = ['#ef4444', '#3b82f6', '#22c55e']

interface LocationEntry { label: string; latitude: number | null; longitude: number | null }
const locations = ref<LocationEntry[]>([])
const activeSlot = ref(0)
const unifiedMapEl = ref<HTMLElement | null>(null)
let unifiedMap: any = null
const unifiedMarkers: Record<number, any> = {}

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initUnifiedMap() {
  if (unifiedMap || !unifiedMapEl.value) return
  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  // Center on first location with coords, or last /map position
  const { mapCenter, mapZoom } = useMapState()
  const firstLoc = locations.value.find(l => l.latitude !== null)
  const center = firstLoc
    ? [firstLoc.longitude!, firstLoc.latitude!]
    : mapCenter.value
  const zoom = firstLoc ? 12 : mapZoom.value

  unifiedMap = new maplibregl.Map({
    container: unifiedMapEl.value,
    style: getStyleUrl(),
    center,
    zoom,
    attributionControl: false,
    fadeDuration: 0,
  })
  unifiedMap.once('load', () => {
    unifiedMap.resize()
    // Add markers for all existing locations
    locations.value.forEach((loc, idx) => {
      if (loc.latitude !== null && loc.longitude !== null) {
        addMapMarker(maplibregl, idx, loc.longitude!, loc.latitude!)
      }
    })
  })

  unifiedMap.on('click', (e: any) => {
    const { lng, lat } = e.lngLat
    const idx = activeSlot.value
    if (idx >= locations.value.length) return
    locations.value[idx].latitude = Math.round(lat * 1e6) / 1e6
    locations.value[idx].longitude = Math.round(lng * 1e6) / 1e6
    updateMapMarker(maplibregl, idx, lng, lat)
    saveLocations()
  })

  unifiedMap.on('style.load', () => {
    // Re-add all markers after style change
    locations.value.forEach((loc, idx) => {
      if (loc.latitude !== null && loc.longitude !== null) {
        addMapMarker(maplibregl, idx, loc.longitude!, loc.latitude!)
      }
    })
  })
}

async function getMapLibre() {
  const mod = await import('maplibre-gl')
  return mod.default || mod
}

function addMapMarker(maplibregl: any, idx: number, lng: number, lat: number) {
  if (unifiedMarkers[idx]) {
    unifiedMarkers[idx].setLngLat([lng, lat])
    return
  }
  unifiedMarkers[idx] = new maplibregl.Marker({ color: SLOT_COLORS[idx] })
    .setLngLat([lng, lat])
    .addTo(unifiedMap)
}

function updateMapMarker(maplibregl: any, idx: number, lng: number, lat: number) {
  if (unifiedMarkers[idx]) {
    unifiedMarkers[idx].setLngLat([lng, lat])
  } else {
    unifiedMarkers[idx] = new maplibregl.Marker({ color: SLOT_COLORS[idx] })
      .setLngLat([lng, lat])
      .addTo(unifiedMap)
  }
}

function removeMapMarker(idx: number) {
  if (unifiedMarkers[idx]) {
    unifiedMarkers[idx].remove()
    delete unifiedMarkers[idx]
  }
}

function destroyUnifiedMap() {
  if (unifiedMap) {
    unifiedMap.remove()
    unifiedMap = null
  }
}

function addLocation() {
  if (locations.value.length >= 3) return
  const labels = ['Home', 'Work', 'Other']
  const usedLabels = locations.value.map(l => l.label)
  const label = labels.find(l => !usedLabels.includes(l)) || 'Other'
  locations.value.push({ label, latitude: null, longitude: null })
  activeSlot.value = locations.value.length - 1
  nextTick(async () => {
    if (!unifiedMap) {
      await initUnifiedMap()
    }
  })
}

function removeLocation(idx: number) {
  removeMapMarker(idx)
  // Remap markers for indices that shifted
  const newMarkers: Record<number, any> = {}
  Object.entries(unifiedMarkers).forEach(([k, m]) => {
    const i = Number(k)
    if (i < idx) newMarkers[i] = m
    else if (i > idx) newMarkers[i - 1] = m
    // i === idx is already removed above
  })
  Object.keys(unifiedMarkers).forEach(k => delete (unifiedMarkers as any)[k])
  Object.assign(unifiedMarkers, newMarkers)

  locations.value.splice(idx, 1)
  if (activeSlot.value >= locations.value.length) {
    activeSlot.value = Math.max(0, locations.value.length - 1)
  }
  if (locations.value.length === 0) {
    destroyUnifiedMap()
  }
  saveLocations()
}

function onLabelChange(_idx: number) {
  // No visual change needed; save is called after
}

async function saveLocations() {
  const valid = locations.value.filter(l => l.latitude !== null && l.longitude !== null)
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/ads/profile/', {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ locations: valid.map(l => ({ label: l.label, latitude: l.latitude, longitude: l.longitude })) })
    })
    showSaved()
  } catch (error) {
    console.error('Failed to save locations:', error)
  }
}

watch(() => colorMode.value, () => {
  if (unifiedMap) unifiedMap.setStyle(getStyleUrl())
})

watch(activeSlot, (idx) => {
  if (!unifiedMap) return
  const loc = locations.value[idx]
  if (loc?.latitude !== null && loc?.longitude !== null) {
    unifiedMap.flyTo({ center: [loc.longitude!, loc.latitude!], zoom: 13, essential: true, speed: 4.5 })
  }
})

onUnmounted(() => destroyUnifiedMap())

function showSaved() {
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}

const childrenAgeKeyMap: Record<string, string> = {
  'Infant (0-2 years)': 'infant',
  'Toddler (2-4 years)': 'toddler',
  'Preschool (4-6 years)': 'preschool',
  'Elementary (6-12 years)': 'elementary',
  'Teen (12-18 years)': 'teen',
  '18+': 'eighteen_plus',
  'No children': 'no_children',
}

const NO_CHILDREN_NAME = 'No children'

function getChildrenAgeLabel(name: string): string {
  const key = childrenAgeKeyMap[name]
  return key ? t(`ads.children_ages.${key}`, name) : name
}

async function saveTargeting() {
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/ads/profile/', {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gender: targeting.value.gender,
        birth_date: targeting.value.birth_date,
        min_reward_sats: targeting.value.min_reward_sats,
        interest_ids: selectedInterests.value
      })
    })
    showSaved()
  } catch (error) {
    console.error('Failed to save targeting:', error)
  }
}

function toggleInterest(id: string) {
  const idx = selectedInterests.value.indexOf(id)
  if (idx >= 0) {
    selectedInterests.value.splice(idx, 1)
  } else {
    selectedInterests.value.push(id)
  }
  saveTargeting()
}

async function setSkillRating(skillId: string, rating: number) {
  if (skillRatings.value[skillId] === rating) {
    delete skillRatings.value[skillId]
  } else {
    skillRatings.value[skillId] = rating
  }
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/ads/profile/', {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_ratings: skillRatings.value })
    })
    showSaved()
  } catch (error) {
    console.error('Failed to save skills:', error)
  }
}

function getNoChildrenId(): string | null {
  const entry = allChildrenAges.value.find((a: any) => a.name === NO_CHILDREN_NAME)
  return entry?.id || null
}

function toggleChildrenAge(ageId: string, ageName: string) {
  const noChildrenId = getNoChildrenId()
  const isSelected = selectedChildrenAges.value.includes(ageId)

  if (isSelected) {
    selectedChildrenAges.value = selectedChildrenAges.value.filter(id => id !== ageId)
  } else {
    if (ageName === NO_CHILDREN_NAME) {
      selectedChildrenAges.value = [ageId]
    } else {
      selectedChildrenAges.value = [
        ...selectedChildrenAges.value.filter(id => id !== noChildrenId),
        ageId
      ]
    }
  }
  saveChildrenAges()
}

async function saveChildrenAges() {
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/ads/profile/', {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ children_age_ids: selectedChildrenAges.value })
    })
    showSaved()
  } catch (error) {
    console.error('Failed to save children ages:', error)
  }
}

function applyProfile(profile: any) {
  targeting.value = {
    gender: profile.gender || 'any',
    birth_date: profile.birth_date || null,
    min_reward_sats: profile.min_reward_sats ?? 10,
  }
  selectedInterests.value = profile.interests || []
  selectedChildrenAges.value = profile.children_ages || []
  const ratings: Record<string, number> = {}
  if (profile.skills && Array.isArray(profile.skills)) {
    profile.skills.forEach((s: any) => { ratings[s.skill_id] = s.level })
  }
  skillRatings.value = ratings

  if (profile.locations && Array.isArray(profile.locations)) {
    locations.value = profile.locations.map((l: any) => ({
      label: l.label || 'Home',
      latitude: l.latitude,
      longitude: l.longitude,
    }))
    if (locations.value.length > 0) {
      nextTick(() => initUnifiedMap())
    }
  }
}

onMounted(async () => {
  const [profile, refData, earningsData] = await Promise.all([
    loadAdsProfile(),
    Promise.all([
      $fetch<any[]>('/api/v1/ads/interests/'),
      $fetch<any[]>('/api/v1/ads/skills/'),
      $fetch<any[]>('/api/v1/ads/children-ages/')
    ]),
    (async () => {
      try {
        await authStore.ensureToken()
        return await $fetch<any>('/api/v1/ads/earnings/', {
          credentials: 'include',
          headers: { 'Authorization': `Bearer ${authStore.token}` }
        })
      } catch { return null }
    })()
  ])

  if (profile) applyProfile(profile)
  allInterests.value = refData[0]
  allSkills.value = refData[1]
  // Put "No children" first
  const ages = refData[2] as any[]
  const noChildrenIdx = ages.findIndex((a: any) => a.name === NO_CHILDREN_NAME)
  if (noChildrenIdx > 0) {
    const [noChildren] = ages.splice(noChildrenIdx, 1)
    ages.unshift(noChildren)
  }
  allChildrenAges.value = ages
  if (earningsData) earnings.value = earningsData
})

definePageMeta({
  middleware: 'auth',
})
</script>
