<template>
  <div class="max-w-2xl mx-auto px-4 py-2">
    <div v-if="pending" class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>
    <template v-else-if="routeData">
      <h1 class="sr-only">{{ routeData.short_name }} — {{ routeData.long_name }}</h1>
      <div class="relative flex items-center gap-2 mb-2 min-w-0">
        <button @click="navigateTo(localePath('/transit'))" :aria-label="$t('transit.back')" class="btn-ghost btn-icon w-11 h-11 -ml-2 flex-shrink-0">
          <ArrowLeft class="w-5 h-5" />
        </button>
        <img :src="routeTypeIcon(routeData.route_type)" :alt="routeTypeFallback(routeData.route_type)" class="w-10 h-10 flex-shrink-0" />
        <span class="flex-shrink-0 inline-block px-2.5 py-1 rounded font-bold text-lg" :style="routeBadgeStyle(routeData)">{{ routeData.short_name }}</span>
        <span v-if="isNightRoute" class="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 text-xs font-medium">
          <Moon class="w-3 h-3" />{{ $t('transit.night_route') }}
        </span>
        <!-- Line variants (percursos) dropdown — only when this line groups multiple
             path-variants. Lets the user see a one-directional feeder is one pattern
             of a larger line. v-show (not v-if) keeps variant links in SSR HTML.
             Menu anchors to the header row (relative above), not the trigger — full
             row width is available so variant names don't wrap in a narrow column. -->
        <div v-if="(routeData.variants?.length ?? 0) > 1" ref="variantsRef" class="min-w-0 ml-auto">
          <button
            @click="variantsOpen = !variantsOpen"
            :aria-expanded="variantsOpen"
            aria-haspopup="menu"
            :aria-label="$t('transit.line_variants')"
            class="flex items-center gap-1 max-w-full px-1.5 py-0.5 rounded-md text-base text-neutral-700 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
            :class="{ 'bg-primary-100 dark:bg-primary-900/40': variantsOpen }"
          >
            <span class="truncate">{{ routeData.long_name }}</span>
            <ChevronDown class="w-4 h-4 flex-shrink-0 transition-transform duration-200" :class="{ 'rotate-180': variantsOpen }" />
          </button>
          <Transition
            enter-active-class="transition ease-out duration-100"
            enter-from-class="opacity-0 scale-95"
            enter-to-class="opacity-100 scale-100"
            leave-active-class="transition ease-in duration-75"
            leave-from-class="opacity-100 scale-100"
            leave-to-class="opacity-0 scale-95"
          >
            <div
              v-show="variantsOpen"
              class="absolute right-0 top-full mt-1 z-50 w-max min-w-[16rem] max-w-full p-1.5 origin-top-right bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-lg"
            >
              <NuxtLink
                v-for="v in routeData.variants"
                :key="v.slug"
                :to="variantPath(v)"
                :aria-current="v.is_current ? 'page' : undefined"
                @click="variantsOpen = false"
                class="flex items-start gap-2 px-3 py-2 rounded-md text-sm transition-colors"
                :class="[
                  v.is_current
                    ? 'bg-primary/10 text-neutral-900 dark:text-neutral-100 font-medium pointer-events-none'
                    : 'text-neutral-700 dark:text-neutral-300 hover:bg-primary-100 dark:hover:bg-primary-900/40',
                  !v.runs_today && !v.is_current ? 'opacity-50' : '',
                ]"
              >
                <component :is="v.directions?.length > 1 ? ArrowLeftRight : ArrowRight" class="w-4 h-4 flex-shrink-0 mt-0.5 text-neutral-400" />
                <span class="flex-1 min-w-0">
                  <span class="block">{{ v.long_name }}</span>
                  <!-- 24h departure profile: filled cell = this variant departs in
                       that hour today (edge-of-day variants read at a glance) -->
                  <span
                    v-if="profileFor(v.slug)?.length"
                    class="mt-1 flex gap-px"
                    :title="profileTitle(profileFor(v.slug)!)"
                    aria-hidden="true"
                  >
                    <span
                      v-for="h in 24"
                      :key="h"
                      class="h-1.5 w-1 rounded-[1px]"
                      :class="profileFor(v.slug)!.includes(h - 1)
                        ? 'bg-secondary dark:bg-secondary-400'
                        : 'bg-neutral-200 dark:bg-neutral-700'"
                    ></span>
                  </span>
                </span>
                <span v-if="!v.runs_today" class="flex-shrink-0 inline-flex items-center gap-1 text-[10px] uppercase font-bold mt-0.5 text-neutral-400 dark:text-neutral-500">
                  <CalendarOff class="w-3 h-3" />{{ $t('transit.not_running_today') }}
                </span>
                <Check v-else-if="v.is_current" class="w-4 h-4 flex-shrink-0 mt-0.5 text-secondary dark:text-secondary-400" />
              </NuxtLink>
            </div>
          </Transition>
        </div>
        <div v-else class="min-w-0 ml-auto truncate text-base text-neutral-700 dark:text-neutral-300">{{ routeData.long_name }}</div>
        <button
          @click="openTimetable"
          :aria-label="$t('transit.schedule')"
          :title="$t('transit.schedule')"
          class="btn-ghost btn-icon w-11 h-11 flex-shrink-0"
        >
          <CalendarDays class="w-5 h-5" />
        </button>
      </div>

      <!-- Stops List — both directions shown simultaneously -->
      <div class="grid grid-cols-1 gap-4 mb-6" :class="{ 'md:grid-cols-2': directionViews.length > 1 }">
        <div v-for="view in directionViews" :key="view.direction_id">
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
            <div
              v-for="s in view.stops"
              :key="s.id"
              class="flex items-center gap-2 hover:bg-primary/15 dark:hover:bg-primary/10 transition-colors min-h-[44px]"
            >
              <!-- Left slot: when a vehicle is at this stop the bus icon takes the
                   time column (an ETA here is the FOLLOWING bus — secondary to "it's
                   here now"; it reappears the moment the vehicle leaves). Otherwise
                   the slot holds the live ETA / scheduled / first-departure time. -->
              <button
                v-if="vehicleAtStop(s.source_id, view.direction_id)"
                @click.stop="openVehicleDetail(vehicleAtStop(s.source_id, view.direction_id))"
                class="relative flex-shrink-0 ml-2 p-0.5 rounded-full hover:bg-primary/30 transition-colors"
                :class="vehicleAtStop(s.source_id, view.direction_id).z ? 'opacity-40' : ''"
                :title="vehicleAtStop(s.source_id, view.direction_id).z ? t('transit.zombie') : t('transit.vehicle_here')"
              >
                <!-- Arrival pulse: route-colored ring expands when the vehicle
                     just hopped to this stop (see reconcileVehiclePulses) -->
                <span
                  v-if="isPulsing(vehicleAtStop(s.source_id, view.direction_id).v)"
                  class="stop-pulse-ring absolute inset-0 rounded-full border-2 pointer-events-none"
                  :style="{ borderColor: routeColorCss, boxShadow: `0 0 0 1.5px ${pulseCasingCss}` }"
                  aria-hidden="true"
                ></span>
                <img
                  :src="routeTypeIcon(routeData.route_type)"
                  class="relative w-9 h-9"
                  :class="{ 'stop-pulse-pop': isPulsing(vehicleAtStop(s.source_id, view.direction_id).v) }"
                />
              </button>
              <button
                v-else-if="etasFor(view.direction_id)[s.source_id] != null"
                @click.stop="openEtaDetail(s.source_id, view.direction_id)"
                class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded bg-primary text-neutral-900 text-xs font-bold font-mono hover:bg-primary/80 transition-colors"
              >{{ formatStopEta(s.source_id, view.direction_id) }}</button>
              <span
                v-else-if="scheduledTimeFor(view.direction_id, s.source_id)"
                class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 text-xs font-mono"
                :title="$t('transit.scheduled')"
              >{{ scheduledTimeFor(view.direction_id, s.source_id) }}</span>
              <span
                v-else-if="view.stops[0]?.source_id === s.source_id && firstDepartureFor(view.direction_id)"
                class="flex-shrink-0 ml-2 px-1.5 py-0.5 rounded text-xs font-mono bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300"
                :title="$t('transit.next_departure')"
              >{{ firstDepartureFor(view.direction_id) }}</span>
              <span v-else class="flex-shrink-0 ml-2 w-10"></span>
              <button
                @click="openStop(s)"
                class="flex-1 p-3 pl-0 min-w-0 text-left text-sm text-neutral-900 dark:text-neutral-100"
              >{{ s.name }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Route Mini-Map -->
      <div
        class="route-mini-map mb-4 cursor-pointer rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700 hover:border-secondary-300 dark:hover:border-secondary-600 transition-colors"
        @click="showRouteOnMap"
      >
        <div ref="miniMapEl" class="mini-map-inner aspect-[1.618]" />
      </div>

      <!-- Tickets -->
      <div v-if="ticketTypes.length" class="mb-6">
        <h2 class="text-sm font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
          {{ $t('tickets.title') }}
        </h2>
        <TicketsTicketPurchaseCard :ticket-types="ticketTypes" :buying-id="buyingTicketId" @buy="startBuy" />
      </div>

      <TicketsTicketBuyModal
        :ticket-type="buyingTicketType"
        @close="buyingTicketType = null; buyingTicketId = null"
        @purchased="onPurchased"
        @show-qr="qrTicket = $event"
      />
      <TicketsTicketQRModal :ticket="qrTicket" @close="qrTicket = null" />

      <!-- Timetable Modal — open state lives in ?timetable=<date> so a direct
           link lands with the timetable already open (gated on isMounted:
           Teleport targets don't exist during SSR) -->
      <TransitTimetableModal
        v-if="isMounted && timetableOpen"
        :route-data="routeData"
        :city="city"
        :slug="slug"
        :selected-date="timetableDate"
        @close="closeTimetable"
        @update:date="setTimetableDate"
      />

      <!-- ETA Detail Modal -->
      <Teleport to="body">
        <div v-if="etaDetail" class="fixed inset-0 z-50 flex items-end sm:items-center justify-center" @click.self="etaDetail = null">
          <div class="fixed inset-0 bg-black/50" @click="etaDetail = null"></div>
          <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-lg sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
            <div class="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">
                ETA {{ etaDetail.stop_source_id }} <span class="text-neutral-400 font-normal">#{{ etaDetail.stop_index }}</span>
              </h3>
              <button @click="etaDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div class="px-4 py-3 space-y-4 text-xs font-mono">
              <!-- Meta -->
              <div class="grid grid-cols-2 gap-2 text-neutral-600 dark:text-neutral-400">
                <div>route: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.route_source_id }}</span></div>
                <div>dir: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.direction }}</span></div>
                <div>ds: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.data_source_id?.slice(0, 8) }}...</span></div>
                <div>stops: <span class="text-neutral-900 dark:text-neutral-100">{{ etaDetail.total_stops }}</span></div>
              </div>

              <!-- Vehicles -->
              <div v-for="v in etaDetail.vehicles" :key="v.vehicle_id"
                class="border rounded-lg p-3 space-y-2"
                :class="v.is_approaching
                  ? 'border-primary bg-primary/5'
                  : 'border-neutral-200 dark:border-neutral-700'"
              >
                <div class="flex items-center justify-between">
                  <span class="font-bold text-neutral-900 dark:text-neutral-100">
                    {{ v.vehicle_id }}
                  </span>
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                    :class="{
                      'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200': v.state.status === 'confirmed',
                      'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200': v.state.status === 'tentative',
                      'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400': v.state.status === 'dual',
                    }"
                  >{{ v.state.status }}</span>
                </div>

                <!-- Vehicle state -->
                <div class="grid grid-cols-2 gap-1 text-neutral-500 dark:text-neutral-400">
                  <div>idx: <span class="text-neutral-800 dark:text-neutral-200">{{ v.state.stop_index }}</span> ({{ v.state.stop_id }})</div>
                  <div>stall: <span class="text-neutral-800 dark:text-neutral-200">{{ v.state.stall_count }}</span></div>
                  <div>pos: <span class="text-neutral-800 dark:text-neutral-200">{{ Number(v.state.lat).toFixed(4) }}, {{ Number(v.state.lon).toFixed(4) }}</span></div>
                  <div>spd: <span class="text-neutral-800 dark:text-neutral-200">{{ v.live.speed ?? '?' }} km/h</span></div>
                  <div v-if="v.live.headsign">hs: <span class="text-neutral-800 dark:text-neutral-200">{{ v.live.headsign }}</span></div>
                  <div v-if="v.live.zombie" class="text-amber-600">ZOMBIE</div>
                </div>

                <!-- ETA breakdown -->
                <template v-if="v.is_approaching">
                  <div class="flex items-center gap-2 text-neutral-900 dark:text-neutral-100">
                    <span class="bg-primary px-1.5 py-0.5 rounded font-bold text-neutral-900">
                      {{ Math.round(v.eta_seconds / 60) }} min
                    </span>
                    <span class="text-neutral-500 dark:text-neutral-400">
                      {{ v.stops_away }} stops &middot;
                      {{ v.observed_segments }} observed / {{ v.fallback_segments }} fallback
                    </span>
                  </div>
                  <!-- Segment chain -->
                  <div class="space-y-0.5">
                    <div v-for="(seg, i) in v.segments" :key="i"
                      class="flex items-center gap-1"
                      :class="seg.observed ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400 dark:text-neutral-500'"
                    >
                      <span class="w-16 text-right">{{ seg.from }}</span>
                      <span class="text-neutral-400">&rarr;</span>
                      <span class="w-16">{{ seg.to }}</span>
                      <span class="ml-auto tabular-nums" :class="seg.observed ? 'text-green-700 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'">
                        {{ seg.avg_s }}s
                      </span>
                      <span v-if="seg.observed" class="text-neutral-400">({{ seg.samples }})</span>
                      <span v-else class="text-amber-500">fallback</span>
                    </div>
                  </div>
                </template>
                <div v-else class="text-neutral-400 italic">not approaching</div>
              </div>

              <div v-if="!etaDetail.vehicles?.length" class="text-neutral-400 text-center py-4">
                No vehicles tracking this route
              </div>
            </div>
          </div>
        </div>
      </Teleport>
      <!-- Vehicle Detail Modal -->
      <Teleport to="body">
        <div v-if="vehicleDetail" class="fixed inset-0 z-50 flex items-end sm:items-center justify-center" @click.self="vehicleDetail = null">
          <div class="fixed inset-0 bg-black/50" @click="vehicleDetail = null"></div>
          <div class="relative bg-white dark:bg-neutral-900 w-full sm:max-w-lg sm:rounded-xl rounded-t-xl max-h-[85vh] overflow-y-auto shadow-xl">
            <div class="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 px-4 py-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <img :src="routeTypeIcon(routeData.route_type)" class="w-6 h-6" />
                <h3 class="font-bold text-sm text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vehicle_id }}</h3>
              </div>
              <button @click="vehicleDetail = null" class="btn-ghost btn-icon btn-sm"><X class="w-4 h-4" /></button>
            </div>
            <div v-if="vehicleDetailLoading" class="flex justify-center py-8">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
            </div>
            <div v-else class="px-4 py-3 space-y-3 text-sm">
              <!-- GTFS-RT data -->
              <div v-if="vehicleDetail.vdata" class="space-y-1.5">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">GTFS-RT</h4>
                <div class="grid grid-cols-2 gap-1 text-xs font-mono">
                  <div>{{ $t('transit.route') }}: <span class="text-neutral-900 dark:text-neutral-100 font-bold">{{ vehicleDetail.vdata.rn }}</span></div>
                  <div>{{ $t('transit.direction') }}: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.hs }}</span></div>
                  <div>pos: <span class="text-neutral-900 dark:text-neutral-100">{{ Number(vehicleDetail.vdata.lat).toFixed(5) }}, {{ Number(vehicleDetail.vdata.lon).toFixed(5) }}</span></div>
                  <div>speed: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.s }} km/h</span></div>
                  <div>bearing: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.b }}°</span></div>
                  <div>status: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.st }}</span></div>
                  <div>stop: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vdata.sid }}</span></div>
                  <div>trip: <span class="text-neutral-900 dark:text-neutral-100 break-all">{{ vehicleDetail.vdata.tid }}</span></div>
                  <div v-if="vehicleDetail.vdata.z" class="col-span-2 text-amber-600 font-bold">ZOMBIE (stale data)</div>
                </div>
                <div v-if="vehicleDetail.stop_name" class="text-xs">
                  <span class="text-neutral-500 dark:text-neutral-400">{{ $t('transit.direction') }} stop:</span>
                  <span class="text-neutral-900 dark:text-neutral-100 ml-1">{{ vehicleDetail.stop_name }}</span>
                </div>
                <div class="text-xs text-neutral-400">
                  updated: {{ vehicleDetail.vdata.t ? new Date(vehicleDetail.vdata.t * 1000).toLocaleTimeString() : '?' }}
                </div>
              </div>

              <div v-if="vehicleDetail.vprev" class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-1.5">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">STT Tracking</h4>
                <div class="grid grid-cols-2 gap-1 text-xs font-mono">
                  <div>state:
                    <span class="px-1 py-0.5 rounded text-[10px] font-bold uppercase"
                      :class="{
                        'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200': vehicleDetail.vprev.st === 'c',
                        'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200': vehicleDetail.vprev.st === 't',
                        'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400': vehicleDetail.vprev.st === 'd',
                      }"
                    >{{ { c: 'confirmed', t: 'tentative', d: 'dual' }[vehicleDetail.vprev.st] || vehicleDetail.vprev.st }}</span>
                  </div>
                  <div>dir: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.d }}</span></div>
                  <div>stop idx: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.idx }}</span></div>
                  <div>stall: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.stall }}</span></div>
                  <div v-if="vehicleDetail.vprev.d_alt != null">alt dir: <span class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.vprev.d_alt }} (idx {{ vehicleDetail.vprev.idx_alt }})</span></div>
                </div>
              </div>

              <!-- Data source -->
              <div v-if="vehicleDetail.data_source_name" class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-1">
                <h4 class="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">{{ $t('transit.data_source') }}</h4>
                <div class="text-xs">
                  <a v-if="vehicleDetail.data_source_url" :href="vehicleDetail.data_source_url" target="_blank" rel="noopener" class="text-link">{{ vehicleDetail.data_source_name }}</a>
                  <span v-else class="text-neutral-900 dark:text-neutral-100">{{ vehicleDetail.data_source_name }}</span>
                </div>
                <div class="text-xs text-neutral-400 font-mono">ds: {{ vehicleDetail.data_source_id?.slice(0, 12) }}...</div>
              </div>
            </div>
          </div>
        </div>
      </Teleport>
    </template>
    <button v-else @click="navigateTo(localePath('/transit'))" class="flex items-center gap-1.5 px-3 py-2.5 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors min-h-[44px]">
      <ArrowLeft class="w-4 h-4" />
      {{ $t('transit.back') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ArrowLeft, ArrowRight, ArrowLeftRight, CalendarDays, CalendarOff, Check, ChevronDown, Moon, X } from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const colorMode = useColorMode()
const { routeTypeIcon, routeTypeFallback, resolveColor, routeBadgeStyle } = useTransitHelpers()

const city = route.params.city as string
const slug = route.params.slug as string

const { data: routeData, pending } = await useFetch(`/api/v1/geo/transit/routes/${city}/${slug}/`)

useSeoMeta({
  title: () => routeData.value?.short_name ? `${routeData.value.short_name} ${routeData.value.long_name} — Parahub` : t('transit.title'),
  ogTitle: () => routeData.value?.short_name ? `${routeData.value.short_name} ${routeData.value.long_name}` : t('transit.title'),
  description: () => routeData.value?.long_name ? `Route ${routeData.value.short_name} — ${routeData.value.long_name}` : t('transit.title'),
  ogDescription: () => routeData.value?.long_name ? `Route ${routeData.value.short_name} — ${routeData.value.long_name}` : t('transit.title'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary_large_image',
})

// SEO: canonical points to the line's canonical variant (lowest path_type), so the
// minor path-variants (e.g. one-directional feeders) don't fragment as duplicate content.
// Self-referential when this is already the canonical or a single-variant route.
const SITE_URL = 'https://parahub.io'
const canonicalSlug = computed(() => routeData.value?.canonical_slug || slug)
const canonicalPlace = computed(() => {
  const v = (routeData.value?.variants ?? []).find((x: any) => x.slug === canonicalSlug.value)
  return v?.place_slug || city
})
useHead({
  link: computed(() => [{
    rel: 'canonical',
    href: `${SITE_URL}${localePath(`/transit/route/${canonicalPlace.value}/${canonicalSlug.value}`)}`,
  }]),
})

function variantPath(v: any): string {
  return localePath(`/transit/route/${v.place_slug || city}/${v.slug}`)
}

// Timetable modal: open state + selected date live in ?timetable=<YYYY-MM-DD>
// so direct links open the page with the timetable already shown. Open = push
// (browser Back closes the modal), day switch = replace (no history spam).
const isMounted = ref(false)
const timetableOpen = computed(() => route.query.timetable !== undefined)
const timetableDate = computed(() => {
  const q = route.query.timetable
  return typeof q === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(q) ? q : agencyTodayISO()
})

function agencyTodayISO(): string {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: routeData.value?.agency_timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date())
  } catch {
    return new Date().toISOString().slice(0, 10)
  }
}

