<script setup lang="ts">
import {
  ArrowLeft, Store, User, Settings2, CalendarX2,
  Star, BadgeCheck, MapPin, Phone, Globe, Mail,
} from 'lucide-vue-next'

// Public, self-contained OWNER rental board — no auth middleware. One page,
// two owners: an establishment (/rental/org/{slug}) or a person
// (/rental/u/{name}). A single item is just this board focused on n=1 (the
// per-item /rental/{slug} page). A shared link shows the owner profile + live
// availability to anonymous visitors; booking itself prompts sign-in
// (RentalBookingSurface).

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toastStore = useToastStore()

// Owner type from the route: 'org' (establishment) | 'u' (person profile).
const ownerType = computed(() => String(route.params.type || ''))
const ownerRef = computed(() => route.params.id as string)   // slug | local_name | ULID
const isOrg = computed(() => ownerType.value === 'org')
const isPerson = computed(() => ownerType.value === 'u')
const validType = computed(() => isOrg.value || isPerson.value)

const loading = ref(true)
const notFound = ref(false)
const board = ref<any>(null)        // RentalBoardResponse
const activeId = ref<string>('')    // active item ULID (the selected tab)
const avail = ref<any>(null)        // AvailabilityWindowResponse for the active item
const availLoading = ref(false)
// Bumped on any booking event so the manager inbox (RentalManagerInbox) re-fetches.
const bookingVersion = ref(0)

const owner = computed(() => board.value?.owner || null)
// Back-link to the owner's full profile (org page or person profile).
const ownerLink = computed(() => {
  const slug = owner.value?.slug || ownerRef.value
  return localePath(isPerson.value ? `/u/${slug}` : `/org/${slug}`)
})
// Address → full map, centered on the org with its native panel open
// (mirrors EstablishmentDetail.openInMap). Establishment-only; empty otherwise.
const mapLink = computed(() => {
  const loc = owner.value?.location
  if (!loc || !isOrg.value) return ''
  const q = new URLSearchParams({
    lat: String(loc.lat), lng: String(loc.lon), zoom: '17',
    establishmentId: String(owner.value?.id || ownerRef.value), layer: 'building',
  })
  return localePath(`/map?${q.toString()}`)
})
const activeItem = computed(() => (board.value?.items || []).find((i: any) => i.item_id === activeId.value))
const tabItems = computed(() => (board.value?.items || []).map((i: any) => ({ id: i.item_id, label: i.title })))

// Localized category label (establishments only): API returns reference data in
// English (category_name); translate via the localized category tree by slug,
// falling back to the English name.
const { fetchCategory } = useCategories()
const localizedCategory = ref('')
watch(owner, async (o) => {
  if (!isOrg.value) { localizedCategory.value = ''; return }
  const fallback = o?.category_name || ''
  if (!o?.category_slug) { localizedCategory.value = fallback; return }
  try { localizedCategory.value = (await fetchCategory(o.category_slug))?.name || fallback }
  catch { localizedCategory.value = fallback }
}, { immediate: true })

const { isOpen } = useOpeningHours(computed(() => owner.value?.opening_hours as Record<string, string> | undefined))

const typeLabels: Record<string, string> = {
  ASSOCIATION: 'directory.organizations.type_association',
  COOPERATIVE: 'directory.organizations.type_cooperative',
  COMPANY: 'directory.organizations.type_company',
  NGO: 'directory.organizations.type_ngo',
  COMMUNITY: 'directory.organizations.type_community',
  CONDOMINIUM: 'condo.title',
}
const getTypeLabel = (type: string) => (typeLabels[type] ? t(typeLabels[type]) : type)

// SEO / share preview — reactive to the loaded owner.
useSeoMeta({
  title: () => owner.value ? `${owner.value.name} — ${t('booking.board.eyebrow')}` : t('booking.board.eyebrow'),
  ogTitle: () => owner.value ? `${owner.value.name} — ${t('booking.board.eyebrow')}` : t('booking.board.eyebrow'),
  description: () => owner.value?.description || t('booking.board.share_desc'),
  ogDescription: () => owner.value?.description || t('booking.board.share_desc'),
  ogImage: () => owner.value?.logo_url || undefined,
})

function authHeaders() {
  return authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {}
}

async function loadBoard() {
  loading.value = true
  notFound.value = false
  if (!validType.value) { notFound.value = true; loading.value = false; return }
  try {
    await authStore.ensureToken()
    const url = isPerson.value
      ? `/api/v1/rental/profiles/${ownerRef.value}/board`
      : `/api/v1/rental/establishments/${ownerRef.value}/board`
    board.value = await $fetch(url, { credentials: 'include', headers: authHeaders() })
    // Honor ?tab=<item_id> on first load (bookmarkable / F5-safe); else first resource.
    const items = board.value.items || []
    const wanted = String(route.query.tab || '')
    const initial = items.find((i: any) => i.item_id === wanted) || items[0]
    if (initial) { activeId.value = initial.item_id }
  } catch (e: any) {
    if (e?.response?.status === 404 || e?.status === 404) notFound.value = true
    else toastStore.error(e?.data?.detail || t('booking.error'))
  } finally {
    loading.value = false
  }
}

