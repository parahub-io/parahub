<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink
      :to="localePath(`/org/${slug}`)"
      class="inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ orgName || slug }}
    </NuxtLink>

    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
      {{ $t('directory.members.title') }}
    </h1>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 dark:border-neutral-600 border-t-neutral-900 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- No access -->
    <div v-else-if="accessDenied" class="py-12 text-center">
      <ShieldOff class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {{ $t('directory.members.no_access') }}
      </h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
        {{ $t('directory.members.no_access_hint') }}
      </p>
    </div>

    <template v-else>
      <!-- Applications waiting on us -->
      <div v-if="applications.length" class="card p-4 mb-4">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-1.5">
          <UserPlus class="w-4 h-4 text-neutral-400" />
          {{ $t('directory.members.applications_title') }}
          <UiBadge variant="warning" type="soft" size="sm">{{ applications.length }}</UiBadge>
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="inv in applications"
            :key="inv.id"
            class="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5"
          >
            <div class="min-w-0">
              <NuxtLink :to="localePath(`/@${handleOf(inv.target_hna)}`)" class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary dark:hover:text-secondary-400">
                {{ inv.target_display_name || handleOf(inv.target_hna) }}
              </NuxtLink>
              <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ formatDate(inv.created_at) }}</div>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <UiButton variant="primary" size="sm" :loading="busyId === inv.id" @click="resolve(inv, 'accept')">
                {{ $t('directory.members.approve') }}
              </UiButton>
              <UiButton variant="outline-error" size="sm" :loading="busyId === inv.id" @click="resolve(inv, 'decline')">
                {{ $t('directory.members.decline') }}
              </UiButton>
            </div>
          </div>
        </div>
      </div>

      <!-- Members -->
      <div class="card p-4 mb-4">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-1.5">
          <Users class="w-4 h-4 text-neutral-400" />
          {{ $t('directory.members.list_title') }}
          <span class="text-neutral-400 font-normal">{{ members.length }}</span>
        </h2>

        <div v-if="!members.length" class="py-12 text-center">
          <Users class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t('directory.members.empty') }}
          </h3>
        </div>

        <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="m in members"
            :key="m.profile_id"
            class="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <NuxtLink :to="localePath(`/@${handleOf(m.profile_hna)}`)" class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary dark:hover:text-secondary-400 truncate">
                  {{ m.profile_display_name || handleOf(m.profile_hna) }}
                </NuxtLink>
                <UiBadge v-if="m.profile_id === ownerId" variant="secondary" type="soft" size="sm">
                  {{ $t('directory.members.role_owner') }}
                </UiBadge>
                <UiBadge v-if="m.is_treasurer" variant="success" type="soft" size="sm">
                  {{ $t('directory.act_as.treasurer') }}
                </UiBadge>
                <UiBadge v-if="m.is_auditor" variant="info" type="soft" size="sm">
                  {{ $t('directory.act_as.auditor') }}
                </UiBadge>
              </div>
              <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                <span v-if="m.position_title">{{ m.position_title }} · </span>
                <span v-if="m.membership_level">{{ $t(`directory.organizations.membership_levels.${m.membership_level}`) }} · </span>
                {{ $t('directory.members.joined') }} {{ formatDate(m.joined_at) }}
              </div>
            </div>

            <div class="flex items-center gap-1.5 shrink-0">
              <select
                v-if="canEdit(m)"
                :value="m.role"
                class="text-xs border border-neutral-300 dark:border-neutral-600 rounded-lg px-2 py-1.5 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
                :disabled="busyId === m.profile_id"
                @change="changeRole(m, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="r in roleOptions(m)" :key="r" :value="r">
                  {{ $t(`directory.members.role_${r.toLowerCase()}`) }}
                </option>
              </select>
              <UiBadge v-else variant="neutral" type="soft" size="sm">
                {{ $t(`directory.members.role_${m.role.toLowerCase()}`) }}
              </UiBadge>

              <UiButton
                v-if="canEdit(m)"
                :variant="removeArmed === m.profile_id ? 'error' : 'outline-error'"
                size="sm"
                :loading="busyId === m.profile_id"
                @click="removeMember(m)"
              >
                {{ removeArmed === m.profile_id ? $t('directory.members.remove_confirm') : $t('directory.members.remove') }}
              </UiButton>
            </div>
          </div>
        </div>
      </div>

      <!-- Offers we sent -->
      <div v-if="invitations.length" class="card p-4 mb-4">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-1.5">
          <Send class="w-4 h-4 text-neutral-400" />
          {{ $t('directory.members.pending_title') }}
        </h2>
        <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="inv in invitations"
            :key="inv.id"
            class="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5"
          >
            <div class="min-w-0">
              <div class="text-sm text-neutral-900 dark:text-neutral-100 truncate">
                <span v-if="inv.target_hna">{{ inv.target_display_name || handleOf(inv.target_hna) }}</span>
                <span v-else class="inline-flex items-center gap-1"><LinkIcon class="w-3.5 h-3.5 text-neutral-400" />{{ $t('directory.members.link_invite') }}</span>
                <span class="text-neutral-400"> · {{ $t(`directory.members.role_${inv.role.toLowerCase()}`) }}</span>
              </div>
              <div class="text-xs" :class="inv.is_expired ? 'text-error' : 'text-neutral-500 dark:text-neutral-400'">
                <span v-if="inv.is_expired">{{ $t('directory.members.expired') }}</span>
                <span v-else-if="inv.expires_at">{{ $t('directory.members.expires') }} {{ formatDate(inv.expires_at) }}</span>
              </div>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <UiButton v-if="inv.token" variant="ghost" size="sm" :icon="Copy" @click="copyLink(inv.token)">
                {{ copiedToken === inv.token ? $t('directory.members.copied') : $t('directory.members.copy_link') }}
              </UiButton>
              <UiButton variant="outline-error" size="sm" :loading="busyId === inv.id" @click="resolve(inv, 'withdraw')">
                {{ $t('directory.members.revoke') }}
              </UiButton>
            </div>
          </div>
        </div>
      </div>

      <!-- Invite -->
      <div class="card p-4">
        <h2 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-1.5">
          <UserPlus class="w-4 h-4 text-neutral-400" />
          {{ $t('directory.members.invite_title') }}
        </h2>

        <UiTabs v-model="inviteMode" :tabs="inviteTabs" variant="pills" class="mb-3" />

        <div class="space-y-3">
          <!-- By name -->
          <div v-if="inviteMode === 'name'" class="relative">
            <input
              v-model="search"
              type="text"
              :placeholder="$t('directory.members.search_placeholder')"
              class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"
              @input="onSearch"
            />
            <div
              v-if="searchResults.length"
              class="absolute z-20 left-0 right-0 mt-1 py-1 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg max-h-60 overflow-y-auto"
            >
              <button
                v-for="p in searchResults"
                :key="p.id"
                type="button"
                class="w-full text-left px-3 py-2 text-sm hover:bg-primary-100 dark:hover:bg-primary-900/40 text-neutral-900 dark:text-neutral-100"
                @click="pick(p)"
              >
                {{ p.display_name || handleOf(p.hna) }}
                <span class="text-neutral-400 text-xs">{{ p.hna }}</span>
              </button>
            </div>
            <p v-if="picked" class="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
              {{ picked.display_name || handleOf(picked.hna) }}
              <button type="button" class="text-xs text-neutral-400 hover:text-error ml-1" @click="picked = null">✕</button>
            </p>
          </div>

          <!-- By link -->
          <p v-else class="text-xs text-neutral-500 dark:text-neutral-400">
            {{ $t('directory.members.link_hint') }}
          </p>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('directory.members.role') }}</label>
              <select
                v-model="inviteRole"
                class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100"
              >
                <option v-for="r in grantableRoles" :key="r" :value="r">
                  {{ $t(`directory.members.role_${r.toLowerCase()}`) }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('directory.members.position') }}</label>
              <input
                v-model="invitePosition"
                type="text"
                :placeholder="$t('directory.members.position_placeholder')"
                class="w-full text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
          </div>

          <p class="text-xs text-neutral-400 dark:text-neutral-500">{{ $t('directory.members.expires_in') }}</p>

          <UiButton
            variant="primary"
            size="sm"
            :loading="inviting"
            :disabled="inviteMode === 'name' && !picked"
            @click="sendInvite"
          >
            {{ inviteMode === 'link' ? $t('directory.members.create_link') : $t('directory.members.invite_button') }}
          </UiButton>

          <div v-if="createdLink" class="mt-2">
            <label class="block text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('directory.members.link_created') }}</label>
            <div class="flex gap-2">
              <input
                :value="createdLink"
                readonly
                class="flex-1 text-xs font-mono border border-neutral-300 dark:border-neutral-600 rounded-lg px-2.5 py-1.5 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 select-all"
              />
              <UiButton variant="outline" size="sm" :icon="Copy" @click="copyText(createdLink)">
                {{ $t('directory.members.copy_link') }}
              </UiButton>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft, Users, UserPlus, Send, ShieldOff, Copy, Link as LinkIcon,
} from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const slug = computed(() => String(route.params.slug))

