<script setup lang="ts">
import { ArrowLeft, MessageCircle, FileSignature, Edit, EyeOff, Eye, Trash2, X, ChevronLeft, ChevronRight, Share2, MapPin, LayoutGrid, Maximize2, ShieldCheck, Clock, Handshake, Send, CalendarClock, Hand, Lock, Play } from 'lucide-vue-next'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()
const { fetchCategoryTree } = useCategories()
const { formatPricingOption, pricingTypeLabel, priceAmount, pricingPeriod } = usePricingFormat()

// Category slug -> translated name map
const categoryNames = ref(new Map<string, string>())

const itemId = computed(() => route.params.id as string)

// Pricing block helpers. A listing can carry several pricing options — a sale
// price and/or one or more rent windows (hour / 3hr / half-day / …). Group them
// by offer kind so each kind keeps its own eyebrow (ПРОДАЖА / АРЕНДА). The price
// block is purely informational; the Book CTA lives in the action zone below (see
// `isRental`), so the rates never carry a button.
const pricingOptions = computed<any[]>(() => item.value?.pricing_options || [])

// A rental listing carries at least one `rent` pricing window. For rentals the
// structured booking flow (/rental/[id]) is the PRIMARY action, so the bottom
// action zone leads with a full-width Book CTA instead of "make offer".
const isRental = computed(() => pricingOptions.value.some(o => o.type === 'rent'))
const pricingGroups = computed(() => {
  const order: string[] = []
  const byType = new Map<string, any[]>()
  for (const opt of pricingOptions.value) {
    const key = opt.type || 'other'
    if (!byType.has(key)) { byType.set(key, []); order.push(key) }
    byType.get(key)!.push(opt)
  }
  return order.map(type => ({ type, options: byType.get(type)! }))
})

// Fetch item with SSR support
const { data: item, pending: loading, error: fetchError, refresh: refreshItem } = await useAsyncData(
  `item-${itemId.value}`,
  () => $fetch(`/api/v1/items/${itemId.value}/`)
)
const error = computed(() => {
  if (!fetchError.value) return null
  return (fetchError.value as any).data?.message || 'Item not found'
})

// Videos (PeerTube/ObjectVideo) attached to this listing. Fetched alongside the
// item — during SSR too — so they slot INTO the media gallery (Steam-style: a
// video sits in the thumbnail strip with a play badge and plays in the main
// stage when picked) instead of stacking in a separate block below it.
const { data: videoData, refresh: refreshVideos } = await useAsyncData(
  `item-videos-${itemId.value}`,
  () => {
    const oid = item.value?.id
    return oid && oid.length === 26
      ? $fetch<any[]>('/api/v1/core/videos/', { params: { object_id: oid } })
      : Promise.resolve([])
  },
  { watch: [() => item.value?.id], default: () => [] }
)

// Unified media list: photos and videos share one global `order` (set by the
// owner on the edit page), so the strip/cover follow that exact sequence. Tie on
// `order` → video first: this reproduces the old "videos lead" convention for
// legacy listings never reordered (single video at order 0, photos 0..n).
const mediaItems = computed<any[]>(() => {
  const vids = (videoData.value || []).map((v: any) => ({ kind: 'video', ...v }))
  const imgs = (item.value?.images || []).map((img: any) => ({ kind: 'image', ...img }))
  return [...vids, ...imgs].sort(
    (a, b) => (a.order - b.order) || (a.kind === 'video' ? -1 : 1)
  )
})

const currentMediaIndex = ref(0)
const currentMedia = computed(() => mediaItems.value[currentMediaIndex.value] || null)

// The video whose inline player is loaded in the main stage. Until a video is
// clicked we show its poster + a big play button (lazy: no PeerTube iframe on
// page load). Resets when the user navigates to other media — unmounting the
// iframe and stopping playback.
const playingVideoId = ref<string | null>(null)
// Whether a freshly mounted inline player starts muted. Captured at mount time
// (NOT a live mirror of showcaseActive) so killing the showcase mid-clip never
// flips the embed `muted` param — that would recompute the iframe src and restart
// the video. The ambient showcase mounts videos muted; a manual play unmutes.
const videoMuted = ref(false)
// The reel below drives the gallery on a fresh, untouched visit (declared here so
// the watcher can read it before the engine block).
const showcaseActive = ref(false)
// Navigating to other media unmounts the player and stops playback — EXCEPT while
// the showcase is driving, where the reel sets playingVideoId itself (it must not
// be nulled out from under the muted autoplay it just mounted).
watch(currentMediaIndex, () => { if (!showcaseActive.value) playingVideoId.value = null })

// Keep the selected index valid as the media list changes (videos load in, or
// the owner deletes one). Clamp rather than let currentMedia go undefined.
watch(() => mediaItems.value.length, (len) => {
  if (currentMediaIndex.value >= len) currentMediaIndex.value = Math.max(0, len - 1)
})