const realtimeStore = useRealtimeStore()
const chime = useChime()
function onBookingEvent(ev: any) {
  if (ev?.item_id === activeId.value) {
    // Audible cue for the manager when a fresh booking lands (not on cancel/confirm).
    if (ev.event === 'created' && board.value?.can_manage) chime.play()
    loadAvailability(true); bookingVersion.value++
  }
}
async function onBooked() {
  await loadAvailability(true)
  bookingVersion.value++   // refresh the manager inbox
}

// The window the SLOTS grid currently shows — set by the surface's week-pager.
const availRange = ref<{ frm?: string; to?: string }>({})
// The booking surface drives which period the SLOTS grid shows.
function onRange(r: { frm: string; to: string }) { availRange.value = r; loadAvailability(true) }

// `quiet` keeps the booking surface mounted (no full-panel spinner) so a pager
// move / booking / realtime refresh doesn't reset the surface's week offset.
// The initial tab load (and tab switch) shows the spinner.
async function loadAvailability(quiet = false) {
  if (!activeId.value) return
  if (!quiet) availLoading.value = true
  try {
    await authStore.ensureToken()
    const now = new Date()
    const f = availRange.value.frm || now.toISOString()
    const tt = availRange.value.to || new Date(now.getTime() + 14 * 24 * 3600 * 1000).toISOString()
    avail.value = await $fetch(`/api/v1/rental/items/${activeId.value}/availability`, {
      credentials: 'include', headers: authHeaders(),
      query: { frm: f, to: tt },
    })
  } catch (e: any) {
    toastStore.error(e?.data?.detail || t('booking.error'))
  } finally {
    if (!quiet) availLoading.value = false
  }
}

// Switching tabs: reload the new item's calendar and move the realtime subscription.
watch(activeId, (next, prev) => {
  if (prev) realtimeStore.unsubscribe([prev])
  avail.value = null
  availRange.value = {}   // new resource → start at the current week
  // Keep the active resource in ?tab= (F5/back-safe); first resource = clean URL.
  const firstId = board.value?.items?.[0]?.item_id
  const query = { ...route.query }
  if (next && next !== firstId) query.tab = next
  else delete query.tab
  router.replace({ query })
  if (next) {
    loadAvailability()
    realtimeStore.connect()
    realtimeStore.on('rental.booking', onBookingEvent)
    realtimeStore.subscribe([next])
  }
})

