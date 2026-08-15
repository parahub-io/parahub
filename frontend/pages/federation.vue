<template>
  <div>
    <Head>
      <Title>{{ $t('federation.page_title') }}</Title>
    </Head>

    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <PageHeader :title="$t('federation.title')" :subtitle="$t('federation.subtitle')" />

      <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
        <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        <span class="sr-only">{{ $t('common.loading') }}</span>
      </div>

      <div v-else class="space-y-6">
        <!-- Stats -->
        <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div v-for="s in statTiles" :key="s.key" class="card p-4 text-center">
            <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ s.value }}</div>
            <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ s.label }}</div>
          </div>
        </div>

        <!-- Node Manifest -->
        <section class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
            <Server class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
            {{ $t('federation.node.title') }}
          </h2>
          <div v-if="manifest" class="space-y-2 text-sm">
            <div class="flex gap-2">
              <span class="text-neutral-500 dark:text-neutral-400 w-32 flex-shrink-0">{{ $t('federation.node.domain') }}:</span>
              <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ manifest.domain }}</span>
            </div>
            <div class="flex gap-2">
              <span class="text-neutral-500 dark:text-neutral-400 w-32 flex-shrink-0">{{ $t('federation.node.name') }}:</span>
              <span class="text-neutral-900 dark:text-neutral-100">{{ manifest.name }}</span>
            </div>
            <div v-if="manifest.registry_git" class="flex gap-2">
              <span class="text-neutral-500 dark:text-neutral-400 w-32 flex-shrink-0">{{ $t('federation.node.registry_git') }}:</span>
              <span class="font-mono text-neutral-900 dark:text-neutral-100 break-all">{{ manifest.registry_git }}</span>
            </div>
            <div v-if="manifest.ws_federation" class="flex gap-2">
              <span class="text-neutral-500 dark:text-neutral-400 w-32 flex-shrink-0">{{ $t('federation.node.ws_url') }}:</span>
              <span class="font-mono text-neutral-900 dark:text-neutral-100 break-all">{{ manifest.ws_federation }}</span>
            </div>
            <div v-if="manifest.capabilities?.length" class="flex gap-2">
              <span class="text-neutral-500 dark:text-neutral-400 w-32 flex-shrink-0">{{ $t('federation.node.capabilities') }}:</span>
              <div class="flex flex-wrap gap-1">
                <UiBadge v-for="cap in manifest.capabilities" :key="cap" variant="secondary" size="sm">
                  {{ cap }}
                </UiBadge>
              </div>
            </div>
          </div>
          <UiAlert v-else variant="warning" :icon="ServerOff">
            {{ $t('federation.node.no_manifest') }}
          </UiAlert>
        </section>

        <!-- Peers -->
        <section class="card p-4">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <Network class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
              {{ $t('federation.peers.title') }}
            </h2>
            <!-- Peer discovery and git sync are staff-only server-side (403 otherwise) -->
            <div v-if="isStaff" class="flex gap-2">
              <UiButton variant="outline" size="sm" :icon="Search" @click="showDiscoverModal = true">
                {{ $t('federation.peers.discover') }}
              </UiButton>
              <UiButton variant="primary" size="sm" :icon="RefreshCw" :loading="syncing" @click="syncAll">
                {{ syncing ? $t('federation.peers.syncing') : $t('federation.peers.sync_all') }}
              </UiButton>
            </div>
          </div>

          <div v-if="peersWithStatus.length" class="overflow-x-auto">
            <table class="w-full text-sm">
              <caption class="sr-only">{{ $t('federation.peers.title') }}</caption>
              <thead>
                <tr class="text-left text-neutral-500 dark:text-neutral-400 border-b border-neutral-300 dark:border-neutral-700">
                  <th class="pb-2 font-medium">{{ $t('federation.peers.domain') }}</th>
                  <th class="pb-2 font-medium">{{ $t('federation.peers.trust_level') }}</th>
                  <th class="pb-2 font-medium">{{ $t('federation.peers.head') }}</th>
                  <th class="pb-2 font-medium">{{ $t('federation.peers.last_fetch') }}</th>
                  <th v-if="isStaff" class="pb-2"><span class="sr-only">{{ $t('federation.peers.sync') }}</span></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-neutral-200 dark:divide-neutral-700">
                <tr v-for="peer in peersWithStatus" :key="peer.domain">
                  <td class="py-2 font-mono text-neutral-900 dark:text-neutral-100">{{ peer.domain }}</td>
                  <td class="py-2">
                    <UiBadge :variant="trustVariant(peer.trust_level)" size="sm">{{ peer.trust_level }}</UiBadge>
                  </td>
                  <td class="py-2 font-mono text-xs text-neutral-500 dark:text-neutral-400">{{ peer.head || '—' }}</td>
                  <td class="py-2 text-xs text-neutral-500 dark:text-neutral-400">{{ peer.last_fetch ? new Date(peer.last_fetch).toLocaleString() : '—' }}</td>
                  <td v-if="isStaff" class="py-2 text-right">
                    <UiButton
                      variant="ghost"
                      size="sm"
                      :icon="RefreshCw"
                      :loading="syncingPeer === peer.domain"
                      @click="syncPeer(peer.domain)"
                    >
                      {{ $t('federation.peers.sync') }}
                    </UiButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="py-12 text-center">
            <Network class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" aria-hidden="true" />
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('federation.peers.no_peers') }}</h3>
          </div>
        </section>

        <!-- Organizations -->
        <section class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
            <Building class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
            {{ $t('federation.organizations.title') }}
            <span v-if="organizations.length" class="text-sm font-normal text-neutral-500 dark:text-neutral-400">({{ organizations.length }})</span>
          </h2>

          <template v-if="organizations.length">
            <div class="divide-y divide-neutral-200 dark:divide-neutral-700">
              <div
                v-for="org in visibleOrganizations"
                :key="org.ulid"
                class="flex items-center justify-between gap-3 py-2"
              >
                <div class="min-w-0">
                  <span class="text-neutral-900 dark:text-neutral-100">{{ org.name }}</span>
                  <span v-if="org.category" class="ml-2 text-xs text-neutral-500 dark:text-neutral-400">{{ org.category }}</span>
                </div>
                <div class="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400 flex-shrink-0">
                  <span class="font-mono">{{ org.node }}</span>
                  <span class="font-mono">{{ org.ulid.substring(0, 8) }}</span>
                </div>
              </div>
            </div>
            <UiButton
              v-if="organizations.length > ORG_PREVIEW_LIMIT && !showAllOrgs"
              variant="ghost"
              size="sm"
              class="mt-2"
              @click="showAllOrgs = true"
            >
              {{ $t('federation.organizations.view_all') }} ({{ organizations.length }})
            </UiButton>
          </template>
          <div v-else class="py-12 text-center">
            <Building class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" aria-hidden="true" />
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('federation.organizations.no_orgs') }}</h3>
          </div>
        </section>

        <!-- Federated Search -->
        <section class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
            <Search class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
            {{ $t('federation.search.title') }}
          </h2>
          <div class="flex gap-2 mb-4">
            <label class="sr-only" for="federation-search">{{ $t('federation.search.title') }}</label>
            <input
              id="federation-search"
              v-model="searchQuery"
              type="search"
              :placeholder="$t('federation.search.placeholder')"
              class="flex-1 min-w-0 px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              @keyup.enter="doSearch"
            >
            <UiButton variant="primary" size="sm" :icon="Search" :loading="searching" :disabled="!searchQuery" @click="doSearch">
              {{ $t('federation.search.search') }}
            </UiButton>
          </div>
          <div
            v-if="searchResults.length"
            class="border border-neutral-300 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
          >
            <div
              v-for="(r, i) in searchResults"
              :key="i"
              class="flex items-center justify-between gap-3 py-2 px-3 bg-white dark:bg-neutral-900"
            >
              <div class="flex items-center gap-2 min-w-0">
                <img v-if="r.avatar_url" :src="r.avatar_url" class="w-8 h-8 rounded-full object-cover flex-shrink-0" alt="">
                <div v-else class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0">
                  <component :is="r.type === 'profile' ? User : Building" class="w-4 h-4 text-neutral-500 dark:text-neutral-400" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ r.display_name || r.name || r.hna }}</span>
                  <span v-if="r.hna" class="ml-2 text-xs text-neutral-500 dark:text-neutral-400 font-mono">{{ r.hna }}</span>
                </div>
              </div>
              <div class="flex items-center gap-2 flex-shrink-0">
                <UiBadge v-if="r.is_verified" variant="success" size="sm">WoT</UiBadge>
                <UiBadge :variant="r.is_local ? 'primary' : 'secondary'" size="sm">{{ r.node }}</UiBadge>
              </div>
            </div>
          </div>
          <div v-else-if="searchDone" class="py-12 text-center">
            <SearchX class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" aria-hidden="true" />
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('federation.search.no_results') }}</h3>
          </div>
        </section>

        <!-- Import Migration Data (staff only) -->
        <section v-if="isStaff" class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
            <Upload class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
            {{ $t('federation.import.title') }}
          </h2>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
            {{ $t('federation.import.description') }}
          </p>
          <div class="flex flex-wrap items-center gap-3">
            <label class="sr-only" for="federation-import">{{ $t('federation.import.title') }}</label>
            <input
              id="federation-import"
              ref="importFileInput"
              type="file"
              accept=".zip"
              class="text-sm text-neutral-500 dark:text-neutral-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-neutral-900 hover:file:bg-primary-600 file:cursor-pointer"
              @change="handleImportFile"
            >
            <UiButton
              v-if="importFile"
              variant="primary"
              size="sm"
              :icon="Upload"
              :loading="importing"
              @click="doImport"
            >
              {{ $t('federation.import.upload') }}
            </UiButton>
          </div>
          <UiAlert v-if="importResult" variant="success" class="mt-3">
            {{ $t('federation.import.success') }}: {{ importResult.imported.contracts }} contracts,
            {{ importResult.imported.debts }} debts,
            {{ importResult.imported.verifications }} verifications,
            {{ importResult.imported.items }} items
          </UiAlert>
        </section>

        <!-- Migrations -->
        <section class="card p-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
            <ArrowRightLeft class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
            {{ $t('federation.migrations.title') }}
          </h2>

          <div
            v-if="migrations.length"
            class="border border-neutral-300 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
          >
            <div v-for="m in migrations" :key="m.id" class="p-4 bg-white dark:bg-neutral-900">
              <div class="flex items-center justify-between gap-3 mb-2">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="font-mono text-neutral-900 dark:text-neutral-100 truncate">{{ m.from_hna }}</span>
                  <ArrowRight class="w-4 h-4 text-neutral-500 dark:text-neutral-400 flex-shrink-0" aria-hidden="true" />
                  <span class="font-mono text-neutral-900 dark:text-neutral-100 truncate">{{ m.to_hna || '—' }}</span>
                </div>
                <UiBadge :variant="migrationVariant(m.status)" size="sm">
                  {{ $t(`federation.migrations.${m.status}`) }}
                </UiBadge>
              </div>

              <!-- Signature status -->
              <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                <span
                  v-for="sig in signatureRow(m)"
                  :key="sig.label"
                  class="inline-flex items-center gap-1"
                  :class="sig.signed ? 'text-success dark:text-success-400' : 'text-neutral-500 dark:text-neutral-400'"
                >
                  <component :is="sig.signed ? Check : Minus" class="w-3.5 h-3.5" aria-hidden="true" />
                  {{ sig.label }}
                </span>
              </div>

              <div v-if="m.git_commit_hash" class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {{ $t('federation.migrations.git_commit') }}: <span class="font-mono">{{ m.git_commit_hash.substring(0, 8) }}</span>
              </div>
              <div v-if="m.export_hash" class="text-xs text-neutral-500 dark:text-neutral-400">
                {{ $t('federation.migrations.export_hash') }}: <span class="font-mono">{{ m.export_hash.substring(0, 16) }}…</span>
              </div>
            </div>
          </div>
          <div v-else class="py-12 text-center">
            <ArrowRightLeft class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-4" aria-hidden="true" />
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('federation.migrations.no_migrations') }}</h3>
          </div>
        </section>
      </div>
    </div>

    <!-- Discover Peer Modal -->
    <Modal v-model="showDiscoverModal" size="md" :title="$t('federation.peers.discover')" :icon="Search">
      <div>
        <label for="discover-url" class="block text-sm text-neutral-500 dark:text-neutral-400 mb-1">
          {{ $t('federation.peers.discover_url') }}
        </label>
        <input
          id="discover-url"
          v-model="discoverUrl"
          type="url"
          :placeholder="$t('federation.peers.discover_placeholder')"
          class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          @keyup.enter="discoverPeer"
        >
      </div>
      <template #footer>
        <UiButton variant="outline" size="sm" @click="showDiscoverModal = false">
          {{ $t('federation.migrations.cancel') }}
        </UiButton>
        <UiButton variant="primary" size="sm" :icon="Search" :disabled="!discoverUrl" :loading="discovering" @click="discoverPeer">
          {{ $t('federation.peers.discover') }}
        </UiButton>
      </template>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { Server, ServerOff, Network, Building, ArrowRightLeft, ArrowRight, Search, SearchX, RefreshCw, Upload, User, Check, Minus } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  keepalive: true
})

