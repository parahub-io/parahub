<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <!-- Loading -->
    <div v-if="loading" class="py-12 text-center" role="status" aria-live="polite">
      <div class="inline-block animate-spin rounded-full h-12 w-12 border-4 border-neutral-300 dark:border-neutral-600 border-t-neutral-900 dark:border-t-neutral-100" />
      <span class="sr-only">{{ $t('common.loading') }}</span>
    </div>

    <!-- Addressed to someone we cannot identify yet -->
    <div v-else-if="needsAuth" class="py-12 text-center">
      <Landmark class="w-16 h-16 mx-auto p-4 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-400 mb-3" />
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {{ $t('directory.invite.title') }}
      </h2>
      <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1 mb-4">
        {{ $t('directory.invite.sign_in_hint') }}
      </p>
      <UiButton variant="primary" :to="localePath(`/login?redirect=/invite/org/${ident}`)">
        {{ $t('directory.invite.sign_in') }}
      </UiButton>
    </div>

    <!-- Gone / not ours -->
    <div v-else-if="!invite" class="py-12 text-center">
      <MailX class="w-16 h-16 mx-auto p-4 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-400 mb-3" />
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {{ $t('directory.invite.not_found') }}
      </h2>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">{{ error }}</p>
      <UiButton variant="outline" size="sm" class="mt-4" :to="localePath('/directory')">
        {{ $t('directory.invite.browse') }}
      </UiButton>
    </div>

    <!-- Resolved -->
    <div v-else-if="done" class="py-12 text-center">
      <component
        :is="done === 'accepted' ? CheckCircle2 : XCircle"
        class="w-16 h-16 mx-auto p-4 rounded-full mb-3"
        :class="done === 'accepted' ? 'bg-success/10 text-success' : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-400'"
      />
      <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {{ done === 'accepted' ? $t('directory.invite.accepted') : $t('directory.invite.declined') }}
      </h2>
      <UiButton
        v-if="done === 'accepted'"
        variant="primary" size="sm" class="mt-4"
        :to="localePath(`/org/${invite.establishment_slug || invite.establishment_id}`)"
      >
        {{ invite.establishment_name }}
      </UiButton>
    </div>

    <!-- The offer -->
    <div v-else class="card p-6 text-center">
      <Landmark class="w-12 h-12 mx-auto text-neutral-400 mb-3" />
      <p class="text-sm text-neutral-500 dark:text-neutral-400">{{ $t('directory.invite.invited_you') }}</p>
      <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 mt-1">
        {{ invite.establishment_name }}
      </h1>

      <div class="mt-3 flex flex-wrap items-center justify-center gap-2">
        <UiBadge variant="secondary" type="soft">
          {{ $t(`directory.members.role_${invite.role.toLowerCase()}`) }}
        </UiBadge>
        <UiBadge v-if="invite.position_title" variant="neutral" type="soft">
          {{ invite.position_title }}
        </UiBadge>
      </div>

      <p v-if="invite.message" class="mt-4 text-sm text-neutral-600 dark:text-neutral-400 italic">
        “{{ invite.message }}”
      </p>

      <p v-if="invite.created_by_hna" class="mt-3 text-xs text-neutral-400 dark:text-neutral-500">
        {{ $t('directory.invite.from') }} {{ invite.created_by_hna.split('@')[0] }}
      </p>

      <UiAlert
        v-if="invite.is_expired"
        variant="warning"
        class="mt-4 text-left"
        :title="$t('directory.invite.expired')"
      />
      <UiAlert
        v-else-if="invite.status !== 'PENDING'"
        variant="info"
        class="mt-4 text-left"
        :title="$t('directory.invite.already_resolved')"
      />

      <!-- A link invite is readable without an account; accepting is not. -->
      <div v-else-if="!authStore.isAuthenticated" class="mt-5">
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
          {{ $t('directory.invite.sign_in_hint') }}
        </p>
        <UiButton variant="primary" :to="localePath(`/login?redirect=/invite/org/${ident}`)">
          {{ $t('directory.invite.sign_in') }}
        </UiButton>
      </div>

      <div v-else class="mt-5 flex justify-center gap-2">
        <UiButton variant="primary" :loading="busy" @click="respond('accept')">
          {{ $t('directory.invite.accept') }}
        </UiButton>
        <UiButton variant="outline" :loading="busy" @click="respond('decline')">
          {{ $t('directory.invite.decline') }}
        </UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle2, XCircle, MailX, Landmark } from 'lucide-vue-next'
import { useToastStore } from '~/stores/toast'

// Deliberately open: a link invite has to be readable by someone who has no
// account yet — that is what it is for. Accepting still needs a profile, and
// `?redirect=` brings them straight back here after signing in.

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()
const toast = useToastStore()

const ident = computed(() => String(route.params.ident))
const loading = ref(true)
const busy = ref(false)
const invite = ref<any>(null)
const error = ref('')
const needsAuth = ref(false)
const done = ref<'accepted' | 'declined' | ''>('')

async function authed() {
  if (!authStore.isAuthenticated) return {}
  await authStore.ensureToken()
  return { Authorization: `Bearer ${authStore.token}` }
}

async function load() {
  needsAuth.value = false
  try {
    invite.value = await $fetch<any>(`/api/v1/geo/invites/${ident.value}/`, {
      credentials: 'include', headers: await authed(),
    })
  } catch (e: any) {
    const status = e?.response?.status ?? e?.statusCode
    // An invitation addressed to a person is unreadable until we know who is
    // asking — "sign in" is the honest answer there, not "not found".
    needsAuth.value = !authStore.isAuthenticated && (status === 403 || status === 401)
    error.value = needsAuth.value ? '' : (e?.data?.detail || e?.response?._data?.detail || '')
    invite.value = null
  } finally {
    loading.value = false
  }
}

async function respond(action: 'accept' | 'decline') {
  busy.value = true
  try {
    await $fetch(`/api/v1/geo/invites/${ident.value}/${action}/`, {
      method: 'POST', credentials: 'include', headers: await authed(),
    })
    done.value = action === 'accept' ? 'accepted' : 'declined'
  } catch (e: any) {
    toast.error(e?.data?.detail || e?.response?._data?.detail || t('directory.members.action_error'))
  } finally {
    busy.value = false
  }
}

onMounted(load)

// On a cold open the client plugin reconciles the session a moment after mount,
// so a named invite can 403 before we know who is asking. Retry once the store
// knows — and never call `ensureSession()` from here: it *clears* the store's
// user when its cookie check fails, which would sign out anyone who lands on
// this page straight after logging in.
watch(() => authStore.isAuthenticated, (signedIn) => {
  if (signedIn && !invite.value) load()
})

useSeoMeta({ title: () => t('directory.invite.title'), robots: 'noindex' })
</script>