function openTimetable() {
  router.push({ query: { ...route.query, timetable: agencyTodayISO() } })
}
function closeTimetable() {
  const q = { ...route.query }
  delete q.timetable
  router.push({ query: q })
}
function setTimetableDate(d: string) {
  router.replace({ query: { ...route.query, timetable: d } })
}

// Variants dropdown: click-outside + ESC close
const variantsOpen = ref(false)
const variantsRef = ref<HTMLElement | null>(null)

function onVariantsDocClick(e: MouseEvent) {
  if (variantsOpen.value && variantsRef.value && !variantsRef.value.contains(e.target as Node)) {
    variantsOpen.value = false
  }
}

function onVariantsDocKey(e: KeyboardEvent) {
  if (e.key === 'Escape') variantsOpen.value = false
}

// Both directions, rendered side-by-side. Single-direction routes (loop/one-way/legacy) → one view.
const directionViews = computed(() => {
  const rd = routeData.value
  if (!rd) return []
  const dirs = rd.directions ?? []
  const stops0 = rd.stops ?? []
  const stops1 = rd.stops_dir1 ?? []
  if (dirs.length > 1) {
    return [
      { direction_id: 0, stops: stops0 },
      // Fallback to reversed dir0 when inbound RouteStops weren't imported (legacy feeds)
      { direction_id: 1, stops: stops1.length ? stops1 : [...stops0].reverse() },
    ]
  }
  const only = dirs[0]?.direction_id ?? 0
  return [{ direction_id: only, stops: stops0 }]
})

