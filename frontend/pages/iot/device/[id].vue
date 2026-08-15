<template>
  <div>
    <Head>
      <Title>{{ device?.name || '...' }} - Parahub</Title>
    </Head>

    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <NuxtLink
        :to="localePath({ path: '/iot', query: { tab: backTab } })"
        class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 mb-4"
      >
        <ArrowLeft class="w-4 h-4" aria-hidden="true" />
        {{ $t('iot.hub_title') }}
      </NuxtLink>

      <div v-if="(!loaded && !device) || leaving" class="py-12 text-center" role="status">
        <div class="h-12 w-12 mx-auto rounded-full border-4 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 animate-spin" />
        <span class="sr-only">{{ $t('iot.loading') }}</span>
      </div>

      <div v-else-if="!device" class="py-12 text-center">
        <img src="/images/para/puzzled.webp" alt="Para" class="mx-auto h-32 w-auto mb-3" />
        <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('iot.device_not_found') }}</h3>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('iot.device_not_found_hint') }}</p>
      </div>

      <div v-else class="space-y-4">
        <!-- ═══ Identity + readout ═══
             Vital signs only. Anything long enough to be pasted somewhere (MAC,
             Yggdrasil, mesh IP) is an identifier, not a reading, and lives in
             the passport card under Overview. -->
        <section class="card p-4">
          <div class="flex items-start gap-4">
            <img :src="illustration" alt="" class="hidden sm:block h-24 w-auto shrink-0" />
            <div class="min-w-0 flex-1">
              <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 break-words">{{ device.name }}</h1>

              <div class="flex items-center gap-1.5 mt-1" role="status">
                <span class="w-2.5 h-2.5 rounded-full" :class="statusColor" aria-hidden="true" />
                <span class="text-sm text-neutral-500 dark:text-neutral-400">{{ status.text }}</span>
              </div>

              <div class="flex items-center gap-1.5 flex-wrap mt-2">
                <UiBadge variant="neutral" type="soft" size="sm">{{ getDeviceTypeLabel(device.device_type) }}</UiBadge>
                <UiBadge v-if="roleLabel" variant="secondary" type="soft" size="sm">{{ roleLabel }}</UiBadge>
                <UiBadge v-if="vpnPill" :variant="vpnPill.variant" type="soft" size="sm">{{ vpnPill.label }}</UiBadge>
                <UiBadge v-if="device.ygg_inbound_ok === false" variant="error" type="soft" size="sm" :title="$t('iot.ssh_unreachable_hint')">
                  {{ $t('iot.ssh_unreachable') }}
                </UiBadge>
                <NuxtLink v-if="device.property_id && propertyName" :to="localePath(`/iot/${device.property_id}`)" class="chip">
                  <Home class="w-3 h-3" aria-hidden="true" /> {{ propertyName }}
                </NuxtLink>
                <span v-if="device.owner_name" class="chip" :title="device.owner_hna || undefined">
                  <Users class="w-3 h-3" aria-hidden="true" /> {{ $t('iot.shared_by', { name: device.owner_name }) }}
                </span>
                <NuxtLink v-if="keepsHostPass" :to="localePath('/free')" class="chip" :title="$t('iot.host_pass_hint')">
                  <Gauge class="w-3 h-3" aria-hidden="true" /> {{ $t('iot.host_pass') }}
                </NuxtLink>
              </div>
            </div>
          </div>

          <UiAlert v-if="hasFirmwareUpdate" variant="warning" :icon="ArrowUpCircle" class="mt-4">
            <div class="font-medium">
              {{ $t('iot.firmware') }}:
              {{ $t('iot.firmware_update_banner', { current: device.connection_info?.firmware_version, latest: device.latest_firmware_version }) }}
            </div>
            <div class="text-sm opacity-90 mt-0.5">{{ $t('iot.firmware_update_help') }}</div>
          </UiAlert>

          <!-- Instrument cluster (design-system § Profile console, readout): the
               value is the strongest text, the caption a mono micro-label. One
               row of equal columns sized to its content: a device reports three
               of these at most, so stretching them across the card would read as
               a banner, and wrapping them can't leave a hairline-coloured hole. -->
          <div
            v-if="readout.length"
            class="mt-4 w-fit max-w-full grid grid-flow-col auto-cols-fr gap-px bg-neutral-300 dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-700 rounded-xl overflow-hidden"
          >
            <div
              v-for="cell in readout" :key="cell.key" :title="cell.title"
              class="min-w-0 bg-white dark:bg-neutral-900 px-3 py-2.5 flex flex-col items-center justify-start gap-1"
            >
              <span class="text-base font-bold tabular-nums text-neutral-900 dark:text-neutral-100 leading-none text-center">{{ cell.value }}</span>
              <span class="text-[9px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400 text-center leading-tight">{{ cell.label }}</span>
            </div>
          </div>
        </section>

        <!-- ═══ Console ═══
             Every capability of this device at once, grouped by what it touches,
             instead of a kebab that hid them and a stack that shouted all their
             help text simultaneously. Tiles open a section; nothing here
             reconfigures the router on a single tap. -->
        <div class="flex flex-wrap gap-3 items-start">
          <UiTileMatrix
            v-for="group in consoleGroups"
            :key="group.id"
            :groups="[group]"
            fill="secondary"
            class="flex-1 min-w-[200px] max-w-[340px]"
            @pick="pick"
          />
        </div>

        <!-- ═══ The open section ═══
             Keyed on the section AND the visit counter: switching remounts (so
             the router is re-read), and `app.vue` KeepAlives every page, so
             coming back bumps `visit` and remounts too. -->
        <div :key="`${active}:${visit}`" class="space-y-4">
          <template v-if="active === 'overview'">
            <IoTDeviceSection :title="$t('iot.section_location')" :help="locationHelp" :icon="MapPin">
              <template v-if="canManage && device.device_type === 'MESH_ROUTER'" #actions>
                <UiButton variant="ghost" size="sm" :icon="MapPinned" class="shrink-0" @click="showLocationPicker = true">
                  {{ hasMap ? $t('iot.change_location') : $t('mesh.set_location') }}
                </UiButton>
              </template>

              <div v-if="hasMap" class="relative rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-700">
                <IoTStaticMapPreview :latitude="lat!" :longitude="lng!" :height="220" :zoom="15" hide-marker />
                <IoTSnapshotMarker :fill="markerFill" :glyph="markerGlyph" />
              </div>
              <p v-else class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ isPlacedNode ? $t('mesh.no_location') : $t('iot.no_location') }}
              </p>
            </IoTDeviceSection>

            <!-- Identifiers. Each one carries a copy button: they are what you
                 paste into an SSH client or quote to support. -->
            <IoTDeviceSection v-if="passport.length" :title="$t('iot.section_passport')" :help="$t('iot.section_passport_help')" :icon="Fingerprint">
              <dl class="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                <div v-for="f in passport" :key="f.label" class="flex justify-between gap-2 text-sm border-b border-neutral-200 dark:border-neutral-700 py-1">
                  <dt class="text-neutral-500 dark:text-neutral-400 shrink-0">{{ f.label }}</dt>
                  <dd class="min-w-0 flex items-center gap-1">
                    <span :class="f.mono ? 'font-mono text-xs' : ''" class="text-neutral-900 dark:text-neutral-100 truncate" :title="f.value">
                      {{ f.value }}
                    </span>
                    <button v-if="f.copy" class="copy-btn" :aria-label="$t('iot.copy')" @click="copy(f.value)">
                      <Copy class="w-3.5 h-3.5" aria-hidden="true" />
                    </button>
                  </dd>
                </div>
              </dl>
            </IoTDeviceSection>

            <!-- ═══ What this box actually does ═══ -->
            <section v-if="device.device_type === 'MESH_ROUTER'" class="card p-4">
              <div class="flex items-start gap-4">
                <img src="/images/para/reading.webp" alt="Para" class="hidden sm:block h-24 w-auto shrink-0" />
                <div class="min-w-0">
                  <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('iot.how_it_works') }}</h2>
                  <ul class="mt-2 space-y-1.5 text-sm text-neutral-600 dark:text-neutral-400">
                    <li v-for="line in howItWorks" :key="line" class="flex gap-2">
                      <span class="text-secondary dark:text-secondary-400" aria-hidden="true">·</span>
                      <span>{{ line }}</span>
                    </li>
                  </ul>
                  <div class="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm">
                    <NuxtLink :to="localePath('/mesh')" class="text-link">{{ $t('mesh.technical_docs') }}</NuxtLink>
                    <a href="/print/mesh.html" target="_blank" rel="noopener noreferrer" class="text-link">{{ $t('mesh.print_sheet') }}</a>
                    <NuxtLink :to="localePath('/mesh/peering')" class="text-link">{{ $t('mesh.free_peering_link') }}</NuxtLink>
                  </div>
                </div>
              </div>
            </section>
          </template>

          <IoTDeviceAccessSection
            v-else-if="active === 'access'"
            :device-id="device.id"
            :firmware-role="firmwareRole"
            :current-ssid="device.connection_info?.private_ssid"
          />

          <IoTDeviceNetworkSection v-else-if="active === 'network'" :device-id="device.id" :firmware-role="firmwareRole" />

          <IoTDeviceVpnSection v-else-if="active === 'vpn'" :device-id="device.id" />

          <IoTDeviceYggSection v-else-if="active === 'ygg'" :device-id="device.id" />

          <IoTDeviceTelemetrySection v-else-if="active === 'telemetry'" :device-id="device.id" :device-name="device.name" />

          <IoTDeviceDiagnosticsSection v-else-if="active === 'diagnostics'" :device-id="device.id" :firmware-role="firmwareRole" />

          <IoTDeviceSharingSection v-else-if="active === 'sharing'" :device-id="device.id" @detached="leave" />

          <IoTDeviceActivitySection v-else-if="active === 'activity'" :device-id="device.id" />

          <IoTDeviceSettingsSection
            v-else-if="active === 'settings'"
            :device="device"
            :can-manage="canManage"
            :is-owner="isOwner"
            @deleted="leave"
          />
        </div>
      </div>
    </div>

    <IoTLocationPickerModal
      v-if="showLocationPicker && device"
      :device-id="device.id"
      :initial-lat="lat ?? undefined"
      :initial-lng="lng ?? undefined"
      :marker-fill="markerFill"
      :marker-glyph="markerGlyph"
      @close="showLocationPicker = false"
      @saved="showLocationPicker = false"
    />
  </div>
