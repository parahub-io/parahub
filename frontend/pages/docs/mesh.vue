<template>
  <div class="min-h-full bg-white dark:bg-neutral-950">
    <DocsHeader :title="$t('about.meshSystem.title')" />

    <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div class="prose-section space-y-8">

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.meshSystem.what.title') }}</h3>
          <p>{{ $t('about.meshSystem.what.text') }}</p>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('about.meshSystem.networks.title') }}</h3>
          <div class="grid sm:grid-cols-2 gap-3 text-sm">
            <div class="border border-secondary-200 dark:border-secondary-900 rounded-lg p-4 bg-secondary-50 dark:bg-secondary-900/30">
              <div class="font-mono font-semibold text-secondary-700 dark:text-secondary-300 mb-2">parahub.io/free</div>
              <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ $t('about.meshSystem.networks.public') }}</p>
            </div>
            <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 bg-neutral-50 dark:bg-neutral-900">
              <div class="font-mono font-semibold text-neutral-700 dark:text-neutral-300 mb-2">Parahub</div>
              <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ $t('about.meshSystem.networks.private') }}</p>
            </div>
          </div>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.meshSystem.earn.title') }}</h3>
          <p>{{ $t('about.meshSystem.earn.text') }}</p>
        </div>

        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('about.meshSystem.global.title') }}</h3>
          <p>{{ $t('about.meshSystem.global.text') }}</p>
        </div>

        <!-- Architecture -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('mesh.docs_architecture') }}</h3>
          <p class="mb-3">{{ $t('mesh.docs_architecture_desc') }}</p>
          <pre class="bg-neutral-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto font-mono leading-relaxed">Radio 0 (2.4GHz)              Radio 1 (5GHz)
├── mesh (802.11s, SAE)       ├── mesh (802.11s, SAE)
├── parahub.io/free (open)    ├── Parahub (WPA2/WPA3, 802.11r)
├── Parahub (WPA2/WPA3)       └── → batman-adv
└── → batman-adv

         bat0 (BATMAN_V)
          │
   ┌──────┼──────┐
br-private │    guest (512kbps / paid unlimited)
10.P.P.0/24│    10.G.G.0/24
  Bee: 10Mbps│    gateway: elected Bumblebee
           │         │
           │    WireGuard VPN ──→ VPS ──→ Mullvad ──→ Internet
           │         OR
           │    Direct Mullvad (optional upgrade)
           │         OR (fallback)
           │    Mesh → nearest Bumblebee with VPN
           │
          ygg0 (Yggdrasil overlay, management)</pre>
        </div>

        <!-- Guest traffic flow -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('mesh.docs_guest_flow') }}</h3>
          <ul class="space-y-1.5 text-sm mb-3">
            <li class="font-mono text-neutral-700 dark:text-neutral-300">{{ $t('mesh.docs_guest_flow_default') }}</li>
            <li class="font-mono text-neutral-700 dark:text-neutral-300">{{ $t('mesh.docs_guest_flow_upgrade') }}</li>
            <li class="font-mono text-neutral-700 dark:text-neutral-300">{{ $t('mesh.docs_guest_flow_fallback') }}</li>
          </ul>
          <p>{{ $t('mesh.docs_guest_flow_desc') }}</p>
        </div>

        <!-- Roaming -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('mesh.docs_roaming') }}</h3>
          <p>{{ $t('mesh.docs_roaming_desc') }}</p>
        </div>

        <!-- Auto-updates -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('mesh.docs_ota') }}</h3>
          <p>{{ $t('mesh.docs_ota_desc') }}</p>
        </div>

        <!-- Verification -->
        <div>
          <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('mesh.docs_verify') }}</h3>
          <p class="mb-3">{{ $t('mesh.docs_verify_desc') }}</p>
          <pre class="bg-neutral-900 text-green-400 p-4 rounded-lg text-sm overflow-x-auto font-mono">batctl if                    # phy0-mesh0, phy1-mesh0
iwinfo                       # 5 wireless interfaces
cat /etc/parahub/keys        # Credentials + Yggdrasil address
uci show network.private     # Private bridge config
wg show                      # WireGuard handshake status</pre>
        </div>

      </div>

      <!-- CTA to firmware page -->
      <div class="mt-8 pt-8 border-t border-neutral-200 dark:border-neutral-800">
        <NuxtLink
          :to="localePath('/mesh')"
          class="flex items-center gap-3 p-4 sm:p-5 border border-neutral-200 dark:border-neutral-800 rounded-lg hover:border-neutral-400 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-900 group"
        >
          <Wifi class="w-5 h-5 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-neutral-900 dark:text-white group-hover:text-secondary dark:group-hover:text-secondary-400">{{ $t('mesh.downloads') }}</div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('mesh.subtitle') }}</div>
          </div>
          <ChevronRight class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
        </NuxtLink>

        <NuxtLink
          :to="localePath('/mesh/peering')"
          class="flex items-center gap-3 p-4 sm:p-5 mt-3 border border-neutral-200 dark:border-neutral-800 rounded-lg hover:border-neutral-400 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-900 group"
        >
          <Handshake class="w-5 h-5 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-neutral-900 dark:text-white group-hover:text-secondary dark:group-hover:text-secondary-400">{{ $t('mesh.peering.title') }}</div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('mesh.peering.link_desc') }}</div>
          </div>
          <ChevronRight class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
        </NuxtLink>

        <a
          href="https://github.com/parahub-io/parahub-mesh"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-3 p-4 sm:p-5 mt-3 border border-neutral-200 dark:border-neutral-800 rounded-lg hover:border-neutral-400 dark:hover:border-neutral-600 hover:bg-neutral-50 dark:hover:bg-neutral-900 group"
        >
          <Code class="w-5 h-5 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-300 flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-neutral-900 dark:text-white group-hover:text-secondary dark:group-hover:text-secondary-400">{{ $t('mesh.source_code') }}</div>
            <div class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">{{ $t('mesh.source_desc') }}</div>
          </div>
          <ExternalLink class="w-4 h-4 text-neutral-300 dark:text-neutral-600 group-hover:text-neutral-500 dark:group-hover:text-neutral-400 flex-shrink-0" />
        </a>
      </div>

      <DocsPrevNext />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight, Wifi, Handshake, Code, ExternalLink } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()
useHead({ title: computed(() => `${t('about.meshSystem.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('mesh.meta_desc')),
  ogTitle: computed(() => `${t('about.meshSystem.title')} — Parahub`),
  ogDescription: computed(() => t('mesh.meta_desc')),
})
useDocsBreadcrumb(t('about.meshSystem.title'), '/docs/mesh')

definePageMeta({ order: 2 })
</script>

<style scoped>
.prose-section {
  @apply text-neutral-700 dark:text-neutral-300 leading-relaxed;
}
</style>