// --- Ambient showcase reel ---------------------------------------------------
// On a fresh, untouched visit the gallery plays itself like a storefront display:
// the first video autoplays MUTED, advances to the next clip when it ends, then
// photos cycle (3s each), then the photo loop repeats. ANY deliberate interaction
// (pointer down on the gallery, arrow/dot/thumb nav, play button, fullscreen)
// kills it permanently for the session — the visitor is now inspecting and we must
// not move media out from under them. Guards: never starts under Save-Data or
// prefers-reduced-motion; the photo cadence pauses when the stage scrolls out of
// view (IntersectionObserver) or the page is kept-alive away; the muted video also
// auto-pauses on tab-hide (VideoPlayer's own guard). Looping returns to the first
// PHOTO — we deliberately don't re-download the videos every cycle.
// A single `reelTimer` drives both the photo cadence AND a per-video WATCHDOG: the
// reel does NOT gate on `ObjectVideo.is_published` (that flag can lag behind
// PeerTube — a fully transcoded clip may still read false), so instead every video
// gets a `duration + slack` fallback. `@ended` (PeerTube's authoritative end
// signal) normally advances first; the watchdog only catches a clip that never
// fires it (still transcoding / failed to play), so the reel can never stall.
// Known limit: clicks INSIDE the PeerTube iframe don't bubble out, so they can't
// kill the reel — but pausing the video there just stalls it (no `ended` fires),
// which is the safe outcome.
const PHOTO_MS = 3000
const stageRef = ref<HTMLElement | null>(null)
let reelTimer: ReturnType<typeof setTimeout> | null = null
let stageObserver: IntersectionObserver | null = null
let stageVisible = true
let reelStarted = false
let reelLooping = false   // false = one-time linear pass; true = photos-only loop

function clearReelTimer() {
  if (reelTimer) { clearTimeout(reelTimer); reelTimer = null }
}

function stopShowcase() {
  showcaseActive.value = false
  clearReelTimer()
}

// Move the reel onto media entry `idx`. Video → mount muted autoplay, advance on
// @ended (with a duration-based watchdog as the stall fallback). Image → show it
// and schedule the next hop in PHOTO_MS (only while the stage is on-screen).
function goToShowcaseIndex(idx: number) {
  clearReelTimer()
  const m = mediaItems.value[idx]
  if (!m) { stopShowcase(); return }
  if (m.kind === 'video') {
    videoMuted.value = true
    currentMediaIndex.value = idx
    playingVideoId.value = m.id
    // Watchdog: advance even if @ended never arrives (stuck / unplayable clip).
    const ms = ((Number(m.duration_seconds) || 30) + 8) * 1000
    reelTimer = setTimeout(advanceShowcase, ms)
  } else {
    playingVideoId.value = null
    currentMediaIndex.value = idx
    if (stageVisible) reelTimer = setTimeout(advanceShowcase, PHOTO_MS)
  }
}

// Advance to the next entry. Linear phase: just the next media item in order. Once
// the one-time pass is exhausted, switch to a photos-only loop — videos are never
// re-downloaded. A video-only listing simply stops after its last clip.
function advanceShowcase() {
  if (!showcaseActive.value) return
  const items = mediaItems.value
  const n = items.length
  if (n === 0) { stopShowcase(); return }
  const cur = currentMediaIndex.value

  if (!reelLooping) {
    if (cur + 1 < n) { goToShowcaseIndex(cur + 1); return }
    reelLooping = true   // linear pass done → enter the photo loop
  }

  const imageIdxs = items.reduce((acc: number[], m: any, i: number) => {
    if (m.kind === 'image') acc.push(i)
    return acc
  }, [])
  if (imageIdxs.length === 0) { stopShowcase(); return }
  const pos = imageIdxs.indexOf(cur)          // -1 when arriving from a video
  goToShowcaseIndex(imageIdxs[(pos + 1) % imageIdxs.length])
}

function maybeStartShowcase() {
  if (reelStarted || !import.meta.client) return
  // Respect explicit low-data / reduced-motion preferences.
  if ((navigator as any).connection?.saveData) return
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  const items = mediaItems.value
  const hasVideo = items.some((m: any) => m.kind === 'video')
  const imageCount = items.filter((m: any) => m.kind === 'image').length
  // Worth auto-playing only with a video, or several photos to cycle.
  if (!hasVideo && imageCount < 2) return
  reelStarted = true
  reelLooping = false
  showcaseActive.value = true
  goToShowcaseIndex(0)
}

function setupStageObserver() {
  if (!import.meta.client || !stageRef.value) return
  if (!('IntersectionObserver' in window)) { maybeStartShowcase(); return }
  stageObserver = new IntersectionObserver((entries) => {
    const visible = entries[0]?.isIntersecting ?? false
    stageVisible = visible
    if (visible) {
      if (!reelStarted) maybeStartShowcase()
      // Resume the photo cadence if we scrolled back onto a still photo. (A video's
      // watchdog is left running off-screen — the clip keeps playing muted.)
      else if (showcaseActive.value && !reelTimer && currentMedia.value?.kind === 'image') {
        reelTimer = setTimeout(advanceShowcase, PHOTO_MS)
      }
    } else if (currentMedia.value?.kind === 'image') {
      clearReelTimer()   // pause photo cadence off-screen; keep any video watchdog
    }
  }, { threshold: 0.5 })
  stageObserver.observe(stageRef.value)
}

const isOwner = computed(() => !!item.value && item.value.owner_id === authStore.profile?.id)

const fullscreenImage = ref(false)
const fullscreenIndex = ref(0)
const showDeleteItemConfirm = ref(false)

// Navigate back to market
function goBackToMarket() {
  // Use browser back only when the previous history entry is the market list
  // itself (preserves filters in its query). Otherwise — came from the edit
  // page (/market/create), another listing, or external — go to the list
  // directly. NB: document.referrer is unreliable, it stays empty across
  // in-app SPA navigation; router history state is the accurate signal.
  const back = router.options.history.state.back
  if (typeof back === 'string' && /\/market(\?|$)/.test(back)) {
    router.back()
  } else {
    router.push(localePath('/market'))
  }
}

// Main-stage navigation cycles ALL media (videos + photos). Any of these is a
// deliberate interaction, so it ends the ambient showcase.
function nextMedia() {
  stopShowcase()
  const n = mediaItems.value.length
  if (n > 1) currentMediaIndex.value = (currentMediaIndex.value + 1) % n
}

function previousMedia() {
  stopShowcase()
  const n = mediaItems.value.length
  if (n > 1) currentMediaIndex.value = (currentMediaIndex.value - 1 + n) % n
}

