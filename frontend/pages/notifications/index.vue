<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Bell, Users, FileText, Vote, Phone, CalendarClock, ShoppingBag, Megaphone, Check, Square, SquareCheckBig } from 'lucide-vue-next'
import { useNotifications, type FeedNotification, type FeedSource } from '~/composables/useNotifications'

definePageMeta({ middleware: 'auth' })

const { t, locale } = useI18n()
const localePath = useLocalePath()
const { items, unreadCount, activeSource, unreadOnly, loadFeed, markRead, markAllRead } = useNotifications()

// URL-synced filters (bookmarkable, survive F5/back). `activeSource`/`unreadOnly` in the
// composable stay the source of truth for the live-feed WS prepend logic, so we mirror the
// URL into them. Default values produce a clean URL (no ?tab=/?unread=).
const activeTab = useTabSync(['all', 'incoming', 'mine'])
const unreadTab = useTabSync(['off', 'on'], 'off', 'unread')
activeSource.value = activeTab.value as FeedSource
unreadOnly.value = unreadTab.value === 'on'
watch(activeTab, (t) => { activeSource.value = t as FeedSource })
watch(unreadTab, (v) => { unreadOnly.value = v === 'on' })

const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(false)
const PAGE = 30

// Source axis: All (merged) / Incoming (others → you) / Mine (your own actions).
const sourceTabs = computed(() => [
  { id: 'all', label: t('notifications.filter_all') },
  { id: 'incoming', label: t('notifications.filter_incoming') },
  { id: 'mine', label: t('notifications.filter_mine') },
])

// Read axis — an orthogonal toggle. "Mine" has no unread state, so the toggle is
// disabled there and never applied; effectiveUnread folds that rule in.
const effectiveUnread = computed(() => activeSource.value !== 'mine' && unreadOnly.value)
function toggleUnread() {
  // Drive the URL param; the watcher mirrors it into unreadOnly.
  if (activeSource.value !== 'mine') unreadTab.value = unreadTab.value === 'on' ? 'off' : 'on'
}

const categoryIcon = (cat: string) => (({
  social: Users,
  contracts: FileText,
  governance: Vote,
  calls: Phone,
  rental: CalendarClock,
  market: ShoppingBag,
  ads: Megaphone,
} as Record<string, any>)[cat] || Bell)

async function initialLoad() {
  loading.value = true
  const res = await loadFeed({ limit: PAGE, source: activeSource.value, unread: effectiveUnread.value })
  hasMore.value = res.length >= PAGE
  loading.value = false
}

async function more() {
  if (loadingMore.value || !items.value.length) return
  loadingMore.value = true
  const before = items.value[items.value.length - 1]?.id
  const res = await loadFeed({ limit: PAGE, before, source: activeSource.value, unread: effectiveUnread.value })
  hasMore.value = res.length >= PAGE
  loadingMore.value = false
}

// Switching source or toggling unread reloads the feed from the top.
watch([activeSource, unreadOnly], () => { initialLoad() })

const emptyText = computed(() => {
  if (effectiveUnread.value) return t('notifications.empty_unread')
  if (activeSource.value === 'mine') return t('notifications.empty_mine')
  if (activeSource.value === 'incoming') return t('notifications.empty_incoming')
  return t('notifications.empty')
})

async function open(n: FeedNotification) {
  if (!n.read) markRead([n.id])
  if (n.url) navigateTo(localePath(n.url))
}

// Relative timestamps in the active locale.
const rtf = computed(() => new Intl.RelativeTimeFormat(locale.value || 'en', { numeric: 'auto' }))
function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const sec = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const min = Math.round(sec / 60)
  const hr = Math.round(min / 60)
  const day = Math.round(hr / 24)
  const mon = Math.round(day / 30)
  if (Math.abs(sec) < 60) return rtf.value.format(sec, 'second')
  if (Math.abs(min) < 60) return rtf.value.format(min, 'minute')
  if (Math.abs(hr) < 24) return rtf.value.format(hr, 'hour')
  if (Math.abs(day) < 30) return rtf.value.format(day, 'day')
  if (Math.abs(mon) < 12) return rtf.value.format(mon, 'month')
  return rtf.value.format(Math.round(mon / 12), 'year')
}