const { t } = useI18n()
const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()

const ORG_PREVIEW_LIMIT = 10

// Registry writes (peer register/discover/sync, migration admin) need
// `federation.admin`; staff hold it implicitly. See parahub/capabilities.py.
const { can } = useCapabilities()
const isStaff = computed(() => can('federation.admin'))

// State
const loading = ref(true)
const manifest = ref<any>(null)
const stats = ref<any>(null)
const peers = ref<any[]>([])
const syncStatuses = ref<any[]>([])
const organizations = ref<any[]>([])
const migrations = ref<any[]>([])
const showAllOrgs = ref(false)
const syncing = ref(false)
const syncingPeer = ref<string | null>(null)
const showDiscoverModal = ref(false)
const discoverUrl = ref('')
const discovering = ref(false)
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const searching = ref(false)
const searchDone = ref(false)
const importFile = ref<File | null>(null)
const importFileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<any>(null)

const statTiles = computed(() => [
  { key: 'organizations', label: t('federation.stats.organizations'), value: stats.value?.organizations ?? 0 },
  { key: 'peers', label: t('federation.stats.peers'), value: stats.value?.peers ?? 0 },
  { key: 'migrations', label: t('federation.stats.migrations'), value: stats.value?.migrations ?? 0 },
  { key: 'connected_peers', label: t('federation.stats.connected_peers'), value: stats.value?.connected_peers ?? 0 },
])

