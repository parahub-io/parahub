<template>
  <div>
    <div class="w-full px-4 sm:px-6 lg:px-8 py-6">
      <div class="max-w-md mx-auto w-full">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-12 text-neutral-500">
          {{ $t('parasos.loading') }}
        </div>

        <!-- Invalid invite -->
        <div v-else-if="error" class="text-center py-12">
          <div class="text-red-500 mb-4">{{ error }}</div>
          <NuxtLink :to="localePath('/sos')" class="btn-outline">
            {{ $t('parasos.groups.title') }}
          </NuxtLink>
        </div>

        <!-- Invite info -->
        <template v-else-if="inviteInfo">
          <div class="border border-neutral-200 dark:border-neutral-700 rounded-xl p-6 space-y-4">
            <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
              {{ $t('parasos.invite.join_title') }}
            </h1>

            <div>
              <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('parasos.invite.join_group_name') }}</p>
              <p class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{{ inviteInfo.group_name }}</p>
              <p v-if="inviteInfo.group_description" class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{{ inviteInfo.group_description }}</p>
              <p class="text-sm text-neutral-500 mt-1">
                {{ $t('parasos.invite.join_members', inviteInfo.group_members_count) }}
              </p>
            </div>

            <!-- Not authenticated -->
            <div v-if="!authStore.isAuthenticated" class="text-center">
              <p class="text-sm text-neutral-500 mb-3">{{ $t('parasos.member.login_to_join') }}</p>
              <NuxtLink :to="localePath('/login')" class="btn-primary">
                {{ $t('common.login') }}
              </NuxtLink>
            </div>

            <!-- Authenticated: join form -->
            <template v-else>
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
                {{ joining ? '...' : $t('parasos.invite.join_button') }}
              </button>
            </template>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toastStore = useToastStore()

const token = route.params.token as string

const loading = ref(true)
const error = ref('')
const inviteInfo = ref<any>(null)
const joining = ref(false)
const joinPresence = ref('LOCAL')

const presenceOptions = computed(() => [
  { value: 'LOCAL', label: t('parasos.member.local'), desc: t('parasos.member.presence_local') },
  { value: 'REMOTE', label: t('parasos.member.remote'), desc: t('parasos.member.presence_remote') },
])

async function joinGroup() {
  joining.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/parasos/groups/${inviteInfo.value.group_id}/join/`, {
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: {
        presence: joinPresence.value,
        invite_token: token,
      },
    })
    toastStore.success(t('parasos.invite.join_success'))
    router.push(localePath(`/sos/${inviteInfo.value.group_id}`))
  } catch (e: any) {
    toastStore.error(e.data?.message || e.data?.detail || t('parasos.errors.join_group'))
  } finally {
    joining.value = false
  }
}

onMounted(async () => {
  try {
    const data = await $fetch<any>(`/api/v1/parasos/invites/${token}/info/`)
    if (!data.is_valid) {
      error.value = t('parasos.errors.invite_invalid')
    } else {
      inviteInfo.value = data
    }
  } catch {
    error.value = t('parasos.errors.fetch_invite')
  } finally {
    loading.value = false
  }
})
</script>
