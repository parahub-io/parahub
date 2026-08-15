<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader title="Moderation queue" subtitle="Abuse reports from across the platform" />

    <!-- Loading -->
    <div v-if="loading && !rows.length" class="py-12 text-center" role="status" aria-live="polite">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 dark:border-neutral-600 border-t-neutral-900 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- No access: the page decides from the API, not from a client-side flag -->
    <div v-else-if="accessDenied" class="py-12 text-center">
      <ShieldOff class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
      <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Not permitted
      </h3>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
        Working the report queue needs the <span class="font-mono">moderation.review</span> capability.
      </p>
    </div>

    <template v-else>
      <UiTabs v-model="activeTab" :tabs="tabs" variant="underline" full-width class="mb-4" />

      <!-- Reason filter -->
      <div class="flex flex-wrap items-center gap-2 mb-4">
        <select
          v-model="reason"
          class="px-3 py-1.5 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"
          @change="reload()"
        >
          <option value="">All reasons</option>
          <option v-for="r in REASONS" :key="r" :value="r">{{ reasonLabel(r) }}</option>
        </select>
        <span class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ total }} report{{ total === 1 ? '' : 's' }}
        </span>
      </div>

      <!-- Empty -->
      <div v-if="!rows.length" class="py-12 text-center">
        <ShieldCheck class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
        <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Nothing here
        </h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          {{ activeTab === 'PENDING' ? 'No reports are waiting for a decision.' : 'No reports in this state.' }}
        </p>
      </div>

      <!-- Queue -->
      <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
        <div v-for="r in rows" :key="r.id">
          <button
            type="button"
            class="w-full text-left px-3 py-3 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
            :aria-expanded="open === r.id"
            @click="open = open === r.id ? '' : r.id"
          >
            <div class="flex flex-wrap items-center gap-2">
              <UiBadge :variant="reasonVariant(r.reason)" type="soft" size="sm">
                {{ reasonLabel(r.reason) }}
              </UiBadge>
              <span class="text-xs font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                {{ r.target_type }}
              </span>
              <UiBadge v-if="r.duplicate_pending" variant="warning" type="soft" size="sm">
                +{{ r.duplicate_pending }} more
              </UiBadge>
              <UiBadge v-if="r.author_reports_actioned" variant="error" type="soft" size="sm">
                repeat: {{ r.author_reports_actioned }}/{{ r.author_reports_total }}
              </UiBadge>
              <UiBadge v-if="r.status !== 'PENDING'" :variant="r.status === 'ACTIONED' ? 'success' : 'neutral'" type="soft" size="sm">
                {{ r.status }}
              </UiBadge>
              <span class="ml-auto text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">
                {{ formatDate(r.created_at) }}
              </span>
            </div>
            <p class="mt-1 text-sm text-neutral-900 dark:text-neutral-100 line-clamp-2">
              {{ r.excerpt || '—' }}
            </p>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">
              by {{ authorName(r) }} · reported by {{ reporterName(r) }}
            </p>
          </button>

          <!-- Expanded: everything the verdict rests on, and the verdict itself -->
          <div v-if="open === r.id" class="px-3 pb-3 pt-1 bg-neutral-50 dark:bg-neutral-800/50">
            <dl class="text-sm space-y-1 mb-3">
              <div v-if="r.details" class="flex gap-2">
                <dt class="text-neutral-500 dark:text-neutral-400 shrink-0">Reporter says</dt>
                <dd class="text-neutral-900 dark:text-neutral-100">{{ r.details }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="text-neutral-500 dark:text-neutral-400 shrink-0">Target</dt>
                <dd class="font-mono text-xs text-neutral-900 dark:text-neutral-100 break-all">
                  {{ r.target_type }}:{{ r.target_id }}
                </dd>
              </div>
              <div v-if="r.reviewed_by" class="flex gap-2">
                <dt class="text-neutral-500 dark:text-neutral-400 shrink-0">Reviewed</dt>
                <dd class="text-neutral-900 dark:text-neutral-100">
                  {{ r.reviewed_by }} · {{ formatDate(r.reviewed_at) }}
                  <span v-if="r.resolution_note" class="text-neutral-500 dark:text-neutral-400">— {{ r.resolution_note }}</span>
                </dd>
              </div>
            </dl>

            <div class="flex flex-wrap gap-2 mb-3">
              <NuxtLink v-if="r.context_url" :to="r.context_url" class="text-link text-sm inline-flex items-center gap-1">
                <ExternalLink class="w-4 h-4" /> Where it was reported
              </NuxtLink>
              <NuxtLink v-if="r.reported_profile" :to="localePath(`/@${r.reported_profile.local_name}`)" class="text-link text-sm inline-flex items-center gap-1">
                <User class="w-4 h-4" /> Author profile
              </NuxtLink>
            </div>

            <input
              v-model="notes[r.id]"
              type="text"
              maxlength="500"
              placeholder="Resolution note (optional) — what was done"
              class="w-full mb-2 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent"
            >
            <div class="flex flex-wrap gap-2">
              <UiButton variant="error" size="sm" :icon="Gavel" :loading="busy === r.id" @click="resolve(r, 'ACTIONED')">
                Action taken
              </UiButton>
              <UiButton variant="outline" size="sm" :icon="X" :loading="busy === r.id" @click="resolve(r, 'DISMISSED')">
                Dismiss
              </UiButton>
              <span v-if="r.duplicate_pending" class="self-center text-xs text-neutral-500 dark:text-neutral-400">
                closes {{ r.duplicate_pending }} other pending report{{ r.duplicate_pending === 1 ? '' : 's' }} on this object
              </span>
            </div>

            <!-- Taking the content down is still a Django-admin job; the row records the outcome -->
            <p class="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
              Removing the content itself happens in the admin for that model — this closes the report.
            </p>
          </div>
        </div>
      </div>

      <div v-if="rows.length < total" class="mt-4 text-center">
        <UiButton variant="outline" size="sm" :loading="loading" @click="loadMore()">Load more</UiButton>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ExternalLink, Gavel, ShieldCheck, ShieldOff, User, X } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