// Thumbnail / dot pick — also ends the showcase, then jumps to that entry.
function selectMedia(idx: number) {
  stopShowcase()
  currentMediaIndex.value = idx
}

// Manual play (poster button) — unmute and end the showcase.
function playCurrentVideo() {
  stopShowcase()
  videoMuted.value = false
  playingVideoId.value = currentMedia.value?.id ?? null
}

// Fullscreen lightbox is photo-only (videos carry their own fullscreen control),
// so it navigates within item.images on its own index, decoupled from the strip.
function openFullscreen() {
  stopShowcase()
  if (currentMedia.value?.kind !== 'image') return
  const imgs = item.value?.images || []
  const idx = imgs.findIndex((im: any) => im.id === currentMedia.value.id)
  fullscreenIndex.value = idx >= 0 ? idx : 0
  fullscreenImage.value = true
}
function nextFullscreenImage() {
  const imgs = item.value?.images || []
  if (imgs.length > 1) fullscreenIndex.value = (fullscreenIndex.value + 1) % imgs.length
}
function previousFullscreenImage() {
  const imgs = item.value?.images || []
  if (imgs.length > 1) fullscreenIndex.value = (fullscreenIndex.value - 1 + imgs.length) % imgs.length
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

// Format price

// Format date
function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString(locale.value, { day: 'numeric', month: 'short', year: 'numeric' })
}

// Contact seller
async function contactSeller() {
  if (!authStore.isAuthenticated) {
    toastStore.warning(t('login_required'))
    return
  }

  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        target_account_id: item.value.owner_account_id,
        item_id: item.value.id,
        item_title: item.value.title
      }
    })

    if (res.room_id) {
      router.push(localePath(`/chat?room_id=${res.room_id}`))
    }
  } catch (e: any) {
    console.error('Failed to create DM:', e)
    toastStore.error(e.data?.message || 'Failed to start chat')
  }
}

// Propose Deal modal
const showProposeDeal = ref(false)
const proposalMessage = ref('')
const proposalSending = ref(false)
const proposalTextarea = ref<HTMLTextAreaElement | null>(null)

// Modal a11y (design-system modal rules): close on Esc + auto-focus the textarea
// on open. Backdrop close is already wired on the overlay.
function onProposeKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') showProposeDeal.value = false
}
watch(showProposeDeal, (open) => {
  if (open) {
    nextTick(() => proposalTextarea.value?.focus())
    window.addEventListener('keydown', onProposeKeydown)
  } else {
    window.removeEventListener('keydown', onProposeKeydown)
  }
})
onBeforeUnmount(() => window.removeEventListener('keydown', onProposeKeydown))

// Fullscreen image lightbox a11y: close on Esc, arrow-key navigation, lock body
// scroll while open. The overlay is Teleport'd to <body> so it escapes the page's
// `relative z-10` stacking context and renders above the fixed navbar (z-50).
function onFullscreenKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') fullscreenImage.value = false
  else if (e.key === 'ArrowLeft') previousFullscreenImage()
  else if (e.key === 'ArrowRight') nextFullscreenImage()
}
watch(fullscreenImage, (open) => {
  if (open) {
    window.addEventListener('keydown', onFullscreenKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    window.removeEventListener('keydown', onFullscreenKeydown)
    document.body.style.overflow = ''
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onFullscreenKeydown)
  document.body.style.overflow = ''
})

function openProposeDeal() {
  if (!authStore.isAuthenticated) {
    toastStore.warning(t('login_required'))
    return
  }
  proposalMessage.value = ''
  showProposeDeal.value = true
}

async function sendProposal() {
  if (!proposalMessage.value.trim()) return
  proposalSending.value = true

  try {
    await authStore.ensureToken()

    // Build a structured deal message
    const pricing = item.value.pricing_options?.[0]
    let dealHeader = `📦 **${item.value.title}**`
    if (pricing) {
      dealHeader += `\n💰 ${formatPricingOption(pricing)}`
    }

    const fullMessage = `${dealHeader}\n\n${proposalMessage.value.trim()}`

    const res = await $fetch<any>('/api/v1/matrix/create-dm', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: {
        target_account_id: item.value.owner_account_id,
        item_id: item.value.id,
        item_title: item.value.title,
        initial_message: fullMessage
      }
    })

    if (res.room_id) {
      toastStore.success(t('market.propose_deal.success'))
      showProposeDeal.value = false
      router.push(localePath(`/chat?room_id=${res.room_id}`))
    }
  } catch (e: any) {
    console.error('Failed to send proposal:', e)
    toastStore.error(e.data?.message || t('market.propose_deal.error'))
  } finally {
    proposalSending.value = false
  }
}

function goToContract() {
  // Rent-priced item → use the rental contract template (role-aware fill in the
  // contracts page maps owner/renter by item ownership). No booking from here;
  // the booking-anchored path is the owner's inbox "Formalize" button.
  const kind = isRental.value ? '&kind=rental' : ''
  router.push(localePath(`/contracts?partner=${item.value.owner_id}&item=${item.value.id}${kind}`))
}