onMounted(loadBoard)
onUnmounted(() => {
  realtimeStore.off('rental.booking', onBookingEvent)
  if (activeId.value) realtimeStore.unsubscribe([activeId.value])
})
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink
      :to="ownerLink"
      class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4"
    >
      <ArrowLeft class="w-4 h-4" /> {{ isPerson ? t('booking.board.back_person') : t('booking.board.back') }}
    </NuxtLink>

    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
      <span class="sr-only">{{ t('booking.loading') }}</span>
    </div>

    <UiAlert v-else-if="notFound" variant="warning" :icon="CalendarX2" :title="t('booking.not_found')" />

    <template v-else>
      <!-- Owner profile header — makes the link a self-contained booking landing -->
      <div class="mb-6 bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4 sm:p-5">
        <div class="flex items-start gap-3">
          <!-- Logo / avatar -->
          <NuxtLink v-if="owner?.logo_url" :to="ownerLink" class="shrink-0">
            <img :src="owner.logo_url" :alt="owner.name"
                 class="w-14 h-14 object-cover border border-neutral-200 dark:border-neutral-700"
                 :class="isPerson ? 'rounded-full' : 'rounded-lg'" />
          </NuxtLink>
          <NuxtLink v-else-if="isPerson" :to="ownerLink"
                    class="shrink-0 w-14 h-14 rounded-full bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 flex items-center justify-center">
            <User class="w-7 h-7 text-neutral-400" />
          </NuxtLink>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 text-xs font-medium text-neutral-500 mb-0.5">
              <component :is="isPerson ? User : Store" class="w-3.5 h-3.5 shrink-0" /> {{ t('booking.board.eyebrow') }}
            </div>
            <!-- Clickable owner name → full profile -->
            <NuxtLink :to="ownerLink" class="group inline-flex items-center gap-2 max-w-full">
              <h1 class="text-2xl font-bold truncate group-hover:text-secondary transition-colors">
                {{ owner?.name }}
              </h1>
              <BadgeCheck v-if="owner?.is_verified" class="w-5 h-5 text-primary shrink-0" />
            </NuxtLink>

            <!-- Meta row: org → category · type · online · rating · open-now;
                 person → hna · reputation -->
            <div class="flex items-center flex-wrap gap-x-2 gap-y-1 mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              <template v-if="isOrg">
                <span v-if="localizedCategory">{{ localizedCategory }}</span>
                <span v-if="owner?.organization_type"
                      class="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded text-xs">
                  {{ getTypeLabel(owner.organization_type) }}
                </span>
                <span v-if="owner?.is_online"
                      class="px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs">
                  Online
                </span>
                <span v-if="owner?.rating_count > 0" class="inline-flex items-center gap-1">
                  <Star class="w-4 h-4 text-yellow-500 fill-yellow-500" />
                  <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ Number(owner.rating_avg).toFixed(1) }}</span>
                  <span class="text-neutral-400">({{ owner.rating_count }})</span>
                </span>
                <span v-if="isOpen === true"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs font-medium">
                  <span class="w-1.5 h-1.5 bg-green-500 rounded-full" /> {{ t('directory.establishments.open_now') }}
                </span>
                <span v-else-if="isOpen === false"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded text-xs font-medium">
                  <span class="w-1.5 h-1.5 bg-red-500 rounded-full" /> {{ t('directory.establishments.closed_now') }}
                </span>
              </template>
              <template v-else>
                <span v-if="owner?.hna" class="font-mono text-xs">{{ owner.hna }}</span>
                <span v-if="owner?.reputation_score > 0" class="inline-flex items-center gap-1">
                  <Star class="w-4 h-4 text-yellow-500 fill-yellow-500" />
                  <span class="font-medium text-neutral-700 dark:text-neutral-300">{{ Number(owner.reputation_score).toFixed(1) }}</span>
                </span>
              </template>
            </div>
          </div>
        </div>

        <!-- Short description / bio -->
        <p v-if="owner?.description"
           class="mt-3 text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed line-clamp-3">
          {{ owner.description }}
        </p>

        <!-- Contact row (establishments only): address + phone + website + email -->
        <div v-if="isOrg && (owner?.full_address || owner?.phone || owner?.website || owner?.email)"
             class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
          <NuxtLink v-if="owner?.full_address && mapLink" :to="mapLink"
                    class="inline-flex items-center gap-1.5 text-secondary hover:underline min-w-0">
            <MapPin class="w-4 h-4 text-neutral-400 shrink-0" />
            <span class="truncate">{{ owner.full_address }}</span>
          </NuxtLink>
          <span v-else-if="owner?.full_address" class="inline-flex items-center gap-1.5 text-neutral-600 dark:text-neutral-400 min-w-0">
            <MapPin class="w-4 h-4 text-neutral-400 shrink-0" />
            <span class="truncate">{{ owner.full_address }}</span>
          </span>
          <a v-if="owner?.phone" :href="`tel:${owner.phone}`" class="inline-flex items-center gap-1.5 text-secondary hover:underline">
            <Phone class="w-4 h-4 text-neutral-400 shrink-0" /> {{ owner.phone }}
          </a>
          <a v-if="owner?.website" :href="owner.website" target="_blank" rel="noopener noreferrer"
             class="inline-flex items-center gap-1.5 text-secondary hover:underline">
            <Globe class="w-4 h-4 text-neutral-400 shrink-0" /> {{ t('booking.board.website') }}
          </a>
          <a v-if="owner?.email" :href="`mailto:${owner.email}`" class="inline-flex items-center gap-1.5 text-secondary hover:underline">
            <Mail class="w-4 h-4 text-neutral-400 shrink-0" /> {{ owner.email }}
          </a>
        </div>
      </div>

      <!-- No bookable items -->
      <div v-if="!board?.items?.length" class="py-12 text-center">
        <CalendarX2 class="w-12 h-12 mx-auto text-neutral-400" />
        <h3 class="mt-3 text-base font-semibold">{{ isPerson ? t('booking.board.empty_person') : t('booking.board.empty') }}</h3>
      </div>

      <template v-else>
        <!-- Resource tabs: switch between the owner's rentable items -->
        <UiTabs v-model="activeId" :tabs="tabItems" variant="underline" class="mb-4" />

        <div v-if="activeItem" class="flex items-center justify-between gap-2 mb-3">
          <span v-if="activeItem.rent_amount != null" class="text-sm text-neutral-500">
            {{ activeItem.rent_amount }} {{ activeItem.currency }} {{ t('booking.per_unit', { unit: t('booking.units.' + activeItem.unit) }) }}
          </span>
          <UiButton v-if="board.can_manage" variant="ghost" size="sm" :icon="Settings2"
                    :to="localePath(`/rental/${activeItem.slug || activeItem.item_id}`)">
            {{ t('booking.board.manage') }}
          </UiButton>
        </div>

        <!-- Active item's availability + booking -->
        <div v-if="availLoading" class="py-12 text-center" role="status" aria-live="polite">
          <div class="h-12 w-12 mx-auto border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin"></div>
          <span class="sr-only">{{ t('booking.loading') }}</span>
        </div>
        <RentalBookingSurface
          v-else-if="avail?.bookable"
          :key="activeId"
          :item-id="activeId"
          :bookable="avail.bookable"
          :slots="avail.slots"
          :can-manage="board?.can_manage"
          @booked="onBooked"
          @range="onRange"
        />

        <!-- Manager inbox for the active resource (parity with the per-item page) -->
        <RentalManagerInbox v-if="board?.can_manage && activeId" :item-id="activeId"
                            :reload-key="bookingVersion" @changed="loadAvailability(true)" />
      </template>
    </template>
  </div>
</template>