useHead({ title: 'Moderation queue' })

const REASONS = ['SPAM', 'FRAUD', 'HARASSMENT', 'SEXUAL', 'VIOLENCE', 'ILLEGAL', 'OTHER']

const activeTab = useTabSync(['PENDING', 'ACTIONED', 'DISMISSED'])
const tabs = computed(() => [
  { id: 'PENDING', label: `Pending${pendingTotal.value ? ` (${pendingTotal.value})` : ''}` },
  { id: 'ACTIONED', label: 'Actioned' },
  { id: 'DISMISSED', label: 'Dismissed' },
])

const loading = ref(true)
const accessDenied = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const pendingTotal = ref(0)
const reason = ref('')
const open = ref('')
const busy = ref('')
const notes = reactive<Record<string, string>>({})

// The reasons are the only strings the reporter also saw, so they keep the
// localized vocabulary; the rest of this console is English like /iot § infra.
function reasonLabel(value: string) {
  return t(`moderation.reasons.${value.toLowerCase()}`)
}

function reasonVariant(value: string) {
  if (['ILLEGAL', 'SEXUAL', 'VIOLENCE'].includes(value)) return 'error'
  if (['FRAUD', 'HARASSMENT'].includes(value)) return 'warning'
  return 'neutral'
}

function nameOf(p: any) {
  return p ? (p.display_name || p.local_name || '—') : '—'
}
const authorName = (r: any) => nameOf(r.reported_profile)
const reporterName = (r: any) => nameOf(r.reporter)

function formatDate(value: string) {
  if (!value) return ''
  const d = new Date(value)
  return isNaN(d.getTime())
    ? ''
    : new Intl.DateTimeFormat(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      }).format(d)
}

async function authed() {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function load(offset = 0) {
  loading.value = true
  try {
    const page = await $fetch<any>('/api/v1/core/reports/queue/', {
      credentials: 'include',
      headers: await authed(),
      params: { status: activeTab.value, reason: reason.value, limit: 50, offset },
    })
    rows.value = offset ? [...rows.value, ...page.items] : page.items
    total.value = page.total
    pendingTotal.value = page.pending_total
  } catch (e: any) {
    if ((e?.response?.status ?? e?.statusCode) === 403) accessDenied.value = true
    else toast.error('Failed to load the queue')
  } finally {
    loading.value = false
  }
}

const reload = () => { open.value = ''; return load(0) }
const loadMore = () => load(rows.value.length)

watch(activeTab, () => reload())

async function resolve(row: any, status: string) {
  busy.value = row.id
  try {
    const out = await $fetch<any>(`/api/v1/core/reports/${row.id}/resolve/`, {
      method: 'POST',
      credentials: 'include',
      headers: await authed(),
      body: { status, note: notes[row.id] || '' },
    })
    toast.success(out.resolved > 1
      ? `${out.resolved} reports closed as ${status}`
      : `Report ${status.toLowerCase()}`)
    delete notes[row.id]
    await reload()
  } catch (e: any) {
    toast.error((e?.response?.status ?? e?.statusCode) === 403
      ? 'Not permitted'
      : 'Failed to resolve the report')
  } finally {
    busy.value = ''
  }
}

onMounted(() => load(0))

// Every page is KeepAlive-cached, so coming back reuses this instance: refetch
// on re-entry or the queue shows what it held when the moderator left it.
let firstActivation = true
onActivated(() => {
  if (firstActivation) { firstActivation = false; return }
  reload()
})
</script>
