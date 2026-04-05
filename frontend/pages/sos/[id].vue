<template>
  <div>
    <div class="w-full px-4 sm:px-6 lg:px-8 py-6">
      <div class="max-w-4xl mx-auto w-full">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-12 text-neutral-500">
          {{ $t('parasos.loading') }}
        </div>

        <template v-else-if="group">
          <!-- Header -->
          <div class="flex items-center gap-3 mb-6">
            <NuxtLink :to="localePath('/sos')" class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
              <ArrowLeft :size="20" />
            </NuxtLink>
            <div class="flex-1 min-w-0">
              <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 truncate">
                {{ group.name }}
              </h1>
              <p class="text-sm text-neutral-500 dark:text-neutral-400">
                {{ $t('parasos.groups.members_count', group.members_count) }}
                <template v-if="group.radius_m"> · {{ $t('parasos.groups.radius', { meters: group.radius_m }) }}</template>
                <template v-if="group.visibility === 'PRIVATE'"> · {{ $t('parasos.visibility.private') }}</template>
              </p>
            </div>
          </div>

          <!-- Active alert banner -->
          <div
            v-if="activeAlert"
            class="mb-6 rounded-lg p-4 border-2"
            :class="alertBannerClass"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2">
                <component :is="alertIcon" :size="20" />
                <span class="font-bold">{{ $t('parasos.sos.active_alert') }}: {{ $t(`parasos.sos.level.${activeAlert.level.toLowerCase()}`) }}</span>
              </div>
              <span class="text-sm font-mono tabular-nums">{{ elapsedTimer }}</span>
            </div>
            <p v-if="activeAlert.message" class="text-sm mb-2">{{ activeAlert.message }}</p>
            <div class="flex items-center gap-2 text-sm">
              <span>{{ activeAlert.sender?.display_name || activeAlert.sender?.hna }}</span>
              <span v-if="activeAlert.seen_count > 0">· {{ activeAlert.seen_count }} {{ $t('parasos.response.seen').toLowerCase() }}</span>
              <span v-if="activeAlert.responding_count > 0">· {{ activeAlert.responding_count }} {{ $t('parasos.response.on_way').toLowerCase() }}</span>
            </div>

            <!-- Sender location link -->
            <a
              v-if="activeAlert.location"
              :href="localePath(`/map?lat=${activeAlert.location.lat}&lng=${activeAlert.location.lon}&zoom=17`)"
              target="_blank"
              class="inline-flex items-center gap-1 text-sm mt-2 underline underline-offset-2"
            >
              <MapPinIcon :size="14" />
              {{ $t('parasos.sos.view_location') }}
            </a>

            <!-- Response buttons (if I'm not the sender) -->
            <div v-if="group.is_member && activeAlert.sender?.id !== authStore.profile?.id" class="flex flex-wrap gap-2 mt-3">
              <button
                v-for="action in responseActions"
                :key="action.status"
                @click="respondToAlert(activeAlert.id, action.status)"
                class="btn-sm inline-flex items-center gap-1.5 transition-colors"
                :class="myResponse?.status === action.status ? 'btn-primary' : 'btn-outline'"
              >
                <component :is="action.icon" :size="16" />
                {{ action.label }}
              </button>
            </div>

            <!-- Resolve button (if I'm the sender or admin) -->
            <div v-if="activeAlert.sender?.id === authStore.profile?.id || group.is_admin" class="flex gap-2 mt-3">
              <button @click="resolveAlert(activeAlert.id, false)" class="btn-success btn-sm">
                {{ $t('parasos.sos.resolve') }}
              </button>
              <button @click="resolveAlert(activeAlert.id, true)" class="btn-outline btn-sm">
                {{ $t('parasos.sos.false_alarm') }}
              </button>
            </div>
          </div>

          <!-- SOS Button (big, prominent) — tap for modal, long press for instant EMERGENCY -->
          <div v-if="group.is_member && !activeAlert" class="mb-6">
            <button
              ref="sosButtonRef"
              @mousedown="startLongPress"
              @mouseup="endLongPress"
              @mouseleave="endLongPress"
              @touchstart.prevent="startLongPress"
              @touchend="endLongPress"
              @touchcancel="endLongPress"
              @keydown="handleSOSKeyDown"
              @keyup="handleSOSKeyUp"
              class="w-full py-4 rounded-lg font-bold text-lg transition-all text-white shadow-lg hover:shadow-xl active:scale-[0.98] relative overflow-hidden"
              :class="longPressProgress > 0 ? 'bg-red-700' : 'bg-red-600 hover:bg-red-700'"
            >
              <!-- Long press progress bar -->
              <div
                v-if="longPressProgress > 0"
                class="absolute inset-0 bg-red-900 transition-none"
                :style="{ width: `${longPressProgress}%` }"
              />
              <span class="relative z-10">
                <AlertTriangle :size="24" class="inline-block mr-2 -mt-1" />
                {{ $t('parasos.sos.send_alert') }}
              </span>
            </button>
            <p class="text-xs text-neutral-500 dark:text-neutral-400 text-center mt-1">
              {{ $t('parasos.sos.long_press_emergency') }}
            </p>
          </div>

          <!-- Join button (if not member) -->
          <div v-if="!group.is_member && authStore.isAuthenticated" class="mb-6">
            <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg p-4 space-y-4">
              <!-- Presence selector -->
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  {{ $t('parasos.member.join_as') }}
                </label>
                <div class="flex gap-3">
                  <button
                    v-for="opt in presenceOptions"
                    :key="opt.value"
                    @click="joinPresence = opt.value"
                    class="flex-1 p-3 rounded-lg border text-sm text-center transition-colors"
                    :class="joinPresence === opt.value
                      ? 'border-secondary bg-secondary text-white'
                      : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'"
                  >
                    <div class="font-medium">{{ opt.label }}</div>
                    <div class="text-xs mt-1 opacity-70">{{ opt.desc }}</div>
                  </button>
                </div>
              </div>

              <button
                @click="joinGroup"
                :disabled="joining"
                class="btn-primary w-full"
              >
                {{ joining ? '...' : $t('parasos.groups.join') }}
              </button>
            </div>
          </div>

          <!-- Main content: two columns on large screens -->
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Left: description + map -->
            <div class="lg:col-span-2 space-y-6">
              <!-- Description -->
              <div v-if="group.description" class="text-neutral-700 dark:text-neutral-300 text-sm whitespace-pre-line">
                {{ group.description }}
              </div>

              <!-- Map (only for location-based groups) -->
              <ClientOnly v-if="group.center">
                <StaticMapPreview
                  :latitude="group.center.lat"
                  :longitude="group.center.lon"
                  :height="250"
                />
              </ClientOnly>

              <!-- Alert history -->
              <div>
                <h3 class="font-medium text-neutral-900 dark:text-neutral-100 mb-3">
                  {{ $t('parasos.groups.alert_history') }}
                </h3>
                <div v-if="alerts.length === 0" class="text-sm text-neutral-500">
                  {{ $t('parasos.groups.no_alerts_yet') }}
                </div>
                <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
                  <div
                    v-for="alert in alerts"
                    :key="alert.id"
                    class="p-3 flex items-center gap-3 text-sm"
                  >
                    <span
                      class="w-2 h-2 rounded-full flex-shrink-0"
                      :class="{
                        'bg-blue-500': alert.level === 'INFO',
                        'bg-amber-500': alert.level === 'WARNING',
                        'bg-red-500': alert.level === 'EMERGENCY',
                      }"
                    />
                    <div class="flex-1 min-w-0">
                      <span class="font-medium">{{ alert.sender_display_name || alert.sender_hna }}</span>
                      <span class="text-neutral-500"> · {{ $t(`parasos.sos.level.${alert.level.toLowerCase()}`) }}</span>
                      <span v-if="alert.message" class="text-neutral-500"> — {{ alert.message }}</span>
                    </div>
                    <span class="text-xs text-neutral-400 flex-shrink-0">{{ timeAgo(alert.created_at) }}</span>
                    <UiBadge
                      :variant="alert.status === 'ACTIVE' ? 'warning' : alert.status === 'FALSE_ALARM' ? 'error' : 'success'"
                      size="sm"
                    >
                      {{ alert.status === 'ACTIVE' ? $t('parasos.sos.active_alert') : alert.status === 'FALSE_ALARM' ? $t('parasos.sos.false_alarm') : $t('parasos.sos.resolved') }}
                    </UiBadge>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: members + privacy -->
            <div class="space-y-6">
              <!-- Members -->
              <div>
                <h3 class="font-medium text-neutral-900 dark:text-neutral-100 mb-3">
                  {{ $t('parasos.groups.members') }} ({{ group.members_count }})
                </h3>
                <div class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
                  <div
                    v-for="member in members"
                    :key="member.id"
                    class="p-3 flex items-center gap-3"
                  >
                    <div class="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-700 flex-shrink-0 overflow-hidden">
                      <img v-if="member.profile_avatar_url" :src="member.profile_avatar_url" class="w-full h-full object-cover" />
                    </div>
                    <div class="flex-1 min-w-0">
                      <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
                        {{ member.profile_display_name || member.profile_hna }}
                      </div>
                      <div class="text-xs text-neutral-500">
                        {{ $t(`parasos.member.${member.presence.toLowerCase()}`) }}
                        <span v-if="member.role === 'ADMIN'" class="ml-1 text-primary-600 dark:text-primary-400">{{ $t('parasos.member.admin') }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Invite Links (admin only) -->
              <div v-if="group.is_admin">
                <h3 class="font-medium text-neutral-900 dark:text-neutral-100 mb-3">
                  {{ $t('parasos.invite.title') }}
                </h3>

                <!-- Private group hint -->
                <p v-if="group.visibility === 'PRIVATE'" class="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
                  {{ $t('parasos.invite.private_group_hint') }}
                </p>

                <!-- Create invite (hidden if there's already a valid one) -->
                <button v-if="!invites.some(i => i.is_valid)" @click="createInvite" class="btn-outline btn-sm w-full mb-3">
                  {{ $t('parasos.invite.create') }}
                </button>

                <!-- Invite list -->
                <div v-if="invites.length" class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
                  <div
                    v-for="inv in invites"
                    :key="inv.id"
                    class="p-3 text-sm"
                  >
                    <div class="flex items-center justify-between mb-1">
                      <span class="font-medium truncate">{{ inv.label || inv.token.slice(0, 12) + '…' }}</span>
                      <span
                        v-if="!inv.is_valid"
                        class="text-xs text-red-500"
                      >{{ inv.expires_at && new Date(inv.expires_at) < new Date() ? $t('parasos.invite.expired') : $t('parasos.invite.exhausted') }}</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs text-neutral-500">
                      <span>{{ $t('parasos.invite.uses', { count: inv.uses_count }) }} / {{ inv.max_uses || $t('parasos.invite.unlimited') }}</span>
                    </div>
                    <div class="flex gap-2 mt-2">
                      <button
                        v-if="inv.is_valid"
                        @click="copyInviteLink(inv.token)"
                        class="btn-outline btn-sm text-xs flex-1"
                      >
                        {{ copiedToken === inv.token ? $t('parasos.invite.copied') : $t('parasos.invite.copy_link') }}
                      </button>
                      <button
                        @click="deleteInvite(inv.id)"
                        class="btn-sm text-xs"
                        :class="pendingDeleteInviteId === inv.id ? 'btn-error' : 'btn-outline-error'"
                      >
                        {{ pendingDeleteInviteId === inv.id ? $t('common.confirm') + '?' : $t('parasos.invite.delete') }}
                      </button>
                    </div>
                  </div>
                </div>
                <p v-else class="text-sm text-neutral-500">
                  {{ $t('parasos.invite.no_invites') }}
                </p>
              </div>

              <!-- Privacy notice -->
              <UiAlert variant="info" :dismissible="false">
                <template #title>{{ $t('parasos.privacy.title') }}</template>
                <ul class="text-xs space-y-1 mt-1">
                  <li>{{ $t('parasos.privacy.no_tracking') }}</li>
                  <li>{{ $t('parasos.privacy.sos_only') }}</li>
                  <li>{{ $t('parasos.privacy.responder_voluntary') }}</li>
                </ul>
              </UiAlert>

              <!-- Leave group -->
              <button
                v-if="group.is_member && !group.is_admin"
                @click="showLeaveConfirm = true"
                class="btn-outline-error btn-sm w-full"
              >
                {{ $t('parasos.groups.leave') }}
              </button>

              <!-- Delete group (admin only) -->
              <button
                v-if="group.is_admin"
                @click="showDeleteGroupConfirm = true"
                class="btn-outline-error btn-sm w-full"
              >
                {{ $t('parasos.groups.delete') }}
              </button>
            </div>
          </div>
        </template>

        <!-- SOS Modal -->
        <Teleport to="body">
          <div v-if="showSOSModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showSOSModal = false" @keydown="handleModalKeydown">
            <div ref="sosModalRef" role="dialog" aria-modal="true" aria-labelledby="sos-modal-title" class="bg-white dark:bg-neutral-900 rounded-xl shadow-xl max-w-md w-full mx-4 p-6">
              <h2 id="sos-modal-title" class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-4">
                {{ $t('parasos.sos.select_level') }}
              </h2>

              <!-- Level buttons -->
              <div class="space-y-3 mb-4" role="radiogroup" :aria-label="$t('parasos.sos.select_level')">
                <button
                  v-for="lvl in sosLevels"
                  :key="lvl.value"
                  @click="sosForm.level = lvl.value"
                  role="radio"
                  :aria-checked="sosForm.level === lvl.value"
                  class="w-full p-3 rounded-lg border text-left transition-colors"
                  :class="sosForm.level === lvl.value
                    ? lvl.activeClass
                    : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'"
                >
                  <div class="flex items-center gap-2">
                    <component :is="lvl.icon" :size="20" />
                    <span class="font-medium">{{ lvl.label }}</span>
                  </div>
                  <p class="text-xs mt-1 opacity-70">{{ lvl.desc }}</p>
                </button>
              </div>

              <!-- Category -->
              <select
                v-model="sosForm.category"
                class="w-full px-3 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm mb-3"
              >
                <option v-for="cat in sosCategories" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </option>
              </select>

              <!-- Message -->
              <textarea
                v-model="sosForm.message"
                :placeholder="$t('parasos.sos.message_placeholder')"
                rows="2"
                class="w-full px-3 py-2.5 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 text-sm resize-none mb-4"
              />

              <!-- Actions -->
              <div class="flex gap-3">
                <button @click="showSOSModal = false" class="btn-ghost flex-1">
                  {{ $t('common.cancel') }}
                </button>
                <button
                  @click="sendSOS"
                  :disabled="sendingSOS"
                  class="flex-1 py-2.5 rounded-lg font-bold text-white transition-colors"
                  :class="sosForm.level === 'EMERGENCY' ? 'bg-red-600 hover:bg-red-700' : sosForm.level === 'WARNING' ? 'bg-amber-600 hover:bg-amber-700' : 'bg-blue-600 hover:bg-blue-700'"
                >
                  {{ sendingSOS ? $t('parasos.sos.sending') : $t('parasos.sos.send_alert') }}
                </button>
              </div>
            </div>
          </div>
        </Teleport>
      </div>
    </div>
  </div>

  <UiConfirmModal
    v-model="showLeaveConfirm"
    :title="t('parasos.groups.leave')"
    :message="t('parasos.groups.leave') + '?'"
    :icon="LogOut"
    variant="warning"
    :confirm-label="t('parasos.groups.leave')"
    @confirm="leaveGroup"
  />

  <UiConfirmModal
    v-model="showDeleteGroupConfirm"
    :title="t('parasos.groups.delete')"
    :message="t('parasos.groups.delete_confirm')"
    :icon="Trash2"
    variant="error"
    :confirm-label="t('parasos.groups.delete')"
    @confirm="deleteGroup"
  />
</template>

<script setup lang="ts">
import { ArrowLeft, AlertTriangle, Info, AlertCircle, Eye, Navigation, MapPin as MapPinIcon, X, Link as LinkIcon, LogOut, Trash2 } from 'lucide-vue-next'
import StaticMapPreview from '~/components/IoT/StaticMapPreview.vue'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const authStore = useAuthStore()
const toastStore = useToastStore()

const realtimeStore = useRealtimeStore()
const groupId = route.params.id as string

const loading = ref(true)
const group = ref<any>(null)

useSeoMeta({
  title: () => group.value?.name ? `${group.value.name} — Parahub` : `${t('parasos.groups.title')} — Parahub`,
})
const members = ref<any[]>([])
const alerts = ref<any[]>([])
const activeAlert = ref<any>(null)
const myResponse = ref<any>(null)

const showSOSModal = ref(false)
const sendingSOS = ref(false)
const joining = ref(false)
const showLeaveConfirm = ref(false)
const showDeleteGroupConfirm = ref(false)
const pendingDeleteInviteId = ref<string | null>(null)
let pendingDeleteInviteTimer: ReturnType<typeof setTimeout> | null = null
const joinPresence = ref('LOCAL')
const invites = ref<any[]>([])
const copiedToken = ref('')

// Accessibility refs
const sosButtonRef = ref<HTMLButtonElement>()
const sosModalRef = ref<HTMLDivElement>()

// Long press for instant EMERGENCY
const longPressProgress = ref(0)
let longPressTimer: ReturnType<typeof setInterval> | null = null
let longPressFired = false
const LONG_PRESS_MS = 1500

function startLongPress() {
  longPressFired = false
  longPressProgress.value = 0
  const start = Date.now()
  longPressTimer = setInterval(() => {
    const elapsed = Date.now() - start
    longPressProgress.value = Math.min(100, (elapsed / LONG_PRESS_MS) * 100)
    if (elapsed >= LONG_PRESS_MS && !longPressFired) {
      longPressFired = true
      endLongPress()
      sendEmergencySOS()
    }
  }, 30)
}

function endLongPress() {
  const wasPressed = longPressTimer !== null
  if (longPressTimer) {
    clearInterval(longPressTimer)
    longPressTimer = null
  }
  if (wasPressed && !longPressFired && longPressProgress.value < 100) {
    // Short press — open modal
    if (longPressProgress.value < 10) showSOSModal.value = true
  }
  longPressProgress.value = 0
}

// Keyboard support for SOS button (Enter/Space — same as mouse/touch)
function handleSOSKeyDown(e: KeyboardEvent) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  if (e.repeat) return // prevent repeated keydown from re-triggering
  e.preventDefault()
  startLongPress()
}

function handleSOSKeyUp(e: KeyboardEvent) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  e.preventDefault()
  endLongPress()
}

// Focus trap + Escape for SOS modal
function handleModalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    showSOSModal.value = false
    return
  }
  if (e.key !== 'Tab') return
  const focusable = sosModalRef.value?.querySelectorAll<HTMLElement>(
    'button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  if (!focusable?.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

// Focus management: trap into modal on open, return to SOS button on close
watch(showSOSModal, async (val) => {
  if (val) {
    await nextTick()
    const firstFocusable = sosModalRef.value?.querySelector<HTMLElement>('button, input, select, textarea')
    firstFocusable?.focus()
  } else {
    sosButtonRef.value?.focus()
  }
})

async function sendEmergencySOS() {
  sosForm.level = 'EMERGENCY'
  sosForm.category = 'OTHER'
  sosForm.message = ''
  await sendSOS()
}

// Elapsed timer for active SOS
const elapsedTimer = ref('')
let timerInterval: ReturnType<typeof setInterval> | null = null

function startElapsedTimer() {
  if (timerInterval) clearInterval(timerInterval)
  updateElapsed()
  timerInterval = setInterval(updateElapsed, 1000)
}

function updateElapsed() {
  if (!activeAlert.value) {
    elapsedTimer.value = ''
    return
  }
  const diff = Date.now() - new Date(activeAlert.value.created_at).getTime()
  const secs = Math.floor(diff / 1000)
  const m = Math.floor(secs / 60)
  const s = secs % 60
  const h = Math.floor(m / 60)
  if (h > 0) {
    elapsedTimer.value = `${h}:${String(m % 60).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  } else {
    elapsedTimer.value = `${m}:${String(s).padStart(2, '0')}`
  }
}

watch(activeAlert, (val) => {
  if (val) startElapsedTimer()
  else if (timerInterval) { clearInterval(timerInterval); elapsedTimer.value = '' }
})

// Realtime SOS events — live updates without page refresh
function _onSosEvent(data: any) {
  if (data.group_id !== groupId) return
  fetchAll()
}

realtimeStore.joinRoom('parasos', groupId)
realtimeStore.on('sos.new', _onSosEvent)
realtimeStore.on('sos.response', _onSosEvent)
realtimeStore.on('sos.resolved', _onSosEvent)

onUnmounted(() => {
  if (timerInterval) clearInterval(timerInterval)
  if (longPressTimer) clearInterval(longPressTimer)
  realtimeStore.off('sos.new', _onSosEvent)
  realtimeStore.off('sos.response', _onSosEvent)
  realtimeStore.off('sos.resolved', _onSosEvent)
})

const sosForm = reactive({
  level: 'EMERGENCY',
  category: 'OTHER',
  message: '',
})

const sosLevels = computed(() => [
  { value: 'INFO', label: t('parasos.sos.level.info'), desc: t('parasos.sos.level.info_desc'), icon: Info, activeClass: 'border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300' },
  { value: 'WARNING', label: t('parasos.sos.level.warning'), desc: t('parasos.sos.level.warning_desc'), icon: AlertCircle, activeClass: 'border-amber-500 bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300' },
  { value: 'EMERGENCY', label: t('parasos.sos.level.emergency'), desc: t('parasos.sos.level.emergency_desc'), icon: AlertTriangle, activeClass: 'border-red-500 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300' },
])

const sosCategories = computed(() => [
  { value: 'OTHER', label: t('parasos.sos.category.other') },
  { value: 'SUSPICIOUS_ACTIVITY', label: t('parasos.sos.category.suspicious_activity') },
  { value: 'ALARM_TRIGGERED', label: t('parasos.sos.category.alarm_triggered') },
  { value: 'MEDICAL', label: t('parasos.sos.category.medical') },
  { value: 'FIRE', label: t('parasos.sos.category.fire') },
  { value: 'INTRUSION', label: t('parasos.sos.category.intrusion') },
])

const presenceOptions = computed(() => [
  { value: 'LOCAL', label: t('parasos.member.local'), desc: t('parasos.member.presence_local') },
  { value: 'REMOTE', label: t('parasos.member.remote'), desc: t('parasos.member.presence_remote') },
])

const responseActions = computed(() => [
  { status: 'SEEN', label: t('parasos.response.i_see'), icon: Eye },
  { status: 'ON_WAY', label: t('parasos.response.on_my_way'), icon: Navigation },
  { status: 'ON_SITE', label: t('parasos.response.im_here'), icon: MapPinIcon },
  { status: 'UNABLE', label: t('parasos.response.cant_help'), icon: X },
])

const alertBannerClass = computed(() => {
  if (!activeAlert.value) return ''
  const level = activeAlert.value.level
  if (level === 'EMERGENCY') return 'border-red-500 bg-red-50 dark:bg-red-950/50 text-red-800 dark:text-red-200'
  if (level === 'WARNING') return 'border-amber-500 bg-amber-50 dark:bg-amber-950/50 text-amber-800 dark:text-amber-200'
  return 'border-blue-500 bg-blue-50 dark:bg-blue-950/50 text-blue-800 dark:text-blue-200'
})

const alertIcon = computed(() => {
  if (!activeAlert.value) return Info
  if (activeAlert.value.level === 'EMERGENCY') return AlertTriangle
  if (activeAlert.value.level === 'WARNING') return AlertCircle
  return Info
})

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return t('parasos.time.just_now')
  if (mins < 60) return t('parasos.time.minutes_ago', { n: mins })
  const hours = Math.floor(mins / 60)
  if (hours < 24) return t('parasos.time.hours_ago', { n: hours })
  return t('parasos.time.days_ago', { n: Math.floor(hours / 24) })
}

async function fetchAll() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const headers = authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {}
    const opts = { credentials: 'include' as const, headers }

    const [groupData, membersData, alertsData] = await Promise.all([
      $fetch<any>(`/api/v1/parasos/groups/${groupId}/`, opts),
      $fetch<any>(`/api/v1/parasos/groups/${groupId}/members/`, opts),
      $fetch<any>(`/api/v1/parasos/groups/${groupId}/alerts/`, opts),
    ])

    group.value = groupData
    members.value = Array.isArray(membersData) ? membersData : membersData.items || []
    const allAlerts = Array.isArray(alertsData) ? alertsData : alertsData.items || []
    alerts.value = allAlerts
    activeAlert.value = allAlerts.find((a: any) => a.status === 'ACTIVE') || null

    // If there's an active alert, fetch its details (with sender info) and my response
    if (activeAlert.value) {
      try {
        const detail = await $fetch<any>(`/api/v1/parasos/alerts/${activeAlert.value.id}/`, opts)
        activeAlert.value = detail

        const responses = await $fetch<any>(`/api/v1/parasos/alerts/${activeAlert.value.id}/responses/`, opts)
        const respList = Array.isArray(responses) ? responses : responses.items || []
        myResponse.value = respList.find((r: any) => r.responder_id === authStore.profile?.id) || null
      } catch { /* ignore */ }
    }
    // Fetch invites for admin
    await fetchInvites()
  } catch (e) {
    console.error('Failed to fetch group:', e)
    toastStore.error(t('parasos.errors.fetch_group'))
  } finally {
    loading.value = false
  }
}

async function sendSOS() {
  sendingSOS.value = true
  try {
    await authStore.ensureToken()

    // Get current location
    let location: { latitude: number; longitude: number } | undefined
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 5000 })
      })
      location = { latitude: pos.coords.latitude, longitude: pos.coords.longitude }
    } catch { /* location optional */ }

    await $fetch(`/api/v1/parasos/groups/${groupId}/sos/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        level: sosForm.level,
        category: sosForm.category,
        message: sosForm.message,
        location,
      },
    })

    showSOSModal.value = false
    sosForm.message = ''
    toastStore.success(t('parasos.sos.sent'))
    await fetchAll()
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.send_sos'))
  } finally {
    sendingSOS.value = false
  }
}