const visibleOrganizations = computed(() =>
  showAllOrgs.value ? organizations.value : organizations.value.slice(0, ORG_PREVIEW_LIMIT)
)

// Merge peers with sync status
const peersWithStatus = computed(() => {
  return peers.value.map(p => {
    const status = syncStatuses.value.find(s => s.domain === p.domain)
    return {
      ...p,
      head: status?.head || '',
      last_fetch: status?.last_fetch || '',
    }
  })
})

type BadgeVariant = 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'neutral'

const trustVariant = (level: string): BadgeVariant => {
  if (level === 'peer') return 'success'
  if (level === 'bootstrap') return 'secondary'
  return 'neutral'
}

const migrationVariant = (status: string): BadgeVariant => {
  const map: Record<string, BadgeVariant> = {
    initiated: 'secondary',
    exported: 'warning',
    signed: 'primary',
    completed: 'success',
    cancelled: 'error',
  }
  return map[status] || 'neutral'
}

const signatureRow = (m: any) => [
  { label: t('federation.migrations.from_user'), signed: m.has_from_signature },
  { label: t('federation.migrations.to_user'), signed: m.has_to_signature },
  { label: t('federation.migrations.from_node'), signed: m.has_from_node_signature },
  { label: t('federation.migrations.to_node_sig'), signed: m.has_to_node_signature },
]

