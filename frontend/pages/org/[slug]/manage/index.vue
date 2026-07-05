<script setup lang="ts">
import {
  Newspaper, Pencil, Trash2, Plus, ArrowLeft,
  Palette, Globe, Video, ExternalLink,
  Send, Check, Undo2, Star, AlertCircle,
  ChevronUp, ChevronDown, LayoutGrid
} from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const estSlug = computed(() => String(route.params.slug))

// Required languages for "Approve" gate. Hardcoded to parahub-associacao for now;
// TODO: move to Site.required_blog_languages when other orgs adopt this workflow.
const REQUIRED_LANGS = computed<string[]>(() =>
  estSlug.value === 'parahub-associacao' ? ['pt', 'en', 'ru'] : []
)

// Access control: check user has management rights for this establishment
const accessDenied = ref(false)
async function checkAccess() {
  try {
    await authStore.ensureToken()
    const res = await $fetch<any[]>('/api/v1/geo/establishments/my-postable/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const hasAccess = res.some((e: any) => e.slug === estSlug.value)
    if (!hasAccess && !authStore.user?.is_superuser) {
      accessDenied.value = true
    }
  } catch {
    accessDenied.value = true
  }
}

// Tabs
const activeTab = useTabSync(['posts', 'pages', 'settings'])
const tabs = computed(() => [
  { id: 'posts', label: t('cms.manage.posts') },
  { id: 'pages', label: t('cms.manage.pages') },
  { id: 'settings', label: t('cms.manage.settings') },
])

// ── Posts ──
const loading = ref(true)
const posts = ref<any[]>([])
const estName = ref('')
const estId = ref('')
const videosRef = ref<{ refresh: () => void } | null>(null)
const deleteTargetGroup = ref<any>(null)
const deleting = ref(false)
const busyTopicKey = ref('')  // topic key currently running an approve/unapprove/publish action
const showPublished = ref(false)  // collapse published section by default

async function fetchPosts() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_slug: estSlug.value, status: 'all', page_size: 200 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    posts.value = res.items

    if (posts.value.length > 0) {
      estName.value = posts.value[0].establishment_name || estSlug.value
      estId.value = posts.value[0].establishment_id || ''
    }
  } catch {
    toast.error('Failed to load posts')
  } finally {
    loading.value = false
  }
}

