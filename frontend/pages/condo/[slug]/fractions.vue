<template>
  <div class="max-w-3xl mx-auto px-4 py-6">
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
    <UiTabs
      model-value="fractions"
      :tabs="condoTabs"
      variant="nav"
      class="mb-6"
    />

    <!-- Loading -->
    <div v-if="pending" class="flex justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-primary" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!fractions?.length" class="text-center py-12">
      <Grid3x3 class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('condo.empty_fractions') }}</p>
    </div>

    <div v-else>
      <!-- Desktop table -->
      <div class="hidden sm:block bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-neutral-50 dark:bg-neutral-800">
              <tr>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.identifier') }}</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.type') }}</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.floor') }}</th>
                <th class="px-4 py-2 text-right text-xs font-medium text-neutral-500">{{ $t('condo.permilagem') }} ‰</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-neutral-500">{{ $t('condo.resident') }}</th>
                <th class="px-4 py-2 text-right text-xs font-medium text-neutral-500"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100 dark:divide-neutral-800">
              <tr v-for="f in fractions" :key="f.id">
                <td class="px-4 py-3 font-medium text-neutral-900 dark:text-neutral-100">{{ f.identifier }}</td>
                <td class="px-4 py-3 text-neutral-500">{{ $t(`condo.type_${f.fraction_type.toLowerCase()}`) }}</td>
                <td class="px-4 py-3 text-neutral-500">{{ f.floor || '-' }}</td>
                <td class="px-4 py-3 text-right font-mono text-neutral-700 dark:text-neutral-300">{{ Number(f.permilagem).toFixed(3) }}</td>
                <td class="px-4 py-3">
                  <div v-if="f.resident_hna" class="flex items-center gap-2">
                    <NuxtLink :to="localePath(`/u/${f.resident_hna.split('@')[0]}`)" class="text-link text-sm">
                      {{ f.resident_display_name || f.resident_hna.split('@')[0] }}
                    </NuxtLink>
                    <UiBadge :variant="f.is_owner ? 'success' : 'secondary'" size="sm">
                      {{ f.is_owner ? $t('condo.owner') : $t('condo.tenant') }}
                    </UiBadge>
                  </div>
                  <span v-else class="text-neutral-400 text-xs italic">{{ $t('condo.vacant') }}</span>
                </td>
                <td class="px-4 py-3 text-right">
                  <button
                    v-if="f.invite_token !== undefined"
                    @click="showInvite(f)"
                    class="text-link text-xs"
                  >
                    {{ $t('condo.invite') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Mobile cards -->
      <div class="sm:hidden space-y-3">
        <div
          v-for="f in fractions"
          :key="f.id"
          class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ f.identifier }}</span>
              <span class="text-neutral-300 dark:text-neutral-600 mx-1.5">&middot;</span>
              <span class="text-sm text-neutral-500">{{ $t(`condo.type_${f.fraction_type.toLowerCase()}`) }}</span>
            </div>
            <span class="font-mono text-sm text-neutral-700 dark:text-neutral-300">{{ Number(f.permilagem).toFixed(3) }} ‰</span>
          </div>
          <div v-if="f.floor" class="text-xs text-neutral-400 mb-2">{{ $t('condo.floor') }}: {{ f.floor }}</div>
          <div class="flex items-center justify-between">
            <div v-if="f.resident_hna" class="flex items-center gap-2">
              <NuxtLink :to="localePath(`/u/${f.resident_hna.split('@')[0]}`)" class="text-link text-sm">{{ f.resident_display_name || f.resident_hna.split('@')[0] }}</NuxtLink>
              <UiBadge :variant="f.is_owner ? 'success' : 'secondary'" size="sm">
                {{ f.is_owner ? $t('condo.owner') : $t('condo.tenant') }}
              </UiBadge>
            </div>
            <UiBadge v-else variant="neutral" size="sm">{{ $t('condo.vacant') }}</UiBadge>
            <button
              v-if="f.invite_token !== undefined"
              @click="showInvite(f)"
              class="text-link text-xs"
            >
              {{ $t('condo.invite') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Invite modal -->
    <div v-if="inviteModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="inviteModal = null">
      <div class="bg-white dark:bg-neutral-900 rounded-lg max-w-sm w-full p-6">
        <h3 class="text-lg font-bold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ $t('condo.invite_link') }}
        </h3>
        <p class="text-sm text-neutral-500 mb-4">{{ inviteModal.identifier }}</p>

        <div v-if="inviteModal.invite_token" class="mb-4">
          <div class="bg-neutral-50 dark:bg-neutral-800 rounded p-3 font-mono text-xs break-all select-all">
            {{ inviteUrl }}
          </div>
          <button @click="copyInvite" class="mt-2 text-sm text-link">
            {{ copied ? $t('condo.invite_copied') : $t('condo.invite_link') }}
          </button>
        </div>
        <div v-else>
          <UiButton variant="primary" size="sm" :loading="generating" @click="generateInvite(inviteModal)">
            {{ $t('condo.invite_generate') }}
          </UiButton>
        </div>

        <UiButton variant="outline" class="w-full mt-4" @click="inviteModal = null">
          {{ $t('common.close') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, Loader2, Grid3x3, Receipt, Vote, Info } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
})

const route = useRoute()
const { t } = useI18n()
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
  title: () => condoName.value ? `${condoName.value} — ${t('condo.fractions_tab')}` : t('condo.meta_fractions_title'),
  ogTitle: () => condoName.value ? `${condoName.value} — ${t('condo.fractions_tab')}` : t('condo.meta_fractions_title'),
  description: () => t('condo.meta_fractions_desc'),
  ogDescription: () => t('condo.meta_fractions_desc'),
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

const fractions = ref<any[] | null>(null)
const pending = ref(true)

onMounted(async () => {
  try {
    await authStore.ensureToken()
    fractions.value = await $fetch<any[]>(`/api/v1/geo/condominiums/${slug}/fractions/`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
  } catch (err) {
    console.error('Failed to fetch fractions:', err)
  } finally {
    pending.value = false
  }
})

const inviteModal = ref<any>(null)
const generating = ref(false)
const copied = ref(false)

const inviteUrl = computed(() => {
  if (!inviteModal.value?.invite_token) return ''
  return `${window.location.origin}/condo/invite/${inviteModal.value.invite_token}`
})

const showInvite = (f: any) => {
  inviteModal.value = f
  copied.value = false
}

const generateInvite = async (f: any) => {
  generating.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch<any>(`/api/v1/geo/condominiums/${slug}/fractions/${f.id}/invite/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
    f.invite_token = data.token
  } catch (err: any) {
    console.error('Failed to generate invite:', err)
  } finally {
    generating.value = false
  }
}

const copyInvite = async () => {
  try {
    await navigator.clipboard.writeText(inviteUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}
</script>
