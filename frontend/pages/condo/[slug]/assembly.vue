<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <!-- Back link -->
    <NuxtLink
      :to="localePath(`/org/${slug}`)"
      class="flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ $t('condo.back') }}
    </NuxtLink>

    <!-- Condo name heading -->
    <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-4">{{ condoName || $t('condo.title') }}</h1>

    <!-- Tab navigation -->
    <UiRouteTabs
      :tabs="condoTabs"
      class="mb-6"
    />

    <!-- Assembly list -->
    <section class="mb-8">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('condo.assembly_history') }}</h2>

      <!-- Loading -->
      <div v-if="loadingAssemblies" class="flex justify-center py-8">
        <Loader2 class="w-6 h-6 animate-spin text-primary" />
      </div>

      <!-- Empty state -->
      <div v-else-if="!assemblies.length" class="text-center py-8">
        <img src="/images/para/building.webp" alt="" class="w-20 h-20 mx-auto mb-3 opacity-80" />
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('condo.empty_assemblies') }}</p>
        <p class="text-xs text-neutral-400 dark:text-neutral-500 mt-1">{{ $t('condo.empty_assemblies_subtitle') }}</p>
      </div>

      <!-- List -->
      <div v-else class="space-y-2">
        <NuxtLink
          v-for="a in assemblies"
          :key="a.id"
          :to="localePath(`/governance/polls/${a.id}`)"
          class="block p-3 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-primary dark:hover:border-primary transition-colors"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p class="font-medium text-neutral-900 dark:text-neutral-100 truncate">{{ a.title }}</p>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                {{ formatDate(a.end_time || a.created_at) }}
                <span class="mx-1">&middot;</span>
                {{ $t('condo.assembly_votes', { voted: a.total_voted, eligible: a.total_eligible }) }}
              </p>
            </div>
            <UiBadge
              :variant="statusVariant(a.status)"
              size="sm"
            >
              {{ $t(`condo.assembly_status_${a.status}`) }}
            </UiBadge>
          </div>
          <div v-if="a.status === 'ended'" class="mt-1.5">
            <UiBadge
              :variant="a.quorum_met ? 'success' : 'error'"
              type="outline"
              size="sm"
            >
              {{ a.quorum_met ? $t('condo.quorum_reached') : $t('condo.quorum_not_reached') }}
            </UiBadge>
          </div>
        </NuxtLink>
      </div>
    </section>

    <!-- Permilagem explanation -->
    <div class="flex items-start gap-2 p-3 rounded-lg bg-primary-100 dark:bg-primary-900/40 text-sm text-neutral-700 dark:text-neutral-300 mb-6">
      <Info class="w-4 h-4 mt-0.5 shrink-0 text-primary-700 dark:text-primary-300" />
      <span>{{ $t('condo.assembly_weight_info') }}</span>
    </div>

    <!-- Create assembly form -->
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('condo.assembly_title') }}</h2>
    <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">{{ $t('condo.assembly_subtitle') }}</p>

    <div class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.poll_title') }}</label>
        <input v-model="form.title" type="text" :placeholder="$t('condo.poll_title_placeholder')" class="input w-full" />
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.poll_description') }}</label>
        <textarea v-model="form.description" :placeholder="$t('condo.poll_description_placeholder')" rows="3" class="input w-full" />
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.poll_options') }}</label>
        <div class="space-y-2">
          <div v-for="(opt, idx) in form.options" :key="idx" class="flex gap-2">
            <input v-model="form.options[idx]" type="text" :placeholder="`${$t('condo.poll_option_placeholder')} ${idx + 1}`" class="input flex-1" />
            <UiButton v-if="form.options.length > 2" variant="ghost" size="sm" @click="form.options.splice(idx, 1)" class="text-error">
              &times;
            </UiButton>
          </div>
        </div>
        <button @click="form.options.push('')" class="mt-2 text-sm text-link">
          + {{ $t('condo.poll_add_option') }}
        </button>
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.quorum_type') }}</label>
        <select v-model="form.quorum_type" class="input w-full">
          <option value="simple_majority">{{ $t('condo.quorum_simple') }}</option>
          <option value="two_thirds">{{ $t('condo.quorum_two_thirds') }}</option>
          <option value="unanimity">{{ $t('condo.quorum_unanimity') }}</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ $t('condo.ends_at') }}</label>
        <input v-model="form.ends_at" type="datetime-local" class="input w-full" />
      </div>

      <UiAlert v-if="error" variant="error" dismissible @dismiss="error = ''">
        {{ error }}
      </UiAlert>

      <UiButton
        variant="primary"
        :loading="submitting"
        :disabled="!form.title || form.options.some(o => !o) || !form.ends_at"
        @click="submit"
      >
        {{ $t('condo.create_assembly') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Grid3x3, Receipt, Vote, Info, Loader2 } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const slug = route.params.slug as string
const condoName = ref('')

const { data: condoInfo } = await useAsyncData(`condo-info-${slug}`, () =>
  $fetch<any>(`/api/v1/geo/condominiums/${slug}/info/`).catch(() => null),
  { server: false }
)
watch(condoInfo, (v) => { if (v?.name) condoName.value = v.name }, { immediate: true })

useSeoMeta({
  title: () => condoName.value ? `${condoName.value} — ${t('condo.assembly_tab')}` : t('condo.meta_assembly_title'),
  ogTitle: () => condoName.value ? `${condoName.value} — ${t('condo.assembly_tab')}` : t('condo.meta_assembly_title'),
  description: () => t('condo.meta_assembly_desc'),
  ogDescription: () => t('condo.meta_assembly_desc'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary',
})

const condoTabs = computed(() => [
  { id: 'overview', label: t('condo.overview_tab'), icon: Info, to: localePath(`/condo/${slug}`) },
  { id: 'fractions', label: t('condo.fractions_tab'), icon: Grid3x3, to: localePath(`/condo/${slug}/fractions`) },
  { id: 'quotas', label: t('condo.quotas_tab'), icon: Receipt, to: localePath(`/condo/${slug}/quotas`) },
  { id: 'assembly', label: t('condo.assembly_tab'), icon: Vote, to: localePath(`/condo/${slug}/assembly`) },
])

// --- Assembly history ---
interface AssemblyItem {
  id: string
  title: string
  status: string
  created_at: string
  end_time: string | null
  total_eligible: number
  total_voted: number
  quorum_percent: number
  quorum_met: boolean
}

const assemblies = ref<AssemblyItem[]>([])
const loadingAssemblies = ref(true)

const localeMap: Record<string, string> = { en: 'en-GB', pt: 'pt-PT', es: 'es-ES', fr: 'fr-FR', ru: 'ru-RU' }

function formatDate(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(localeMap[locale.value] || locale.value, {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function statusVariant(status: string): 'success' | 'primary' | 'neutral' | 'error' {
  if (status === 'active') return 'primary'
  if (status === 'ended') return 'neutral'
  if (status === 'cancelled') return 'error'
  return 'neutral'
}

async function fetchAssemblies() {
  loadingAssemblies.value = true
  try {
    await authStore.ensureToken()
    assemblies.value = await $fetch<AssemblyItem[]>(`/api/v1/geo/condominiums/${slug}/assemblies/`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
  } catch {
    // Silent fail — history is non-critical
  } finally {
    loadingAssemblies.value = false
  }
}

onMounted(fetchAssemblies)

// --- Create form ---
const form = reactive({
  title: '',
  description: '',
  options: ['', ''],
  quorum_type: 'simple_majority',
  ends_at: '',
})

const submitting = ref(false)
const error = ref('')

const submit = async () => {
  submitting.value = true
  error.value = ''
  try {
    await authStore.ensureToken()
    const result = await $fetch<any>(`/api/v1/geo/condominiums/${slug}/assembly/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
      body: {
        title: form.title,
        description: form.description,
        options: form.options.filter(o => o.trim()),
        quorum_type: form.quorum_type,
        ends_at: new Date(form.ends_at).toISOString(),
      }
    })
    await navigateTo(localePath(`/governance/polls/${result.poll_id}`))
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Error creating assembly'
  } finally {
    submitting.value = false
  }
}
</script>
