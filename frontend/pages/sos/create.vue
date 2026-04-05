<template>
  <div>
    <div class="w-full px-4 sm:px-6 lg:px-8 py-6">
      <div class="max-w-2xl mx-auto w-full">
        <!-- Header -->
        <div class="flex items-center gap-3 mb-6">
          <NuxtLink :to="localePath('/sos')" class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
            <ArrowLeft :size="20" />
          </NuxtLink>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ $t('parasos.create_group.title') }}
          </h1>
        </div>

        <!-- Disclaimer -->
        <UiAlert variant="info" class="mb-6">
          <template #title>{{ $t('parasos.disclaimer.title') }}</template>
          <ul class="text-sm space-y-1 mt-1">
            <li>{{ $t('parasos.disclaimer.not_police') }}</li>
            <li>{{ $t('parasos.disclaimer.no_obligation') }}</li>
            <li>{{ $t('parasos.disclaimer.no_intervention') }}</li>
          </ul>
        </UiAlert>

        <form @submit.prevent="createGroup" class="space-y-6">
          <!-- Name -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('parasos.create_group.name_label') }}
            </label>
            <input
              v-model="form.name"
              type="text"
              required
              :placeholder="$t('parasos.create_group.name_placeholder')"
              class="w-full px-4 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm"
            />
          </div>

          <!-- Description -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('parasos.create_group.description_label') }}
            </label>
            <textarea
              v-model="form.description"
              rows="3"
              :placeholder="$t('parasos.create_group.description_placeholder')"
              class="w-full px-4 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent text-sm resize-none"
            />
          </div>

          <!-- Visibility -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('parasos.create_group.visibility_label') }}
            </label>
            <div class="flex gap-3">
              <button
                v-for="opt in visibilityOptions"
                :key="opt.value"
                type="button"
                @click="form.visibility = opt.value"
                class="flex-1 p-3 rounded-lg border text-sm text-center transition-colors"
                :class="form.visibility === opt.value
                  ? 'border-secondary bg-secondary text-white'
                  : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'"
              >
                <div class="font-medium">{{ opt.label }}</div>
                <div class="text-xs mt-1 opacity-70">{{ opt.desc }}</div>
              </button>
            </div>
          </div>

          <!-- Group type (local vs friends) -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('parasos.create_group.group_type_label') }}
            </label>
            <div class="flex gap-3">
              <button
                v-for="opt in groupTypeOptions"
                :key="opt.value"
                type="button"
                @click="form.hasLocation = opt.value"
                class="flex-1 p-3 rounded-lg border text-sm text-center transition-colors"
                :class="form.hasLocation === opt.value
                  ? 'border-secondary bg-secondary text-white'
                  : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'"
              >
                <div class="font-medium">{{ opt.label }}</div>
                <div class="text-xs mt-1 opacity-70">{{ opt.desc }}</div>
              </button>
            </div>
          </div>

          <!-- Map for location (only for location-based groups) -->
          <template v-if="form.hasLocation">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('parasos.create_group.location_label') }}
              </label>

              <!-- Property selector -->
              <div v-if="properties.length" class="mb-2">
                <select
                  @change="onPropertySelect($event)"
                  class="w-full px-3 py-2 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm"
                >
                  <option value="">{{ $t('parasos.create_group.select_property') }}</option>
                  <option v-for="p in properties" :key="p.id" :value="p.id">
                    {{ p.name }} — {{ p.address || $t(`parasos.create_group.property_type_${p.property_type}`, p.property_type) }}
                  </option>
                </select>
              </div>

              <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
                {{ $t('parasos.create_group.location_hint') }}
              </p>
              <div class="rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700">
                <ClientOnly>
                  <StaticMapPreview
                    :latitude="form.center.latitude"
                    :longitude="form.center.longitude"
                    :height="250"
                    :interactive="true"
                    @update:center="onMapClick"
                  />
                  <template #fallback>
                    <div class="h-[250px] bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
                      <span class="text-sm text-neutral-400">{{ $t('parasos.loading') }}</span>
                    </div>
                  </template>
                </ClientOnly>
              </div>
            </div>

            <!-- Radius -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                {{ $t('parasos.create_group.radius_label') }}: {{ form.radius_m }}m
              </label>
              <input
                v-model.number="form.radius_m"
                type="range"
                min="100"
                max="5000"
                step="100"
                class="w-full accent-primary"
              />
              <div class="flex justify-between text-xs text-neutral-400">
                <span>100m</span>
                <span>5000m</span>
              </div>
            </div>
          </template>

          <!-- Quiet hours -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('parasos.create_group.quiet_hours_label') }}
            </label>
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-2">
                <span class="text-sm text-neutral-500">{{ $t('parasos.create_group.quiet_start') }}</span>
                <select
                  v-model.number="form.quiet_hours_start"
                  class="px-3 py-2 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm"
                >
                  <option :value="null">—</option>
                  <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
                </select>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-sm text-neutral-500">{{ $t('parasos.create_group.quiet_end') }}</span>
                <select
                  v-model.number="form.quiet_hours_end"
                  class="px-3 py-2 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm"
                >
                  <option :value="null">—</option>
                  <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Submit -->
          <UiButton
            type="submit"
            variant="primary"
            :loading="submitting"
            :disabled="!form.name || (form.hasLocation && !form.center.latitude)"
            class="w-full"
          >
            {{ $t('parasos.create_group.submit') }}
          </UiButton>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const router = useRouter()