</template>

<script setup lang="ts">
import {
  Activity, ArrowLeft, ArrowUpCircle, Copy, Fingerprint, Gauge, Globe, Home, Info,
  KeyRound, MapPin, MapPinned, Network, ScrollText, Settings, Shield, Stethoscope, Users,
} from 'lucide-vue-next'
import type { TileGroup } from '~/components/ui/TileMatrix.vue'
import { NAVIGATION_GLYPH } from '~/composables/useMapToggleableLayer'

definePageMeta({ middleware: 'auth' })

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

const store = useIoTStore()
const propertyStore = usePropertyStore()
const toastStore = useToastStore()
const {
  getDeviceTypeLabel, getDeviceStatus, getHardwareName,
  formatDate, formatRelativeShort, formatUptime, getBatteryInfo, getSpeedInfo,
} = useIoT()

const deviceId = computed(() => route.params.id as string)
const device = computed(() => store.getDeviceById(deviceId.value))

// Delete and transfer drop the device from the store; the redirect is queued in
// the same tick, so this keeps the "not found" state from flashing on the way out.
const leaving = ref(false)
const showLocationPicker = ref(false)

// Token-authed, so the fetch is client-only — and `loaded` has to be a plain ref
// rather than an async-data `pending`: the server must render the same branch the
// client renders on its first paint (the spinner), or hydration mismatches on the
// "not found" markup. Arriving from the device list, the store already holds the
// device, so the content shows at once and this only refreshes it.
const loaded = ref(false)

