<template>
  <div>
    <Head>
      <Title>{{ $t('federation.page_title') }}</Title>
    </Head>

    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-3">
          <Globe class="w-7 h-7 text-primary" />
          {{ $t('federation.title') }}
        </h1>
      </div>

      <!-- Stats Cards -->
      <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.organizations }}</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('federation.stats.organizations') }}</div>
        </div>
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.peers }}</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('federation.stats.peers') }}</div>
        </div>
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.migrations }}</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('federation.stats.migrations') }}</div>
        </div>
        <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ stats.connected_peers }}</div>
          <div class="text-xs text-neutral-500 mt-1">{{ $t('federation.stats.connected_peers') }}</div>
        </div>
      </div>

      <!-- Node Manifest -->
      <section class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
          <Server class="w-5 h-5 text-primary" />
          {{ $t('federation.node.title') }}
        </h2>
        <div v-if="manifest" class="space-y-2 text-sm">
          <div class="flex gap-2">
            <span class="text-neutral-500 w-32 flex-shrink-0">{{ $t('federation.node.domain') }}:</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ manifest.domain }}</span>
          </div>
          <div class="flex gap-2">
            <span class="text-neutral-500 w-32 flex-shrink-0">{{ $t('federation.node.name') }}:</span>
            <span class="text-neutral-900 dark:text-neutral-100">{{ manifest.name }}</span>
          </div>
          <div v-if="manifest.registry_git" class="flex gap-2">
            <span class="text-neutral-500 w-32 flex-shrink-0">{{ $t('federation.node.registry_git') }}:</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100 break-all">{{ manifest.registry_git }}</span>
          </div>
          <div v-if="manifest.ws_federation" class="flex gap-2">
            <span class="text-neutral-500 w-32 flex-shrink-0">{{ $t('federation.node.ws_url') }}:</span>
            <span class="font-mono text-neutral-900 dark:text-neutral-100 break-all">{{ manifest.ws_federation }}</span>
          </div>
          <div v-if="manifest.capabilities?.length" class="flex gap-2">
            <span class="text-neutral-500 w-32 flex-shrink-0">{{ $t('federation.node.capabilities') }}:</span>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="cap in manifest.capabilities"
                :key="cap"
                class="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs font-medium"
              >{{ cap }}</span>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-500">
          {{ $t('federation.node.no_manifest') }}
        </div>
      </section>

      <!-- Peers -->
      <section class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Network class="w-5 h-5 text-primary" />
            {{ $t('federation.peers.title') }}
          </h2>
          <div class="flex gap-2">
            <button @click="showDiscoverModal = true" class="btn-outline btn-sm gap-1">
              <Search class="w-4 h-4" />
              {{ $t('federation.peers.discover') }}
            </button>
            <button @click="syncAll" :disabled="syncing" class="btn-primary btn-sm gap-1">
              <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': syncing }" />
              {{ syncing ? $t('federation.peers.syncing') : $t('federation.peers.sync_all') }}
            </button>
          </div>
        </div>

        <div v-if="peers.length" class="overflow-x-auto">
          <table class="w-full text-sm">
            <caption class="sr-only">{{ $t('federation.peers.title') }}</caption>
            <thead>
              <tr class="text-left text-neutral-500 border-b border-neutral-200 dark:border-neutral-700">
                <th class="pb-2">{{ $t('federation.peers.domain') }}</th>
                <th class="pb-2">{{ $t('federation.peers.trust_level') }}</th>
                <th class="pb-2">{{ $t('federation.peers.head') }}</th>
                <th class="pb-2">{{ $t('federation.peers.last_fetch') }}</th>
                <th class="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="peer in peersWithStatus" :key="peer.domain" class="border-b border-neutral-200/50 dark:border-neutral-700/50">
                <td class="py-2 font-mono text-neutral-900 dark:text-neutral-100">{{ peer.domain }}</td>
                <td class="py-2">
                  <span class="px-2 py-0.5 rounded text-xs font-medium"
                    :class="{
                      'bg-success/10 text-success dark:bg-success/20 dark:text-success-400': peer.trust_level === 'peer',
                      'bg-secondary/10 text-secondary dark:bg-secondary/20 dark:text-secondary-400': peer.trust_level === 'bootstrap',
                      'bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400': peer.trust_level === 'observed',
                    }">
                    {{ peer.trust_level }}
                  </span>
                </td>
                <td class="py-2 font-mono text-xs text-neutral-500">{{ peer.head || '-' }}</td>
                <td class="py-2 text-xs text-neutral-500">{{ peer.last_fetch ? new Date(peer.last_fetch).toLocaleString() : '-' }}</td>
                <td class="py-2">
                  <button @click="syncPeer(peer.domain)" class="text-primary hover:underline text-xs">
                    {{ $t('federation.peers.sync') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-sm text-neutral-500">
          {{ $t('federation.peers.no_peers') }}
        </div>
      </section>

      <!-- Organizations -->
      <section class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
          <Building class="w-5 h-5 text-primary" />
          {{ $t('federation.organizations.title') }}
          <span v-if="organizations.length" class="text-sm font-normal text-neutral-500">({{ organizations.length }})</span>
        </h2>

        <div v-if="organizations.length" class="space-y-2">
          <div
            v-for="org in organizations.slice(0, showAllOrgs ? undefined : 10)"
            :key="org.ulid"
            class="flex items-center justify-between py-2 border-b border-neutral-200/50 dark:border-neutral-700/50 last:border-0"
          >
            <div>
              <span class="text-neutral-900 dark:text-neutral-100">{{ org.name }}</span>
              <span v-if="org.category" class="ml-2 text-xs text-neutral-500">{{ org.category }}</span>
            </div>
            <div class="flex items-center gap-3 text-xs text-neutral-500">
              <span class="font-mono">{{ org.node }}</span>
              <span class="font-mono">{{ org.ulid.substring(0, 8) }}</span>
            </div>
          </div>
          <button
            v-if="organizations.length > 10 && !showAllOrgs"
            @click="showAllOrgs = true"
            class="text-primary text-sm hover:underline"
          >
            {{ $t('federation.organizations.view_all') }} ({{ organizations.length }})
          </button>
        </div>
        <div v-else class="text-sm text-neutral-500">
          {{ $t('federation.organizations.no_orgs') }}
        </div>
      </section>

      <!-- Federated Search -->
      <section class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
          <Search class="w-5 h-5 text-primary" />
          {{ $t('federation.search.title') }}
        </h2>
        <div class="flex gap-2 mb-4">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="$t('federation.search.placeholder')"
            class="flex-1 px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm"
            @keyup.enter="doSearch"
          >
          <button @click="doSearch" :disabled="!searchQuery || searching" class="btn-primary btn-sm gap-1">
            <Search class="w-4 h-4" />
            {{ searching ? '...' : $t('federation.search.search') }}
          </button>
        </div>
        <div v-if="searchResults.length" class="space-y-2">
          <div
            v-for="(r, i) in searchResults"
            :key="i"
            class="flex items-center justify-between py-2 px-3 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700"
          >
            <div class="flex items-center gap-2">
              <img v-if="r.avatar_url" :src="r.avatar_url" class="w-8 h-8 rounded-full object-cover" alt="">
              <div v-else class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                <component :is="r.type === 'profile' ? User : Building" class="w-4 h-4 text-neutral-500" />
              </div>
              <div>
                <span class="text-sm text-neutral-900 dark:text-neutral-100">{{ r.display_name || r.name || r.hna }}</span>
                <span v-if="r.hna" class="ml-2 text-xs text-neutral-500 font-mono">{{ r.hna }}</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span v-if="r.is_verified" class="text-success text-xs">WoT</span>
              <span class="px-2 py-0.5 rounded text-xs font-medium"
                :class="r.is_local ? 'bg-primary/10 text-primary' : 'bg-secondary/10 text-secondary dark:bg-secondary/20 dark:text-secondary-400'">
                {{ r.node }}
              </span>
            </div>
          </div>
        </div>
        <div v-else-if="searchDone" class="text-sm text-neutral-500">
          {{ $t('federation.search.no_results') }}
        </div>
      </section>

      <!-- Import Migration Data (staff only) -->
      <section v-if="isStaff" class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
          <Upload class="w-5 h-5 text-primary" />
          {{ $t('federation.import.title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
          {{ $t('federation.import.description') }}
        </p>
        <div class="flex items-center gap-3">
          <input
            ref="importFileInput"
            type="file"
            accept=".zip"
            class="text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary file:text-black hover:file:bg-primary/90"
            @change="handleImportFile"
          >
          <button
            v-if="importFile"
            @click="doImport"
            :disabled="importing"
            class="btn-primary btn-sm gap-1"
          >
            <Upload class="w-4 h-4" />
            {{ importing ? '...' : $t('federation.import.upload') }}
          </button>
        </div>
        <div v-if="importResult" class="mt-3 p-3 bg-success/10 dark:bg-success/20 rounded-lg text-sm text-success dark:text-success-400">
          {{ $t('federation.import.success') }}: {{ importResult.imported.contracts }} contracts, {{ importResult.imported.debts }} debts, {{ importResult.imported.verifications }} verifications, {{ importResult.imported.items }} items
        </div>
      </section>

      <!-- Migrations -->
      <section class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2 mb-4">
          <ArrowRightLeft class="w-5 h-5 text-primary" />
          {{ $t('federation.migrations.title') }}
        </h2>

        <div v-if="migrations.length" class="space-y-3">
          <div
            v-for="m in migrations"
            :key="m.id"
            class="p-4 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2">
                <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ m.from_hna }}</span>
                <ArrowRight class="w-4 h-4 text-neutral-500" />
                <span class="font-mono text-neutral-900 dark:text-neutral-100">{{ m.to_hna || '?' }}</span>
              </div>
              <span class="px-2 py-0.5 rounded text-xs font-medium"
                :class="{
                  'bg-secondary/10 text-secondary dark:bg-secondary/20 dark:text-secondary-400': m.status === 'initiated',
                  'bg-warning/10 text-warning dark:bg-warning/20 dark:text-warning': m.status === 'exported',
                  'bg-primary/10 text-neutral-800 dark:bg-primary/20 dark:text-primary': m.status === 'signed',
                  'bg-success/10 text-success dark:bg-success/20 dark:text-success-400': m.status === 'completed',
                  'bg-error/10 text-error dark:bg-error/20 dark:text-red-400': m.status === 'cancelled',
                }">
                {{ $t(`federation.migrations.${m.status}`) }}
              </span>
            </div>

            <!-- Signature status -->
            <div class="flex gap-4 text-xs text-neutral-500">
              <span :class="m.has_from_signature ? 'text-success' : ''">
                {{ $t('federation.migrations.from_user') }}: {{ m.has_from_signature ? 'OK' : '-' }}
              </span>
              <span :class="m.has_to_signature ? 'text-success' : ''">
                {{ $t('federation.migrations.to_user') }}: {{ m.has_to_signature ? 'OK' : '-' }}
              </span>
              <span :class="m.has_from_node_signature ? 'text-success' : ''">
                {{ $t('federation.migrations.from_node') }}: {{ m.has_from_node_signature ? 'OK' : '-' }}
              </span>
              <span :class="m.has_to_node_signature ? 'text-success' : ''">
                {{ $t('federation.migrations.to_node_sig') }}: {{ m.has_to_node_signature ? 'OK' : '-' }}
              </span>
            </div>

            <div v-if="m.git_commit_hash" class="mt-1 text-xs text-neutral-500">
              {{ $t('federation.migrations.git_commit') }}: <span class="font-mono">{{ m.git_commit_hash.substring(0, 8) }}</span>
            </div>
            <div v-if="m.export_hash" class="text-xs text-neutral-500">
              {{ $t('federation.migrations.export_hash') }}: <span class="font-mono">{{ m.export_hash.substring(0, 16) }}...</span>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-neutral-500">
          {{ $t('federation.migrations.no_migrations') }}
        </div>
      </section>
    </div>

    <!-- Discover Peer Modal -->
    <Teleport to="body">
      <div v-if="showDiscoverModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showDiscoverModal = false">
        <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 w-full max-w-md mx-4">
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
            {{ $t('federation.peers.discover') }}
          </h3>
          <div class="space-y-3">
            <div>
              <label class="block text-sm text-neutral-500 mb-1">{{ $t('federation.peers.discover_url') }}</label>
              <input
                v-model="discoverUrl"
                type="url"
                :placeholder="$t('federation.peers.discover_placeholder')"
                class="w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 text-sm"
              >
            </div>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button @click="showDiscoverModal = false" class="btn-outline btn-sm">
              {{ $t('federation.migrations.cancel') }}
            </button>
            <button @click="discoverPeer" :disabled="!discoverUrl || discovering" class="btn-primary btn-sm gap-1">
              <Search class="w-4 h-4" />
              {{ discovering ? '...' : $t('federation.peers.discover') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { Globe, Server, Network, Building, ArrowRightLeft, ArrowRight, Search, RefreshCw, Upload, User } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  keepalive: true
})

const { t } = useI18n()
const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()

// Staff check
const isStaff = computed(() => authStore.user?.is_staff)

// State
const manifest = ref<any>(null)
const stats = ref<any>(null)
const peers = ref<any[]>([])
const syncStatuses = ref<any[]>([])
const organizations = ref<any[]>([])
const migrations = ref<any[]>([])
const showAllOrgs = ref(false)
const syncing = ref(false)
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
  }
}

// Discover peer
const discoverPeer = async () => {
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