// Fetch data
const fetchAll = async () => {
  await authStore.ensureToken()
  const headers: Record<string, string> = {}
  if (authStore.token) headers['Authorization'] = `Bearer ${authStore.token}`

  try {
    const [manifestRes, statsRes, peersRes, orgsRes] = await Promise.all([
      $fetch('/api/v1/federation/node/', { credentials: 'include' }),
      $fetch('/api/v1/federation/stats/', { credentials: 'include' }),
      $fetch('/api/v1/federation/peers/', { credentials: 'include' }),
      $fetch('/api/v1/federation/organizations/', { credentials: 'include' }),
    ])
    manifest.value = manifestRes
    stats.value = statsRes
    peers.value = peersRes as any[]
    organizations.value = orgsRes as any[]
  } catch (e) {
    console.error('Federation fetch error:', e)
  }

  // Staff-only: sync status + migrations
  if (isStaff.value) {
    try {
      const [syncRes, migRes] = await Promise.all([
        $fetch('/api/v1/federation/sync/status/', {
          credentials: 'include',
          headers,
        }),
        $fetch('/api/v1/federation/migrations/', {
          credentials: 'include',
          headers,
        }),
      ])
      syncStatuses.value = (syncRes as any)?.peers || []
      migrations.value = migRes as any[]
    } catch (e) {
      console.error('Staff federation fetch error:', e)
    }
  }

  loading.value = false
}

