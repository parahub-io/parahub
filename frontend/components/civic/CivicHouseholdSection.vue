<template>
  <section>
    <div class="bg-neutral-100 dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
      <div class="flex items-center justify-between gap-3 mb-3">
        <div class="flex items-center gap-2">
          <Users class="w-5 h-5 text-neutral-600 dark:text-neutral-400" aria-hidden="true" />
          <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ $t('civic.household.members') }}</span>
          <span v-if="members.length" class="text-sm text-neutral-500 dark:text-neutral-400">({{ members.length }})</span>
        </div>
        <UiButton variant="outline" size="sm" :icon="UserPlus" :loading="inviting" @click="generateInvite">
          {{ $t('civic.household.invite') }}
        </UiButton>
      </div>

      <div v-if="inviteUrl" class="mb-3">
        <div class="flex gap-2">
          <input
            :value="inviteUrl" readonly
            class="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300"
          />
          <UiButton variant="secondary" size="sm" :icon="Copy" @click="copyInvite">
            {{ copied ? $t('civic.household.linkCopied') : $t('civic.household.copyLink') }}
          </UiButton>
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('civic.household.inviteHint') }}</p>
      </div>

      <div class="divide-y divide-neutral-200 dark:divide-neutral-700">
        <div v-for="m in members" :key="m.profile_id" class="py-2 flex items-center justify-between gap-3 text-sm">
          <div class="flex items-center gap-2 min-w-0">
            <User class="w-4 h-4 text-neutral-400 shrink-0" aria-hidden="true" />
            <span class="font-medium text-neutral-800 dark:text-neutral-200 truncate">
              {{ m.display_name || m.hna.split('@')[0] }}
            </span>
            <UiBadge v-if="m.is_owner" variant="secondary" type="soft">owner</UiBadge>
          </div>
          <UiButton
            v-if="!m.is_owner"
            :variant="pendingRemove === m.profile_id ? 'error' : 'ghost'"
            size="sm"
            @click="removeMember(m.profile_id)"
          >
            {{ pendingRemove === m.profile_id ? $t('common.confirm', 'Sure?') : $t('civic.household.remove') }}
          </UiButton>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Users, User, UserPlus, Copy } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const props = defineProps<{ propertyId: string }>()

const { t: $t } = useI18n()
const authStore = useAuthStore()

const members = ref<any[]>([])
const inviteUrl = ref('')
const inviting = ref(false)
const copied = ref(false)
const pendingRemove = ref<string | null>(null)
let removeTimer: ReturnType<typeof setTimeout> | null = null

async function authed(): Promise<Record<string, string>> {
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function load() {
  try {
    members.value = await $fetch(`/api/v1/iot/properties/${props.propertyId}/household/`, {
      credentials: 'include', headers: await authed(),
    })
  } catch { /* not accessible */ }
}

async function generateInvite() {
  inviting.value = true
  try {
    const res: any = await $fetch(`/api/v1/iot/properties/${props.propertyId}/household/invite/`, {
      method: 'POST', credentials: 'include', headers: await authed(),
    })
    inviteUrl.value = `${window.location.origin}/household/join?token=${res.token}`
  } catch { /* owner-only */ }
  inviting.value = false
}

async function copyInvite() {
  try {
    await navigator.clipboard.writeText(inviteUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch { /* clipboard unavailable */ }
}

// Two-tap destructive confirmation (design-system pattern)
async function removeMember(profileId: string) {
  if (pendingRemove.value !== profileId) {
    pendingRemove.value = profileId
    if (removeTimer) clearTimeout(removeTimer)
    removeTimer = setTimeout(() => { pendingRemove.value = null }, 3000)
    return
  }
  pendingRemove.value = null
  try {
    await $fetch(`/api/v1/iot/properties/${props.propertyId}/household/${profileId}/`, {
      method: 'DELETE', credentials: 'include', headers: await authed(),
    })
    await load()
  } catch { /* keep list */ }
}

onMounted(load)
</script>