// Same ladder the backend enforces (geo/permissions.py ROLE_RANK): a role is
// only offered when the viewer stands at or above it.
const ROLE_RANK: Record<string, number> = { OWNER: 3, ADMIN: 2, EMPLOYEE: 1, CONTRACTOR: 1, MEMBER: 0 }
const DIRECT_ROLES = ['EMPLOYEE', 'CONTRACTOR']
const ALL_ROLES = ['OWNER', 'ADMIN', 'EMPLOYEE', 'CONTRACTOR', 'MEMBER']
const LINK_INVITE_MAX_RANK = 1

const loading = ref(true)
const accessDenied = ref(false)
const orgId = ref('')
const orgName = ref('')
const ownerId = ref('')
const members = ref<any[]>([])
const invites = ref<any[]>([])
const busyId = ref('')
const removeArmed = ref('')
let removeTimer: any = null

const applications = computed(() => invites.value.filter(i => i.direction === 'REQUEST'))
const invitations = computed(() => invites.value.filter(i => i.direction === 'INVITE'))

const myRank = computed(() => {
  if (authStore.user?.is_staff) return ROLE_RANK.OWNER
  const me = authStore.profile?.id
  if (!me) return -1
  if (ownerId.value && ownerId.value === me) return ROLE_RANK.OWNER
  const mine = members.value.find(m => m.profile_id === me)
  return mine ? (ROLE_RANK[mine.role] ?? -1) : -1
})