async function load() {
  await Promise.all([
    store.getDevice(deviceId.value).catch(() => null),
    propertyStore.properties.length ? Promise.resolve() : propertyStore.fetchProperties(),
  ])
  loaded.value = true
}

// `app.vue` KeepAlives every page and its prop overrides `definePageMeta`, so
// coming back here reuses the cached instance and no child ever re-runs
// `onMounted`. The page's own `onActivated` DOES fire (its parent is the
// KeepAlive itself, unlike its children — verified against the network log), so
// it bumps `visit`, which keys the open section and remounts it: every return
// re-reads the router instead of redisplaying what it said last time.
const visit = ref(0)
let booted = false

onActivated(() => {
  if (booted) visit.value++
  booted = true
  load()
})

watch(deviceId, () => { loaded.value = false; load() })

const accessRole = computed(() => device.value?.access_role || 'OWNER')
const isOwner = computed(() => accessRole.value === 'OWNER')
const canManage = computed(() => accessRole.value !== 'VIEWER')
const firmwareRole = computed(() => device.value?.connection_info?.firmware_role)

const status = computed(() => (device.value ? getDeviceStatus(device.value) : { status: 'never', text: '' }))
const STATUS_COLORS: Record<string, string> = {
  online: 'bg-green-500', recent: 'bg-yellow-500', offline: 'bg-red-500', never: 'bg-neutral-400',
}
const statusColor = computed(() => STATUS_COLORS[status.value.status] || 'bg-neutral-400')