const authStore = useAuthStore()
const toastStore = useToastStore()
const propertyStore = usePropertyStore()
const { mapCenter } = useMapState()

useSeoMeta({ title: `${t('parasos.create_group.title')} — Parahub` })

const submitting = ref(false)
const properties = ref<Array<{ id: string; name: string; property_type: string; address: string; latitude: number; longitude: number }>>([])

const visibilityOptions = computed(() => [
  { value: 'PUBLIC', label: t('parasos.create_group.visibility_public'), desc: t('parasos.create_group.visibility_public_desc') },
  { value: 'PRIVATE', label: t('parasos.create_group.visibility_private'), desc: t('parasos.create_group.visibility_private_desc') },
])

const groupTypeOptions = computed(() => [
  { value: true, label: t('parasos.create_group.group_type_local'), desc: t('parasos.create_group.group_type_local_desc') },
  { value: false, label: t('parasos.create_group.group_type_friends'), desc: t('parasos.create_group.group_type_friends_desc') },
])

// Initial center from saved map state
const form = reactive({
  name: '',
  description: '',
  visibility: 'PUBLIC' as 'PUBLIC' | 'PRIVATE',
  hasLocation: true,
  center: { latitude: mapCenter.value[1], longitude: mapCenter.value[0] },
  radius_m: 1000,
  quiet_hours_start: null as number | null,
  quiet_hours_end: null as number | null,
})

function onMapClick(lat: number, lon: number) {
  form.center.latitude = lat
  form.center.longitude = lon
}

function onPropertySelect(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  if (!id) return
  const prop = properties.value.find(p => p.id === id)
  if (prop) {
    form.center.latitude = prop.latitude
    form.center.longitude = prop.longitude
  }
}

async function createGroup() {
  if (!form.name) return
  if (form.hasLocation && !form.center.latitude) return
  submitting.value = true
  try {
    await authStore.ensureToken()
    const body: Record<string, any> = {
      name: form.name,
      description: form.description,
      visibility: form.visibility,
      quiet_hours_start: form.quiet_hours_start,
      quiet_hours_end: form.quiet_hours_end,
    }
    if (form.hasLocation) {
      body.center = form.center
      body.radius_m = form.radius_m
    }
    const data = await $fetch<any>('/api/v1/parasos/groups/', {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body,
    })
    router.push(localePath(`/sos/${data.id}`))
  } catch (e: any) {
    console.error('Failed to create group:', e)
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.create_group'))
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  // Try geolocation for more precise initial position
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        form.center.latitude = pos.coords.latitude
        form.center.longitude = pos.coords.longitude
      },
      () => { /* keep mapState fallback */ },
      { enableHighAccuracy: true },
    )
  }

  // Load user properties for quick selection
  try {
    await propertyStore.fetchProperties()
    properties.value = propertyStore.properties
    // If user has a property and no geolocation yet, center on first property
    if (properties.value.length && form.center.latitude === mapCenter.value[1]) {
      form.center.latitude = properties.value[0].latitude
      form.center.longitude = properties.value[0].longitude
    }
  } catch { /* ignore — properties are optional */ }
})
</script>
