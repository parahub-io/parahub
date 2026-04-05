<script setup lang="ts">
import {
  Newspaper, Pencil, Trash2, Plus, Pin, ArrowLeft,
  Palette, Globe, ExternalLink
} from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const { t, locale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const profileName = computed(() => String(route.params.name))

// Guard: only the owner can access
const isOwner = computed(() => authStore.user?.profile?.local_name === profileName.value)

// Tabs
const activeTab = ref('posts')
const tabs = computed(() => [
  { id: 'posts', label: t('cms.manage.posts') },
  { id: 'pages', label: t('cms.manage.pages') },
  { id: 'settings', label: t('cms.manage.settings') },
])

// ── Posts ──
const loading = ref(true)
const posts = ref<any[]>([])
const deleteTarget = ref<any>(null)
const deleting = ref(false)

async function fetchPosts() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const headers = { Authorization: `Bearer ${authStore.token}` }
    const opts = { credentials: 'include' as const, headers }

    const drafts = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { author_name: profileName.value, status: 'draft', page_size: 100 },
      ...opts,
    })
    const published = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { author_name: profileName.value, page_size: 100 },
      ...opts,
    })
    const archived = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { author_name: profileName.value, status: 'archived', page_size: 100 },
      ...opts,
    })

    const all = [...drafts.items, ...published.items, ...archived.items]
    const seen = new Set<string>()
    posts.value = all.filter(p => {
      if (seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })
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

// ── Pages ──
const sitePages = ref<any[]>([])
const pagesLoading = ref(false)
const editingPage = ref<any>(null)
const pageForm = reactive({ title: '', slug: '', content: '', order: 0, show_in_nav: true, is_published: true })
const pageSaving = ref(false)
const deletePageTarget = ref<any>(null)
const deletingPage = ref(false)

async function fetchPages() {
  pagesLoading.value = true
  try {
    await authStore.ensureToken()
    sitePages.value = await $fetch<any[]>(`/api/v1/cms/sites/by-profile/${profileName.value}/pages/`, {
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
  if (!pageForm.title.trim()) return
  pageSaving.value = true
  try {
    await authStore.ensureToken()
    const headers = { Authorization: `Bearer ${authStore.token}` }

    if (editingPage.value?.id) {
      await $fetch(`/api/v1/cms/sites/by-profile/${profileName.value}/pages/${editingPage.value.id}/`, {
        method: 'PATCH', body: { ...pageForm }, credentials: 'include', headers,
      })
    } else {
      await $fetch(`/api/v1/cms/sites/by-profile/${profileName.value}/pages/`, {
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
  if (!deletePageTarget.value) return
  deletingPage.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/sites/by-profile/${profileName.value}/pages/${deletePageTarget.value.id}/`, {
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
  try {
    await authStore.ensureToken()
    siteData.value = await $fetch<any>(`/api/v1/cms/sites/by-profile/${profileName.value}/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    siteForm.accent_color = siteData.value.accent_color
    siteForm.hero_text = siteData.value.hero_text
    siteForm.hero_image_id = siteData.value.hero_image_id
  } catch { /* ignore */ }
}

async function saveSite() {
  siteSaving.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/sites/by-profile/${profileName.value}/`, {
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
  domainSaving.value = true
  domainMessage.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/cms/sites/by-profile/${profileName.value}/domain/`, {
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
  domainVerifying.value = true
  domainMessage.value = ''
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/cms/sites/by-profile/${profileName.value}/domain/verify/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    domainMessage.value = res.message
    await fetchSite()
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
  await fetchPosts()
  await Promise.all([fetchPages(), fetchSite()])
})

useHead({ title: computed(() => `${t('cms.manage.title')} — ${profileName.value}`) })

function statusBadge(status: string) {
  if (status === 'published') return { variant: 'success' as const, label: t('cms.published') }
  if (status === 'archived') return { variant: 'default' as const, label: t('cms.archived') }
  return { variant: 'warning' as const, label: t('cms.draft') }
}
</script>

<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Not owner guard -->
      <div v-if="!isOwner" class="text-center py-12">
        <h2 class="text-xl font-semibold text-neutral-700 dark:text-neutral-300">{{ t('common.accessDenied') }}</h2>
      </div>

      <template v-else>
        <NuxtLink :to="localePath(`/u/${profileName}`)" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
          <ArrowLeft class="w-4 h-4" />
          {{ profileName }}
        </NuxtLink>

        <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ t('cms.manage.title') }}
          </h1>
          <div class="flex items-center gap-3">
            <NuxtLink :to="localePath(`/u/${profileName}/blog`)" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-secondary">
              <Newspaper class="w-4 h-4" />
              {{ t('cms.manage.viewBlog') }}
            </NuxtLink>
            <a :href="`https://${profileName}.u.parahub.io`" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-secondary">
              <ExternalLink class="w-4 h-4" />
              {{ t('cms.manage.viewSite') }}
            </a>
          </div>
        </div>

        <UiTabs v-model="activeTab" :tabs="tabs" class="mb-6" />

        <!-- POSTS TAB -->
        <div v-if="activeTab === 'posts'">
          <div class="flex justify-between items-center mb-4">
            <span />
            <UiButton variant="primary" size="sm" :icon="Plus" :to="localePath('/blog/create')">
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
                <NuxtLink :to="localePath(`/u/${profileName}/blog/${post.slug}`)" class="text-sm font-medium text-neutral-900 dark:text-neutral-100 hover:text-secondary truncate block">
                  {{ post.title }}
                </NuxtLink>
                <div class="text-xs text-neutral-500 mt-0.5">
                  <span v-if="post.published_at">{{ new Date(post.published_at).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) }}</span>
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

        <!-- PAGES TAB -->
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

        <!-- SETTINGS TAB -->
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
                placeholder="Welcome to my site..."
              />
            </div>

            <!-- Subdomain info -->
            <div class="text-sm text-neutral-500 dark:text-neutral-400">
              {{ t('cms.site.subdomain') }}: <a :href="`https://${profileName}.u.parahub.io`" target="_blank" rel="noopener" class="text-link"><code class="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs">{{ profileName }}.u.parahub.io</code></a>
            </div>

            <UiButton variant="primary" :loading="siteSaving" @click="saveSite">
              {{ t('common.save') }}
            </UiButton>
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
                  placeholder="my-name.com"
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