async function respondToAlert(alertId: string, status: string) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/alerts/${alertId}/respond/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { status, note: '' },
    })
    await fetchAll()
  } catch (e: any) {
    console.error('Failed to respond:', e)
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.respond'))
  }
}

async function resolveAlert(alertId: string, falseAlarm: boolean) {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/alerts/${alertId}/resolve/?false_alarm=${falseAlarm}`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    await fetchAll()
  } catch (e: any) {
    console.error('Failed to resolve:', e)
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.resolve'))
  }
}

async function joinGroup() {
  joining.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/groups/${groupId}/join/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { presence: joinPresence.value },
    })
    toastStore.success(t('parasos.groups.joined'))
    await fetchAll()
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.join_group'))
  } finally {
    joining.value = false
  }
}

async function leaveGroup() {
  showLeaveConfirm.value = false
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/groups/${groupId}/leave/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    toastStore.success(t('parasos.groups.left'))
    navigateTo(localePath('/sos'))
  } catch (e: any) {
    const msg = e?.data?.detail || e?.data?.message || t('parasos.errors.leave_group')
    toastStore.error(msg)
  }
}

async function deleteGroup() {
  showDeleteGroupConfirm.value = false
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/groups/${groupId}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    toastStore.success(t('parasos.groups.deleted'))
    navigateTo(localePath('/sos'))
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.delete_group'))
  }
}

async function fetchInvites() {
  if (!group.value?.is_admin) return
  try {
    await authStore.ensureToken()
    const data = await $fetch<any>(`/api/v1/parasos/groups/${groupId}/invites/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    invites.value = Array.isArray(data) ? data : data.items || []
  } catch { /* ignore — not admin or fetch failed */ }
}

async function createInvite() {
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/groups/${groupId}/invites/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { label: '', max_uses: 0 },
    })
    await fetchInvites()
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.create_invite'))
  }
}

async function deleteInvite(inviteId: string) {
  if (pendingDeleteInviteId.value !== inviteId) {
    pendingDeleteInviteId.value = inviteId
    if (pendingDeleteInviteTimer) clearTimeout(pendingDeleteInviteTimer)
    pendingDeleteInviteTimer = setTimeout(() => { pendingDeleteInviteId.value = null }, 3000)
    return
  }
  pendingDeleteInviteId.value = null
  if (pendingDeleteInviteTimer) clearTimeout(pendingDeleteInviteTimer)
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/invites/${inviteId}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    await fetchInvites()
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.delete_invite'))
  }
}

function copyInviteLink(token: string) {
  const url = `${window.location.origin}${localePath(`/sos/join/${token}`)}`
  navigator.clipboard.writeText(url)
  copiedToken.value = token
  setTimeout(() => { copiedToken.value = '' }, 2000)
}

onMounted(() => fetchAll())
</script>
