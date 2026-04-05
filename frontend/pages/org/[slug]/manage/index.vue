<script setup lang="ts">
import {
  Newspaper, Pencil, Trash2, Plus, Pin, ArrowLeft,
  Palette, Globe, Video, ExternalLink,
  ListOrdered, CheckCircle2, Clock, Send
} from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const estSlug = computed(() => String(route.params.slug))

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
const activeTab = ref('posts')
const tabs = computed(() => [
  { id: 'posts', label: t('cms.manage.posts') },
  { id: 'queue', label: t('cms.manage.queue') },
  { id: 'pages', label: t('cms.manage.pages') },
  { id: 'settings', label: t('cms.manage.settings') },
])

// ── Posts ──
const loading = ref(true)
const posts = ref<any[]>([])
const estName = ref('')
const estId = ref('')
const deleteTarget = ref<any>(null)
const deleting = ref(false)

async function fetchPosts() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const drafts = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_slug: estSlug.value, status: 'draft', page_size: 100 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const published = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_slug: estSlug.value, page_size: 100 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const archived = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_slug: estSlug.value, status: 'archived', page_size: 100 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })

    const all = [...drafts.items, ...published.items, ...archived.items]
    const seen = new Set<string>()
    posts.value = all.filter(p => {
      if (seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })

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

async function deletePost() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/posts/${deleteTarget.value.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    posts.value = posts.value.filter(p => p.id !== deleteTarget.value.id)
    toast.success(t('cms.postDeleted'))
  } catch {
    toast.error('Failed to delete post')
  } finally {
    deleting.value = false
    deleteTarget.value = null
  }
}

// ── Queue ──
const queuePosts = ref<any[]>([])
const queueLoading = ref(false)
const publishingId = ref('')

// 2x/week: Mon + Thu, starting from a configured date
const QUEUE_START = new Date('2026-04-14') // first Monday
function suggestedDate(order: number): string {
  const week = Math.floor((order - 1) / 2)
  const isSecond = (order - 1) % 2 === 1
  const d = new Date(QUEUE_START)
  d.setDate(d.getDate() + week * 7 + (isSecond ? 3 : 0))
  return d.toLocaleDateString(locale.value, { day: 'numeric', month: 'short' })
}

interface QueueGroup {
  order: number
  posts: any[]
  allPublished: boolean
}

const queueGroups = computed<QueueGroup[]>(() => {
  const map = new Map<number, any[]>()
  for (const p of queuePosts.value) {
    if (p.publish_order == null) continue
    if (!map.has(p.publish_order)) map.set(p.publish_order, [])
    map.get(p.publish_order)!.push(p)
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([order, posts]) => ({
      order,
      posts: posts.sort((a: any, b: any) => a.language.localeCompare(b.language)),
      allPublished: posts.every((p: any) => p.status === 'published'),
    }))
})

const nextUnpublished = computed(() => {
  const g = queueGroups.value.find(g => !g.allPublished)
  return g?.order ?? null
})