// Held in a ref, not derived: deleting or transferring the device empties the
// store row, and the back link still has to point at the tab we came from.
const backTab = ref('network')
watch(device, (d) => {
  if (!d) return
  backTab.value = d.device_type === 'TRACKER' ? 'trackers'
    : d.device_type === 'SENSOR' || d.device_type === 'ACTUATOR' ? 'sensors'
      : 'network'
}, { immediate: true })

const ILLUSTRATIONS: Record<string, string> = {
  MESH_ROUTER: '/images/iot/network.webp',
  GATEWAY: '/images/iot/network.webp',
  TRACKER: '/images/iot/tracker.webp',
  SENSOR: '/images/iot/station.webp',
  ACTUATOR: '/images/iot/station.webp',
}
const illustration = computed(() => ILLUSTRATIONS[device.value?.device_type || ''] || '/images/iot/object.webp')

const roleLabel = computed(() => {
  if (device.value?.device_type !== 'MESH_ROUTER') return null
  if (firmwareRole.value === 'bumblebee') return 'Bumblebee'
  if (firmwareRole.value === 'bee') return 'Bee'
  return null
})

const vpnPill = computed(() => {
  if (firmwareRole.value !== 'bumblebee') return null
  const mode = device.value?.connection_info?.vpn_mode
  if (mode === 'vps') return { label: 'VPS', variant: 'secondary' as const }
  if (mode === 'mullvad') return { label: 'Mullvad', variant: 'success' as const }
  if (mode === 'none') return { label: 'No VPN', variant: 'error' as const }
  return null
})

const keepsHostPass = computed(() => !!device.value?.keeps_host_pass && status.value.status === 'online')

// A mesh node is put somewhere by its owner and lands on the coverage map; a
// tracker just reports where it is. Same section, two different meanings.
const isPlacedNode = computed(() =>
  device.value?.device_type === 'MESH_ROUTER' || device.value?.device_type === 'GATEWAY')
