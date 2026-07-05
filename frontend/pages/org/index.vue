<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader
      :title="$t('directory.my_orgs.title')"
      :subtitle="$t('directory.my_orgs.subtitle')"
      :create-to="canCreateOrg ? localePath('/org/create') : undefined"
      :create-label="canCreateOrg ? $t('directory.organizations.create_button') : undefined"
    />

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status">
      <div class="inline-block h-12 w-12 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="!orgs.length" class="py-12 text-center">
      <Building2 class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('directory.my_orgs.empty_title') }}</h3>
      <p class="text-neutral-600 dark:text-neutral-400 mb-5 max-w-md mx-auto">{{ $t('directory.my_orgs.empty_desc') }}</p>
      <div class="flex items-center justify-center gap-3">
        <UiButton v-if="canCreateOrg" variant="primary" :icon="Plus" :to="localePath('/org/create')">
          {{ $t('directory.organizations.create_button') }}
        </UiButton>
        <NuxtLink :to="localePath('/directory?type=organizations')" class="text-link">
          {{ $t('directory.my_orgs.browse_directory') }}
        </NuxtLink>
      </div>
    </div>

    <!-- Grouped lists -->
    <div v-else class="space-y-6">
      <section v-for="group in visibleGroups" :key="group.key">
        <h2 class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-2">
          <component :is="group.icon" class="w-3.5 h-3.5" />
          {{ $t(group.labelKey) }}
          <span class="text-neutral-300 dark:text-neutral-600">&middot;</span>
          {{ group.items.length }}
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <NuxtLink
            v-for="org in group.items"
            :key="org.id"
            :to="localePath(`/org/${org.slug || org.id}`)"
            class="flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-3 bg-white dark:bg-neutral-900 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            <!-- Icon / logo -->
            <div class="flex-shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
              <img v-if="org.logo_url" :src="org.logo_url" :alt="org.name" class="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover" />
              <component v-else :is="getEstablishmentIcon(org)" class="w-5 h-5 sm:w-6 sm:h-6 text-neutral-400 dark:text-neutral-500" />
            </div>

            <!-- Content -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="text-sm sm:text-base font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ org.name }}</h3>
                <BadgeCheck v-if="org.is_verified" class="w-4 h-4 text-primary flex-shrink-0" />
                <UiBadge v-if="org.organization_type" variant="neutral" type="soft" size="sm" class="hidden sm:inline-flex flex-shrink-0">
                  {{ getTypeLabel(org.organization_type) }}
                </UiBadge>
              </div>
              <div class="flex items-center flex-wrap gap-1.5 mt-1">
                <!-- Role / position -->
                <UiBadge :variant="roleVariant(org.role)" type="soft" size="sm">
                  {{ org.position_title || $t(`directory.my_orgs.role.${org.role.toLowerCase()}`) }}
                </UiBadge>
                <UiBadge v-if="org.is_treasurer" variant="warning" type="soft" size="sm">
                  <Coins class="w-3 h-3 -mt-0.5 mr-0.5 inline" />{{ $t('directory.my_orgs.treasurer') }}
                </UiBadge>
                <UiBadge v-if="org.is_auditor" variant="success" type="soft" size="sm">
                  <ShieldCheck class="w-3 h-3 -mt-0.5 mr-0.5 inline" />{{ $t('directory.my_orgs.auditor') }}
                </UiBadge>
              </div>
            </div>

            <!-- Stats -->
            <div class="flex-shrink-0 flex items-center gap-3 text-xs text-neutral-400 dark:text-neutral-500">
              <span v-if="org.member_count > 0" class="flex items-center gap-1" :title="$t('directory.organizations.members_tooltip', { count: org.member_count })">
                <Users class="w-3.5 h-3.5" />
                {{ org.member_count }}
              </span>
              <ChevronRight class="w-4 h-4 hidden sm:block" />
            </div>
          </NuxtLink>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Building2, Landmark, Briefcase, Heart, Building, Users,
  BadgeCheck, ChevronRight, Coins, ShieldCheck, Crown, Plus,
} from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()

useSeoMeta({ title: t('directory.my_orgs.title') + ' - Parahub', robots: 'noindex' })

interface MyOrg {
  id: string
  name: string
  slug: string | null
  logo_url: string | null
  organization_type: string | null
  role: string
  position_title: string | null
  is_treasurer: boolean
  is_auditor: boolean
  is_verified: boolean
  member_count: number
}

const orgs = ref<MyOrg[]>([])
const loading = ref(true)

// Mirrors backend WoT gate (3+ verifications or foundation member)
const canCreateOrg = computed(() =>
  authStore.isAuthenticated &&
  !!(authStore.user?.profile?.is_verified_wot || authStore.user?.profile?.is_foundation_member)
)

// Roles split into the three things "my organization" can mean to a person.
const groups = computed(() => [
  { key: 'manage', labelKey: 'directory.my_orgs.group_manage', icon: Crown,
    items: orgs.value.filter(o => o.role === 'OWNER' || o.role === 'ADMIN') },
  { key: 'member', labelKey: 'directory.my_orgs.group_member', icon: Users,
    items: orgs.value.filter(o => o.role === 'MEMBER') },
  { key: 'work', labelKey: 'directory.my_orgs.group_work', icon: Briefcase,
    items: orgs.value.filter(o => o.role === 'EMPLOYEE' || o.role === 'CONTRACTOR') },
])

const visibleGroups = computed(() => groups.value.filter(g => g.items.length))

const roleVariant = (role: string) =>
  role === 'OWNER' || role === 'ADMIN' ? 'secondary' : 'neutral'

const getTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    ASSOCIATION: t('directory.organizations.type_association'),
    COOPERATIVE: t('directory.organizations.type_cooperative'),
    COMPANY: t('directory.organizations.type_company'),
    NGO: t('directory.organizations.type_ngo'),
    COMMUNITY: t('directory.organizations.type_community'),
    CONDOMINIUM: t('directory.organizations.type_condominium'),
    GOVERNMENT: t('directory.organizations.type_government'),
  }
  return labels[type] || type
}

const getEstablishmentIcon = (org: MyOrg) => {
  if (org.organization_type === 'ASSOCIATION' || org.organization_type === 'NGO') return Landmark
  if (org.organization_type === 'COOPERATIVE') return Users
  if (org.organization_type === 'COMPANY') return Briefcase
  if (org.organization_type === 'COMMUNITY') return Heart
  if (org.organization_type === 'CONDOMINIUM') return Building
  return Building2
}

const fetchOrgs = async () => {
  loading.value = true
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    orgs.value = await $fetch<MyOrg[]>('/api/v1/geo/establishments/mine/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch (err) {
    console.error('Failed to load my organizations:', err)
  } finally {
    loading.value = false
  }
}

onMounted(fetchOrgs)
</script>