// Sync
const syncAll = async () => {
  syncing.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/federation/sync/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    showSuccess(t('federation.peers.sync_success'))
    await fetchAll()
  } catch (e: any) {
    showError(e.data?.detail || t('federation.peers.sync_error'))
  } finally {
    syncing.value = false
  }
}

const syncPeer = async (domain: string) => {
  syncingPeer.value = domain
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/federation/sync/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { domain },
    })
    showSuccess(t('federation.peers.sync_success'))
    await fetchAll()
  } catch (e: any) {
    showError(e.data?.detail || t('federation.peers.sync_error'))
  } finally {
    syncingPeer.value = null
  }
}

// Discover peer
const discoverPeer = async () => {
  if (!discoverUrl.value || discovering.value) return
  discovering.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch('/api/v1/federation/peers/discover/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      params: { url: discoverUrl.value },
    }) as any
    showSuccess(t('federation.peers.discover_success', { domain: res.domain }))
    showDiscoverModal.value = false
    discoverUrl.value = ''
    await fetchAll()
  } catch (e: any) {
    showError(e.data?.detail || t('federation.peers.discover_error'))
  } finally {
    discovering.value = false
  }
}

// Federated search
const doSearch = async () => {
  if (!searchQuery.value || searchQuery.value.length < 2) return
  searching.value = true
  searchDone.value = false
  try {
    const res = await $fetch('/api/v1/federation/search/', {
      credentials: 'include',
      params: { q: searchQuery.value },
    }) as any
    searchResults.value = res.results || []
    searchDone.value = true
  } catch (e: any) {
    showError(e.data?.detail || 'Search failed')
  } finally {
    searching.value = false
  }
}

// Import
const handleImportFile = (e: Event) => {
  const input = e.target as HTMLInputElement
  importFile.value = input.files?.[0] || null
}

const doImport = async () => {
  if (!importFile.value) return
  importing.value = true
  importResult.value = null
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('file', importFile.value)
    const res = await $fetch('/api/v1/federation/migration/import/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: formData,
    })
    importResult.value = res
    showSuccess(t('federation.import.success'))
  } catch (e: any) {
    showError(e.data?.detail || 'Import failed')
  } finally {
    importing.value = false
  }
}

onMounted(fetchAll)
</script>