const routeCenter = computed(() => {
  if (!routeData.value?.stops?.length) return { lat: 0, lon: 0 }
  const stops = routeData.value.stops
  const mid = stops[Math.floor(stops.length / 2)]
  return { lat: mid.lat, lon: mid.lon }
})

function openStop(s: any) {
  if (s.slug && s.place_slug) {
    navigateTo(localePath(`/transit/stop/${s.place_slug}/${s.slug}`))
  } else {
    navigateTo(localePath(`/transit/stop/${city}/${s.slug || s.id}`))
  }
}

// GTFS static schedule: {direction: {stop_source_id: "HH:MM"}}
const scheduleData = ref<{
  schedule: Record<string, Record<string, string>>
  schedule_next: Record<string, Record<string, string>>
  first_departure: Record<string, string>
  is_night: boolean
  variants_profile?: Record<string, number[]>
}>({ schedule: {}, schedule_next: {}, first_departure: {}, is_night: false, variants_profile: {} })

// Variants dropdown hour-strips: hours with departures today per variant slug
const profileFor = (slug: string): number[] | null =>
  scheduleData.value.variants_profile?.[slug] ?? null

// "05–07, 20, 23" — readable summary of departure hours for the strip tooltip
function profileTitle(hours: number[]): string {
  const parts: string[] = []
  for (let i = 0; i < hours.length; i++) {
    let j = i
    while (j + 1 < hours.length && hours[j + 1] === hours[j] + 1) j++
    const a = String(hours[i]).padStart(2, '0')
    const b = String(hours[j]).padStart(2, '0')
    parts.push(i === j ? a : `${a}–${b}`)
    i = j
  }
  return parts.join(', ')
}

