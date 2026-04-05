<script setup lang="ts">
import {
  ArrowLeft, Upload, X, FileText, Download, Trash2, Video, Tag
} from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'
import { useCategories } from '~/composables/useCategories'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const router = useRouter()
const { t, locale: currentLocale } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const editId = computed(() => String(route.query.edit || ''))
const isEdit = computed(() => !!editId.value)

const translateFromId = computed(() => String(route.query.translate || ''))

// Form state
const form = reactive({
  title: '',
  content: '',
  status: 'draft' as string,
  language: 'en',
  establishment_id: '' as string,
  meta_description: '',
  featured_image_id: '',
  is_pinned: false,
  allow_comments: true,
  allow_tips: true,
  tag_ids: [] as string[],
  translation_of_id: '' as string,
})

// Translation search
const translationSearch = ref('')
const translationResults = ref<any[]>([])
const selectedOriginal = ref<any>(null)
const searchingTranslation = ref(false)

const saving = ref(false)
const postFiles = ref<any[]>([])
const uploading = ref(false)

// Load postable establishments for "Post as"
const establishments = ref<any[]>([])

// Tags (categories)
const { fetchRootCategories } = useCategories()
const availableTags = ref<any[]>([])
const tagSearch = ref('')
const filteredTags = computed(() => {
  if (!tagSearch.value.trim()) return availableTags.value
  const q = tagSearch.value.toLowerCase()
  return availableTags.value.filter(t => t.name.toLowerCase().includes(q))
})

function toggleTag(tag: any) {
  const idx = form.tag_ids.indexOf(tag.id)
  if (idx >= 0) {
    form.tag_ids.splice(idx, 1)
  } else {
    form.tag_ids.push(tag.id)
  }
}

function getTagById(id: string) {
  return availableTags.value.find(t => t.id === id)
}