const grantableRoles = computed(() => {
  const ceiling = inviteMode.value === 'link'
    ? Math.min(myRank.value, LINK_INVITE_MAX_RANK)
    : myRank.value
  return ALL_ROLES.filter(r => ROLE_RANK[r] <= ceiling)
})

function canEdit(m: any) {
  const me = authStore.profile?.id
  if (m.profile_id === me) return false
  if (m.profile_id === ownerId.value) return false
  return (ROLE_RANK[m.role] ?? 0) <= myRank.value
}

// Demotions are immediate; a promotion into authority has to be accepted, so
// the select only offers what the backend would actually write.
function roleOptions(m: any) {
  const current = ROLE_RANK[m.role] ?? 0
  return ALL_ROLES.filter(r =>
    r === m.role || (ROLE_RANK[r] <= myRank.value && (ROLE_RANK[r] < current || DIRECT_ROLES.includes(r)))
  )
}

function handleOf(hna?: string) {
  return (hna || '').split('@')[0]
}

function formatDate(value?: string) {
  if (!value) return ''
  const d = new Date(value)
  return isNaN(d.getTime()) ? '' : new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(d)
}

async function authed() {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function loadAll() {
  loading.value = true
  try {
    const est = await $fetch<any>(`/api/v1/geo/establishments/${slug.value}/`, {
      credentials: 'include', headers: await authed(),
    })
    orgId.value = est.id
    orgName.value = est.name
    ownerId.value = est.owner_id || ''

    members.value = await $fetch<any[]>(`/api/v1/geo/establishments/${orgId.value}/members/`, {
      credentials: 'include', headers: await authed(),
    })
    await loadInvites()
  } catch (e: any) {
    if ((e?.response?.status ?? e?.statusCode) === 403) accessDenied.value = true
    else toast.error(t('directory.members.load_error'))
  } finally {
    loading.value = false
  }
}

async function loadInvites() {
  try {
    invites.value = await $fetch<any[]>(`/api/v1/geo/establishments/${orgId.value}/invites/`, {
      credentials: 'include', headers: await authed(),
    })
  } catch (e: any) {
    if ((e?.response?.status ?? e?.statusCode) === 403) accessDenied.value = true
    else throw e
  }
}

function apiError(e: any) {
  const detail = e?.data?.detail || e?.response?._data?.detail
  toast.error(detail || t('directory.members.action_error'))
}

async function changeRole(m: any, role: string) {
  if (role === m.role) return
  busyId.value = m.profile_id
  try {
    const updated = await $fetch<any>(`/api/v1/geo/establishments/${orgId.value}/members/${m.profile_id}/`, {
      method: 'PATCH', credentials: 'include', headers: await authed(), body: { role },
    })
    Object.assign(m, updated)
    toast.success(t('directory.members.role_changed'))
  } catch (e: any) {
    apiError(e)
    await loadAll()
  } finally {
    busyId.value = ''
  }
}

async function removeMember(m: any) {
  if (removeArmed.value !== m.profile_id) {
    removeArmed.value = m.profile_id
    clearTimeout(removeTimer)
    removeTimer = setTimeout(() => { removeArmed.value = '' }, 3000)
    return
  }
  removeArmed.value = ''
  busyId.value = m.profile_id
  try {
    await $fetch(`/api/v1/geo/establishments/${orgId.value}/members/${m.profile_id}/`, {
      method: 'DELETE', credentials: 'include', headers: await authed(),
    })
    members.value = members.value.filter(x => x.profile_id !== m.profile_id)
    toast.success(t('directory.members.removed'))
  } catch (e: any) {
    apiError(e)
  } finally {
    busyId.value = ''
  }
}

async function resolve(inv: any, action: 'accept' | 'decline' | 'withdraw') {
  busyId.value = inv.id
  try {
    if (action === 'withdraw') {
      await $fetch(`/api/v1/geo/invites/${inv.id}/`, {
        method: 'DELETE', credentials: 'include', headers: await authed(),
      })
    } else {
      await $fetch(`/api/v1/geo/invites/${inv.id}/${action}/`, {
        method: 'POST', credentials: 'include', headers: await authed(),
      })
    }
    invites.value = invites.value.filter(i => i.id !== inv.id)
    if (action === 'accept') await loadAll()
    toast.success(t('directory.members.done'))
  } catch (e: any) {
    apiError(e)
  } finally {
    busyId.value = ''
  }
}

// ── Invite form ──
const inviteMode = ref<'name' | 'link'>('name')
const inviteTabs = computed(() => [
  { id: 'name', label: t('directory.members.invite_by_name') },
  { id: 'link', label: t('directory.members.invite_by_link') },
])
const search = ref('')
const searchResults = ref<any[]>([])
const picked = ref<any>(null)
const inviteRole = ref('MEMBER')
const invitePosition = ref('')
const inviting = ref(false)
const createdLink = ref('')
const copiedToken = ref('')
let searchTimer: any = null

// A role the viewer may no longer grant (link mode caps at EMPLOYEE) must not
// stay selected in the box.
watch([inviteMode, grantableRoles], () => {
  if (!grantableRoles.value.includes(inviteRole.value)) {
    inviteRole.value = grantableRoles.value[grantableRoles.value.length - 1] || 'MEMBER'
  }
})

function onSearch() {
  picked.value = null
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const q = search.value.trim().replace(/^@/, '')
    if (q.length < 2) { searchResults.value = []; return }
    try {
      const res: any = await $fetch('/api/v1/profiles/search/', {
        credentials: 'include', headers: await authed(), query: { q, page_size: 5 },
      })
      const memberIds = new Set(members.value.map(m => m.profile_id))
      searchResults.value = (res?.items || res || []).filter((p: any) => !memberIds.has(p.id))
    } catch { searchResults.value = [] }
  }, 300)
}