// Day grouping (Today / Yesterday / localized date).
function dayKey(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date()
  const yest = new Date(); yest.setDate(today.getDate() - 1)
  const same = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  if (same(d, today)) return t('notifications.today')
  if (same(d, yest)) return t('notifications.yesterday')
  return d.toLocaleDateString(locale.value || 'en', { day: 'numeric', month: 'long', year: 'numeric' })
}

const groups = computed(() => {
  const out: { key: string; items: FeedNotification[] }[] = []
  for (const n of items.value) {
    const k = dayKey(n.created_at)
    let g = out[out.length - 1]
    if (!g || g.key !== k) { g = { key: k, items: [] }; out.push(g) }
    g.items.push(n)
  }
  return out
})

onMounted(initialLoad)
</script>

<template>
  <div>
    <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ $t('notifications.title') }}
        </h1>
        <UiButton v-if="unreadCount > 0" variant="ghost" size="sm" :icon="Check" @click="markAllRead">
          {{ $t('notifications.mark_all_read') }}
        </UiButton>
      </div>

      <!-- Filters: source = underline tabs (which stream); unread = an orthogonal
           checkbox filter. Kept visually distinct so the two axes don't read as one tab strip. -->
      <div class="mb-5 flex flex-wrap items-center gap-x-4 gap-y-3">
        <UiTabs v-model="activeTab" :tabs="sourceTabs" />
        <button
          type="button"
          role="checkbox"
          :aria-checked="effectiveUnread"
          :disabled="activeSource === 'mine'"
          @click="toggleUnread"
          class="inline-flex items-center gap-2 px-2 py-1.5 text-sm font-medium rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-100 dark:hover:bg-primary-900/40"
          :class="effectiveUnread
            ? 'text-neutral-900 dark:text-neutral-100'
            : 'text-neutral-600 dark:text-neutral-300'"
        >
          <component
            :is="effectiveUnread ? SquareCheckBig : Square"
            class="w-4 h-4 shrink-0"
            :class="effectiveUnread ? 'text-secondary dark:text-secondary-400' : 'text-neutral-400 dark:text-neutral-500'"
          />
          {{ $t('notifications.unread_only') }}
          <UiBadge v-if="unreadCount" variant="primary" type="solid" size="sm">
            {{ unreadCount }}
          </UiBadge>
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="space-y-2">
        <div v-for="i in 6" :key="i" class="h-16 rounded-xl bg-neutral-100 dark:bg-neutral-800 animate-pulse"></div>
      </div>

      <!-- Empty -->
      <div v-else-if="!items.length" class="text-center py-16">
        <Bell class="w-12 h-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
        <p class="text-neutral-500 dark:text-neutral-400">{{ emptyText }}</p>
      </div>

      <!-- Feed -->
      <div v-else class="space-y-6">
        <div v-for="g in groups" :key="g.key">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-2">
            {{ g.key }}
          </h2>
          <div class="space-y-2">
            <button
              v-for="n in g.items"
              :key="n.id"
              @click="open(n)"
              class="w-full flex items-start gap-3 text-left p-3 rounded-xl border transition-colors"
              :class="n.read
                ? 'border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700/50'
                : 'border-primary-200 dark:border-primary-900/50 bg-primary-50 dark:bg-primary-900/15 hover:bg-primary-100 dark:hover:bg-primary-900/25'"
            >
              <div class="mt-0.5 shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-neutral-100 dark:bg-neutral-700">
                <component :is="categoryIcon(n.category)" class="w-4 h-4 text-neutral-600 dark:text-neutral-300" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate">{{ n.title }}</span>
                  <span v-if="!n.read" class="shrink-0 w-2 h-2 rounded-full bg-primary"></span>
                </div>
                <p v-if="n.body" class="text-sm text-neutral-600 dark:text-neutral-400 mt-0.5 break-words">{{ n.body }}</p>
                <span class="text-xs text-neutral-400 dark:text-neutral-500 mt-1 block">{{ timeAgo(n.created_at) }}</span>
              </div>
            </button>
          </div>
        </div>

        <div v-if="hasMore" class="text-center pt-2">
          <UiButton variant="outline" size="sm" :loading="loadingMore" @click="more">
            {{ $t('notifications.load_more') }}
          </UiButton>
        </div>
      </div>
    </div>
  </div>
</template>