async function fetchQueue() {
  if (!estId.value) return
  queueLoading.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_id: estId.value, status: 'draft', page_size: 200 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    const pub = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { establishment_id: estId.value, page_size: 200 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    // Merge, dedup, keep only those with publish_order
    const all = [...res.items, ...pub.items]
    const seen = new Set<string>()
    queuePosts.value = all.filter(p => {
      if (!p.publish_order || seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })
  } catch { /* ignore */ }
  queueLoading.value = false
}

async function publishTopic(order: number) {
  const group = queueGroups.value.find(g => g.order === order)
  if (!group) return
  const drafts = group.posts.filter((p: any) => p.status !== 'published')
  if (!drafts.length) return

  publishingId.value = String(order)
  try {
    await authStore.ensureToken()
    for (const post of drafts) {
      await $fetch(`/api/v1/cms/posts/${post.id}/`, {
        method: 'PATCH',
        body: { status: 'published' },
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    }
    toast.success(t('cms.postPublished'))
    await fetchQueue()
    await fetchPosts()
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to publish')
  }
  publishingId.value = ''
}

// ── Pages ──
const sitePages = ref<any[]>([])
const pagesLoading = ref(false)
const editingPage = ref<any>(null)
const pageForm = reactive({ title: '', slug: '', content: '', order: 0, show_in_nav: true, is_published: true })
const pageSaving = ref(false)
const deletePageTarget = ref<any>(null)
const deletingPage = ref(false)

async function fetchPages() {
  if (!estId.value) return
  pagesLoading.value = true
  try {
    await authStore.ensureToken()
    sitePages.value = await $fetch<any[]>(`/api/v1/cms/sites/by-establishment/${estId.value}/pages/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
  } catch { /* ignore */ }
  pagesLoading.value = false
}

function startEditPage(page?: any) {
  if (page) {
    editingPage.value = page
    pageForm.title = page.title
    pageForm.slug = page.slug
    pageForm.content = page.content
    pageForm.order = page.order
    pageForm.show_in_nav = page.show_in_nav
    pageForm.is_published = page.is_published
  } else {
    editingPage.value = { id: null }
    pageForm.title = ''
    pageForm.slug = ''
    pageForm.content = ''
    pageForm.order = sitePages.value.length
    pageForm.show_in_nav = true
    pageForm.is_published = true
  }
}

async function savePage() {
  if (!estId.value || !pageForm.title.trim()) return
  pageSaving.value = true
  try {
    await authStore.ensureToken()
    const headers = { Authorization: `Bearer ${authStore.token}` }

    if (editingPage.value?.id) {
      await $fetch(`/api/v1/cms/sites/by-establishment/${estId.value}/pages/${editingPage.value.id}/`, {
        method: 'PATCH', body: { ...pageForm }, credentials: 'include', headers,
      })
    } else {
      await $fetch(`/api/v1/cms/sites/by-establishment/${estId.value}/pages/`, {
        method: 'POST', body: { ...pageForm }, credentials: 'include', headers,
      })
    }
    toast.success(t('cms.manage.pageSaved'))
    editingPage.value = null
    await fetchPages()
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to save page')
  }
  pageSaving.value = false
}

async function deletePage() {
  if (!deletePageTarget.value || !estId.value) return
  deletingPage.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/sites/by-establishment/${estId.value}/pages/${deletePageTarget.value.id}/`, {
      method: 'DELETE', credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    sitePages.value = sitePages.value.filter(p => p.id !== deletePageTarget.value.id)
    toast.success(t('cms.manage.pageDeleted'))
  } catch { toast.error('Failed to delete page') }
  deletingPage.value = false
  deletePageTarget.value = null
}

// ── Site Settings ──
const siteData = ref<any>(null)
const siteForm = reactive({ accent_color: '#F5C518', hero_text: '', hero_image_id: '' })
const siteSaving = ref(false)

async function fetchSite() {
  if (!estId.value) return
  try {
    await authStore.ensureToken()
    siteData.value = await $fetch<any>(`/api/v1/cms/sites/by-establishment/${estId.value}/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    siteForm.accent_color = siteData.value.accent_color
    siteForm.hero_text = siteData.value.hero_text
    siteForm.hero_image_id = siteData.value.hero_image_id
  } catch { /* ignore */ }
}

async function saveSite() {
  if (!estId.value) return
  siteSaving.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/sites/by-establishment/${estId.value}/`, {
      method: 'PATCH',
      body: { ...siteForm },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    toast.success(t('common.saved'))
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to save settings')
  }
  siteSaving.value = false
}

// ── Custom Domain ──
const domainForm = reactive({ domain: '' })
const domainSaving = ref(false)
const domainVerifying = ref(false)
const domainMessage = ref('')

watch(() => siteData.value?.custom_domain, (v) => {
  if (v) domainForm.domain = v
}, { immediate: true })

async function setDomain() {
  if (!estId.value) return
  domainSaving.value = true
  domainMessage.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/cms/sites/by-establishment/${estId.value}/domain/`, {
      method: 'POST',
      body: { domain: domainForm.domain.trim() },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    domainMessage.value = res.message
    await fetchSite()
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to set domain')
  }
  domainSaving.value = false
}

async function verifyDomain() {
  if (!estId.value) return
  domainVerifying.value = true
  domainMessage.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/cms/sites/by-establishment/${estId.value}/domain/verify/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    domainMessage.value = res.message
    await fetchSite()
    // Poll for SSL readiness if verified but not yet SSL-ready
    if (siteData.value?.custom_domain_verified && !siteData.value?.custom_domain_ssl_ready) {
      pollSslStatus()
    }
  } catch (e: any) {
    toast.error(e.data?.message || 'Verification failed')
  }
  domainVerifying.value = false
}

let sslPollTimer: ReturnType<typeof setInterval> | null = null
function pollSslStatus() {
  if (sslPollTimer) return
  sslPollTimer = setInterval(async () => {
    await fetchSite()
    if (siteData.value?.custom_domain_ssl_ready) {
      clearInterval(sslPollTimer!)
      sslPollTimer = null
      domainMessage.value = 'SSL certificate ready — your domain is live!'
      toast.success('Custom domain is live!')
    }
  }, 5000)
}
onUnmounted(() => { if (sslPollTimer) clearInterval(sslPollTimer) })

async function removeDomain() {
  domainForm.domain = ''
  await setDomain()
}

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

  await Promise.all([fetchPosts(), fetchQueue(), fetchPages(), fetchSite()])
})

useHead({ title: computed(() => `${t('cms.manage.title')} — ${estName.value || estSlug.value}`) })

function statusBadge(status: string) {
  if (status === 'published') return { variant: 'success' as const, label: t('cms.published') }
  if (status === 'archived') return { variant: 'default' as const, label: t('cms.archived') }
  return { variant: 'warning' as const, label: t('cms.draft') }
}
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

      <!-- ═══ POSTS TAB ═══ -->
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
          <img src="/images/para/reading.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.noPosts') }}</h3>
          <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.noPostsDesc') }}</p>
        </div>

        <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="post in posts"
            :key="post.id"
            class="flex items-center gap-4 p-4 bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            <UiBadge :variant="statusBadge(post.status).variant" type="soft" size="sm" class="shrink-0">
              {{ statusBadge(post.status).label }}
            </UiBadge>
            <Pin v-if="post.is_pinned" class="w-4 h-4 text-yellow-500 shrink-0" />
            <div class="flex-1 min-w-0">
              <NuxtLink :to="localePath(`/org/${estSlug}/blog/${post.slug}`)" class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary truncate block">
                {{ post.title }}
              </NuxtLink>
              <div class="text-xs text-neutral-500 mt-0.5">
                {{ post.author_display_name || post.author_hna }}
                <span v-if="post.published_at"> &middot; {{ new Date(post.published_at).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) }}</span>
              </div>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <NuxtLink :to="localePath(`/blog/create?edit=${post.id}`)" class="p-2 rounded text-neutral-500 hover:text-secondary hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Pencil class="w-4 h-4" />
              </NuxtLink>
              <button @click="deleteTarget = post" class="p-2 rounded text-neutral-500 hover:text-red-500 hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <UiConfirmModal
          v-if="deleteTarget"
          :model-value="true"
          :title="t('cms.deletePost')"
          :message="t('cms.deletePostConfirm')"
          :icon="Trash2"
          variant="error"
          :confirm-label="t('cms.deletePost')"
          :loading="deleting"
          @confirm="deletePost"
          @update:model-value="deleteTarget = null"
        />
      </div>

      <!-- ═══ QUEUE TAB ═══ -->
      <div v-else-if="activeTab === 'queue'">
        <div v-if="queueLoading" class="flex justify-center py-12">
          <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" />
        </div>

        <div v-else-if="queueGroups.length === 0" class="text-center py-12">
          <ListOrdered class="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
          <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.noPosts') }}</p>
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="group in queueGroups"
            :key="group.order"
            class="border rounded-lg p-4 flex items-center gap-4"
            :class="[
              group.allPublished
                ? 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10'
                : group.order === nextUnpublished
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                  : 'border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800'
            ]"
          >
            <!-- Order number -->
            <span
              class="text-lg font-bold w-8 text-center shrink-0"
              :class="group.allPublished ? 'text-green-500' : 'text-neutral-400'"
            >
              {{ group.order }}
            </span>

            <!-- Posts -->
            <div class="flex-1 min-w-0 space-y-1">
              <div v-for="post in group.posts" :key="post.id" class="flex items-center gap-2">
                <UiBadge :variant="post.language === 'pt' ? 'info' : 'default'" type="soft" size="sm">
                  {{ post.language.toUpperCase() }}
                </UiBadge>
                <NuxtLink
                  :to="localePath(`/blog/create?edit=${post.id}`)"
                  class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary truncate"
                >
                  {{ post.title }}
                </NuxtLink>
              </div>
            </div>

            <!-- Suggested date -->
            <div class="text-xs text-neutral-500 shrink-0 hidden sm:flex items-center gap-1">
              <Clock class="w-3 h-3" />
              {{ suggestedDate(group.order) }}
            </div>

            <!-- Action -->
            <div class="shrink-0">
              <CheckCircle2 v-if="group.allPublished" class="w-5 h-5 text-green-500" />
              <UiButton
                v-else
                variant="primary"
                size="sm"
                :icon="Send"
                :loading="publishingId === String(group.order)"
                :disabled="group.order !== nextUnpublished"
                @click="publishTopic(group.order)"
              >
                {{ t('cms.manage.publishTopic') }}
              </UiButton>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ PAGES TAB ═══ -->
      <div v-else-if="activeTab === 'pages'">
        <div class="flex justify-between items-center mb-4">
          <span />
          <UiButton variant="primary" size="sm" :icon="Plus" @click="startEditPage()">
            {{ t('cms.manage.newPage') }}
          </UiButton>
        </div>

        <!-- Page editor inline -->
        <div v-if="editingPage" class="card p-4 mb-6 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">
            {{ editingPage.id ? t('cms.manage.editPage') : t('cms.manage.createPage') }}
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.title') }}</label>
              <input v-model="pageForm.title" type="text" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">Slug</label>
              <input v-model="pageForm.slug" type="text" class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent" placeholder="auto-generated" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.content') }}</label>
            <BlogEditor v-model="pageForm.content" :post-id="editingPage?.id || ''" />
          </div>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input type="checkbox" v-model="pageForm.show_in_nav" class="rounded" />
              {{ t('cms.manage.showInNav') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <input type="checkbox" v-model="pageForm.is_published" class="rounded" />
              {{ t('cms.published') }}
            </label>
            <div class="flex items-center gap-2">
              <label class="text-sm text-neutral-700 dark:text-neutral-300">{{ t('cms.manage.order') }}:</label>
              <input v-model.number="pageForm.order" type="number" min="0" class="w-20 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-2 py-1 text-sm" />
            </div>
          </div>
          <div class="flex gap-2">
            <UiButton variant="primary" :loading="pageSaving" @click="savePage">{{ t('common.save') }}</UiButton>
            <UiButton variant="ghost" @click="editingPage = null">{{ t('common.cancel') }}</UiButton>
          </div>
        </div>

        <div v-if="pagesLoading" class="flex justify-center py-8">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900" />
        </div>

        <div v-else-if="sitePages.length === 0 && !editingPage" class="text-center py-12">
          <img src="/images/para/focused.png" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.manage.noPagesYet') }}</h3>
          <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.manage.noPagesDesc') }}</p>
        </div>

        <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
          <div
            v-for="page in sitePages"
            :key="page.id"
            class="flex items-center gap-4 p-4 bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            <span class="text-xs text-neutral-400 w-6 text-center shrink-0">{{ page.order }}</span>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ page.title }}</span>
              <span class="text-xs text-neutral-500 ml-2">/{{ page.slug }}</span>
            </div>
            <UiBadge v-if="page.show_in_nav" variant="info" type="soft" size="sm">nav</UiBadge>
            <UiBadge v-if="!page.is_published" variant="default" type="soft" size="sm">{{ t('cms.draft') }}</UiBadge>
            <div class="flex items-center gap-1 shrink-0">
              <button @click="startEditPage(page)" class="p-2 rounded text-neutral-500 hover:text-secondary hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Pencil class="w-4 h-4" />
              </button>
              <button @click="deletePageTarget = page" class="p-2 rounded text-neutral-500 hover:text-red-500 hover:bg-neutral-100 dark:hover:bg-neutral-700">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <UiConfirmModal
          v-if="deletePageTarget"
          :model-value="true"
          :title="t('cms.manage.deletePage')"
          :message="t('cms.manage.deletePageConfirm')"
          :icon="Trash2"
          variant="error"
          :confirm-label="t('cms.manage.deletePage')"
          :loading="deletingPage"
          @confirm="deletePage"
          @update:model-value="deletePageTarget = null"
        />
      </div>

      <!-- ═══ SETTINGS TAB ═══ -->
      <div v-else-if="activeTab === 'settings'" class="space-y-6">
        <div class="card p-4 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Palette class="w-5 h-5" />
            {{ t('cms.site.branding') }}
          </h3>

          <!-- Accent color -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.accentColor') }}</label>
            <div class="flex items-center gap-3">
              <input v-model="siteForm.accent_color" type="color" class="w-10 h-10 rounded border border-neutral-300 dark:border-neutral-600 cursor-pointer" />
              <input v-model="siteForm.accent_color" type="text" maxlength="7" class="w-28 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm font-mono" />
            </div>
          </div>

          <!-- Hero text -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.heroText') }}</label>
            <textarea
              v-model="siteForm.hero_text"
              rows="3"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
              placeholder="Welcome to our community..."
            />
          </div>

          <!-- Subdomain info -->
          <div v-if="estSlug" class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('cms.site.subdomain') }}: <a :href="`https://${estSlug}.org.parahub.io`" target="_blank" rel="noopener" class="text-link"><code class="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs">{{ estSlug }}.org.parahub.io</code></a>
          </div>

          <UiButton variant="primary" :loading="siteSaving" @click="saveSite">
            {{ t('common.save') }}
          </UiButton>
        </div>

        <!-- Videos -->
        <div v-if="estId" class="card p-4 space-y-3">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Video class="w-5 h-5" />
            {{ t('videos.upload.button') }}
          </h3>
          <ObjectVideos :object-id="estId" />
          <VideoUpload :object-id="estId" />
        </div>

        <!-- Custom domain -->
        <div class="card p-4 space-y-4">
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <Globe class="w-5 h-5" />
            {{ t('cms.site.customDomain') }}
          </h3>

          <p class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('cms.site.domainDesc') }}
          </p>

          <div class="flex items-end gap-3">
            <div class="flex-1">
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.site.domain') }}</label>
              <input
                v-model="domainForm.domain"
                type="text"
                placeholder="my-org.pt"
                class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <UiButton variant="outline" size="sm" :loading="domainSaving" @click="setDomain" class="shrink-0">
              {{ siteData?.custom_domain ? t('cms.site.updateDomain') : t('cms.site.setDomain') }}
            </UiButton>
          </div>

          <!-- Status -->
          <div v-if="siteData?.custom_domain" class="space-y-2">
            <div class="flex items-center gap-2 text-sm">
              <span class="text-neutral-700 dark:text-neutral-300">{{ siteData.custom_domain }}</span>
              <UiBadge v-if="siteData.custom_domain_verified && siteData.custom_domain_ssl_ready" variant="success" type="soft" size="sm">{{ t('cms.site.domainLive') }}</UiBadge>
              <UiBadge v-else-if="siteData.custom_domain_verified" variant="warning" type="soft" size="sm">{{ t('cms.site.sslPending') }}</UiBadge>
              <UiBadge v-else variant="default" type="soft" size="sm">{{ t('cms.site.notVerified') }}</UiBadge>
            </div>

            <div class="flex gap-2">
              <UiButton v-if="!siteData.custom_domain_verified" variant="primary" size="sm" :loading="domainVerifying" @click="verifyDomain">
                {{ t('cms.site.verifyCname') }}
              </UiButton>
              <UiButton variant="ghost" size="sm" @click="removeDomain">
                {{ t('cms.site.removeDomain') }}
              </UiButton>
            </div>

            <p v-if="domainMessage" class="text-sm" :class="siteData.custom_domain_verified ? 'text-green-600 dark:text-green-400' : 'text-neutral-500'">
              {{ domainMessage }}
            </p>
          </div>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>
