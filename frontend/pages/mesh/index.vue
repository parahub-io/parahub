<template>
  <div class="min-h-screen bg-white dark:bg-neutral-900">
    <!-- Hero -->
    <div class="bg-primary py-16">
      <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <div class="flex items-center justify-center gap-3 mb-4">
          <Radio class="w-10 h-10 text-neutral-900" />
          <h1 class="text-4xl font-bold text-neutral-900">{{ $t('mesh.title') }}</h1>
        </div>
        <p class="text-lg text-neutral-800 max-w-2xl mx-auto mb-2">
          {{ $t('mesh.subtitle') }}
        </p>
        <p class="text-sm text-neutral-700 font-mono">
          {{ $t('mesh.version', { version: firmwareVersion }) }}
        </p>
      </div>
    </div>

    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-12">

      <!-- Benefits -->
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="b in benefits" :key="b.title" class="card p-5">
          <div class="flex items-center gap-2 mb-2">
            <component :is="b.icon" class="w-5 h-5 text-secondary" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100">{{ $t(b.title) }}</h3>
          </div>
          <p class="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">{{ $t(b.desc) }}</p>
        </div>
      </div>

      <!-- Downloads -->
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6 flex items-center gap-2">
          <Download class="w-6 h-6" />
          {{ $t('mesh.downloads') }}
        </h2>

        <div class="space-y-6">
          <div v-for="device in devices" :key="device.id" class="card p-6">
            <div class="flex flex-col sm:flex-row gap-5 mb-4">
              <!-- Device image -->
              <div class="flex-shrink-0 self-center sm:self-start">
                <img
                  :src="device.image"
                  :alt="device.name"
                  class="w-28 h-28 object-contain"
                  loading="lazy"
                />
              </div>

              <!-- Device info -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <h3 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ device.name }}</h3>
                  <UiBadge
                    :variant="device.role === 'bumblebee' ? 'warning' : 'secondary'"
                    type="soft"
                    size="sm"
                  >
                    {{ device.role === 'bumblebee' ? $t('mesh.role_bumblebee') : $t('mesh.role_bee') }}
                  </UiBadge>
                  <UiBadge v-if="device.recommended" variant="success" type="soft" size="sm">
                    {{ $t('mesh.recommended') }}
                  </UiBadge>
                </div>
                <div class="flex flex-wrap gap-3 mt-1 text-sm text-neutral-500 dark:text-neutral-400">
                  <span class="font-mono">{{ device.target }}</span>
                  <span>{{ device.flash }} {{ $t('mesh.flash') }}</span>
                  <span>{{ device.ram }} {{ $t('mesh.ram') }}</span>
                  <span>{{ device.radios }} {{ $t('mesh.radios') }}</span>
                  <span>~{{ device.powerW }} {{ $t('mesh.watts') }}</span>
                </div>
                <p class="mt-1.5 text-sm text-neutral-600 dark:text-neutral-400">
                  {{ $t(`mesh.desc_${device.id}`) }}
                </p>
                <div class="flex items-center gap-3 mt-1.5">
                  <span class="text-lg font-bold text-success dark:text-success">{{ device.price }}</span>
                  <a
                    v-if="device.buyUrl"
                    :href="device.buyUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-sm text-secondary hover:underline flex items-center gap-1"
                  >
                    <ExternalLink class="w-3.5 h-3.5" />
                    {{ $t('mesh.buy') }}
                  </a>
                </div>
              </div>
            </div>

            <div class="grid sm:grid-cols-2 gap-3">
              <a
                v-if="device.factoryUrl"
                :href="device.factoryUrl"
                class="btn-primary flex items-center gap-3 px-4 py-3"
              >
                <Download class="w-5 h-5 flex-shrink-0" />
                <div>
                  <div class="text-sm font-semibold">{{ $t('mesh.factory') }}</div>
                  <div class="text-xs opacity-70">{{ device.factorySize }}</div>
                </div>
              </a>
              <a
                :href="device.sysupgradeUrl"
                :class="[
                  'btn-secondary flex items-center gap-3 px-4 py-3',
                  !device.factoryUrl ? 'sm:col-span-2' : ''
                ]"
              >
                <RefreshCw class="w-5 h-5 flex-shrink-0" />
                <div>
                  <div class="text-sm font-semibold">{{ $t('mesh.sysupgrade') }}</div>
                  <div class="text-xs opacity-70">{{ device.sysupgradeSize }}</div>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>

      <!-- What's Included -->
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Package class="w-6 h-6" />
          {{ $t('mesh.what_included') }}
        </h2>

        <!-- Bumblebee packages -->
        <div class="mb-6">
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
            <UiBadge variant="warning" type="soft">{{ $t('mesh.role_bumblebee') }}</UiBadge>
            <span class="text-sm font-normal text-neutral-500 dark:text-neutral-400">{{ $t('mesh.role_bumblebee_desc') }}</span>
          </h3>
          <ul class="space-y-2">
            <li v-for="pkg in packagesBumblebee" :key="pkg" class="flex items-start gap-2 text-neutral-700 dark:text-neutral-300">
              <Check class="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
              <span>{{ $t(pkg) }}</span>
            </li>
          </ul>
        </div>

        <!-- Bee packages -->
        <div>
          <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
            <UiBadge variant="secondary" type="soft">{{ $t('mesh.role_bee') }}</UiBadge>
            <span class="text-sm font-normal text-neutral-500 dark:text-neutral-400">{{ $t('mesh.role_bee_desc') }}</span>
          </h3>
          <ul class="space-y-2">
            <li v-for="pkg in packagesBee" :key="pkg" class="flex items-start gap-2 text-neutral-700 dark:text-neutral-300">
              <Check class="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
              <span>{{ $t(pkg) }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Energy Transparency -->
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <BatteryCharging class="w-6 h-6" />
          {{ $t('mesh.energy_title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">{{ $t('mesh.energy_desc') }}</p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-neutral-200 dark:border-neutral-700">
                <th class="text-left py-2 pr-4 font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.device') }}</th>
                <th class="text-right py-2 px-4 font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.watts') }}</th>
                <th class="text-right py-2 pl-4 font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.kwh_month') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="device in devices" :key="'energy-' + device.id" class="border-b border-neutral-100 dark:border-neutral-800">
                <td class="py-2 pr-4 text-neutral-700 dark:text-neutral-300">{{ device.name }}</td>
                <td class="py-2 px-4 text-right font-mono text-neutral-600 dark:text-neutral-400">~{{ device.powerW }}</td>
                <td class="py-2 pl-4 text-right font-mono text-neutral-600 dark:text-neutral-400">{{ (device.powerW * 24 * 30.44 / 1000).toFixed(1) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="border-t-2 border-neutral-300 dark:border-neutral-600">
                <td class="py-2 pr-4 font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.energy_total') }}</td>
                <td class="py-2 px-4 text-right font-mono font-bold text-neutral-900 dark:text-neutral-100">~{{ totalPowerW }}</td>
                <td class="py-2 pl-4 text-right font-mono font-bold text-neutral-900 dark:text-neutral-100">{{ totalKwhMonth }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p class="text-xs text-neutral-400 dark:text-neutral-500 mt-3">{{ $t('mesh.energy_note') }}</p>
      </div>

      <!-- Flash Instructions (Tabs) -->
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <HardDrive class="w-6 h-6" />
          {{ $t('mesh.flash_instructions') }}
        </h2>
        <UiTabs v-model="flashTab" :tabs="flashTabs" class="mb-4" />
        <UiAlert v-if="flashTab === 'glinet'" variant="info" :icon="null">{{ $t('mesh.flash_glinet') }}</UiAlert>
        <UiAlert v-else-if="flashTab === 'asus'" variant="warning" :icon="null">{{ $t('mesh.flash_asus') }}</UiAlert>
        <UiAlert v-else-if="flashTab === 'tplink'" variant="error" :icon="null">{{ $t('mesh.flash_tplink') }}</UiAlert>
        <template v-else-if="flashTab === 'cudy'">
          <UiAlert variant="info" :icon="null">{{ $t('mesh.flash_cudy') }}</UiAlert>
          <a
            href="/firmware/cudy_ap3000outdoor-v1-sysupgrade_20251119.bin"
            class="mt-3 inline-flex items-center gap-2 text-sm text-secondary hover:underline"
          >
            <Download class="w-4 h-4 flex-shrink-0" />
            {{ $t('mesh.flash_cudy_mirror') }}
          </a>
        </template>
        <UiAlert v-else-if="flashTab === 'openwrt'" variant="info" :icon="null">{{ $t('mesh.flash_openwrt') }}</UiAlert>
        <p class="mt-4 text-neutral-600 dark:text-neutral-400">
          {{ $t('mesh.after_flash') }}
        </p>
      </div>

      <!-- First Boot -->
      <div>
        <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
          <Zap class="w-6 h-6" />
          {{ $t('mesh.first_boot') }}
        </h2>
        <ol class="space-y-3">
          <li v-for="(step, i) in bootSteps" :key="i" class="flex items-start gap-3 text-neutral-700 dark:text-neutral-300">
            <span class="flex-shrink-0 w-7 h-7 bg-primary/20 rounded-full flex items-center justify-center text-sm font-bold text-neutral-900 dark:text-neutral-100">
              {{ i + 1 }}
            </span>
            <span>{{ $t(step) }}</span>
          </li>
        </ol>
      </div>

      <!-- Speed Upgrade CTA -->
      <NuxtLink
        :to="localePath('/free')"
        class="card block p-6 text-center border-primary hover:border-primary transition-colors group"
      >
        <div class="flex items-center justify-center gap-2 mb-2">
          <Zap class="w-6 h-6 text-primary" />
          <span class="text-xl font-bold text-neutral-900 dark:text-neutral-100">{{ $t('mesh.subscribe_cta') }}</span>
        </div>
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.subscribe_cta_desc') }}</p>
      </NuxtLink>

      <!-- Technical Docs + Source Code -->
      <div class="grid sm:grid-cols-2 gap-4">
        <NuxtLink
          :to="localePath('/docs/mesh')"
          class="card p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors group"
        >
          <div class="flex items-center gap-2 mb-1">
            <BookOpen class="w-5 h-5 text-neutral-400 group-hover:text-secondary" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 group-hover:text-secondary">
              {{ $t('mesh.technical_docs') }}
            </h3>
          </div>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.technical_docs_desc') }}</p>
        </NuxtLink>

        <a
          href="https://git.parahub.io/norn/parahub-mesh"
          target="_blank"
          rel="noopener noreferrer"
          class="card p-5 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors group"
        >
          <div class="flex items-center gap-2 mb-1">
            <Code class="w-5 h-5 text-neutral-400 group-hover:text-secondary" />
            <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 group-hover:text-secondary">
              {{ $t('mesh.source_code') }}
            </h3>
          </div>
          <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('mesh.source_desc') }}</p>
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Radio, Download, RefreshCw, Package, Check, Zap, HardDrive, Code, ExternalLink, BookOpen, Wifi, Shield, Globe, Settings, Coins, BatteryCharging } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()

definePageMeta({
  auth: false,
})

useHead({
  title: computed(() => `${t('mesh.title')} — Parahub`),
})

useSeoMeta({
  description: computed(() => t('mesh.meta_desc')),
  ogTitle: computed(() => `${t('mesh.title')} — Parahub`),
  ogDescription: computed(() => t('mesh.meta_desc')),
})

const firmwareVersion = '25.12.0-ph23'

const benefits = [
  { icon: Wifi, title: 'mesh.benefit_seamless', desc: 'mesh.benefit_seamless_desc' },
  { icon: Globe, title: 'mesh.benefit_free_wifi', desc: 'mesh.benefit_free_wifi_desc' },
  { icon: Shield, title: 'mesh.benefit_privacy', desc: 'mesh.benefit_privacy_desc' },
  { icon: Zap, title: 'mesh.benefit_zero_config', desc: 'mesh.benefit_zero_config_desc' },
  { icon: Settings, title: 'mesh.benefit_remote', desc: 'mesh.benefit_remote_desc' },
  { icon: Coins, title: 'mesh.benefit_earn', desc: 'mesh.benefit_earn_desc' },
]

const devices = [
  {
    id: 'mt6000',
    name: 'GL.iNet GL-MT6000 (Flint 2)',
    target: 'mediatek/filogic',
    flash: '8GB eMMC',
    ram: '1GB',
    radios: '2x WiFi 6',
    role: 'bumblebee',
    recommended: true,
    powerW: 10,
    price: '~\u20AC170',
    buyUrl: 'https://www.gl-inet.com/products/gl-mt6000/',
    image: '/images/mesh/mt6000.webp',
    factoryUrl: '/firmware/openwrt-25.12.0-mediatek-filogic-glinet_gl-mt6000-squashfs-factory.bin',
    factorySize: '45 MB',
    sysupgradeUrl: '/firmware/openwrt-25.12.0-mediatek-filogic-glinet_gl-mt6000-squashfs-sysupgrade.bin',
    sysupgradeSize: '17 MB'
  },
  {
    id: 'axt1800',
    name: 'GL.iNet GL-AXT1800 (Slate AX)',
    target: 'qualcommax/ipq60xx',
    flash: '128MB',
    ram: '512MB',
    radios: '2x WiFi 6',
    role: 'bumblebee',
    recommended: false,
    powerW: 10,
    price: '~\u20AC120',
    buyUrl: 'https://www.gl-inet.com/products/gl-axt1800/',
    image: '/images/mesh/axt1800.webp',
    factoryUrl: '/firmware/openwrt-25.12.0-qualcommax-ipq60xx-glinet_gl-axt1800-squashfs-factory.ubi',
    factorySize: '20 MB',
    sysupgradeUrl: '/firmware/openwrt-25.12.0-qualcommax-ipq60xx-glinet_gl-axt1800-squashfs-sysupgrade.bin',
    sysupgradeSize: '19 MB'
  },
  {
    id: 'mt3000',
    name: 'GL.iNet GL-MT3000 (Beryl AX)',
    target: 'mediatek/filogic',
    flash: '256MB',
    ram: '512MB',
    radios: '2x WiFi 6',
    role: 'bumblebee',
    recommended: false,
    powerW: 8,
    price: '~\u20AC100',
    buyUrl: 'https://www.gl-inet.com/products/gl-mt3000/',
    image: '/images/mesh/mt3000.webp',
    factoryUrl: null,
    factorySize: null,
    sysupgradeUrl: '/firmware/openwrt-25.12.0-mediatek-filogic-glinet_gl-mt3000-squashfs-sysupgrade.bin',
    sysupgradeSize: '16 MB'
  },
  {
    id: 'ax53u',
    name: 'Asus RT-AX53U',
    target: 'ramips/mt7621',
    flash: '128MB',
    ram: '256MB',
    radios: '2x WiFi 6',
    role: 'bumblebee',
    recommended: false,
    powerW: 7,
    price: '~\u20AC50',
    buyUrl: null,
    image: '/images/mesh/ax53u.webp',
    factoryUrl: '/firmware/openwrt-25.12.0-ramips-mt7621-asus_rt-ax53u-squashfs-factory.bin',
    factorySize: '17 MB',
    sysupgradeUrl: '/firmware/openwrt-25.12.0-ramips-mt7621-asus_rt-ax53u-squashfs-sysupgrade.bin',
    sysupgradeSize: '15 MB'
  },
  {
    id: 'ap3000outdoor',
    name: 'Cudy AP3000 Outdoor V1',
    target: 'mediatek/filogic',
    flash: '64MB',
    ram: '256MB',
    radios: '2x WiFi 6 (2.4+5GHz)',
    role: 'bumblebee',
    recommended: false,
    powerW: 11,
    price: '~\u20AC60',
    buyUrl: 'https://www.cudy.com/en-eu/products/ap3000-outdoor-1-0',
    image: '/images/mesh/ap3000outdoor.webp',
    factoryUrl: null,
    factorySize: null,
    sysupgradeUrl: '/firmware/openwrt-25.12.0-mediatek-filogic-cudy_ap3000outdoor-v1-squashfs-sysupgrade.bin',
    sysupgradeSize: '16 MB'
  },
  {
    id: 'cpe710',
    name: 'TP-Link CPE710 v1',
    target: 'ath79/generic',
    flash: '16MB',
    ram: '128MB',
    radios: '1x WiFi 5 (5GHz, 23dBi)',
    role: 'bee',
    recommended: false,
    powerW: 8,
    price: '~\u20AC80',
    buyUrl: null,
    image: '/images/mesh/cpe710.webp',
    factoryUrl: '/firmware/openwrt-25.12.0-ath79-generic-tplink_cpe710-v1-squashfs-factory.bin',
    factorySize: '7.9 MB',
    sysupgradeUrl: '/firmware/openwrt-25.12.0-ath79-generic-tplink_cpe710-v1-squashfs-sysupgrade.bin',
    sysupgradeSize: '16 MB'
  },
  {
    id: 'ar300m16',
    name: 'GL.iNet GL-AR300M16-EXT',
    target: 'ath79/generic',
    flash: '16MB',
    ram: '128MB',
    radios: '1x WiFi 4 (2.4GHz)',
    role: 'bee',
    recommended: false,
    powerW: 1.5,
    price: '~\u20AC40',
    buyUrl: 'https://www.gl-inet.com/products/gl-ar300m/',
    image: '/images/mesh/ar300m16.webp',
    factoryUrl: null,
    factorySize: null,
    sysupgradeUrl: '/firmware/openwrt-25.12.0-ath79-generic-glinet_gl-ar300m16-squashfs-sysupgrade.bin',
    sysupgradeSize: '7.4 MB'
  }
]

const totalPowerW = computed(() => devices.reduce((sum, d) => sum + d.powerW, 0))
const totalKwhMonth = computed(() => (totalPowerW.value * 24 * 30.44 / 1000).toFixed(1))

const packagesBumblebee = [
  'mesh.pkg_mesh',
  'mesh.pkg_wifi',
  'mesh.pkg_guest',
  'mesh.pkg_private',
  'mesh.pkg_yggdrasil',
  'mesh.pkg_vpn',
  'mesh.pkg_speed_control',
  'mesh.pkg_doh',
  'mesh.pkg_luci',
  'mesh.pkg_diag'
]

const packagesBee = [
  'mesh.pkg_mesh',
  'mesh.pkg_wifi',
  'mesh.pkg_private',
  'mesh.pkg_host_speed',
  'mesh.pkg_luci',
  'mesh.pkg_heartbeat'
]

const bootSteps = [
  'mesh.boot_step1',
  'mesh.boot_step2',
  'mesh.boot_step3',
  'mesh.boot_step4',
  'mesh.boot_step5',
  'mesh.boot_step6'
]

const flashTab = ref('glinet')
const flashTabs = computed(() => [
  { id: 'glinet', label: t('mesh.flash_tab_glinet') },
  { id: 'asus', label: t('mesh.flash_tab_asus') },
  { id: 'tplink', label: t('mesh.flash_tab_tplink') },
  { id: 'cudy', label: t('mesh.flash_tab_cudy') },
  { id: 'openwrt', label: t('mesh.flash_tab_openwrt') },
])
</script>