const locationHelp = computed(() =>
  isPlacedNode.value ? t('iot.section_location_help') : t('iot.section_location_help_reported'))

const propertyName = computed(() =>
  propertyStore.properties.find(p => p.id === device.value?.property_id)?.name)

const hasFirmwareUpdate = computed(() => {
  const d = device.value
  if (!d || d.device_type !== 'MESH_ROUTER') return false
  const current = d.connection_info?.firmware_version
  const latest = d.latest_firmware_version
  return !!current && !!latest && current !== latest
})

// Map viewport — mesh routers carry an owner-set position, trackers a live fix
const lat = computed(() => device.value?.latitude ?? device.value?.connection_info?.latitude ?? null)
const lng = computed(() => device.value?.longitude ?? device.value?.connection_info?.longitude ?? null)
const hasMap = computed(() => lat.value != null && lng.value != null)

const MARKER_STATUS_FILLS: Record<string, string> = {
  online: '#4E4EC8', recent: '#a3a3a3', never: '#a3a3a3', offline: '#ef4444',
}
const markerFill = computed(() => MARKER_STATUS_FILLS[status.value.status] || '#a3a3a3')
const markerGlyph = computed(() => {
  if (device.value?.device_type === 'MESH_ROUTER') return 'wifi' as const
  if (device.value?.device_type === 'TRACKER') return NAVIGATION_GLYPH
  return null
})

// ── Readout ──────────────────────────────────────────────────────────────────
// Scalars a glance can take in. Client and neighbour counts are deliberately
// absent: the payload carries `mesh_originators` (every MAC seen multi-hop, two
// per node) and `guest_leases` (terminator nodes only), so neither is a number
// this page could label honestly.
const readout = computed(() => {
  const d = device.value
  if (!d) return []
  const info = d.connection_info
  const out: { key: string; label: string; value: string; title?: string }[] = []

  if (info?.firmware_version) out.push({ key: 'fw', label: t('iot.firmware'), value: info.firmware_version })
  if (info?.uptime) out.push({ key: 'up', label: t('iot.uptime'), value: formatUptime(info.uptime) })
  if (d.speed != null) out.push({ key: 'speed', label: t('iot.speed'), value: getSpeedInfo(d.speed) })
  if (d.battery_level != null) out.push({ key: 'bat', label: t('iot.battery'), value: getBatteryInfo(d.battery_level).level })
  if (d.last_seen) {
    out.push({
      key: 'seen',
      label: t('iot.cap_seen'),
      value: formatRelativeShort(d.last_seen),
      title: formatDate(d.last_seen),
    })
  }
  return out
})

interface Fact { label: string; value: string; mono?: boolean; copy?: boolean }

const passport = computed<Fact[]>(() => {
  const d = device.value
  if (!d) return []
  const info = d.connection_info
  const out: Fact[] = []

  if (info?.hardware_profile && info.hardware_profile !== 'unknown') {
    out.push({ label: t('iot.hardware'), value: getHardwareName(info.hardware_profile) })
  }
  if (d.imei) out.push({ label: 'IMEI', value: d.imei, mono: true, copy: true })
  if (d.device_id) out.push({ label: 'MAC', value: d.device_id, mono: true, copy: true })
  if (info?.yggdrasil_address && !['unknown', 'none'].includes(info.yggdrasil_address)) {
    out.push({ label: 'Yggdrasil', value: info.yggdrasil_address, mono: true, copy: true })
  }
  if (info?.mesh_ip && info.mesh_ip !== 'unknown') {
    out.push({ label: 'Mesh IP', value: info.mesh_ip, mono: true, copy: true })
  }
  return out
})

