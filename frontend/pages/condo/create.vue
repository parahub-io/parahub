<template>
  <div class="max-w-2xl mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
      {{ $t('condo.create_title') }}
    </h1>

    <!-- Step indicator -->
    <div class="flex items-center gap-2 mb-8">
      <button
        v-for="(label, idx) in steps"
        :key="idx"
        @click="idx < step ? step = idx : null"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          idx === step ? 'bg-primary text-neutral-900' : idx < step ? 'bg-primary/20 text-primary cursor-pointer' : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-400'
        ]"
      >
        {{ idx + 1 }}. {{ label }}
      </button>
    </div>

    <!-- Step 1: Address -->
    <div v-if="step === 0" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('condo.step_address') }}
        </label>
        <input
          v-model="addressQuery"
          type="text"
          :placeholder="$t('condo.address_placeholder')"
          class="input w-full"
          @input="searchAddress"
        />
      </div>

      <!-- Search results -->
      <div v-if="addressResults.length" class="border border-neutral-200 dark:border-neutral-700 rounded-lg divide-y divide-neutral-100 dark:divide-neutral-800">
        <button
          v-for="r in addressResults"
          :key="r.id || r.label"
          @click="selectAddress(r)"
          class="w-full text-left px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800 text-sm"
        >
          <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ r.label || r.name }}</div>
          <div v-if="r.locality" class="text-xs text-neutral-500">{{ r.locality }}, {{ r.country }}</div>
        </button>
      </div>

      <!-- Selected address -->
      <UiAlert v-if="selectedAddress" variant="success" :title="selectedAddress.label || selectedAddress.name">
        <p v-if="selectedAddress.locality" class="text-xs">
          {{ selectedAddress.locality }}, {{ selectedAddress.country }}
        </p>
      </UiAlert>

      <button
        @click="step = 1"
        :disabled="!selectedAddress"
        class="btn-primary"
      >
        {{ $t('condo.next') }}
      </button>
    </div>

    <!-- Step 2: Info -->
    <div v-if="step === 1" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.name') }}</label>
        <input v-model="form.name" type="text" :placeholder="$t('condo.name_placeholder')" class="input w-full" />
      </div>
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.nif') }}</label>
        <input v-model="form.legal_entity_id" type="text" :placeholder="$t('condo.nif_placeholder')" class="input w-full" />
      </div>
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.description') }}</label>
        <textarea v-model="form.description" :placeholder="$t('condo.description_placeholder')" rows="3" class="input w-full" />
      </div>
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.regulamento') }}</label>
        <textarea v-model="form.terms_content" :placeholder="$t('condo.regulamento_placeholder')" rows="4" class="input w-full font-mono text-xs" />
      </div>

      <div class="flex gap-3">
        <button @click="step = 0" class="btn-outline">{{ $t('condo.back') }}</button>
        <button @click="step = 2" :disabled="!form.name" class="btn-primary">{{ $t('condo.next') }}</button>
      </div>
    </div>

    <!-- Step 3: Fractions -->
    <div v-if="step === 2" class="space-y-4">
      <div>
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('condo.fractions_title') }}</h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('condo.fractions_subtitle') }}</p>
      </div>

      <!-- Fractions table -->
      <div class="space-y-3">
        <div
          v-for="(f, idx) in fractions"
          :key="idx"
          class="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3"
        >
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <label class="text-xs text-neutral-500">{{ $t('condo.identifier') }}</label>
              <input v-model="f.identifier" type="text" :placeholder="$t('condo.identifier_placeholder')" class="input w-full text-sm" />
            </div>
            <div>
              <label class="text-xs text-neutral-500">{{ $t('condo.floor') }}</label>
              <input v-model="f.floor" type="text" :placeholder="$t('condo.floor_placeholder')" class="input w-full text-sm" />
            </div>
            <div>
              <label class="text-xs text-neutral-500">{{ $t('condo.type') }}</label>
              <select v-model="f.fraction_type" class="input w-full text-sm">
                <option value="APARTMENT">{{ $t('condo.type_apartment') }}</option>
                <option value="GARAGE">{{ $t('condo.type_garage') }}</option>
                <option value="STORAGE">{{ $t('condo.type_storage') }}</option>
                <option value="COMMERCIAL">{{ $t('condo.type_commercial') }}</option>
                <option value="OTHER">{{ $t('condo.type_other') }}</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-neutral-500">{{ $t('condo.permilagem') }} ‰</label>
              <input v-model.number="f.permilagem" type="number" step="0.001" min="0" max="1000" class="input w-full text-sm" />
            </div>
          </div>
          <div class="flex items-center justify-between mt-2">
            <input v-model="f.description" type="text" :placeholder="$t('condo.description_fraction_placeholder')" class="input flex-1 text-xs" />
            <button @click="fractions.splice(idx, 1)" class="ml-2 text-red-500 hover:text-red-700 text-xs">
              {{ $t('condo.remove_fraction') }}
            </button>
          </div>
        </div>
      </div>

      <button @click="addFraction" class="btn-outline btn-sm">
        + {{ $t('condo.add_fraction') }}
      </button>

      <!-- Permilagem total bar -->
      <div class="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ $t('condo.total_permilagem') }}</span>
          <span
            :class="[
              'text-lg font-bold',
              permilagemTotal === 1000 ? 'text-green-600' : permilagemTotal > 1000 ? 'text-red-600' : 'text-yellow-600'
            ]"
          >
            {{ permilagemTotal.toFixed(3) }} ‰
          </span>
        </div>
        <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2">
          <div
            :style="{ width: Math.min(permilagemTotal / 10, 100) + '%' }"
            :class="[
              'h-2 rounded-full transition-all',
              permilagemTotal === 1000 ? 'bg-green-500' : permilagemTotal > 1000 ? 'bg-red-500' : 'bg-yellow-500'
            ]"
          />
        </div>
      </div>

      <!-- Error -->
      <p v-if="submitError" class="text-sm text-red-600">{{ submitError }}</p>

      <div class="flex gap-3">
        <button @click="step = 1" class="btn-outline">{{ $t('condo.back') }}</button>
        <button
          @click="submit"
          :disabled="submitting || permilagemTotal !== 1000 || fractions.length === 0"
          class="btn-primary"
        >
          <Loader2 v-if="submitting" class="w-4 h-4 inline animate-spin mr-1" />
          {{ submitting ? $t('condo.creating') : $t('condo.create') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

// Track onboarding: user has visited condo section
if (import.meta.client) {
  localStorage.setItem('onboarding:condo', '1')
}

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

useSeoMeta({
  title: () => t('condo.meta_create_title'),
  ogTitle: () => t('condo.meta_create_title'),
  description: () => t('condo.meta_create_desc'),
  ogDescription: () => t('condo.meta_create_desc'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary',
})

const baseUrl = useRuntimeConfig().public.siteUrl || 'https://parahub.io'
useHead({
  script: [{
    type: 'application/ld+json',
    innerHTML: JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      'name': 'Parahub — Gestão de Condomínio',
      'url': `${baseUrl}/condo/create`,
      'applicationCategory': 'BusinessApplication',
      'operatingSystem': 'Web',
      'offers': { '@type': 'Offer', 'price': '0', 'priceCurrency': 'EUR' },
      'description': 'Plataforma gratuita e open-source de gestão de condomínio. Assembleias digitais, votação ponderada, quotas — Lei 8/2022.',
    }),
  }],
})

const steps = computed(() => [
  t('condo.step_address'),
  t('condo.step_info'),
  t('condo.step_fractions'),
])

const step = ref(0)
const submitting = ref(false)
const submitError = ref('')

// Step 1: Address
const addressQuery = ref('')
const addressResults = ref<any[]>([])
const selectedAddress = ref<any>(null)
const buildingId = ref('')

let searchTimeout: any = null
const searchAddress = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(async () => {
    if (addressQuery.value.length < 3) {
      addressResults.value = []
      return
    }
    try {
      const data = await $fetch<any>(`/api/v1/geo/geocode/search?q=${encodeURIComponent(addressQuery.value)}`)
      addressResults.value = data.features?.map((f: any) => ({
        label: f.properties?.label || f.properties?.name,
        name: f.properties?.name,
        locality: f.properties?.locality || f.properties?.region,
        country: f.properties?.country,
        lat: f.geometry?.coordinates?.[1],
        lon: f.geometry?.coordinates?.[0],
        street: f.properties?.street,
        house_number: f.properties?.housenumber,
        postal_code: f.properties?.postalcode,
        country_a: f.properties?.country_a,
      })) || []
    } catch {
      addressResults.value = []
    }
  }, 300)
}

