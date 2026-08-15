<template>
  <div v-if="ready && !allDone">
    <!-- Collapsed chip -->
    <button
      v-if="collapsed"
      @click="setCollapsed(false)"
      class="flex items-center gap-2 px-3 py-2 bg-white dark:bg-neutral-800 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
      :aria-label="$t('dashboard.getting_started')"
      :aria-expanded="false"
    >
      <ListChecks class="w-4 h-4 text-secondary dark:text-secondary-400" />
      <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ $t('dashboard.getting_started') }}</span>
      <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ doneCount }}/{{ steps.length }}</span>
    </button>

    <!-- Expanded console -->
    <div
      v-else
      class="w-72 bg-white dark:bg-neutral-800 rounded-lg shadow-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden"
    >
      <div class="flex items-center justify-between pl-3 pr-2 py-2 border-b border-neutral-200 dark:border-neutral-700">
        <div class="flex items-center gap-2 min-w-0">
          <ListChecks class="w-4 h-4 flex-shrink-0 text-secondary dark:text-secondary-400" />
          <span class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">{{ $t('dashboard.getting_started') }}</span>
        </div>
        <div class="flex items-center gap-1.5 flex-shrink-0">
          <span class="text-xs text-neutral-400 dark:text-neutral-500">{{ doneCount }}/{{ steps.length }}</span>
          <button
            @click="setCollapsed(true)"
            :aria-label="$t('common.close')"
            class="p-1 rounded hover:bg-primary-100 dark:hover:bg-primary-900/40 text-neutral-500 dark:text-neutral-400"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <div class="divide-y divide-neutral-200 dark:divide-neutral-700">
        <NuxtLink
          v-for="step in steps"
          :key="step.key"
          :to="localePath(step.to)"
          class="flex items-center gap-2.5 px-3 py-2 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
        >
          <div
            class="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
            :class="step.done ? 'bg-success/10 dark:bg-success/20' : 'bg-primary/10 dark:bg-primary-900/30'"
          >
            <Check v-if="step.done" class="w-4 h-4 text-success dark:text-success-300" />
            <component v-else :is="step.icon" class="w-4 h-4 text-neutral-700 dark:text-neutral-200" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <div
                class="text-sm font-medium leading-tight"
                :class="step.done ? 'text-neutral-400 dark:text-neutral-500 line-through' : 'text-neutral-900 dark:text-neutral-100'"
              >{{ step.label }}</div>
              <!-- WoT is the one step other people complete for you — show how far along -->
              <span
                v-if="step.progress && !step.done"
                class="ml-auto text-xs font-medium text-secondary dark:text-secondary-400 flex-shrink-0"
              >{{ step.progress }}</span>
            </div>
            <div v-if="!step.done" class="text-xs text-neutral-500 dark:text-neutral-400 leading-tight mt-0.5">{{ step.desc }}</div>
          </div>
        </NuxtLink>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated } from 'vue'
import { User, KeyRound, ShieldCheck, Check, X, ListChecks } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { usePGP } from '~/composables/usePGP'

// Onboarding quest log — the map is the home screen, so the first steps live
// here as a HUD console. They are the setup a newcomer needs before the
// platform works at all: a recognisable profile, keys to sign with (one seed
// derives both PGP and the wallet), and the WoT verifications that open
// everything else. Posting a listing is deliberately absent — that is a want,
// not setup, and a checkbox for it only breeds "test" listings. Every step is
// server-derived, so the log closes by itself; a localStorage flag then skips
// the fetch forever.
const DONE_KEY = 'onboarding:done'
const COLLAPSED_KEY = 'questlog:collapsed'

const authStore = useAuthStore()
const { t } = useI18n()
const localePath = useLocalePath()
// The server only knows a key is registered to the account; signing needs the
// seed on this device too, so the step counts both and points at whichever
// half is missing.
const { hasKeys: deviceHasKeys, loadKeys: loadDeviceKeys } = usePGP()

const ready = ref(false)
const collapsed = ref(false)
const serverSteps = ref({
  has_profile: false,
  has_keys: false,
  verifications_count: 0,
  verifications_required: 3,
})

const steps = computed(() => [
  {
    key: 'profile',
    to: '/profile',
    icon: User,
    done: serverSteps.value.has_profile,
    progress: '',
    label: t('dashboard.action_profile'),
    desc: t('dashboard.action_profile_desc'),
  },
  {
    key: 'keys',
    // Account already has a key but this device doesn't hold the seed → restore
    to: serverSteps.value.has_keys && !deviceHasKeys.value ? '/seed-restore' : '/seed-setup',
    icon: KeyRound,
    done: serverSteps.value.has_keys && deviceHasKeys.value,
    progress: '',
    label: t('dashboard.action_keys'),
    desc: t('dashboard.action_keys_desc'),
  },
  {
    key: 'verification',
    to: '/docs/wot',
    icon: ShieldCheck,
    done: serverSteps.value.verifications_count >= serverSteps.value.verifications_required,
    progress: `${serverSteps.value.verifications_count}/${serverSteps.value.verifications_required}`,
    label: t('dashboard.action_verify'),
    desc: t('dashboard.action_verify_desc'),
  },
])

const doneCount = computed(() => steps.value.filter(s => s.done).length)
const allDone = computed(() => steps.value.every(s => s.done))

function setCollapsed(value: boolean) {
  collapsed.value = value
  localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0')
}

async function refresh() {
  if (!authStore.isAuthenticated) return
  if (localStorage.getItem(DONE_KEY) === '1') {
    ready.value = false
    return
  }
  try {
    await authStore.ensureToken()
    const [data] = await Promise.all([
      $fetch<{ steps: typeof serverSteps.value; complete: boolean }>(
        '/api/v1/dashboard/onboarding',
        { credentials: 'include', headers: { Authorization: `Bearer ${authStore.token}` } },
      ),
      loadDeviceKeys().catch(() => {}),
    ])
    serverSteps.value = data.steps
    // allDone, not data.complete — the server can't see this device's seed
    if (allDone.value) {
      localStorage.setItem(DONE_KEY, '1')
      ready.value = false
      return
    }
    collapsed.value = localStorage.getItem(COLLAPSED_KEY) === '1'
    ready.value = true
  } catch {
    // Quest log is a nice-to-have — stay hidden rather than surface an error on the map
  }
}

onMounted(refresh)
// MapView is KeepAlive-cached — re-check progress when the user returns to the map
onActivated(refresh)
</script>