async function deleteTopic() {
  const group = deleteTargetGroup.value
  if (!group) return
  deleting.value = true
  try {
    await authStore.ensureToken()
    // Delete every language version of the topic via existing per-post endpoint.
    // No batch-delete endpoint: the per-post DELETE already handles ObjectFile,
    // ObjectPhoto and ObjectComment cleanup correctly, so looping is safer than
    // reimplementing that logic on the server.
    for (const p of group.posts) {
      await $fetch(`/api/v1/cms/posts/${p.id}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    }
    const deletedIds = new Set(group.posts.map((p: any) => p.id))
    posts.value = posts.value.filter(p => !deletedIds.has(p.id))
    toast.success(t('cms.postDeleted'))
  } catch {
    toast.error('Failed to delete')
  } finally {
    deleting.value = false
    deleteTargetGroup.value = null
  }
}

// ── Topic grouping ──
// A topic = original post (translation_of_id null) + all its translations.
// Posts without translation_of_id are their own topic root.
// Posts with translation_of_id are attached to the root with that id.

interface TopicGroup {
  key: string            // root post id
  order: number | null   // publish_order of the root (or any member — they share)
  displayTitle: string   // title shown in the row — user's UI locale if available, else root
  displayPostId: string  // id of the displayed translation — edit target for title click
  posts: any[]           // all language versions, root first then alphabetical
  missingLangs: string[] // languages missing to fulfill REQUIRED_LANGS
  allApproved: boolean
  anyApproved: boolean
  allPublished: boolean
  anyPublished: boolean
}

const topicGroups = computed<TopicGroup[]>(() => {
  const byRoot = new Map<string, any[]>()
  for (const p of posts.value) {
    // Skip archived posts — they shouldn't leak into Drafts
    if (p.status === 'archived') continue
    const rootKey = p.translation_of_id || p.id
    if (!byRoot.has(rootKey)) byRoot.set(rootKey, [])
    byRoot.get(rootKey)!.push(p)
  }

  const groups: TopicGroup[] = []
  for (const [rootKey, group] of byRoot.entries()) {
    // Sort: root post (primary) first, then others alphabetically by language.
    // For parahub-associacao this puts PT first since PT is always the root.
    const sorted = [...group].sort((a, b) => {
      if (a.id === rootKey) return -1
      if (b.id === rootKey) return 1
      return a.language.localeCompare(b.language)
    })
    const rootPost = sorted[0]  // always the root after the sort above
    // Show the user's UI locale (which is auto-synced from Profile.preferred_language
    // by plugins/i18n-backend-sync.client.ts) if a translation in that language exists,
    // so editors see "their" title and click-to-edit lands on their language version.
    // Falls back to the root (PT for parahub-associacao) when their language is missing.
    const displayPost = sorted.find(p => p.language === locale.value) || rootPost
    const order = sorted.find(p => p.publish_order != null)?.publish_order ?? null
    const langsPresent = new Set(sorted.map(p => p.language))
    const missingLangs = REQUIRED_LANGS.value.filter(l => !langsPresent.has(l))

    groups.push({
      key: rootKey,
      order,
      displayTitle: displayPost.title,
      displayPostId: displayPost.id,
      posts: sorted,
      missingLangs,
      allApproved: sorted.every(p => !!p.approved_at),
      anyApproved: sorted.some(p => !!p.approved_at),
      allPublished: sorted.every(p => p.status === 'published'),
      anyPublished: sorted.some(p => p.status === 'published'),
    })
  }

  // Sort by publish_order ASC (nulls last), then by first post title
  groups.sort((a, b) => {
    if (a.order == null && b.order == null) return a.displayTitle.localeCompare(b.displayTitle)
    if (a.order == null) return 1
    if (b.order == null) return -1
    return a.order - b.order
  })
  return groups
})

const draftGroups = computed(() =>
  topicGroups.value.filter(g => !g.anyApproved && !g.anyPublished)
)
const readyGroups = computed(() =>
  topicGroups.value.filter(g => g.anyApproved && !g.anyPublished)
)
const publishedGroups = computed(() =>
  topicGroups.value.filter(g => g.anyPublished)
)

// The top of `readyGroups` is the recommended next — highlighted but not enforced.
const nextRecommendedKey = computed(() => readyGroups.value[0]?.key ?? null)

function canApprove(group: TopicGroup): boolean {
  return group.missingLangs.length === 0 && !group.anyApproved && !group.anyPublished
}

async function batchAction(group: TopicGroup, endpoint: 'batch-approve' | 'batch-unapprove' | 'batch-publish') {
  busyTopicKey.value = group.key
  try {
    await authStore.ensureToken()
    const updated = await $fetch<any[]>(`/api/v1/cms/posts/${endpoint}/`, {
      method: 'POST',
      body: { post_ids: group.posts.map(p => p.id) },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    // Merge updated posts back into local state
    const byId = new Map(updated.map(p => [p.id, p]))
    posts.value = posts.value.map(p => byId.get(p.id) || p)
    if (endpoint === 'batch-approve') toast.success(t('cms.manage.topicApproved'))
    else if (endpoint === 'batch-unapprove') toast.success(t('cms.manage.topicUnapproved'))
    else if (endpoint === 'batch-publish') toast.success(t('cms.manage.topicPublished'))
  } catch (e: any) {
    toast.error(e.data?.detail || e.data?.message || 'Action failed')
  } finally {
    busyTopicKey.value = ''
  }
}

function approveTopic(group: TopicGroup) { return batchAction(group, 'batch-approve') }
function unapproveTopic(group: TopicGroup) { return batchAction(group, 'batch-unapprove') }
function publishTopic(group: TopicGroup) { return batchAction(group, 'batch-publish') }

// ── Shared (Pages, Site, Nav Sections, Domain) ──
const apiPrefix = computed(() => estId.value ? `by-establishment/${estId.value}` : '')
const site = useSiteManage(apiPrefix)

// ── Init ──
onMounted(async () => {
  await checkAccess()
  if (accessDenied.value) return

  // Always resolve estId from slug first (don't depend on posts)
  try {
    await authStore.ensureToken()
    const res = await $fetch<any[]>('/api/v1/geo/establishments/my-postable/', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const est = res.find((e: any) => e.slug === estSlug.value)
    if (est) {
      estId.value = est.id
      estName.value = est.name
    }
  } catch { /* ignore */ }

  await Promise.all([fetchPosts(), site.fetchPages(), site.fetchSite()])
})

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

useHead({ title: computed(() => `${t('cms.manage.title')} — ${estName.value || estSlug.value}`) })
</script>

<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Access denied -->
      <div v-if="accessDenied" class="text-center py-12">
        <UiAlert variant="error">{{ t('common.accessDenied') || 'Access denied' }}</UiAlert>
      </div>

      <template v-else>
      <NuxtLink :to="localePath(`/org/${estSlug}`)" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ estName || estSlug }}
      </NuxtLink>

      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
          {{ t('cms.manage.title') }}
        </h1>
        <div class="flex items-center gap-3">
          <NuxtLink :to="localePath(`/org/${estSlug}/blog`)" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-secondary">
            <Newspaper class="w-4 h-4" />
            {{ t('cms.manage.viewBlog') }}
          </NuxtLink>
          <a :href="`https://${estSlug}.org.parahub.io`" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-secondary">
            <ExternalLink class="w-4 h-4" />
            {{ t('cms.manage.viewSite') }}
          </a>
        </div>
      </div>

      <UiTabs v-model="activeTab" :tabs="tabs" class="mb-6" />

      <!-- ═══ POSTS TAB — lifecycle sections ═══ -->
      <div v-if="activeTab === 'posts'">
        <div class="flex justify-between items-center mb-4">
          <span />
          <UiButton variant="primary" size="sm" :icon="Plus" :to="localePath(`/blog/create?est=${estSlug}`)">
            {{ t('cms.newPost') }}
          </UiButton>
        </div>

        <div v-if="loading" class="flex justify-center py-12" role="status">
          <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        </div>

        <div v-else-if="posts.length === 0" class="text-center py-12">
          <img src="/images/para/reading.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.noPosts') }}</h3>
          <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.noPostsDesc') }}</p>
        </div>

        <template v-else>
          <!-- DRAFTS SECTION -->
          <section class="mb-8">
            <h2 class="text-sm font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-3">
              {{ t('cms.manage.drafts') }} <span class="text-neutral-400">({{ draftGroups.length }})</span>
            </h2>
            <div v-if="draftGroups.length === 0" class="text-sm text-neutral-400 italic py-4">
              {{ t('cms.manage.sectionEmpty') }}
            </div>
            <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
              <BlogTopicRow
                v-for="group in draftGroups"
                :key="group.key"
                :group="group"
                :est-slug="estSlug"
                :busy="busyTopicKey === group.key"
                :can-approve="canApprove(group)"
                :locale="locale"
                :t="t"
                :local-path="localePath"
                @approve="approveTopic"
                @delete="(g) => deleteTargetGroup = g"
              />
            </div>
          </section>

          <!-- READY SECTION -->
          <section class="mb-8">
            <h2 class="text-sm font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-3">
              {{ t('cms.manage.ready') }} <span class="text-neutral-400">({{ readyGroups.length }})</span>
            </h2>
            <div v-if="readyGroups.length === 0" class="text-sm text-neutral-400 italic py-4">
              {{ t('cms.manage.sectionEmpty') }}
            </div>
            <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
              <BlogTopicRow
                v-for="group in readyGroups"
                :key="group.key"
                :group="group"
                :est-slug="estSlug"
                :busy="busyTopicKey === group.key"
                :section="'ready'"
                :is-next-recommended="group.key === nextRecommendedKey"
                :locale="locale"
                :t="t"
                :local-path="localePath"
                @unapprove="unapproveTopic"
                @publish="publishTopic"
                @delete="(g) => deleteTargetGroup = g"
              />
            </div>
          </section>

          <!-- PUBLISHED SECTION (collapsible) -->
          <section>
            <button
              class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-3 hover:text-secondary"
              @click="showPublished = !showPublished"
            >
              <ChevronDown v-if="showPublished" class="w-4 h-4" />
              <ChevronUp v-else class="w-4 h-4" />
              {{ t('cms.manage.publishedSection') }} <span class="text-neutral-400">({{ publishedGroups.length }})</span>
            </button>
            <div v-if="showPublished">
              <div v-if="publishedGroups.length === 0" class="text-sm text-neutral-400 italic py-4">
                {{ t('cms.manage.sectionEmpty') }}
              </div>
              <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
                <BlogTopicRow
                  v-for="group in publishedGroups"
                  :key="group.key"
                  :group="group"
                  :est-slug="estSlug"
                  :busy="busyTopicKey === group.key"
                  :section="'published'"
                  :locale="locale"
                  :t="t"
                  :local-path="localePath"
                  @delete="(g) => deleteTargetGroup = g"
                />
              </div>
            </div>
          </section>
        </template>

        <UiConfirmModal
          v-if="deleteTargetGroup"
          :model-value="true"
          :title="t('cms.deleteTopic')"
          :message="t('cms.deleteTopicConfirm')"
          :icon="Trash2"
          variant="error"
          :confirm-label="t('cms.deleteTopic')"
          :loading="deleting"
          @confirm="deleteTopic"
          @update:model-value="deleteTargetGroup = null"
        />
      </div>

      <!-- ═══ PAGES TAB ═══ -->
      <div v-else-if="activeTab === 'pages'">
        <div class="flex justify-between items-center mb-4">
          <span />
          <UiButton variant="primary" size="sm" :icon="Plus" @click="site.startEditPage()">
            {{ t('cms.manage.newPage') }}
          </UiButton>
        </div>

        <!-- Page editor inline -->
        <div v-if="site.editingPage.value" class="card p-4 mb-6 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">
            {{ site.editingPage.value.id ? t('cms.manage.editPage') : t('cms.manage.createPage') }}
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.title') }}</label>
              <input v-model="site.pageForm.title" type="text" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">Slug</label>
              <input v-model="site.pageForm.slug" type="text" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent" placeholder="auto-generated" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.content') }}</label>
            <BlogEditor v-model="site.pageForm.content" :post-id="site.editingPage.value?.id || ''" />
          </div>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input type="checkbox" v-model="site.pageForm.show_in_nav" class="rounded" />
              {{ t('cms.manage.showInNav') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input type="checkbox" v-model="site.pageForm.is_published" class="rounded" />
              {{ t('cms.published') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input type="checkbox" v-model="site.pageForm.is_homepage" class="rounded" />
              {{ t('cms.manage.isHomepage') }}
            </label>
            <div class="flex items-center gap-2">
              <label class="text-sm text-neutral-700 dark:text-neutral-300">{{ t('cms.manage.order') }}:</label>
              <input v-model.number="site.pageForm.order" type="number" min="0" class="w-20 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-2 py-1 text-sm" />
            </div>
          </div>
          <div class="flex gap-2">
            <UiButton variant="primary" :loading="site.pageSaving.value" @click="site.savePage">{{ t('common.save') }}</UiButton>
            <UiButton variant="ghost" @click="site.editingPage.value = null">{{ t('common.cancel') }}</UiButton>
          </div>
        </div>

        <div v-if="site.pagesLoading.value" class="flex justify-center py-8">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900" />
        </div>

        <div v-else-if="site.sitePages.value.length === 0 && !site.editingPage.value" class="text-center py-12">
          <img src="/images/para/welcome.webp" alt="" aria-hidden="true" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.manage.noPagesYet') }}</h3>
          <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.manage.noPagesDesc') }}</p>
        </div>

        <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="page in site.sitePages.value"
            :key="page.id"
            class="flex items-center gap-4 p-4 bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            <span class="text-xs text-neutral-400 w-6 text-center shrink-0">{{ page.order }}</span>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ page.title }}</span>
              <span class="text-xs text-neutral-500 ml-2">/{{ page.slug }}</span>
            </div>
            <UiBadge v-if="page.is_homepage" variant="success" type="soft" size="sm">{{ t('cms.manage.homepage') }}</UiBadge>
            <UiBadge v-if="page.show_in_nav" variant="info" type="soft" size="sm">nav</UiBadge>
            <UiBadge v-if="!page.is_published" variant="default" type="soft" size="sm">{{ t('cms.draft') }}</UiBadge>
            <span v-if="page.updated_at" class="text-xs text-neutral-400 shrink-0" :title="t('cms.manage.lastUpdated')">{{ timeAgo(page.updated_at) }}</span>
            <div class="flex items-center gap-1 shrink-0">
              <button @click="site.startEditPage(page)" class="p-2 rounded text-neutral-500 hover:text-secondary hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Pencil class="w-4 h-4" />
              </button>
              <button @click="site.deletePageTarget.value = page" class="p-2 rounded text-neutral-500 hover:text-red-500 hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <UiConfirmModal
          v-if="site.deletePageTarget.value"
          :model-value="true"
          :title="t('cms.manage.deletePage')"
          :message="t('cms.manage.deletePageConfirm')"
          :icon="Trash2"
          variant="error"
          :confirm-label="t('cms.manage.deletePage')"
          :loading="site.deletingPage.value"
          @confirm="site.deletePage"
          @update:model-value="site.deletePageTarget.value = null"
        />
      </div>

      <!-- ═══ SETTINGS TAB ═══ -->
      <div v-else-if="activeTab === 'settings'" class="space-y-6">
        <!-- Site URLs (subdomain + custom domain together, so it's clear which ones are live) -->
        <div class="card p-4 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Globe class="w-5 h-5" />
            {{ t('cms.site.siteUrls') }}
          </h3>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('cms.site.siteUrlsDesc') }}
          </p>

          <div class="space-y-2">
            <div v-if="estSlug" class="flex items-center gap-2 text-sm">
              <UiBadge variant="default" type="soft" size="sm">{{ t('cms.site.subdomain') }}</UiBadge>
              <a :href="`https://${estSlug}.org.parahub.io`" target="_blank" rel="noopener" class="text-link"><code class="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs">{{ estSlug }}.org.parahub.io</code></a>
            </div>

            <div v-if="site.siteData.value?.custom_domain" class="flex items-center gap-2 text-sm">
              <UiBadge variant="default" type="soft" size="sm">{{ t('cms.site.customDomain') }}</UiBadge>
              <a :href="`https://${site.siteData.value.custom_domain}`" target="_blank" rel="noopener" class="text-link"><code class="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs">{{ site.siteData.value.custom_domain }}</code></a>
              <UiBadge v-if="site.siteData.value.custom_domain_verified && site.siteData.value.custom_domain_ssl_ready" variant="success" type="soft" size="sm">{{ t('cms.site.domainLive') }}</UiBadge>
              <UiBadge v-else-if="site.siteData.value.custom_domain_verified" variant="warning" type="soft" size="sm">{{ t('cms.site.sslPending') }}</UiBadge>
              <UiBadge v-else variant="default" type="soft" size="sm">{{ t('cms.site.notVerified') }}</UiBadge>
            </div>
          </div>

          <!-- Custom domain form -->
          <div class="pt-2 border-t border-neutral-200 dark:border-neutral-700 space-y-3">
            <p class="text-sm text-neutral-500 dark:text-neutral-400">
              {{ t('cms.site.domainDesc') }}
            </p>
            <div class="flex items-end gap-3">
              <div class="flex-1">
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.domain') }}</label>
                <input
                  v-model="site.domainForm.domain"
                  type="text"
                  placeholder="my-org.pt"
                  class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              <UiButton variant="outline" size="sm" :loading="site.domainSaving.value" @click="site.setDomain" class="shrink-0">
                {{ site.siteData.value?.custom_domain ? t('cms.site.updateDomain') : t('cms.site.setDomain') }}
              </UiButton>
            </div>

            <div v-if="site.siteData.value?.custom_domain" class="flex gap-2">
              <UiButton v-if="!site.siteData.value.custom_domain_verified" variant="primary" size="sm" :loading="site.domainVerifying.value" @click="site.verifyDomain">
                {{ t('cms.site.verifyCname') }}
              </UiButton>
              <UiButton variant="ghost" size="sm" @click="site.removeDomain">
                {{ t('cms.site.removeDomain') }}
              </UiButton>
            </div>

            <p v-if="site.domainMessage.value" class="text-sm" :class="site.siteData.value?.custom_domain_verified ? 'text-green-600 dark:text-green-400' : 'text-neutral-500'">
              {{ site.domainMessage.value }}
            </p>
          </div>
        </div>

        <div class="card p-4 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Palette class="w-5 h-5" />
            {{ t('cms.site.branding') }}
          </h3>

          <!-- Accent color -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.accentColor') }}</label>
            <div class="flex items-center gap-3">
              <input v-model="site.siteForm.accent_color" type="color" class="w-10 h-10 rounded border border-neutral-300 dark:border-neutral-600 cursor-pointer" />
              <input v-model="site.siteForm.accent_color" type="text" maxlength="7" class="w-28 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm font-mono" />
            </div>
          </div>

          <!-- Hero text -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.heroText') }}</label>
            <textarea
              v-model="site.siteForm.hero_text"
              rows="3"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="Welcome to our community..."
            />
          </div>

          <UiButton variant="primary" :loading="site.siteSaving.value" @click="site.saveSite">
            {{ t('common.save') }}
          </UiButton>
        </div>

        <!-- Nav Sections -->
        <div class="card p-4 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <LayoutGrid class="w-5 h-5" />
            {{ t('cms.site.navSections') }}
          </h3>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('cms.site.navSectionsDesc') }}
          </p>

          <!-- Enabled sections (ordered) -->
          <div v-if="site.sortedSections.value.length" class="space-y-1">
            <div
              v-for="(section, idx) in site.sortedSections.value"
              :key="section.type"
              class="flex items-center gap-3 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2"
            >
              <span class="text-xs text-neutral-400 w-5 text-center shrink-0">{{ idx + 1 }}</span>
              <span class="flex-1 text-sm font-medium text-neutral-900 dark:text-neutral-100">
                {{ t(site.SECTION_LABEL_KEY[section.type as keyof typeof site.SECTION_LABEL_KEY]) }}
              </span>
              <button
                :disabled="idx === 0"
                :title="t('cms.site.moveUp')"
                class="p-1 rounded text-neutral-400 hover:text-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                @click="site.moveSection(section.type as any, -1)"
              >
                <ChevronUp class="w-4 h-4" />
              </button>
              <button
                :disabled="idx === site.sortedSections.value.length - 1"
                :title="t('cms.site.moveDown')"
                class="p-1 rounded text-neutral-400 hover:text-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                @click="site.moveSection(section.type as any, 1)"
              >
                <ChevronDown class="w-4 h-4" />
              </button>
              <button
                class="p-1 rounded text-neutral-400 hover:text-red-500"
                @click="site.toggleSection(section.type as any)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Disabled sections (available to add) -->
          <div v-if="site.disabledSections.value.length" class="flex flex-wrap gap-2">
            <button
              v-for="type in site.disabledSections.value"
              :key="type"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600 text-neutral-500 hover:border-secondary hover:text-secondary transition-colors"
              @click="site.toggleSection(type)"
            >
              <Plus class="w-3.5 h-3.5" />
              {{ t(site.SECTION_LABEL_KEY[type]) }}
            </button>
          </div>

          <UiButton variant="primary" :loading="site.siteSaving.value" @click="site.saveSite">
            {{ t('common.save') }}
          </UiButton>
        </div>

        <!-- Videos -->
        <div v-if="estId" class="card p-4 space-y-3">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Video class="w-5 h-5" />
            {{ t('videos.upload.button') }}
          </h3>
          <ObjectVideos ref="videosRef" :object-id="estId" :editable="true" />
          <VideoUpload :object-id="estId" @uploaded="videosRef?.refresh()" />
        </div>
      </div>
      </template>
    </div>
  </div>
</template>