// Owner actions
async function toggleActive() {
  try {
    await authStore.ensureToken()
    const willActivate = !item.value.is_active
    await $fetch(`/api/v1/items/${item.value.id}/${willActivate ? 'activate' : 'deactivate'}/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    // Reassign item.value wholesale: mutating a nested property of useAsyncData
    // data (item.value.is_active = …) does NOT trigger a re-render in the prod
    // build, so the button label stayed stale and the toast read the old value.
    item.value = { ...item.value, is_active: willActivate }
    toastStore.success(willActivate ? t('market.messages.activated') : t('market.messages.deactivated'))
  } catch (e: any) {
    toastStore.error(e.data?.message || 'Failed to update item')
  }
}

async function deleteItem() {
  showDeleteItemConfirm.value = false
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/items/${item.value.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    toastStore.success(t('market.messages.deleted'))
    useState('marketDirty', () => false).value = true
    router.push(localePath('/market'))
  } catch (e: any) {
    toastStore.error(e.data?.message || 'Failed to delete item')
  }
}

function editItem() {
  router.push(localePath(`/market/create?edit=${item.value.slug || item.value.id}`))
}

// Share
async function shareItem() {
  const url = window.location.href
  if (navigator.share) {
    await navigator.share({ title: item.value.title, url })
  } else {
    await navigator.clipboard.writeText(url)
    toastStore.success(t('common.link_copied'))
  }
}

// Build category name lookup from translated tree
function buildCategoryNames(categories: any[]) {
  for (const cat of categories) {
    categoryNames.value.set(cat.slug, cat.name)
    if (cat.children?.length) {
      buildCategoryNames(cat.children)
    }
  }
}

function getCategoryName(slug: string, fallback: string) {
  return categoryNames.value.get(slug) || fallback
}

// Real-time updates
useObjectSubscription(item)

// Init (client-side only)
onMounted(async () => {
  // Load translated category names
  try {
    const tree = await fetchCategoryTree()
    buildCategoryNames(tree)
  } catch (e) {
    // Fallback to English names from API
  }
})

// Kick off the ambient showcase once the gallery DOM is bound. Cleanup covers both
// kept-alive away (onDeactivated → stop the reel) and true unmount/LRU eviction.
onMounted(() => nextTick(setupStageObserver))
onDeactivated(() => stopShowcase())
onBeforeUnmount(() => {
  clearReelTimer()
  stageObserver?.disconnect()
  stageObserver = null
})

// This page is kept-alive (app.vue NuxtPage :keepalive). Returning to it after an
// edit (/market/create saves, then navigates back) reactivates the cached instance
// WITHOUT re-running setup, so useAsyncData never refetches and the page would show
// stale — or, after create.vue cleared the cache, an empty — listing. Refetch on
// every re-activation. Skip the very first activation (it coincides with onMounted's
// initial fetch). The existing data stays visible during the background refresh — the
// template only shows the spinner when there is nothing yet (`loading && !item`) — so
// normal back-navigation updates in place with no flash.
let hasActivated = false
onActivated(() => {
  if (!hasActivated) {
    hasActivated = true
    return
  }
  refreshItem()
  refreshVideos()
})

// SEO - comprehensive meta tags for sharing
useSeoMeta({
  title: () => item.value?.title || t('market.item_detail'),
  ogTitle: () => item.value?.title || t('market.item_detail'),
  description: () => item.value?.description?.slice(0, 160) || t('market.item_detail'),
  ogDescription: () => item.value?.description?.slice(0, 160) || t('market.item_detail'),
  ogImage: () => item.value?.images?.[0]?.url || '/og-image.jpg',
  ogType: 'product',
  twitterCard: 'summary_large_image',
})

// JSON-LD Product structured data
const _baseUrl = useRuntimeConfig().public.siteUrl || 'https://parahub.io'
useHead({
  script: computed(() => {
    if (!item.value) return []
    const baseUrl = _baseUrl
    const pricing = item.value.pricing_options?.[0]
    const jsonLd: Record<string, any> = {
      '@context': 'https://schema.org',
      '@type': 'Product',
      'name': item.value.title,
      'url': `${baseUrl}/market/${item.value.slug || item.value.id}`,
    }
    if (item.value.description) jsonLd.description = item.value.description
    if (item.value.images?.[0]?.url) jsonLd.image = item.value.images[0].url
    if (item.value.owner_hna) {
      jsonLd.seller = { '@type': 'Person', 'name': item.value.owner_hna }
    }
    if (pricing && pricing.amount) {
      jsonLd.offers = {
        '@type': 'Offer',
        'price': pricing.amount,
        'priceCurrency': pricing.currency || 'EUR',
        'availability': item.value.is_active ? 'https://schema.org/InStock' : 'https://schema.org/Discontinued',
      }
    } else if (pricing?.type === 'free') {
      jsonLd.offers = {
        '@type': 'Offer',
        'price': '0',
        'priceCurrency': 'EUR',
        'availability': 'https://schema.org/InStock',
      }
    }
    return [{ type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd) }]
  })
})

// Public page: listings are shareable + SEO-indexed (see useSeoMeta / JSON-LD
// above). No auth middleware — anonymous visitors must be able to view a listing.
// Write actions (contact, propose deal) self-gate with a login prompt; owner
// actions are hidden unless item.owner_id === current profile.
</script>

<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900">
    <!-- Header -->
    <div class="bg-white dark:bg-neutral-800 border-b border-neutral-200 dark:border-neutral-700 sticky top-0 z-10">
      <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
        <button
          @click="goBackToMarket"
          class="flex items-center gap-2 text-neutral-500 hover:text-primary transition-colors"
        >
          <LayoutGrid :size="20" />
          <span class="hidden sm:inline">{{ t('market.back_to_market') }}</span>
          <span class="sm:hidden">{{ t('market.title') }}</span>
        </button>

        <div v-if="item" class="flex items-center gap-1">
          <LikeButton :target-id="item.id" target-type="item" />
          <UiButton variant="ghost" :icon="Share2" icon-only :aria-label="t('common.share')" @click="shareItem" />
        </div>
      </div>
    </div>

    <!-- Loading (only when there's nothing to show yet; a background refresh on
         kept-alive re-entry keeps the existing listing visible) -->
    <div v-if="loading && !item" class="py-12 text-center" role="status" aria-live="polite">
      <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
      <span class="sr-only">{{ t('common.loading') }}</span>
    </div>

    <!-- Error (only when there's no listing to fall back on — a failed background
         refresh must not blow away a listing that's already on screen) -->
    <div v-else-if="error && !item" class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
      <p class="text-error mb-4">{{ error }}</p>
      <NuxtLink :to="localePath('/market')" class="text-link">
        {{ t('market.back_to_market') }}
      </NuxtLink>
    </div>

    <!-- Item Content -->
    <div v-else-if="item" class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div class="card rounded-xl overflow-hidden">
        <!-- Media gallery (Steam-style): videos + photos in one strip. A video
             sits among the thumbnails with a play badge; picking it plays inline
             in the main stage. -->
        <div v-if="mediaItems.length > 0" class="relative" @pointerdown="stopShowcase">
          <!-- Main stage -->
          <div ref="stageRef" class="aspect-video bg-neutral-100 dark:bg-neutral-700 relative">
            <!-- Photo -->
            <template v-if="currentMedia?.kind === 'image'">
              <img
                :src="currentMedia.url"
                :alt="item.title"
                class="w-full h-full object-contain"
              />
              <button
                @click="openFullscreen"
                class="absolute top-3 right-3 p-2 bg-black/50 hover:bg-black/70 text-white rounded-full transition-opacity"
                :title="t('market.zoom_image')"
              >
                <Maximize2 :size="18" />
              </button>
            </template>

            <!-- Video -->
            <template v-else-if="currentMedia?.kind === 'video'">
              <!-- Inline player, mounted only once the user hits play -->
              <div v-if="playingVideoId === currentMedia.id" class="absolute inset-0">
                <VideoPlayer
                  :embed-url="currentMedia.embed_url"
                  :title="currentMedia.title"
                  autoplay
                  :muted="videoMuted"
                  @ended="advanceShowcase"
                />
              </div>
              <!-- Poster + play button (lazy: no iframe until clicked) -->
              <button
                v-else
                type="button"
                class="group absolute inset-0 w-full h-full"
                :aria-label="t('videos.play', 'Play video')"
                @click="playCurrentVideo"
              >
                <img
                  v-if="currentMedia.thumbnail_url"
                  :src="currentMedia.thumbnail_url"
                  :alt="currentMedia.title"
                  class="w-full h-full object-contain"
                />
                <span class="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors">
                  <span class="flex items-center justify-center w-16 h-16 rounded-full bg-black/60 text-white group-hover:bg-primary group-hover:text-neutral-900 transition-colors shadow-lg">
                    <Play :size="30" class="ml-1 fill-current" />
                  </span>
                </span>
              </button>
            </template>
          </div>

          <!-- Navigation across the full media list -->
          <template v-if="mediaItems.length > 1">
            <button
              @click.stop="previousMedia"
              class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center"
            >
              <ChevronLeft :size="24" />
            </button>
            <button
              @click.stop="nextMedia"
              class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/50 hover:bg-black/70 text-white rounded-full flex items-center justify-center"
            >
              <ChevronRight :size="24" />
            </button>

            <!-- Dots -->
            <div class="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
              <button
                v-for="(_, idx) in mediaItems"
                :key="idx"
                @click.stop="selectMedia(idx)"
                class="w-2 h-2 rounded-full transition-all"
                :class="currentMediaIndex === idx ? 'bg-white w-6' : 'bg-white/50 hover:bg-white/70'"
              />
            </div>
          </template>

          <!-- Thumbnails -->
          <div v-if="mediaItems.length > 1" class="p-3 flex gap-2 overflow-x-auto">
            <button
              v-for="(m, idx) in mediaItems"
              :key="m.id"
              @click="selectMedia(idx)"
              class="relative w-16 h-16 flex-shrink-0 rounded overflow-hidden border-2 transition"
              :class="currentMediaIndex === idx ? 'border-secondary' : 'border-transparent hover:border-neutral-300'"
            >
              <img
                v-if="(m.kind === 'image' ? m.url : m.thumbnail_url)"
                :src="m.kind === 'image' ? m.url : m.thumbnail_url"
                :alt="m.kind === 'video' ? m.title : `${item.title} ${idx + 1}`"
                class="w-full h-full object-cover"
              />
              <span v-else class="w-full h-full flex items-center justify-center bg-neutral-200 dark:bg-neutral-700">
                <Play :size="16" class="text-neutral-500" />
              </span>
              <!-- Video badges: play glyph + duration (Steam-style) -->
              <template v-if="m.kind === 'video'">
                <span class="absolute inset-0 flex items-center justify-center bg-black/30">
                  <Play :size="18" class="text-white fill-white drop-shadow" />
                </span>
                <span
                  v-if="m.duration_seconds"
                  class="absolute bottom-0.5 right-0.5 px-1 rounded bg-black/75 text-white text-[10px] leading-tight tabular-nums"
                >
                  {{ formatDuration(m.duration_seconds) }}
                </span>
              </template>
            </button>
          </div>
        </div>

        <!-- No media placeholder -->
        <div v-else class="h-48 bg-neutral-100 dark:bg-neutral-700 flex items-center justify-center">
          <span class="text-neutral-400 text-lg">{{ t('market.no_image') }}</span>
        </div>

        <!-- Content -->
        <div class="p-6">
          <!-- Listing meta — type eyebrow + category breadcrumb + qualifier badges on
               one wrapping row. The offer/want direction is a compact coloured eyebrow
               (<MarketListingType>, not a stand-alone pill), so it states the direction
               without claiming its own row. Each chevron is glued to its following label
               (whitespace-nowrap); the row wraps segment-by-segment on mobile. -->
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5 mb-3">
            <MarketListingType :item-type="item.item_type" display="eyebrow" />

            <template v-if="item.category_path?.length">
              <span class="text-neutral-300 dark:text-neutral-600" aria-hidden="true">·</span>
              <div class="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm text-neutral-500 dark:text-neutral-400">
                <span
                  v-for="(cat, idx) in item.category_path"
                  :key="cat.id"
                  class="flex items-center gap-1 whitespace-nowrap"
                >
                  <span v-if="idx > 0" class="text-neutral-400">›</span>
                  <NuxtLink
                    :to="localePath(`/market?category=${cat.slug}`)"
                    class="hover:text-secondary hover:underline"
                  >
                    {{ getCategoryName(cat.slug, cat.name) }}
                  </NuxtLink>
                </span>
              </div>
            </template>

            <!-- Made-by-hand (producer, not reseller — swadeshi / bread-labour) +
                 registered-only (hidden from anonymous visitors + search engines).
                 Small, trailing — they qualify the listing, they don't headline it. -->
            <UiBadge v-if="item.self_made" variant="warning" type="soft" size="sm">
              <Hand class="w-3 h-3 mr-1" />
              {{ t('market.item.self_made_badge') }}
            </UiBadge>
            <UiBadge v-if="item.visibility === 'REGISTERED'" variant="neutral" type="soft" size="sm">
              <Lock class="w-3 h-3 mr-1" />
              {{ t('market.item.registered_badge') }}
            </UiBadge>
          </div>

          <!-- Title -->
          <div class="flex items-start gap-2 mb-4">
            <h1 class="text-2xl font-bold text-neutral-900 dark:text-white">
              {{ item.title }}
            </h1>
            <DemoBadge :is-demo="item.is_demo" class="mt-1.5" />
          </div>

          <!-- Description -->
          <p class="text-neutral-600 dark:text-neutral-300 whitespace-pre-wrap mb-6">
            {{ item.description || t('market.detail_modal.no_description') }}
          </p>

          <!-- Price — the listing's key field, set by typography rather than a
               tinted box: the amount reads as the focal point by weight (matches
               the clean text price on the market list cards; the old soft-yellow
               fill read as a warning banner). Single option → one hero price.
               Multiple tiers (rental windows) → an aligned two-column table:
               period on the left, amount right-aligned in its own column, with a
               single Book CTA — not a ragged price+button row per tier. -->
          <div class="mb-6">
            <!-- 2+ options: one block per offer kind. The Book CTA sits on the
                 rent group's header, so it never reads as applying to a sale. -->
            <div v-if="pricingOptions.length > 1" class="space-y-5">
              <div v-for="grp in pricingGroups" :key="grp.type">
                <span
                  v-if="pricingTypeLabel(grp.options[0])"
                  class="block text-[11px] font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-2"
                >
                  {{ pricingTypeLabel(grp.options[0]) }}
                </span>
                <!-- single price in this group → inline; multiple tiers → table -->
                <div
                  v-if="grp.options.length === 1"
                  class="text-2xl font-bold text-neutral-900 dark:text-white leading-none"
                >
                  {{ formatPricingOption(grp.options[0]) }}
                </div>
                <div v-else class="divide-y divide-neutral-100 dark:divide-neutral-800">
                  <div
                    v-for="(opt, idx) in grp.options"
                    :key="idx"
                    class="flex items-baseline justify-between gap-4 py-2"
                  >
                    <span class="text-sm text-neutral-600 dark:text-neutral-300 truncate">
                      {{ pricingPeriod(opt) }}
                    </span>
                    <span class="text-xl font-bold text-neutral-900 dark:text-white tabular-nums whitespace-nowrap">
                      {{ priceAmount(opt) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Single option: hero price -->
            <div v-else-if="pricingOptions.length === 1">
              <div
                v-if="pricingTypeLabel(pricingOptions[0])"
                class="text-[11px] font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400 mb-0.5"
              >
                {{ pricingTypeLabel(pricingOptions[0]) }}
              </div>
              <div class="text-4xl font-bold text-neutral-900 dark:text-white leading-none">
                {{ formatPricingOption(pricingOptions[0]) }}
              </div>
            </div>

            <!-- No price set: free -->
            <div
              v-else
              class="text-3xl font-bold text-success dark:text-success-400 leading-none"
            >
              {{ t('market.item.free') }}
            </div>
          </div>

          <!-- Location -->
          <div v-if="item.location_name" class="mb-6 flex items-center gap-2 text-neutral-600 dark:text-neutral-400">
            <MapPin :size="18" />
            <span>{{ item.location_name }}</span>
          </div>

          <!-- Tags -->
          <div v-if="item.tags?.length" class="mb-6">
            <div class="flex flex-wrap gap-2">
              <UiBadge v-for="tag in item.tags" :key="tag" variant="neutral" type="soft" size="lg">
                {{ tag }}
              </UiBadge>
            </div>
          </div>

          <!-- Demand indicator -->
          <UiAlert
            v-if="item.demand_count"
            variant="info"
            :title="item.item_type === 'CREDIT'
              ? t('market.item.demand_people_need', item.demand_count, { n: item.demand_count })
              : t('market.item.demand_offers_available', item.demand_count, { n: item.demand_count })"
            class="mb-6"
          >
            <NuxtLink
              :to="localePath(`/market?item_type=${item.item_type === 'CREDIT' ? 'DEBIT' : 'CREDIT'}&category=${item.category_path?.[item.category_path.length - 1]?.slug || ''}`)"
              class="text-link font-medium"
            >
              {{ item.item_type === 'CREDIT'
                ? t('market.item.demand_view_requests')
                : t('market.item.demand_view_offers')
              }}
            </NuxtLink>
          </UiAlert>

          <!-- Owner & Trust Signals — a compact seller card. Avatar + identity sit
               together; the WoT pill and listing meta flow on a wrapping row beneath
               so nothing collides or breaks mid-word on narrow mobile. (The old rigid
               3-column flex hard-pinned the posted-date column, which crowded the
               trust text and forced the long owner name to wrap mid-word.) Posted date
               is secondary metadata → folded into the muted meta line, not its own
               competing column. -->
          <div class="border-t border-neutral-200 dark:border-neutral-700 pt-6 mb-6">
            <div class="flex items-start gap-3 sm:gap-4">
              <!-- Avatar -->
              <NuxtLink :to="localePath(`/u/${item.owner_hna?.split('@')[0] || item.owner_id}`)" class="shrink-0">
                <img
                  v-if="item.owner_avatar_url"
                  :src="item.owner_avatar_url"
                  :alt="item.owner_display_name || item.owner_hna"
                  class="w-12 h-12 rounded-full object-cover"
                />
                <div v-else class="w-12 h-12 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center">
                  <span class="text-lg font-medium text-neutral-500 dark:text-neutral-400">
                    {{ (item.owner_display_name || item.owner_hna || '?')[0].toUpperCase() }}
                  </span>
                </div>
              </NuxtLink>

              <!-- Identity + trust -->
              <div class="flex-1 min-w-0">
                <!-- Name (+ establishment) -->
                <div class="flex items-center gap-x-2 gap-y-0.5 flex-wrap">
                  <template v-if="item.establishment_name">
                    <NuxtLink
                      :to="localePath(`/org/${item.establishment_slug || item.establishment_id}`)"
                      class="font-medium text-neutral-900 dark:text-white hover:text-secondary dark:hover:text-secondary-400"
                    >
                      {{ item.establishment_name }}
                    </NuxtLink>
                    <span class="text-neutral-400">·</span>
                    <NuxtLink
                      :to="localePath(`/u/${item.owner_hna?.split('@')[0] || item.owner_id}`)"
                      class="text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary"
                    >
                      {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
                    </NuxtLink>
                  </template>
                  <NuxtLink
                    v-else
                    :to="localePath(`/u/${item.owner_hna?.split('@')[0] || item.owner_id}`)"
                    class="font-medium text-neutral-900 dark:text-white hover:text-secondary dark:hover:text-secondary-400"
                  >
                    {{ item.owner_display_name || item.owner_hna?.split('@')[0] || item.owner_id }}
                  </NuxtLink>
                </div>

                <!-- Trust pill + listing meta — wraps gracefully on mobile -->
                <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
                  <!-- WoT verification — same visual language as the profile header -->
                  <span
                    v-if="item.owner_is_verified"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-success-50 dark:bg-success-950/30 border border-success-300 dark:border-success-700"
                  >
                    <ShieldCheck class="w-3.5 h-3.5 text-success" />
                    <span class="font-semibold text-success-700 dark:text-success-400">
                      {{ t('market.trust.wot_verified', { count: item.owner_verifications_count || 3 }) }}
                    </span>
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700"
                    :title="t('market.trust.wot_badge', { count: item.owner_verifications_count || 0 })"
                  >
                    <ShieldCheck class="w-3.5 h-3.5 text-neutral-400" />
                    <span class="font-medium text-neutral-600 dark:text-neutral-400">{{ item.owner_verifications_count || 0 }}/3</span>
                    <span class="w-10 h-1.5 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                      <span class="block h-full bg-neutral-400 dark:bg-neutral-500 rounded-full" :style="{ width: `${((item.owner_verifications_count || 0) / 3) * 100}%` }" />
                    </span>
                  </span>

                  <!-- Member since -->
                  <span v-if="item.owner_created_at" class="inline-flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
                    <Clock :size="13" />
                    {{ t('market.trust.member_since', { date: formatDate(item.owner_created_at) }) }}
                  </span>

                  <!-- Posted -->
                  <span class="inline-flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
                    <CalendarClock :size="13" />
                    {{ t('market.detail_modal.posted') }} {{ formatDate(item.created_at) }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div v-if="item.owner_id === authStore.profile?.id" class="grid grid-cols-3 gap-3">
            <UiButton variant="outline" :icon="Edit" class="!whitespace-normal min-w-0 text-center" @click="editItem">
              {{ t('market.actions.edit') }}
            </UiButton>
            <UiButton variant="outline" :icon="item.is_active ? EyeOff : Eye" class="!whitespace-normal min-w-0 text-center" @click="toggleActive">
              {{ item.is_active ? t('market.actions.hide') : t('market.actions.activate') }}
            </UiButton>
            <UiButton variant="outline-error" :icon="Trash2" class="!whitespace-normal min-w-0 text-center" @click="showDeleteItemConfirm = true">
              {{ t('market.actions.delete') }}
            </UiButton>
          </div>
          <!-- Visitor actions. For a rental the structured booking flow is the
               primary path → a full-width Book CTA leads, with "make offer" + message
               demoted to an equal secondary row; the inline Book button was removed
               from the price block so there is one unambiguous primary. Non-rental
               keeps offer-as-primary. Long i18n labels (RU "Сделать предложение") must
               wrap, not overflow: the base .btn-* whitespace-nowrap would push the icon
               outside the pill and clip the text against the neighbour in this narrow
               grid. -->
          <div v-else-if="isRental" class="space-y-3">
            <UiButton
              variant="primary"
              :icon="CalendarClock"
              class="w-full"
              :to="localePath(`/rental/${itemId}`)"
            >
              {{ t('booking.book') }}
            </UiButton>
            <div class="grid grid-cols-2 gap-3">
              <UiButton variant="outline" :icon="Handshake" class="!whitespace-normal min-w-0 text-center" @click="openProposeDeal">
                {{ item.item_type === 'DEBIT' ? t('market.actions.respond') : t('market.actions.make_offer') }}
              </UiButton>
              <UiButton variant="secondary" :icon="MessageCircle" class="!whitespace-normal min-w-0 text-center" @click="contactSeller">
                {{ t('directory.users.message') }}
              </UiButton>
            </div>
          </div>
          <div v-else class="grid grid-cols-2 gap-3">
            <UiButton :icon="Handshake" class="!whitespace-normal min-w-0 text-center" @click="openProposeDeal">
              {{ item.item_type === 'DEBIT' ? t('market.actions.respond') : t('market.actions.make_offer') }}
            </UiButton>
            <UiButton variant="secondary" :icon="MessageCircle" class="!whitespace-normal min-w-0 text-center" @click="contactSeller">
              {{ t('directory.users.message') }}
            </UiButton>
          </div>
        </div>
      </div>
    </div>

    <!-- Propose Deal Modal -->
    <Teleport to="body">
      <div
        v-if="showProposeDeal && item"
        class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/50"
          @click="showProposeDeal = false"
        />

        <!-- Modal -->
        <div class="relative w-full sm:max-w-lg bg-white dark:bg-neutral-800 rounded-t-2xl sm:rounded-xl shadow-xl max-h-[90vh] overflow-y-auto" @click.stop>
          <!-- Header -->
          <div class="flex items-center justify-between p-4 border-b border-neutral-200 dark:border-neutral-700">
            <h2 class="text-lg font-semibold text-neutral-900 dark:text-white">
              {{ t('market.propose_deal.title') }}
            </h2>
            <button
              @click="showProposeDeal = false"
              :aria-label="t('common.close')"
              class="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg"
            >
              <X :size="20" />
            </button>
          </div>

          <!-- Item summary -->
          <div class="p-4 border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50">
            <div class="flex items-center gap-3">
              <img
                v-if="item.images?.[0]?.url"
                :src="item.images[0].url"
                :alt="item.title"
                class="w-16 h-16 rounded-lg object-cover"
              />
              <div class="flex-1 min-w-0">
                <h3 class="font-medium text-neutral-900 dark:text-white truncate">{{ item.title }}</h3>
                <div v-if="item.pricing_options?.length" class="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mt-0.5">
                  {{ formatPricingOption(item.pricing_options[0]) }}
                </div>
                <div v-else class="text-sm font-semibold text-success dark:text-success-400 mt-0.5">
                  {{ t('market.item.free') }}
                </div>
              </div>
            </div>
          </div>

          <!-- Message form -->
          <div class="p-4 space-y-4">
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                {{ t('market.propose_deal.message_label') }}
              </label>
              <textarea
                ref="proposalTextarea"
                v-model="proposalMessage"
                :placeholder="item.item_type === 'DEBIT' ? t('market.propose_deal.message_placeholder_request') : t('market.propose_deal.message_placeholder')"
                rows="4"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
              />
            </div>

            <!-- Send button -->
            <UiButton
              class="w-full"
              :icon="Send"
              :loading="proposalSending"
              :disabled="!proposalMessage.trim()"
              @click="sendProposal"
            >
              {{ proposalSending ? t('market.propose_deal.sending') : t('market.propose_deal.send') }}
            </UiButton>

            <!-- Contract escalation link -->
            <div class="text-center text-sm text-neutral-500 dark:text-neutral-400">
              {{ t('market.propose_deal.or_formalize') }}
              <button
                @click="showProposeDeal = false; goToContract()"
                class="text-link ml-1"
              >
                {{ t('market.propose_deal.formalize_link') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Fullscreen Image Modal (Teleport to body: escapes the page stacking
         context so it covers the fixed navbar instead of slipping behind it) -->
    <Teleport to="body">
      <div
        v-if="fullscreenImage && item?.images?.length"
        class="fixed inset-0 z-[90] bg-black flex items-center justify-center"
        role="dialog"
        aria-modal="true"
        @click="fullscreenImage = false"
      >
        <button
          @click.stop="fullscreenImage = false"
          :aria-label="t('common.close')"
          class="absolute right-4 z-10 p-2 text-white bg-black/40 hover:bg-white/20 rounded-full"
          :style="{ top: 'calc(1rem + var(--safe-area-inset-top, env(safe-area-inset-top, 0px)))' }"
        >
          <X :size="28" />
        </button>

        <img
          :src="item.images[fullscreenIndex]?.url"
          :alt="item.title"
          class="max-w-full max-h-full object-contain"
          @click.stop
        />

        <template v-if="item.images.length > 1">
          <button
            @click.stop="previousFullscreenImage"
            class="absolute left-4 top-1/2 -translate-y-1/2 p-3 bg-white/20 hover:bg-white/30 rounded-full"
          >
            <ChevronLeft :size="32" class="text-white" />
          </button>
          <button
            @click.stop="nextFullscreenImage"
            class="absolute right-4 top-1/2 -translate-y-1/2 p-3 bg-white/20 hover:bg-white/30 rounded-full"
          >
            <ChevronRight :size="32" class="text-white" />
          </button>
        </template>

        <!-- Hint: it isn't obvious you can dismiss by clicking anywhere -->
        <p class="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/70 text-sm pointer-events-none select-none">
          {{ t('market.detail_modal.tap_to_close') }}
        </p>
      </div>
    </Teleport>
  </div>

  <UiConfirmModal
    v-model="showDeleteItemConfirm"
    :title="t('market.actions.delete')"
    :message="t('market.confirm_delete')"
    :icon="Trash2"
    variant="error"
    :confirm-label="t('market.actions.delete')"
    @confirm="deleteItem"
  />
</template>
