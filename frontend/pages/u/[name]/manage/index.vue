<script setup lang="ts">
import {
  Newspaper, Pencil, Trash2, Plus, Pin, ArrowLeft,
  Palette, Globe, ExternalLink,
  ChevronUp, ChevronDown, LayoutGrid
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
const activeTab = useTabSync(['posts', 'pages', 'settings'])
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
    const res = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { author_name: profileName.value, status: 'all', page_size: 100 },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    posts.value = res.items
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

// ── Shared (Pages, Site, Nav Sections, Domain) ──
const apiPrefix = computed(() => `by-profile/${profileName.value}`)
const site = useSiteManage(apiPrefix)

// ── Init ──
onMounted(async () => {
  await fetchPosts()
  await Promise.all([site.fetchPages(), site.fetchSite()])
})

useHead({ title: computed(() => `${t('cms.manage.title')} — ${profileName.value}`) })
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
            <img src="/images/para/reading.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
            <h3 class="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">{{ t('cms.noPosts') }}</h3>
            <p class="text-neutral-500 dark:text-neutral-400">{{ t('cms.noPostsDesc') }}</p>
          </div>

          <div v-else class="border rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
            <div
              v-for="post in posts"
              :key="post.id"
              class="flex items-center gap-4 p-4 bg-white dark:bg-neutral-800 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
            >
              <UiBadge :variant="site.statusBadge(post.status).variant" type="soft" size="sm" class="shrink-0">
                {{ site.statusBadge(post.status).label }}
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
                <NuxtLink :to="{ path: localePath('/blog/create'), query: { edit: post.id, back: localePath(`/u/${profileName}/manage`) } }" class="p-2 rounded text-neutral-500 hover:text-secondary hover:bg-neutral-100 dark:hover:bg-neutral-700">
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

        <!-- SETTINGS TAB -->
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
              <div class="flex items-center gap-2 text-sm">
                <UiBadge variant="default" type="soft" size="sm">{{ t('cms.site.subdomain') }}</UiBadge>
                <a :href="`https://${profileName}.u.parahub.io`" target="_blank" rel="noopener" class="text-link"><code class="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-xs">{{ profileName }}.u.parahub.io</code></a>
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
                    placeholder="my-name.com"
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
                placeholder="Welcome to my site..."
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

        </div>
      </template>
    </div>
  </div>
</template>