const isNightRoute = computed(() => scheduleData.value.is_night)
const scheduleFor = (dirId: number) => scheduleData.value.schedule[String(dirId)] ?? {}
const scheduleNextFor = (dirId: number) => scheduleData.value.schedule_next[String(dirId)] ?? {}
const firstDepartureFor = (dirId: number) => scheduleData.value.first_departure[String(dirId)] ?? null

// Static schedule badge for a stop: the soonest upcoming departure, falling
// back to the FOLLOWING trip (schedule_next) when the soonest one isn't a
// catchable arrival here — so a stop just behind the live bus shows the next
// trip's gray time instead of going blank.
//
// Two reasons the soonest time isn't catchable:
//   1. It elapsed since the fetch. The schedule is fetched with server-side
//      "≥ now" filtering, then ages client-side; when a live vehicle passes a
//      stop its yellow ETA badge disappears, and without this the stale gray
//      time loaded at page-open would resurface — a trail of past times behind
//      the bus. Server guarantees badge ≥ fetch time, so "elapsed" = badge lies
//      between fetch time and now, measured forward from the fetch moment —
//      exact across midnight (night routes keep their 00:xx badges).
//   2. It belongs to a bus running AHEAD of schedule. Stops it already passed
//      keep its trip's still-future scheduled times (neither "≥ now" filtering
//      nor check 1 drops them, and RT↔static trip_id matching is unreliable —
//      e.g. Carris Metropolitana). Positional rule: behind the rearmost live
//      vehicle of a direction, the next real arrival is a trip yet to depart
//      the origin, so a time earlier than first_departure can only be the trip
//      that vehicle is already running.
// In both cases the FOLLOWING trip (schedule_next) is the genuine next arrival
// and is shown instead. Re-fetched every 60s, which rolls cur/next forward.
// Reactive to WS ticks and the refresh timer.
function scheduledTimeFor(dirId: number, stopSourceId: string): string | null {
  void liveVehicles.value
  void scheduleRefreshTick.value
  const cur = scheduleFor(dirId)[stopSourceId] || null
  const next = scheduleNextFor(dirId)[stopSourceId] || null
  const nowMin = minutesOfDayInStopTz()
  const rear = rearmostLiveIndex(dirId)
  const i = stopIndexByDir.value[dirId]?.get(stopSourceId)
  const fd = firstDepartureFor(dirId)

  const elapsedSinceFetch = (hhmm: string): boolean => {
    if (scheduleFetchedMin < 0) return false
    const [bh, bm] = hhmm.split(':').map(Number)
    const sinceFetchBadge = (bh * 60 + bm - scheduleFetchedMin + 1440) % 1440
    const sinceFetchNow = (nowMin - scheduleFetchedMin + 1440) % 1440
    return sinceFetchBadge < sinceFetchNow
  }
  const servedByLiveBus = (hhmm: string): boolean => {
    if (rear == null || i == null || i >= rear || !fd) return false
    const [bh, bm] = hhmm.split(':').map(Number)
    const [fh, fm] = fd.split(':').map(Number)
    const fwdBadge = (bh * 60 + bm - nowMin + 1440) % 1440
    const fwdFirst = (fh * 60 + fm - nowMin + 1440) % 1440
    return fwdBadge < fwdFirst
  }

  if (cur && !elapsedSinceFetch(cur) && !servedByLiveBus(cur)) return cur
  if (next && !elapsedSinceFetch(next) && !servedByLiveBus(next)) return next
  return null
}