const selectAddress = async (r: any) => {
  selectedAddress.value = r
  addressResults.value = []
  addressQuery.value = r.label || r.name

  // Create or find building
  try {
    await authStore.ensureToken()
    const building = await $fetch<any>('/api/v1/geo/buildings/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: {
        location: { latitude: r.lat, longitude: r.lon },
        country: (r.country_a || 'PT').substring(0, 2),
        city: r.locality || '',
        street: r.street || '',
        house_number: r.house_number || '',
        postal_code: r.postal_code || '',
        full_address: r.label || r.name,
      }
    })
    buildingId.value = building.id
    // Auto-fill name
    if (!form.name) {
      form.name = `${t('condo.title')} ${r.street || ''} ${r.house_number || ''}`.trim()
    }
  } catch (err: any) {
    console.error('Failed to create building:', err)
  }
}

// Step 2: Info
const form = reactive({
  name: '',
  legal_entity_id: '',
  description: '',
  terms_content: '',
})

// Step 3: Fractions
const fractions = reactive<Array<{
  identifier: string
  description: string
  floor: string
  fraction_type: string
  permilagem: number
}>>([])

const addFraction = () => {
  fractions.push({
    identifier: '',
    description: '',
    floor: '',
    fraction_type: 'APARTMENT',
    permilagem: 0,
  })
}

// Start with 2 fractions
addFraction()
addFraction()

const permilagemTotal = computed(() => {
  return fractions.reduce((sum, f) => sum + (Number(f.permilagem) || 0), 0)
})

const submit = async () => {
  submitting.value = true
  submitError.value = ''
  try {
    await authStore.ensureToken()
    const result = await $fetch<any>('/api/v1/geo/condominiums/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: {
        world_object_id: buildingId.value,
        name: form.name,
        description: form.description,
        legal_entity_id: form.legal_entity_id,
        terms_content: form.terms_content,
        fractions: fractions.map(f => ({
          identifier: f.identifier,
          description: f.description,
          floor: f.floor,
          fraction_type: f.fraction_type,
          permilagem: f.permilagem,
        })),
      }
    })
    await navigateTo(localePath(`/org/${result.slug}`))
  } catch (err: any) {
    submitError.value = err?.data?.detail || err?.message || 'Error creating condominium'
  } finally {
    submitting.value = false
  }
}
</script>
