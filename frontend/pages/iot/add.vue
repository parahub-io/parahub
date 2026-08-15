<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <Head>
      <Title>{{ $t('iot.wizard.title') }} - Parahub</Title>
    </Head>

    <NuxtLink
      :to="localePath('/iot')"
      class="inline-flex items-center gap-1 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors mb-4"
    >
      <ArrowLeft class="w-4 h-4" />
      {{ $t('iot.hub_title') }}
    </NuxtLink>

    <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mb-6">
      {{ $t('iot.wizard.title') }}
    </h1>

    <!-- Step indicator -->
    <div class="flex items-center gap-2 mb-8 flex-wrap">
      <button
        v-for="(s, idx) in steps"
        :key="s.id"
        type="button"
        :class="[
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          idx === step ? 'bg-primary text-neutral-900'
            : idx < step && !locked ? 'bg-primary/20 text-secondary dark:text-primary cursor-pointer'
            : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-400',
        ]"
        @click="goToStep(idx)"
      >
        {{ idx + 1 }}. {{ s.label }}
      </button>
    </div>

    <!-- ═══ Step: pick what to add ═══ -->
    <div v-if="currentStep === 'pick'">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('iot.wizard.pick_title') }}
      </h2>
      <div class="grid gap-4 grid-cols-1 sm:grid-cols-2">
        <IoTWizardOptionCard
          image="/images/iot/tracker.webp"
          :title="$t('iot.wizard.pick_tracker')"
          :description="$t('iot.wizard.pick_tracker_desc')"
          @select="pickBranch('tracker')"
        />
        <IoTWizardOptionCard
          image="/images/iot/network.webp"
          :title="$t('iot.wizard.pick_network')"
          :description="$t('iot.wizard.pick_network_desc')"
          @select="pickBranch('network')"
        />
        <IoTWizardOptionCard
          image="/images/iot/station.webp"
          :title="$t('iot.wizard.pick_station')"
          :description="$t('iot.wizard.pick_station_desc')"
          @select="pickBranch('station')"
        />
        <IoTWizardOptionCard
          image="/images/iot/object.webp"
          :title="$t('iot.wizard.pick_object')"
          :description="$t('iot.wizard.pick_object_desc')"
          @select="pickBranch('object')"
        />
      </div>
    </div>

    <!-- ═══ Step: tracker variant ═══ -->
    <div v-else-if="currentStep === 'variant' && branch === 'tracker'">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('iot.wizard.tracker_variant_title') }}
      </h2>
      <div class="grid gap-4 grid-cols-1 sm:grid-cols-2">
        <IoTWizardOptionCard
          image="/images/iot/tracker-phone.webp"
          :title="$t('iot.wizard.tracker_phone')"
          :description="$t('iot.wizard.tracker_phone_desc')"
          @select="trackerVariant = 'phone'; step++"
        />
        <IoTWizardOptionCard
          image="/images/iot/tracker-hardware.webp"
          :title="$t('iot.wizard.tracker_hw')"
          :description="$t('iot.wizard.tracker_hw_desc')"
          @select="trackerVariant = 'hardware'; step++"
        />
      </div>
      <a
        :href="TRACCAR_SITE"
        target="_blank"
        rel="noopener noreferrer"
        class="mt-4 inline-flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors"
      >
        <ExternalLink class="w-3.5 h-3.5" />
        {{ $t('iot.wizard.traccar_about') }}
      </a>
    </div>

    <!-- ═══ Step: network variant ═══ -->
    <div v-else-if="currentStep === 'variant' && branch === 'network'">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('iot.wizard.network_variant_title') }}
      </h2>
      <div class="grid gap-4 grid-cols-1 sm:grid-cols-2">
        <IoTWizardOptionCard
          image="/images/iot/network-claim.webp"
          :title="$t('iot.wizard.network_claim')"
          :description="$t('iot.wizard.network_claim_desc')"
          @select="step++"
        />
        <IoTWizardOptionCard
          image="/images/iot/network-flash.webp"
          :title="$t('iot.wizard.network_flash')"
          :description="$t('iot.wizard.network_flash_desc')"
          :to="localePath('/mesh')"
        />
      </div>
      <a
        href="/print/mesh.html"
        target="_blank"
        rel="noopener noreferrer"
        class="mt-4 inline-flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 hover:text-secondary dark:hover:text-secondary-400 transition-colors"
      >
        <Printer class="w-4 h-4" />
        {{ $t('mesh.print_sheet') }}
      </a>
    </div>

    <!-- ═══ Step: station variant ═══ -->
    <div v-else-if="currentStep === 'variant' && branch === 'station'">
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
        {{ $t('iot.wizard.station_variant_title') }}
      </h2>
      <div class="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <IoTWizardOptionCard
          image="/images/iot/station-airgradient.webp"
          title="AirGradient"
          :description="$t('iot.wizard.station_ag_desc')"
          @select="stationSource = 'AIRGRADIENT'; step++"
        />
        <IoTWizardOptionCard
          image="/images/iot/station-ecowitt.webp"
          title="Ecowitt"
          :description="$t('iot.wizard.station_eco_desc')"
          @select="stationSource = 'ECOWITT'; step++"
        />
        <IoTWizardOptionCard
          image="/images/iot/station-generic.webp"
          :title="$t('iot.wizard.station_generic')"
          :description="$t('iot.wizard.station_generic_desc')"
          @select="stationSource = 'GENERIC'; step++"
        />
      </div>
    </div>

    <!-- ═══ Step: tracker setup ═══ -->
    <div v-else-if="currentStep === 'setup' && branch === 'tracker'" class="space-y-4">
      <!-- Phone: the app must be installed first — its identifier goes into the form -->
      <div v-if="trackerVariant === 'phone'" class="card p-4">
        <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
          {{ $t('iot.wizard.phone_setup_title') }}
        </h2>
        <ol class="space-y-3 text-sm text-neutral-700 dark:text-neutral-300">
          <li class="flex gap-3">
            <span class="wizard-step-num">1</span>
            <div class="flex-1 min-w-0">
              {{ $t('iot.wizard.phone_step1') }}
              <div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                <a
                  v-for="link in TRACCAR_APP_LINKS"
                  :key="link.href"
                  :href="link.href"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-link inline-flex items-center gap-1 text-sm font-medium"
                >
                  <ExternalLink class="w-3.5 h-3.5" />
                  {{ link.label }}
                </a>
              </div>
            </div>
          </li>
          <li class="flex gap-3">
            <span class="wizard-step-num">2</span>
            <div class="flex-1 min-w-0">
              {{ $t('iot.wizard.phone_step2') }}
              <div class="mt-1 flex items-center gap-2">
                <code class="flex-1 truncate text-xs bg-neutral-100 dark:bg-neutral-900 rounded px-2 py-1.5 text-neutral-700 dark:text-neutral-300">{{ osmandUrl }}</code>
                <UiButton variant="ghost" size="sm" :icon="Copy" icon-only @click="copy(osmandUrl)" />
              </div>
            </div>
          </li>
          <li class="flex gap-3">
            <span class="wizard-step-num">3</span>
            <span>{{ $t('iot.wizard.phone_step3') }}</span>
          </li>
        </ol>
      </div>

      <div>
        <label for="w-name" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('iot.wizard.name_label') }} <span class="text-red-500">*</span>
        </label>
        <input id="w-name" v-model="trackerForm.name" type="text" maxlength="100"
               :placeholder="$t('iot.wizard.tracker_name_ph')" class="wizard-input" />
      </div>

      <div v-if="trackerVariant === 'phone'">
        <label for="w-identifier" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('iot.wizard.identifier_label') }} <span class="text-red-500">*</span>
        </label>
        <input id="w-identifier" v-model="trackerForm.device_id" type="text" maxlength="64"
               placeholder="123456" class="wizard-input font-mono" />
        <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.identifier_hint') }}</p>
      </div>

      <div v-else>
        <label for="w-imei" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          IMEI <span class="text-red-500">*</span>
        </label>
        <input id="w-imei" v-model="trackerForm.imei" type="text" maxlength="15" pattern="[0-9]{15}"
               placeholder="123456789012345" class="wizard-input font-mono" />
        <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.imei_hint') }}</p>
      </div>

      <UiAlert v-if="createError" variant="error">{{ createError }}</UiAlert>

      <div class="flex gap-3 pt-2">
        <button class="btn-outline" @click="step--">{{ $t('iot.back') }}</button>
        <UiButton variant="primary" :loading="creating" :disabled="!trackerValid" @click="createTracker">
          {{ $t('iot.wizard.create_and_continue') }}
        </UiButton>
      </div>
    </div>

    <!-- ═══ Step: station setup ═══ -->
    <div v-else-if="currentStep === 'setup' && branch === 'station'" class="space-y-4">
      <div>
        <label for="w-stname" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('iot.wizard.name_label') }} <span class="text-red-500">*</span>
        </label>
        <input id="w-stname" v-model="stationForm.name" type="text" maxlength="100"
               :placeholder="$t('map.env.name_placeholder')" class="wizard-input" />
      </div>

      <div v-if="stationSource === 'AIRGRADIENT'">
        <label for="w-serial" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('iot.wizard.serial_label') }} <span class="text-red-500">*</span>
        </label>
        <input id="w-serial" v-model="stationForm.external_id" type="text"
               placeholder="d83bda1ac64c" class="wizard-input font-mono" />
        <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.serial_hint') }}</p>
      </div>

      <label class="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300 cursor-pointer">
        <input v-model="stationForm.is_public" type="checkbox" class="rounded border-neutral-300 dark:border-neutral-600" />
        {{ $t('map.env.public_toggle') }}
      </label>

      <div>
        <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
          {{ $t('map.env.location') }} <span class="text-red-500">*</span>
        </label>
        <p class="text-xs text-neutral-400 mb-2">{{ $t('map.env.click_map') }}</p>
        <div v-if="propertiesWithCoords.length" class="flex flex-wrap gap-1.5 mb-2">
          <button v-for="prop in propertiesWithCoords" :key="prop.id" type="button"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-300 hover:border-primary"
                  @click="flyToProperty(prop)">
            <Home class="w-3 h-3" /> {{ prop.name }}
          </button>
        </div>
        <div ref="mapContainer" class="w-full h-56 rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600 cursor-crosshair" />
        <div class="mt-1.5 text-sm font-mono" :class="stationForm.lat !== null ? 'text-neutral-700 dark:text-neutral-300' : 'text-neutral-400'">
          {{ stationForm.lat !== null ? `${stationForm.lat.toFixed(6)}, ${stationForm.lng!.toFixed(6)}` : $t('mesh.no_location') }}
        </div>
      </div>

      <UiAlert v-if="createError" variant="error">{{ createError }}</UiAlert>

      <div class="flex gap-3 pt-2">
        <button class="btn-outline" @click="step--">{{ $t('iot.back') }}</button>
        <UiButton variant="primary" :loading="creating" :disabled="!stationValid" @click="createStation">
          {{ $t('iot.wizard.create_and_continue') }}
        </UiButton>
      </div>
    </div>

    <!-- ═══ Step: claim a pre-provisioned router ═══ -->
    <div v-else-if="currentStep === 'claim'" class="space-y-4">
      <template v-if="!claimedName">
        <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('iot.claim_intro') }}</p>

        <template v-if="!claimPreviewData">
          <div>
            <label for="w-mac" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              {{ $t('iot.claim_mac_label') }}
            </label>
            <input id="w-mac" v-model="claimMac" type="text" placeholder="AA:BB:CC:DD:EE:FF"
                   autocapitalize="characters" autocomplete="off" spellcheck="false"
                   class="wizard-input font-mono" @blur="normalizeClaimMac"
                   @keydown.enter="handleClaimPreview" />
            <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{{ $t('iot.claim_mac_hint') }}</p>
          </div>

          <UiAlert v-if="claimError" variant="error">{{ claimError }}</UiAlert>

          <div class="flex gap-3 pt-2">
            <button class="btn-outline" @click="step--">{{ $t('iot.back') }}</button>
            <UiButton variant="primary" :loading="claimBusy" :disabled="!claimMac.trim()" @click="handleClaimPreview">
              {{ $t('iot.claim_find') }}
            </UiButton>
          </div>
        </template>

        <template v-else>
          <div class="card p-4">
            <div class="flex items-center justify-between mb-2">
              <span class="font-semibold text-neutral-900 dark:text-neutral-100">{{ claimPreviewData.name }}</span>
              <span class="flex items-center gap-1.5 text-xs" role="status">
                <span class="w-2 h-2 rounded-full" :class="claimPreviewData.online ? 'bg-green-500' : 'bg-red-500'" />
                {{ claimPreviewData.online ? $t('iot.status_online') : $t('iot.status_offline') }}
              </span>
            </div>
            <div class="space-y-1 text-sm text-neutral-500 dark:text-neutral-400">
              <div v-if="claimPreviewData.hardware_profile" class="flex justify-between">
                <span>{{ $t('iot.claim_hardware') }}</span>
                <span class="text-neutral-900 dark:text-neutral-100">{{ getHardwareName(claimPreviewData.hardware_profile) }}</span>
              </div>
              <div v-if="claimPreviewData.last_seen" class="flex justify-between">
                <span>{{ $t('iot.last_heartbeat') }}</span>
                <span class="text-neutral-900 dark:text-neutral-100">{{ formatRelativeTime(claimPreviewData.last_seen) }}</span>
              </div>
            </div>
          </div>

          <UiAlert v-if="claimError" variant="error">{{ claimError }}</UiAlert>

          <div class="flex gap-3 pt-2">
            <button class="btn-outline" @click="claimPreviewData = null; claimError = ''">{{ $t('iot.back') }}</button>
            <UiButton variant="primary" :loading="claimBusy" @click="handleClaim">
              {{ $t('iot.claim_confirm') }}
            </UiButton>
          </div>
        </template>
      </template>

      <!-- Claimed: success -->
      <div v-else class="text-center py-8">
        <img src="/images/para/celebrating.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
        <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {{ $t('iot.wizard.claimed_title') }}
        </h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{{ claimedName }}</p>
        <UiButton class="mt-6" variant="primary" @click="finish">{{ $t('iot.wizard.finish') }}</UiButton>
      </div>
    </div>

    <!-- ═══ Step: verify (device/station created, waiting for first data) ═══ -->
    <div v-else-if="currentStep === 'verify'" class="space-y-4">
      <!-- Hardware tracker: configure after creation, identifier = IMEI -->
      <div v-if="branch === 'tracker' && trackerVariant === 'hardware'" class="card p-4">
        <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('iot.wizard.hw_configure_title') }}
        </h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('iot.wizard.hw_configure_intro') }}</p>
        <div class="space-y-2 text-sm">
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.hw_server') }}</span>
            <code class="flex-1 truncate text-xs bg-neutral-100 dark:bg-neutral-900 rounded px-2 py-1.5 text-neutral-700 dark:text-neutral-300">{{ trackerHost }}</code>
            <UiButton variant="ghost" size="sm" :icon="Copy" icon-only @click="copy(trackerHost)" />
          </div>
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.hw_port') }}</span>
            <span class="text-neutral-700 dark:text-neutral-300">{{ $t('iot.wizard.hw_port_hint') }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.hw_id') }}</span>
            <code class="flex-1 truncate text-xs bg-neutral-100 dark:bg-neutral-900 rounded px-2 py-1.5 text-neutral-700 dark:text-neutral-300">{{ trackerForm.imei }}</code>
          </div>
        </div>
      </div>

      <!-- Phone tracker: start tracking in the app -->
      <UiAlert v-else-if="branch === 'tracker' && trackerVariant === 'phone'" variant="info">
        {{ $t('iot.wizard.phone_verify_hint') }}
      </UiAlert>

      <!-- Ecowitt: paste the minted ingest path into the console -->
      <div v-else-if="branch === 'station' && stationSource === 'ECOWITT'" class="card p-4">
        <h2 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mb-1">
          {{ $t('iot.wizard.eco_configure_title') }}
        </h2>
        <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-3">{{ $t('iot.wizard.eco_configure_intro') }}</p>
        <div class="space-y-2 text-sm">
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.hw_server') }}</span>
            <code class="flex-1 truncate text-xs bg-neutral-100 dark:bg-neutral-900 rounded px-2 py-1.5 text-neutral-700 dark:text-neutral-300">wx.parahub.io</code>
            <UiButton variant="ghost" size="sm" :icon="Copy" icon-only @click="copy('wx.parahub.io')" />
          </div>
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.eco_path') }}</span>
            <code class="flex-1 truncate text-xs bg-neutral-100 dark:bg-neutral-900 rounded px-2 py-1.5 text-neutral-700 dark:text-neutral-300">{{ createdStation?.ingest_path }}</code>
            <UiButton variant="ghost" size="sm" :icon="Copy" icon-only @click="copy(createdStation?.ingest_path || '')" />
          </div>
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.hw_port') }}</span>
            <span class="text-neutral-700 dark:text-neutral-300">{{ $t('iot.wizard.eco_port80') }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-28 shrink-0 text-neutral-500 dark:text-neutral-400">{{ $t('iot.wizard.eco_interval') }}</span>
            <span class="text-neutral-700 dark:text-neutral-300">{{ $t('iot.wizard.eco_interval_value') }}</span>
          </div>
        </div>
      </div>

      <!-- AirGradient: joins via the mesh poll bridge -->
      <UiAlert v-else-if="branch === 'station' && stationSource === 'AIRGRADIENT'" variant="info" :title="$t('iot.wizard.ag_configure_title')">
        {{ $t('iot.wizard.ag_configure_body') }}
      </UiAlert>

      <!-- Generic station: no automated setup -->
      <UiAlert v-else-if="branch === 'station'" variant="info">
        {{ $t('iot.wizard.generic_note') }}
      </UiAlert>

      <!-- Live status -->
      <div class="text-center py-8">
        <template v-if="connected">
          <img src="/images/para/celebrating.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {{ branch === 'station' ? $t('iot.wizard.verify_connected_station') : $t('iot.wizard.verify_connected') }}
          </h2>
          <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{{ createdName }}</p>
          <UiButton class="mt-6" variant="primary" @click="finish">{{ $t('iot.wizard.finish') }}</UiButton>
        </template>
        <template v-else>
          <img src="/images/para/searching.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <div class="inline-flex items-center gap-2 text-neutral-500 dark:text-neutral-400" role="status">
            <span class="h-4 w-4 rounded-full border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 animate-spin" />
            {{ $t('iot.wizard.verify_waiting') }}
            <span class="sr-only">{{ $t('iot.wizard.verify_waiting') }}</span>
          </div>
          <p class="text-sm text-neutral-400 mt-2">{{ waitingHint }}</p>
          <div class="mt-6">
            <UiButton variant="ghost" @click="finish">
              {{ $t('iot.wizard.finish_without') }}
            </UiButton>
          </div>
        </template>
      </div>
    </div>

    <!-- ═══ Step: object form ═══ -->
    <div v-else-if="currentStep === 'form'">
      <IoTPropertyForm @submit="onPropertyCreated" @cancel="goToStep(0)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { ArrowLeft, Copy, ExternalLink, Home, Printer } from 'lucide-vue-next'
import type { ClaimPreview } from '~/stores/iot'
import { LEAF_GLYPH, WIND_GLYPH } from '~/composables/useMapToggleableLayer'
import { ENV_WEATHER_COLOR } from '~/composables/useMapIoTLayers'
import { createDeviceHexElement } from '~/utils/pickerMarker'

definePageMeta({
  middleware: 'auth',
})

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const { t: $t } = useI18n()
const config = useRuntimeConfig()
const colorMode = useColorMode()

const iotStore = useIoTStore()
const envStore = useEnvStore()
const propertyStore = usePropertyStore()
const toastStore = useToastStore()
const { getHardwareName, formatRelativeTime } = useIoT()
const { apiErrorMessage } = useApiError()

type Branch = 'tracker' | 'network' | 'station' | 'object'
const BRANCHES: Branch[] = ['tracker', 'network', 'station', 'object']

const branch = ref<Branch | null>(null)
const trackerVariant = ref<'phone' | 'hardware' | null>(null)
const stationSource = ref<'AIRGRADIENT' | 'ECOWITT' | 'GENERIC' | null>(null)
const step = ref(0)

const propertyId = typeof route.query.property === 'string' ? route.query.property : undefined

// Deep links: /iot/add?type=tracker[&variant=claim]
const initType = route.query.type
if (typeof initType === 'string' && (BRANCHES as string[]).includes(initType)) {
  branch.value = initType as Branch
  step.value = 1
  if (initType === 'network' && route.query.variant === 'claim') step.value = 2
}

const stepIds = computed<string[]>(() => {
  switch (branch.value) {
    case 'tracker': return ['pick', 'variant', 'setup', 'verify']
    case 'network': return ['pick', 'variant', 'claim']
    case 'station': return ['pick', 'variant', 'setup', 'verify']
    case 'object': return ['pick', 'form']
    default: return ['pick']
  }
})

const STEP_LABELS: Record<string, string> = {
  pick: 'step_pick',
  variant: 'step_variant',
  setup: 'step_setup',
  claim: 'step_claim',
  verify: 'step_verify',
  form: 'step_setup',
}

const steps = computed(() => stepIds.value.map(id => ({ id, label: $t(`iot.wizard.${STEP_LABELS[id]}`) })))
const currentStep = computed(() => stepIds.value[step.value])

// Once something is created/claimed the earlier steps can't be re-entered
const locked = computed(() => !!(createdDevice.value || createdStation.value || claimedName.value))

function goToStep(idx: number) {
  if (idx >= step.value || locked.value) return
  if (idx === 0) {
    branch.value = null
    trackerVariant.value = null
    stationSource.value = null
    createError.value = ''
    router.replace({ query: { ...route.query, type: undefined, variant: undefined } })
  }
  step.value = idx
}

function pickBranch(b: Branch) {
  branch.value = b
  step.value = 1
  router.replace({ query: { ...route.query, type: b } })
}

// ── Forms ──
const trackerForm = reactive({ name: '', device_id: '', imei: '' })
const stationForm = reactive({
  name: '',
  external_id: '',
  is_public: true,
  lat: null as number | null,
  lng: null as number | null,
})

const creating = ref(false)
const createError = ref('')
const createdDevice = ref<any>(null)
const createdStation = ref<any>(null)

const trackerValid = computed(() => {
  if (trackerForm.name.trim().length < 2) return false
  if (trackerVariant.value === 'phone') return trackerForm.device_id.trim().length > 0
  return /^\d{15}$/.test(trackerForm.imei)
})

const stationValid = computed(() => {
  if (stationForm.name.trim().length < 2) return false
  if (stationForm.lat === null) return false
  if (stationSource.value === 'AIRGRADIENT') return stationForm.external_id.trim().length > 0
  return true
})

const createdName = computed(() => createdDevice.value?.name || createdStation.value?.name || '')

// ── Create actions ──
async function createTracker() {
  if (!trackerValid.value || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    // Traccar matches on device_id (uniqueid) — for hardware trackers that is the IMEI
    const body: Record<string, any> = {
      name: trackerForm.name.trim(),
      device_type: 'TRACKER',
      device_id: trackerVariant.value === 'phone' ? trackerForm.device_id.trim() : trackerForm.imei.trim(),
    }
    if (trackerVariant.value === 'hardware') body.imei = trackerForm.imei.trim()
    if (propertyId) body.property_id = propertyId
    createdDevice.value = await iotStore.createDevice(body as any)
    step.value++
    startPolling()
  } catch (e: any) {
    createError.value = e?.data?.detail || e?.message || $t('iot.device_form.error_title')
  } finally {
    creating.value = false
  }
}

async function createStation() {
  if (!stationValid.value || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    createdStation.value = await envStore.createStation({
      name: stationForm.name.trim(),
      source: stationSource.value!,
      latitude: stationForm.lat!,
      longitude: stationForm.lng!,
      is_public: stationForm.is_public,
      external_id: stationForm.external_id.trim() || undefined,
      property_id: propertyId || undefined,
    })
    step.value++
    startPolling()
  } catch (e: any) {
    createError.value = e?.data?.detail || $t('map.env.create_failed')
  } finally {
    creating.value = false
  }
}

// ── Claim (pre-provisioned router by sticker MAC) ──
const claimMac = ref('')
const claimPreviewData = ref<ClaimPreview | null>(null)
const claimBusy = ref(false)
const claimError = ref('')
const claimedName = ref('')

// People copy the label as they see it: run together, in caps, with dashes.
// The backend strips separators anyway — echo back the canonical form once the
// field is left, so it is visible that the input was understood.
function normalizeClaimMac() {
  const hex = claimMac.value.toLowerCase().replace(/[^0-9a-f]/g, '')
  if (hex.length === 12) claimMac.value = hex.toUpperCase().match(/../g)!.join(':')
}

function claimErrText(err: any): string {
  const status = err?.status || err?.statusCode
  const data = err?.data ?? err?.response?._data ?? {}
  if (status === 429) {
    // retry_after = seconds left in the window; a countdown beats "try later",
    // which just invites more taps (each one counting against the budget)
    const sec = Number(data.retry_after) || 0
    return sec > 0
      ? $t('iot.claim_rate_limited_in', { min: Math.ceil(sec / 60) })
      : $t('iot.claim_rate_limited')
  }
  if (status === 400) return $t('iot.claim_bad_mac')
  // 404/409 carry a LocalizedHttpError `code` matching an iot.claim_* key
  return apiErrorMessage(err, 'iot', $t('iot.claim_failed'))
}

async function handleClaimPreview() {
  if (claimBusy.value || !claimMac.value.trim()) return
  claimBusy.value = true
  claimError.value = ''
  try {
    claimPreviewData.value = await iotStore.claimPreview(claimMac.value)
  } catch (err: any) {
    claimError.value = claimErrText(err)
  } finally {
    claimBusy.value = false
  }
}

async function handleClaim() {
  if (claimBusy.value) return
  claimBusy.value = true
  claimError.value = ''
  try {
    const res = await iotStore.claimDevice(claimMac.value)
    claimedName.value = res.name
  } catch (err: any) {
    claimError.value = claimErrText(err)
  } finally {
    claimBusy.value = false
  }
}

// ── Verify: poll for the first signal ──
const connected = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  poll()
  pollTimer = setInterval(poll, branch.value === 'station' ? 8000 : 5000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function poll() {
  try {
    if (createdStation.value) {
      await envStore.fetchStations()
      const st = envStore.stations.find(s => s.id === createdStation.value.id)
      if (st?.last_reading_at) { connected.value = true; stopPolling() }
    } else if (createdDevice.value) {
      const d = await iotStore.getDevice(createdDevice.value.id)
      if (d.last_seen) { connected.value = true; stopPolling() }
    }
  } catch { /* transient — keep polling */ }
}

onUnmounted(stopPolling)

const waitingHint = computed(() => {
  if (branch.value === 'tracker') return $t('iot.wizard.wait_hint_tracker')
  if (branch.value === 'station' && stationSource.value === 'AIRGRADIENT') return $t('iot.wizard.wait_hint_ag')
  if (branch.value === 'station') return $t('iot.wizard.wait_hint_eco')
  return ''
})

// ── Traccar (third-party): the platform behind both tracker variants ──
const TRACCAR_SITE = 'https://www.traccar.org/'
const TRACCAR_APP_LINKS = [
  { label: 'Google Play', href: 'https://play.google.com/store/apps/details?id=org.traccar.client' },
  // No storefront in the path — Apple redirects the visitor to their own country's store
  { label: 'App Store', href: 'https://apps.apple.com/app/traccar-client/id843156974' },
]

// ── Tracker endpoints ──
const trackerHost = config.public.traccarPublicHost || ''
const osmandUrl = `http://${trackerHost}:5055`

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toastStore.success($t('iot.wizard.copied'))
  } catch { /* clipboard unavailable */ }
}

// ── Station location map (mounts when the station setup step is visible) ──
const mapContainer = ref<HTMLElement | null>(null)
let map: any = null
let marker: any = null
let maplibregl: any = null

const propertiesWithCoords = computed(() =>
  propertyStore.properties.filter(p => p.latitude && p.longitude)
)

// The picker places the env-station hex the device will wear on /map:
// no-data sky-blue fill, air stations carry the leaf, weather the wind.
const stationMarker = () => new maplibregl.Marker({
  element: createDeviceHexElement(ENV_WEATHER_COLOR, stationSource.value === 'AIRGRADIENT' ? LEAF_GLYPH : WIND_GLYPH),
  anchor: 'center',
})

const placeMarker = (lng: number, lat: number) => {
  stationForm.lat = Math.round(lat * 1e6) / 1e6
  stationForm.lng = Math.round(lng * 1e6) / 1e6
  if (marker) {
    marker.setLngLat([lng, lat])
  } else if (map && maplibregl) {
    marker = stationMarker().setLngLat([lng, lat]).addTo(map)
  }
}

const flyToProperty = (prop: { latitude: number; longitude: number }) => {
  if (map) map.flyTo({ center: [prop.longitude, prop.latitude], zoom: 17, essential: true, speed: 4.5 })
  placeMarker(prop.longitude, prop.latitude)
}

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initMap() {
  if (!mapContainer.value || map) return
  const mod = await import('maplibre-gl')
  maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  const { mapCenter, mapZoom } = useMapState()
  map = new maplibregl.Map({
    container: mapContainer.value,
    style: getStyleUrl(),
    center: mapCenter.value,
    zoom: mapZoom.value,
    attributionControl: false,
    fadeDuration: 0,
  })
  map.once('load', () => map.resize())
  map.on('click', (e: any) => placeMarker(e.lngLat.lng, e.lngLat.lat))
  if (stationForm.lat !== null && stationForm.lng !== null) {
    marker = stationMarker()
      .setLngLat([stationForm.lng, stationForm.lat])
      .addTo(map)
  }
}

function destroyMap() {
  if (map) { map.remove(); map = null; marker = null }
}

watch(
  () => currentStep.value === 'setup' && branch.value === 'station',
  async (active) => {
    if (active) { await nextTick(); initMap() } else { destroyMap() }
  },
  { immediate: true },
)

onUnmounted(destroyMap)

// ── Object branch ──
function onPropertyCreated() {
  toastStore.success($t('iot.wizard.object_created'))
  navigateTo(localePath('/iot?tab=objects'))
}

// ── Finish ──
const FINISH_TARGETS: Record<Branch, string> = {
  tracker: '/iot',
  network: '/iot?tab=network',
  station: '/iot?tab=sensors',
  object: '/iot?tab=objects',
}

function finish() {
  navigateTo(localePath(FINISH_TARGETS[branch.value || 'tracker']))
}

onMounted(() => {
  if (!propertyStore.properties.length) propertyStore.fetchProperties()
})
</script>

<style scoped>
.wizard-input {
  @apply w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent;
}
.wizard-step-num {
  @apply flex-shrink-0 w-6 h-6 rounded-full bg-primary text-neutral-900 text-xs font-bold flex items-center justify-center;
}
</style>