onMounted(async () => {
  if (authStore.isAuthenticated) {
    await authStore.ensureToken()
    try {
      const res = await $fetch<any[]>('/api/v1/geo/establishments/my-postable/', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      establishments.value = res
    } catch { /* ignore */ }
  }

  // Load root categories for tag selection
  try {
    const roots = await fetchRootCategories()
    availableTags.value = roots.map((c: any) => ({ id: c.id, name: c.name, slug: c.slug, icon: c.icon }))
  } catch { /* ignore */ }

  // Load existing post if editing
  if (editId.value) {
    try {
      const post = await $fetch<any>(`/api/v1/cms/posts/${editId.value}/`, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      form.title = post.title
      form.content = post.content
      form.status = post.status
      form.language = post.language
      form.establishment_id = post.establishment_id || ''
      form.meta_description = post.meta_description || ''
      form.featured_image_id = post.featured_image_id || ''
      form.is_pinned = post.is_pinned
      form.allow_comments = post.allow_comments
      form.allow_tips = post.allow_tips
      form.tag_ids = (post.tags || []).map((t: any) => t.id)
      form.translation_of_id = post.translation_of_id || ''
      postFiles.value = post.files || []

      // Load the original post info if this is a translation
      if (post.translation_of_id) {
        try {
          const orig = await $fetch<any>(`/api/v1/cms/posts/${post.translation_of_id}/`, {
            credentials: 'include',
            headers: { Authorization: `Bearer ${authStore.token}` },
          })
          selectedOriginal.value = orig
        } catch { /* ignore */ }
      }
    } catch (e: any) {
      toast.error('Failed to load post')
    }
  }

  // Handle ?translate=POST_ID — pre-fill translation_of and copy settings
  if (translateFromId.value && !editId.value) {
    try {
      const orig = await $fetch<any>(`/api/v1/cms/posts/${translateFromId.value}/`, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      form.translation_of_id = orig.translation_of_id || orig.id  // point to the root original
      form.establishment_id = orig.establishment_id || ''
      form.is_pinned = orig.is_pinned
      form.allow_comments = orig.allow_comments
      form.allow_tips = orig.allow_tips
      form.tag_ids = (orig.tags || []).map((t: any) => t.id)
      selectedOriginal.value = orig.translation_of_id ? { id: orig.translation_of_id, title: '...' } : orig

      // Load the actual original if we pointed to a parent
      if (orig.translation_of_id) {
        try {
          const root = await $fetch<any>(`/api/v1/cms/posts/${orig.translation_of_id}/`)
          selectedOriginal.value = root
        } catch { /* ignore */ }
      }
    } catch { /* ignore */ }
  }

  // Default language: auto-select unused language in translate flow, otherwise use locale
  if (!editId.value) {
    if (translateFromId.value && selectedOriginal.value) {
      // Collect languages already used by the original + its translations
      const orig = selectedOriginal.value
      const usedLangs = new Set<string>([orig.language])
      if (orig.translations) {
        for (const tr of orig.translations) {
          usedLangs.add(tr.language)
        }
      }
      // Pick the first available language not already used
      const available = languages.find(l => !usedLangs.has(l.code))
      form.language = available ? available.code : currentLocale.value
    } else {
      form.language = currentLocale.value
    }
  }
})

async function save(targetStatus?: string) {
  if (!form.title.trim()) {
    toast.error('Title is required')
    return
  }

  saving.value = true
  try {
    await authStore.ensureToken()
    const body = {
      ...form,
      status: targetStatus || form.status,
      establishment_id: form.establishment_id || null,
      translation_of_id: form.translation_of_id || null,
    }

    let post: any
    if (isEdit.value) {
      post = await $fetch<any>(`/api/v1/cms/posts/${editId.value}/`, {
        method: 'PATCH',
        body,
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    } else {
      post = await $fetch<any>('/api/v1/cms/posts/', {
        method: 'POST',
        body,
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
    }

    toast.success(targetStatus === 'published' ? t('cms.postPublished') : t('cms.postSaved'))

    if (post.status === 'published') {
      if (post.establishment_slug) {
        router.push(localePath(`/org/${post.establishment_slug}/blog/${post.slug}`))
      } else {
        router.push(localePath(`/blog/${post.slug}`))
      }
    } else if (!isEdit.value) {
      // Redirect to edit mode after first save
      router.replace({ query: { edit: post.id } })
    }
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to save post')
  } finally {
    saving.value = false
  }
}

async function uploadFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !editId.value) return

  uploading.value = true
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('file', file)

    const res = await $fetch<any>(`/api/v1/cms/posts/${editId.value}/files/`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    postFiles.value.push(res)
    toast.success(t('cms.files.uploaded'))
  } catch (e: any) {
    toast.error(e.data?.message || 'Failed to upload file')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function deleteFile(fileId: string) {
  if (!editId.value) return
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/cms/posts/${editId.value}/files/${fileId}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    postFiles.value = postFiles.value.filter(f => f.id !== fileId)
    toast.success(t('cms.files.deleted'))
  } catch {
    toast.error('Failed to delete file')
  }
}

const languages = [
  { code: 'en', name: 'English' },
  { code: 'pt', name: 'Português' },
  { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'ru', name: 'Русский' },
]

// Translation search with debounce
let searchTimeout: ReturnType<typeof setTimeout>
watch(translationSearch, (q) => {
  clearTimeout(searchTimeout)
  if (!q.trim() || q.length < 2) {
    translationResults.value = []
    return
  }
  searchTimeout = setTimeout(() => searchOriginalPosts(q), 300)
})

async function searchOriginalPosts(q: string) {
  searchingTranslation.value = true
  try {
    const res = await $fetch<{ items: any[] }>('/api/v1/cms/posts/', {
      params: { page_size: 20, search: q },
    })
    // Also filter client-side for exact substring match
    const needle = q.toLowerCase()
    translationResults.value = res.items
      .filter((p: any) => p.title.toLowerCase().includes(needle) && p.id !== editId.value)
  } catch { /* ignore */ }
  searchingTranslation.value = false
}

function selectOriginal(post: any) {
  selectedOriginal.value = post
  form.translation_of_id = post.id
  translationSearch.value = ''
  translationResults.value = []
}

function clearOriginal() {
  selectedOriginal.value = null
  form.translation_of_id = ''
}

function onVideoUploaded(data: { peertube_uuid: string; title: string }) {
  // Insert ::video[uuid] at the end of content
  const tag = `\n\n::video[${data.peertube_uuid}]\n`
  form.content = form.content.trimEnd() + tag
}

useHead({ title: isEdit.value ? t('cms.editPost') : t('cms.createPost') })
</script>

<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Back -->
      <NuxtLink :to="localePath('/blog')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-secondary mb-4">
        <ArrowLeft class="w-4 h-4" />
        {{ t('cms.blog') }}
      </NuxtLink>

      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
        {{ isEdit ? t('cms.editPost') : t('cms.createPost') }}
      </h1>

      <!-- Form -->
      <div class="space-y-6">
        <!-- Post as -->
        <div v-if="establishments.length > 0">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ t('cms.postAs') }}
          </label>
          <select
            v-model="form.establishment_id"
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
          >
            <option value="">{{ t('cms.personal') }}</option>
            <option v-for="est in establishments" :key="est.id" :value="est.id">
              {{ est.name }}
            </option>
          </select>
        </div>

        <!-- Title -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ t('cms.title') }}
          </label>
          <input
            v-model="form.title"
            type="text"
            :placeholder="t('cms.titlePlaceholder')"
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-lg font-semibold focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>

        <!-- Content editor -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ t('cms.content') }}
          </label>
          <BlogEditor v-model="form.content" :post-id="editId" />
        </div>

        <!-- Settings row -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <!-- Language -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ t('cms.language') }}
            </label>
            <select
              v-model="form.language"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
            >
              <option v-for="lang in languages" :key="lang.code" :value="lang.code">
                {{ lang.name }}
              </option>
            </select>
          </div>

          <!-- Meta description -->
          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ t('cms.metaDescription') }}
            </label>
            <input
              v-model="form.meta_description"
              type="text"
              :placeholder="t('cms.metaDescriptionPlaceholder')"
              maxlength="300"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
        </div>

        <!-- Tags -->
        <div v-if="availableTags.length > 0">
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            <Tag class="w-4 h-4 inline -mt-0.5" />
            {{ t('cms.tags') }}
          </label>
          <!-- Selected tags -->
          <div v-if="form.tag_ids.length > 0" class="flex flex-wrap gap-1.5 mb-2">
            <span
              v-for="tagId in form.tag_ids"
              :key="tagId"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-100 dark:bg-primary-900/40 text-sm text-neutral-800 dark:text-neutral-200"
            >
              <span v-if="getTagById(tagId)?.icon" class="text-xs">{{ getTagById(tagId)?.icon }}</span>
              {{ getTagById(tagId)?.name || tagId }}
              <button type="button" @click="toggleTag({ id: tagId })" class="p-0.5 hover:text-red-500">
                <X class="w-3 h-3" />
              </button>
            </span>
          </div>
          <!-- Tag search + list -->
          <input
            v-model="tagSearch"
            type="text"
            :placeholder="t('cms.selectTags')"
            class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent mb-2"
          />
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="tag in filteredTags"
              :key="tag.id"
              type="button"
              @click="toggleTag(tag)"
              :class="[
                'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm border transition-colors',
                form.tag_ids.includes(tag.id)
                  ? 'border-primary bg-primary-100 dark:bg-primary-900/40 text-neutral-900 dark:text-neutral-100'
                  : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-primary hover:bg-primary-100/50 dark:hover:bg-primary-900/20',
              ]"
            >
              <span v-if="tag.icon" class="text-xs">{{ tag.icon }}</span>
              {{ tag.name }}
            </button>
          </div>
        </div>

        <!-- Translation of -->
        <div>
          <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
            {{ t('cms.translationOf') }}
          </label>
          <div v-if="selectedOriginal" class="flex items-center gap-2 p-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800">
            <span class="text-xs font-medium uppercase text-neutral-400">{{ selectedOriginal.language }}</span>
            <span class="text-sm text-neutral-900 dark:text-neutral-100 flex-1 truncate">{{ selectedOriginal.title }}</span>
            <button @click="clearOriginal" class="p-1 text-neutral-400 hover:text-red-500">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div v-else class="relative">
            <input
              v-model="translationSearch"
              type="text"
              :placeholder="t('cms.translationOfPlaceholder')"
              class="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
            />
            <div v-if="translationResults.length > 0" class="absolute z-10 mt-1 w-full bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg max-h-48 overflow-auto">
              <button
                v-for="post in translationResults"
                :key="post.id"
                @click="selectOriginal(post)"
                class="w-full text-left px-3 py-2 text-sm hover:bg-primary-100 dark:hover:bg-primary-900/40 flex items-center gap-2"
              >
                <span class="text-xs font-medium uppercase text-neutral-400 shrink-0">{{ post.language }}</span>
                <span class="truncate">{{ post.title }}</span>
              </button>
            </div>
            <p class="text-xs text-neutral-400 mt-1">{{ t('cms.translationOfNone') }}</p>
          </div>
        </div>

        <!-- Toggles -->
        <div class="flex flex-wrap gap-4">
          <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input type="checkbox" v-model="form.allow_comments" class="rounded" />
            {{ t('cms.allowComments') }}
          </label>
          <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input type="checkbox" v-model="form.allow_tips" class="rounded" />
            {{ t('cms.allowTips') }}
          </label>
          <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input type="checkbox" v-model="form.is_pinned" class="rounded" />
            {{ t('cms.isPinned') }}
          </label>
        </div>

        <!-- Files (only in edit mode) -->
        <div v-if="isEdit" class="card p-4">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
            <FileText class="w-5 h-5" />
            {{ t('cms.files.title') }}
          </h2>

          <!-- File list -->
          <div v-if="postFiles.length > 0" class="space-y-2 mb-3">
            <div
              v-for="file in postFiles"
              :key="file.id"
              class="flex items-center justify-between p-2 rounded border border-neutral-200 dark:border-neutral-700"
            >
              <div class="flex items-center gap-2 min-w-0">
                <FileText class="w-4 h-4 text-neutral-500 shrink-0" />
                <a :href="file.url" target="_blank" class="text-sm text-link truncate">{{ file.filename }}</a>
                <span class="text-xs text-neutral-400">{{ Math.round(file.size_bytes / 1024) }} KB</span>
              </div>
              <button @click="deleteFile(file.id)" class="p-1 text-neutral-400 hover:text-red-500">
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Upload -->
          <label class="btn-outline btn-sm cursor-pointer inline-flex items-center gap-2">
            <Upload class="w-4 h-4" />
            {{ uploading ? '...' : t('cms.files.upload') }}
            <input type="file" class="hidden" @change="uploadFile" :disabled="uploading" />
          </label>
          <p class="text-xs text-neutral-400 mt-1">{{ t('cms.files.maxSize') }}</p>
        </div>

        <!-- Photos (only in edit mode) -->
        <BlogPostPhotos v-if="isEdit" :post-id="editId" :editable="true" />

        <!-- Video upload (needs post ID for ObjectVideo) -->
        <div class="card p-4">
          <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
            <Video class="w-5 h-5" />
            {{ t('videos.upload.button') }}
          </h2>
          <template v-if="isEdit">
            <p class="text-xs text-neutral-400 mb-3">{{ t('cms.videoUploadHint') }}</p>
            <VideoUpload :object-id="editId" @uploaded="onVideoUploaded" />
          </template>
          <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">
            {{ t('cms.editor.saveFirstForVideo') }}
          </p>
        </div>

        <!-- Actions -->
        <div class="flex gap-3 pt-2">
          <UiButton
            variant="outline"
            :loading="saving"
            @click="save('draft')"
            class="flex-1"
          >
            {{ t('cms.saveDraft') }}
          </UiButton>
          <UiButton
            variant="primary"
            :loading="saving"
            @click="save('published')"
            class="flex-1"
          >
            {{ t('cms.publish') }}
          </UiButton>
        </div>
      </div>
    </div>
  </div>
</template>
