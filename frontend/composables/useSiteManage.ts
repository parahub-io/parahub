/**
 * Shared logic for CMS manage panels (org + profile).
 *
 * Parameterised by `apiPrefix` which resolves to either:
 *   - `by-establishment/{id}`   (org manage)
 *   - `by-profile/{name}`      (profile manage)
 */

const SECTION_TYPES = ['blog', 'gallery', 'items', 'contact'] as const
type SectionType = typeof SECTION_TYPES[number]

const SECTION_LABEL_KEY: Record<SectionType, string> = {
  blog: 'cms.site.sectionBlog',
  gallery: 'cms.site.sectionGallery',
  items: 'cms.site.sectionItems',
  contact: 'cms.site.sectionContact',
}

export function useSiteManage(apiPrefix: Ref<string> | ComputedRef<string>) {
  const authStore = useAuthStore()
  const toast = useToastStore()
  const { t } = useI18n()

  // ── Pages ──
  const sitePages = ref<any[]>([])
  const pagesLoading = ref(false)
  const editingPage = ref<any>(null)
  const pageForm = reactive({
    title: '', slug: '', content: '', order: 0,
    show_in_nav: true, is_published: true, is_homepage: false,
  })
  const pageSaving = ref(false)
  const deletePageTarget = ref<any>(null)
  const deletingPage = ref(false)

  async function fetchPages() {
    if (!apiPrefix.value) return
    pagesLoading.value = true
    try {
      await authStore.ensureToken()
      sitePages.value = await $fetch<any[]>(`/api/v1/cms/sites/${apiPrefix.value}/pages/`, {
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
      pageForm.is_homepage = page.is_homepage || false
    } else {
      editingPage.value = { id: null }
      pageForm.title = ''
      pageForm.slug = ''
      pageForm.content = ''
      pageForm.order = sitePages.value.length
      pageForm.show_in_nav = true
      pageForm.is_published = true
      pageForm.is_homepage = false
    }
  }

  async function savePage() {
    if (!apiPrefix.value || !pageForm.title.trim()) return
    pageSaving.value = true
    try {
      await authStore.ensureToken()
      const headers = { Authorization: `Bearer ${authStore.token}` }
      if (editingPage.value?.id) {
        await $fetch(`/api/v1/cms/sites/${apiPrefix.value}/pages/${editingPage.value.id}/`, {
          method: 'PATCH', body: { ...pageForm }, credentials: 'include', headers,
        })
      } else {
        await $fetch(`/api/v1/cms/sites/${apiPrefix.value}/pages/`, {
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
    if (!deletePageTarget.value || !apiPrefix.value) return
    deletingPage.value = true
    try {
      await authStore.ensureToken()
      await $fetch(`/api/v1/cms/sites/${apiPrefix.value}/pages/${deletePageTarget.value.id}/`, {
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
  const siteForm = reactive({
    accent_color: '#F5C518', hero_text: '', hero_image_id: '',
    nav_sections: [] as { type: string; order: number }[],
  })
  const siteSaving = ref(false)

  async function fetchSite() {
    if (!apiPrefix.value) return
    try {
      await authStore.ensureToken()
      siteData.value = await $fetch<any>(`/api/v1/cms/sites/${apiPrefix.value}/`, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      siteForm.accent_color = siteData.value.accent_color
      siteForm.hero_text = siteData.value.hero_text
      siteForm.hero_image_id = siteData.value.hero_image_id
      siteForm.nav_sections = Array.isArray(siteData.value.nav_sections)
        ? [...siteData.value.nav_sections]
        : []
    } catch { /* ignore */ }
  }

  async function saveSite() {
    if (!apiPrefix.value) return
    siteSaving.value = true
    try {
      await authStore.ensureToken()
      await $fetch(`/api/v1/cms/sites/${apiPrefix.value}/`, {
        method: 'PATCH', body: { ...siteForm },
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      toast.success(t('common.saved'))
    } catch (e: any) {
      toast.error(e.data?.message || 'Failed to save settings')
    }
    siteSaving.value = false
  }

  // ── Nav Sections ──
  function isSectionEnabled(type: SectionType) {
    return siteForm.nav_sections.some(s => s.type === type)
  }

  function toggleSection(type: SectionType) {
    const idx = siteForm.nav_sections.findIndex(s => s.type === type)
    if (idx >= 0) {
      siteForm.nav_sections.splice(idx, 1)
    } else {
      const maxOrder = siteForm.nav_sections.length > 0
        ? Math.max(...siteForm.nav_sections.map(s => s.order))
        : 0
      siteForm.nav_sections.push({ type, order: maxOrder + 1 })
    }
    reindexSections()
  }

  function moveSection(type: SectionType, direction: -1 | 1) {
    const sorted = [...siteForm.nav_sections].sort((a, b) => a.order - b.order)
    const idx = sorted.findIndex(s => s.type === type)
    const swapIdx = idx + direction
    if (swapIdx < 0 || swapIdx >= sorted.length) return
    const tmp = sorted[idx].order
    sorted[idx].order = sorted[swapIdx].order
    sorted[swapIdx].order = tmp
    siteForm.nav_sections = sorted
  }

  function reindexSections() {
    const sorted = [...siteForm.nav_sections].sort((a, b) => a.order - b.order)
    sorted.forEach((s, i) => { s.order = i + 1 })
    siteForm.nav_sections = sorted
  }

  const sortedSections = computed(() =>
    [...siteForm.nav_sections].sort((a, b) => a.order - b.order),
  )

  const disabledSections = computed(() =>
    SECTION_TYPES.filter(t => !isSectionEnabled(t)),
  )

  // ── Custom Domain ──
  const domainForm = reactive({ domain: '' })
  const domainSaving = ref(false)
  const domainVerifying = ref(false)
  const domainMessage = ref('')

  watch(() => siteData.value?.custom_domain, (v) => {
    if (v) domainForm.domain = v
  }, { immediate: true })

  async function setDomain() {
    if (!apiPrefix.value) return
    domainSaving.value = true
    domainMessage.value = ''
    try {
      await authStore.ensureToken()
      const res = await $fetch<any>(`/api/v1/cms/sites/${apiPrefix.value}/domain/`, {
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
    if (!apiPrefix.value) return
    domainVerifying.value = true
    domainMessage.value = ''
    try {
      await authStore.ensureToken()
      const res = await $fetch<any>(`/api/v1/cms/sites/${apiPrefix.value}/domain/verify/`, {
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

  // ── Util ──
  function statusBadge(status: string) {
    if (status === 'published') return { variant: 'success' as const, label: t('cms.published') }
    if (status === 'archived') return { variant: 'default' as const, label: t('cms.archived') }
    return { variant: 'warning' as const, label: t('cms.draft') }
  }

  return {
    // Pages
    sitePages, pagesLoading, editingPage, pageForm, pageSaving,
    deletePageTarget, deletingPage,
    fetchPages, startEditPage, savePage, deletePage,
    // Site
    siteData, siteForm, siteSaving,
    fetchSite, saveSite,
    // Nav sections
    SECTION_TYPES, SECTION_LABEL_KEY,
    isSectionEnabled, toggleSection, moveSection,
    sortedSections, disabledSections,
    // Domain
    domainForm, domainSaving, domainVerifying, domainMessage,
    setDomain, verifyDomain, removeDomain,
    // Util
    statusBadge,
  }
}