// ── Console ──────────────────────────────────────────────────────────────────
// Grouped by what a tile touches: the device as a possession, the network it
// runs, how it is doing. A group whose tiles are all gated away disappears
// whole, so a viewer or a `bee` sees a smaller console, never an empty frame.
const baseGroups = computed<TileGroup[]>(() => {
  const d = device.value
  if (!d) return []
  const mesh = d.device_type === 'MESH_ROUTER'
  const gateway = firmwareRole.value === 'bumblebee'
  const manage = canManage.value

  const groups: TileGroup[] = [
    {
      id: 'device',
      label: t('iot.group_device'),
      items: [
        { id: 'overview', icon: Info, label: t('iot.tile_overview') },
        { id: 'sharing', icon: Users, label: t('iot.sharing_title') },
        // Readable at every role on purpose: the owner sees what a helper
        // changed, and the helper sees that the record is not private.
        { id: 'activity', icon: ScrollText, label: t('iot.activity_title') },
        // Rename, map attribution and removal are all manager-or-owner gated,
        // so for a viewer the section would render an empty card.
        ...(manage ? [{ id: 'settings', icon: Settings, label: t('iot.tile_settings') }] : []),
      ],
    },
    {
      id: 'connection',
      label: t('iot.group_connection'),
      items: [
        // Both password endpoints are MANAGER+, and guest shaping / uplink
        // budgets exist only on the L3 gateway role.
        ...(mesh && manage ? [{ id: 'access', icon: KeyRound, label: t('iot.tile_access') }] : []),
        ...(mesh && manage ? [{ id: 'network', icon: Network, label: t('iot.tile_network') }] : []),
        ...(mesh && manage && gateway ? [{ id: 'vpn', icon: Shield, label: 'VPN' }] : []),
        ...(mesh && manage && gateway ? [{ id: 'ygg', icon: Globe, label: 'Yggdrasil' }] : []),
      ],
    },
    {
      id: 'health',
      label: t('iot.group_health'),
      items: [
        ...(mesh ? [{ id: 'telemetry', icon: Activity, label: t('iot.telemetry') }] : []),
        ...(mesh && manage ? [{ id: 'diagnostics', icon: Stethoscope, label: t('iot.tile_diagnostics') }] : []),
      ],
    },
  ]

  // Column count per frame: three or fewer tiles sit on one row, so the console
  // reads as a band rather than a staircase; only a four-tile group wraps, and
  // it wraps square.
  return groups
    .filter(g => g.items.length)
    .map(g => ({ ...g, cols: g.items.length === 4 ? 2 : Math.min(g.items.length, 3) }))
})

// The open section lives in the URL, so it survives a reload, deep-links, and
// leaves the back button pointing at the device list rather than at the last
// tile that was tapped. An `?s=` a role can't reach falls back to the overview,
// which is what keeps the gating above authoritative.
const sectionIds = computed(() => new Set(
  baseGroups.value.flatMap(g => g.items.map(it => it.id)),
))
const active = computed(() => {
  const s = route.query.s as string | undefined
  return s && sectionIds.value.has(s) ? s : 'overview'
})

// Split from `baseGroups` on purpose: reading `active` inside the builder would
// close the loop groups → active → sectionIds → groups.
const consoleGroups = computed<TileGroup[]>(() => baseGroups.value.map(g => ({
  ...g,
  items: g.items.map(it => ({ ...it, active: it.id === active.value })),
})))

function pick(id: string) {
  const query = { ...route.query }
  if (id === 'overview') delete query.s
  else query.s = id
  router.replace({ query })
}

const howItWorks = computed(() => [
  t('iot.how_private_wifi'),
  t('iot.how_guest_wifi'),
  t('iot.how_mesh'),
  t('iot.how_updates'),
])

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toastStore.success(t('iot.copied'))
  } catch { /* clipboard unavailable */ }
}

function leave() {
  leaving.value = true
  router.push(localePath({ path: '/iot', query: { tab: backTab.value } }))
}
</script>

<style scoped>
.chip {
  @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium;
  @apply bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300;
  @apply hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors;
}

.copy-btn {
  @apply p-1 rounded text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300;
  @apply hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors shrink-0;
}
</style>
