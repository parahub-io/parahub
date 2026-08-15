<template>
  <IoTDeviceSection :title="$t('iot.telemetry')" :help="$t('iot.section_telemetry_help')" :icon="Activity">
    <template #actions>
      <div class="flex items-center gap-2 shrink-0">
        <UiTabs v-model="range" :tabs="rangeTabs" variant="pills" />
        <UiButton
          variant="ghost" size="sm" :icon="Download" icon-only :loading="csvBusy"
          :aria-label="$t('iot.export_csv')" :title="$t('iot.export_csv')" @click="downloadCsv"
        />
      </div>
    </template>

    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('iot.loading') }}</span>
    </div>

    <p v-else-if="!points.length" class="text-sm text-neutral-500 dark:text-neutral-400">
      {{ $t('iot.telemetry_empty') }}
    </p>

    <div v-else>
      <div class="text-xs text-neutral-400 dark:text-neutral-500 mb-1">{{ $t('iot.chart_uplink') }}</div>
      <UiTimeChart :series="uplinkSeries" :format="fmtBps" :height="140" />

      <template v-if="clientsSeries">
        <div class="text-xs text-neutral-400 dark:text-neutral-500 mt-4 mb-1">{{ $t('iot.chart_clients') }}</div>
        <UiTimeChart :series="clientsSeries" :height="100" :format="fmtCount" />
      </template>

      <!-- Availability strip: one cell per bucket, filled where a heartbeat landed -->
      <div class="mt-4 flex gap-px h-2 rounded overflow-hidden">
        <div
          v-for="(b, i) in availability" :key="i" class="flex-1"
          :class="b ? 'bg-success/80' : 'bg-neutral-200 dark:bg-neutral-700'"
        />
      </div>
      <div class="flex justify-between text-[10px] text-neutral-400 dark:text-neutral-500 mt-1">
        <span>−{{ hours === 24 ? $t('iot.range_24h') : $t('iot.range_7d') }}</span>
        <span>{{ $t('iot.availability') }}</span>
        <span>{{ $t('iot.now') }}</span>
      </div>
    </div>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Activity, Download, Loader2 } from 'lucide-vue-next'
import { saveFile } from '~/utils/download'
import type { TimeChartSeries } from '~/components/ui/TimeChart.vue'

interface Props {
  deviceId: string
  deviceName: string
}

const props = defineProps<Props>()

const { t } = useI18n()
const { fmtBps } = useIoT()
const authStore = useAuthStore()
const toastStore = useToastStore()

// Two windows, matching what the stats endpoint keeps at raw resolution
const range = ref('24')
const rangeTabs = computed(() => [
  { id: '24', label: t('iot.range_24h') },
  { id: '168', label: t('iot.range_7d') },
])
const hours = computed(() => Number(range.value))
const points = ref<any[]>([])
const loading = ref(true)
const csvBusy = ref(false)

const fmtCount = (v: number) => String(Math.round(v))

async function load() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>(`/api/v1/iot/devices/${props.deviceId}/stats`, {
      params: { hours: hours.value },
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    points.value = res?.points || []
  } catch {
    points.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(hours, load)

const uplinkSeries = computed<TimeChartSeries[]>(() => [
  { key: 'rx', label: `↓ ${t('iot.series_down')}`, points: points.value.map(p => ({ t: Date.parse(p.t), v: p.wan_rx_bps })) },
  { key: 'tx', label: `↑ ${t('iot.series_up')}`, points: points.value.map(p => ({ t: Date.parse(p.t), v: p.wan_tx_bps })) },
])

const clientsSeries = computed<TimeChartSeries[] | null>(() => {
  const wifi = points.value.map(p => ({ t: Date.parse(p.t), v: p.wifi_clients }))
  const guest = points.value.map(p => ({ t: Date.parse(p.t), v: p.guest_clients }))
  if (!wifi.some(p => p.v != null) && !guest.some(p => p.v != null)) return null
  return [
    { key: 'wifi', label: t('iot.series_wifi'), points: wifi },
    { key: 'guest', label: t('iot.series_guest'), points: guest },
  ]
})

const availability = computed(() => {
  const n = hours.value === 24 ? 48 : 84
  const end = Date.now()
  const start = end - hours.value * 3600_000
  const out: boolean[] = new Array(n).fill(false)
  for (const p of points.value) {
    const i = Math.floor(((Date.parse(p.t) - start) / (end - start)) * n)
    if (i >= 0 && i < n) out[i] = true
  }
  return out
})

async function downloadCsv() {
  if (csvBusy.value) return
  csvBusy.value = true
  try {
    await authStore.ensureToken()
    const res = await fetch(`/api/v1/iot/devices/${props.deviceId}/stats.csv?hours=720`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (!res.ok) throw new Error(String(res.status))
    await saveFile(await res.blob(), `${props.deviceName.replace(/[^\w-]+/g, '_')}-telemetry-30d.csv`)
  } catch {
    toastStore.error(t('iot.export_failed'))
  } finally {
    csvBusy.value = false
  }
}
</script>