// source_id → display index per direction, to resolve a vehicle's sid and a
// badge's stop to positions in the rendered list (first occurrence wins on
// loop routes that visit a stop twice)
const stopIndexByDir = computed<Record<number, Map<string, number>>>(() => {
  const out: Record<number, Map<string, number>> = {}
  for (const view of directionViews.value) {
    const m = new Map<string, number>()
    view.stops.forEach((s: any, i: number) => { if (!m.has(s.source_id)) m.set(s.source_id, i) })
    out[view.direction_id] = m
  }
  return out
})

// Smallest stop index among live vehicles of a direction (zombies included —
// a stale position still proves the stops behind it were served), or null
// when none resolve to this variant's stop list
function rearmostLiveIndex(dirId: number): number | null {
  const idx = stopIndexByDir.value[dirId]
  if (!idx) return null
  let rear: number | null = null
  for (const v of liveVehicles.value) {
    if (v.d !== dirId || !v.sid) continue
    const i = idx.get(v.sid)
    if (i != null && (rear == null || i < rear)) rear = i
  }
  return rear
}

// Agency-clock minute of day at the last successful schedule fetch; -1 until
// the first fetch lands. Anchors the staleness check in scheduledTimeFor.
let scheduleFetchedMin = -1

function minutesOfDayInStopTz(): number {
  const [h, m] = formatClockInStopTz(new Date()).split(':').map(Number)
  return h * 60 + m
}