function pick(p: any) {
  picked.value = p
  search.value = p.display_name || p.hna
  searchResults.value = []
}

function inviteUrl(token: string) {
  return `${window.location.origin}/invite/org/${token}`
}

async function sendInvite() {
  inviting.value = true
  createdLink.value = ''
  try {
    const body: Record<string, any> = {
      role: inviteRole.value,
      position_title: invitePosition.value,
    }
    if (inviteMode.value === 'name') body.profile_id = picked.value?.id
    const inv = await $fetch<any>(`/api/v1/geo/establishments/${orgId.value}/invites/`, {
      method: 'POST', credentials: 'include', headers: await authed(), body,
    })
    if (inv.token) createdLink.value = inviteUrl(inv.token)
    picked.value = null
    search.value = ''
    invitePosition.value = ''
    await loadInvites()
    toast.success(t('directory.members.invite_sent'))
  } catch (e: any) {
    apiError(e)
  } finally {
    inviting.value = false
  }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(t('directory.members.copied'))
  } catch { /* clipboard blocked — the field is select-all anyway */ }
}

async function copyLink(token: string) {
  await copyText(inviteUrl(token))
  copiedToken.value = token
  setTimeout(() => { copiedToken.value = '' }, 2000)
}

onMounted(loadAll)

useSeoMeta({ title: () => `${orgName.value || slug.value} — ${t('directory.members.title')}`, robots: 'noindex' })
</script>