async function loadSchedule() {
  try {
    const data = await $fetch<typeof scheduleData.value>(
      `/api/v1/geo/transit/routes/${city}/${slug}/schedule/`
    )
    scheduleData.value = data
    scheduleFetchedMin = minutesOfDayInStopTz()
  } catch {}
}

// Minute timer: re-fetch the schedule so passed stops pick up the next trip's
// departure (server recomputes "≥ now"); the tick alone drops stale badges on
// routes with no live vehicles to drive WS reactivity.
const scheduleRefreshTick = ref(0)
let scheduleRefreshTimer: ReturnType<typeof setInterval> | null = null

function startScheduleRefresh() {
  scheduleRefreshTimer = setInterval(() => {
    scheduleRefreshTick.value++
    if (document.visibilityState === 'visible') loadSchedule()
  }, 60_000)
}

// Route-wide ETA predictions: both directions from WS
// allEtas: {0: {stop_src: seconds}, 1: {stop_src: seconds}}
const allEtas = ref<Record<number, Record<string, number>>>({})
const etasFor = (dirId: number) => allEtas.value[dirId] ?? {}

// Render a clock label (HH:MM) in the STOP's timezone, not the viewer's browser
// zone — else a cross-timezone viewer sees live ETA/now in their local clock,
// inconsistent with the agency-local static schedule badges. agency_timezone
// comes from route detail; falls back to browser-local if missing/invalid.
function formatClockInStopTz(date: Date): string {
  const tz = routeData.value?.agency_timezone
  if (tz) {
    try {
      return new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
      }).format(date)
    } catch { /* invalid tz → browser-local fallback below */ }
  }
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

function formatStopEta(stopSourceId: string, dirId: number): string {
  const eta = etasFor(dirId)[stopSourceId]
  if (eta == null) return ''
  return formatClockInStopTz(new Date(Date.now() + eta * 1000))
}

// ETA detail modal (REST endpoint for full breakdown)
const etaDetail = ref<any>(null)

async function openEtaDetail(stopSourceId: string, dirId: number) {
  try {
    const data = await $fetch(
      `/api/v1/geo/transit/routes/${city}/${slug}/eta/${stopSourceId}/`,
      { params: { direction: dirId } }
    )
    etaDetail.value = data
  } catch {}
}

// Vehicle detail modal
const vehicleDetail = ref<any>(null)
const vehicleDetailLoading = ref(false)

async function openVehicleDetail(v: any) {
  const vid = v?.v
  const dsId = routeData.value?.data_source_id
  if (!vid || !dsId) {
    vehicleDetail.value = { vehicle_id: vid || '?', vdata: v }
    return
  }
  vehicleDetail.value = { vehicle_id: vid }
  vehicleDetailLoading.value = true
  try {
    const data = await $fetch(`/api/v1/geo/transit/vehicles/state/`, { params: { ds_id: dsId, vid } })
    vehicleDetail.value = data
  } catch {
    vehicleDetail.value = { vehicle_id: vid, vdata: v }
  }
  vehicleDetailLoading.value = false
}

// Live vehicle positions + ETAs via WebSocket
const liveStopIds = ref<string[]>([])
const liveVehicles = ref<any[]>([])
let liveWs: WebSocket | null = null

// ── Stop-hop pulse ──────────────────────────────────────────────────────────
// When a vehicle moves to a new stop (its `sid` changed between WS pushes) the
// list icon pulses on arrival — a route-colored ring expands + the icon pops —
// so the eye catches the hop. No bounce-back: the bus is only ever shown where
// it actually is; the old stop reverts to its time badge. Keyed by `v.v`. The
// mini-map keeps the real continuous lat/lon (it animates position, not a stop).
// Shared mechanic: useStopHopPulse (+ global .stop-pulse-* CSS).
const { isPulsing, reconcile: reconcileVehiclePulses } = useStopHopPulse<any>({
  key: v => v.v,
  changed: (a, b) => a.sid !== b.sid,
})

const routeColorCss = computed(() =>
  routeData.value ? `#${resolveColor(routeData.value)}` : 'currentColor'
)

// Casing behind the pulse ring so it reads on any row background whatever the
// route color (most feeds → default bus yellow, invisible on the light row).
// Same dark-on-light / light-on-dark rationale as the mini-map line casing.
const pulseCasingCss = computed(() =>
  colorMode.value === 'dark' ? 'rgba(241, 245, 249, 0.55)' : 'rgba(30, 41, 59, 0.45)'
)

function vehicleAtStop(stopSourceId: string, dirId: number) {
  return liveVehicles.value.find(v => v.sid === stopSourceId && v.d === dirId) || null
}

let liveWsIntentionalClose = false
let liveWsReconnectTimer: ReturnType<typeof setTimeout> | null = null

function connectLiveWS() {
  if (!import.meta.client) return
  const dsId = routeData.value?.data_source_id
  const sourceId = routeData.value?.source_id
  if (!dsId || !sourceId) return

  liveWsIntentionalClose = false
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/v1/transit/`)
  liveWs = ws

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'subscribe_route', ds_id: dsId, route_source_id: sourceId }))
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'route_vehicles' || msg.type === 'route_live') {
        liveStopIds.value = msg.stop_ids || []
        liveVehicles.value = msg.vehicles || []
        reconcileVehiclePulses(liveVehicles.value)
        if (msg.etas) {
          // Convert string keys to numbers: {"0": {...}} → {0: {...}}
          const parsed: Record<number, Record<string, number>> = {}
          for (const [k, v] of Object.entries(msg.etas)) {
            parsed[Number(k)] = v as Record<string, number>
          }
          allEtas.value = parsed
        }
      }
    } catch {}
  }

  ws.onclose = () => {
    liveWs = null
    if (!liveWsIntentionalClose) {
      scheduleLiveWsReconnect()
    }
  }
}

function scheduleLiveWsReconnect(delayMs = 3000) {
  if (liveWsReconnectTimer) clearTimeout(liveWsReconnectTimer)
  if (liveWsIntentionalClose) return
  liveWsReconnectTimer = setTimeout(() => {
    liveWsReconnectTimer = null
    if (!liveWsIntentionalClose) connectLiveWS()
  }, delayMs)
}

function onLiveWsVisibilityChange() {
  if (document.visibilityState !== 'visible') return
  // Schedule data aged in the background (refresh timer is visibility-gated)
  loadSchedule()
  if (!liveWs || liveWs.readyState === WebSocket.CLOSED || liveWs.readyState === WebSocket.CLOSING) {
    scheduleLiveWsReconnect(0)
  }
}

onMounted(() => {
  isMounted.value = true
  loadSchedule()
  startScheduleRefresh()
  connectLiveWS()
  document.addEventListener('visibilitychange', onLiveWsVisibilityChange)
  document.addEventListener('click', onVariantsDocClick)
  document.addEventListener('keydown', onVariantsDocKey)

  // Lazy mini-map: create when container enters viewport
  if (miniMapEl.value) {
    miniMapObserver = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !miniMapCreated) createMiniMap()
      },
      { rootMargin: '200px' }
    )
    miniMapObserver.observe(miniMapEl.value)
  }
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onLiveWsVisibilityChange)
  document.removeEventListener('click', onVariantsDocClick)
  document.removeEventListener('keydown', onVariantsDocKey)
  liveWsIntentionalClose = true
  if (scheduleRefreshTimer) clearInterval(scheduleRefreshTimer)
  if (liveWsReconnectTimer) clearTimeout(liveWsReconnectTimer)
  liveWs?.close()
  liveWs = null
  miniMapObserver?.disconnect()
  miniMapObserver = null
  if (miniMap) { miniMap.remove(); miniMap = null }
})

// ── Tickets ──
const ticketTypes = ref<any[]>([])
const buyingTicketId = ref<string | null>(null)
const buyingTicketType = ref<any | null>(null)
const qrTicket = ref<any | null>(null)
const authStore = useAuthStore()

async function loadTicketTypes() {
  if (!routeData.value?.id) return
  try {
    const data = await $fetch<any[]>(`/api/v1/tickets/types/`, {
      params: { route_id: routeData.value.id },
    })
    ticketTypes.value = data || []
  } catch {}
}

function startBuy(tt: any) {
  if (!tt.operator_ln_address && !tt.operator_spark_address) {
    alert(t('tickets.error_no_ln_address'))
    return
  }
  buyingTicketId.value = tt.id
  buyingTicketType.value = tt
}

function onPurchased() {
  loadTicketTypes()
}

watch(() => routeData.value, () => loadTicketTypes(), { immediate: true })

function showRouteOnMap(e?: MouseEvent) {
  // Zoom +/- buttons live inside the clickable mini-map wrapper
  if ((e?.target as HTMLElement)?.closest('.maplibregl-ctrl')) return
  if (!routeData.value) return
  ;(window as any)._transitRouteData = routeData.value
  const c = routeCenter.value
  router.push(localePath(`/map?lat=${c.lat}&lng=${c.lon}&zoom=13&transit=1&routeCity=${city}&routeSlug=${slug}&returnTo=${encodeURIComponent(route.fullPath)}`))
}

// ── Mini-Map ──
const miniMapEl = ref<HTMLElement | null>(null)
let miniMap: any = null
let miniMapGl: any = null         // cached maplibre-gl module (needed when rebuilding overlays)
let miniMapCreated = false
let miniMapObserver: IntersectionObserver | null = null

const getMiniMapStyle = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function createMiniMap() {
  if (miniMapCreated || !miniMapEl.value || !routeData.value) return
  miniMapCreated = true

  const mod = await import('maplibre-gl')
  miniMapGl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const c = routeCenter.value
  miniMap = new miniMapGl.Map({
    container: miniMapEl.value,
    style: getMiniMapStyle(),
    center: [c.lon, c.lat],
    zoom: 12,
    interactive: false,
    attributionControl: false,
    trackResize: false,
    fadeDuration: 0,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })
  miniMap.addControl(new miniMapGl.NavigationControl({ showCompass: false }), 'top-right')

  miniMap.once('load', () => { buildMiniMapOverlays() })
}

// Builds (or rebuilds) all overlay sources/layers on the mini-map. Called once
// on initial load, and again after a setStyle() on theme toggle — setStyle wipes
// every custom source/layer/image, so the route line, stops and vehicles must be
// re-added or the map goes blank under the new basemap.
async function buildMiniMapOverlays() {
  if (!miniMap || !miniMapGl || !routeData.value) return
  miniMap.resize()

  const routeColor = `#${resolveColor(routeData.value)}`

  // Route line, with a casing under it so it stays legible whatever the
  // route color: many feeds ship no route_color → default bus yellow, which
  // is invisible on the light map style. Casing contrasts with the basemap
  // (dark on light theme, light on dark) — a fixed casing would itself hide
  // a same-toned route color (e.g. dark metro line on the dark theme).
  const lineCasing = colorMode.value === 'dark' ? '#f1f5f9' : '#1e293b'
  const geom = routeData.value?.geometry
  if (geom) {
    miniMap.addSource('route-line', {
      type: 'geojson',
      data: { type: 'Feature', geometry: geom, properties: {} },
    })
    miniMap.addLayer({
      id: 'route-line-casing',
      type: 'line',
      source: 'route-line',
      paint: { 'line-color': lineCasing, 'line-width': 6, 'line-opacity': 0.9 },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })
    miniMap.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route-line',
      paint: { 'line-color': routeColor, 'line-width': 3, 'line-opacity': 1 },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })
  }

  // Stop circles
  const stops = routeData.value?.stops
  if (stops?.length) {
    miniMap.addSource('route-stops', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: stops.map((s: any) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
          properties: {},
        })),
      },
    })
    miniMap.addLayer({
      id: 'route-stops',
      type: 'circle',
      source: 'route-stops',
      paint: {
        'circle-radius': 3,
        'circle-color': routeColor,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': lineCasing,
      },
    })

    // Fit bounds
    const bounds = new miniMapGl.LngLatBounds()
    stops.forEach((s: any) => bounds.extend([s.lon, s.lat]))
    miniMap.fitBounds(bounds, { padding: 20, duration: 0 })
  }

  // Vehicle icons: same yellow transit-type SVG as /map, no backdrop.
  // Above — direction status dot (colors fixed regardless of route color: 0=outbound blue, 1=inbound orange).
  // Below — route-color bar (route identity). All sizes are 2x rasters drawn at icon-size 0.5 for retina.
  const iconName = _resolveTransitIcon(routeData.value?.route_type ?? 3)
  await _loadMiniMapIcon(miniMap, `mini-${iconName}`, `/img/transit/${iconName}.svg`, 64)
  _addRouteBarImage(miniMap, 'mini-route-bar', routeColor)
  miniMap.addSource('route-vehicles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  // Route-color bar under the icon (32x3 rendered, pure color — no outline)
  miniMap.addLayer({
    id: 'route-vehicles-bar',
    type: 'symbol',
    source: 'route-vehicles',
    layout: {
      'icon-image': 'mini-route-bar',
      'icon-size': 0.5,
      'icon-offset': [0, 39],
      'icon-rotation-alignment': 'viewport',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
  miniMap.addLayer({
    id: 'route-vehicles-icon',
    type: 'symbol',
    source: 'route-vehicles',
    layout: {
      'icon-image': `mini-${iconName}`,
      'icon-size': 0.5,
      'icon-rotation-alignment': 'viewport',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
  // Direction status dot above the icon (clears its top edge). Only for routes
  // with more than one direction — on a single-direction route (loop/circular)
  // the dot disambiguates nothing, so it's omitted as noise above the bus.
  if (directionViews.value.length > 1) {
    miniMap.addLayer({
      id: 'route-vehicles-dir',
      type: 'circle',
      source: 'route-vehicles',
      paint: {
        'circle-radius': 5,
        'circle-translate': [0, -23],
        'circle-translate-anchor': 'viewport',
        'circle-color': ['case', ['==', ['get', 'dir'], 0], DIR_DOT_COLORS[0], DIR_DOT_COLORS[1]],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
      },
    })
  }
  updateMiniMapVehicles()
}

// Fixed direction colors (colorblind-safe pair): 0 = outbound, 1 = inbound
const DIR_DOT_COLORS: Record<number, string> = { 0: '#2563eb', 1: '#f97316' }

const _ROUTE_TYPE_ICON: Record<number, string> = {
  0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry',
  7: 'train', 11: 'trolleybus', 200: '2bus', 1100: 'airplane', 1501: 'bus-taxi',
}
function _resolveTransitIcon(rt: number): string {
  if (_ROUTE_TYPE_ICON[rt]) return _ROUTE_TYPE_ICON[rt]
  if (rt >= 200 && rt <= 299) return '2bus'
  if (rt >= 900 && rt <= 999) return 'tram'
  if (rt >= 100 && rt <= 199) return 'train'
  if (rt >= 400 && rt <= 499) return 'metro'
  if (rt >= 700 && rt <= 799) return 'bus'
  return 'bus'
}

// 64x6 raster: route-color bar (= 32x3 at icon-size 0.5)
function _addRouteBarImage(map: any, id: string, color: string) {
  if (map.hasImage(id)) return
  const canvas = document.createElement('canvas')
  canvas.width = 64; canvas.height = 6
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = color
  ctx.fillRect(0, 0, 64, 6)
  const data = ctx.getImageData(0, 0, 64, 6)
  map.addImage(id, { width: 64, height: 6, data: new Uint8Array(data.data.buffer) })
}

function _loadMiniMapIcon(map: any, id: string, url: string, size: number): Promise<void> {
  return new Promise(resolve => {
    if (map.hasImage(id)) { resolve(); return }
    const img = new Image(size, size)
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = size; canvas.height = size
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, size, size)
      const data = ctx.getImageData(0, 0, size, size)
      map.addImage(id, { width: size, height: size, data: new Uint8Array(data.data.buffer) })
      resolve()
    }
    img.onerror = () => resolve()
    img.src = url
  })
}

function updateMiniMapVehicles() {
  if (!miniMap || !miniMap.getSource('route-vehicles')) return
  const geojson = {
    type: 'FeatureCollection' as const,
    features: liveVehicles.value.map((v: any) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [v.lon, v.lat] },
      properties: { dir: v.d ?? 0 },
    })),
  }
  ;(miniMap.getSource('route-vehicles') as any).setData(geojson)
}

watch(liveVehicles, updateMiniMapVehicles)

watch(() => colorMode.value, () => {
  if (!miniMap) return
  // setStyle drops every custom source/layer/image — re-add the overlays once
  // the new basemap finishes loading, else the route vanishes on theme toggle.
  miniMap.once('style.load', () => { buildMiniMapOverlays() })
  miniMap.setStyle(getMiniMapStyle())
})
</script>

<style scoped>
/* Stop-hop pulse keyframes are global (assets/css/main.css) — shared with the
   stop page. The ring/pop classes are applied in the template above. */
.mini-map-inner {
  width: 100%;
  height: 100%;
}

.mini-map-inner :deep(.maplibregl-ctrl-bottom-left),
.mini-map-inner :deep(.maplibregl-ctrl-bottom-right) {
  display: none;
}
</style>
