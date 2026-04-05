<template>
  <div class="max-w-md mx-auto px-4 py-16">
    <!-- Loading -->
    <div v-if="pending" class="flex justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-primary" />
    </div>

    <!-- Error -->
    <div v-else-if="fetchError" class="space-y-4">
      <UiAlert variant="error">{{ $t('condo.invite_error') }}</UiAlert>
      <NuxtLink :to="localePath('/')" class="text-link text-sm">Parahub →</NuxtLink>
    </div>

    <!-- Invite info -->
    <div v-else-if="invite" class="bg-white dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700 p-6">
      <h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">{{ $t('condo.invite_accept_title') }}</h1>
      <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-6">{{ $t('condo.invite_accept_subtitle') }}</p>

      <div class="space-y-3 mb-6">
        <div class="flex justify-between text-sm">
          <span class="text-neutral-500">{{ $t('condo.title') }}</span>
          <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ invite.condominium_name }}</span>
        </div>
        <div v-if="invite.address" class="flex justify-between text-sm">
          <span class="text-neutral-500">{{ $t('condo.step_address') }}</span>
          <span class="text-neutral-700 dark:text-neutral-300 text-right max-w-[200px]">{{ invite.address }}</span>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-neutral-500">{{ $t('condo.invite_fraction') }}</span>
          <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ invite.fraction_identifier }}</span>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-neutral-500">{{ $t('condo.type') }}</span>
          <span class="text-neutral-700 dark:text-neutral-300">{{ $t(`condo.type_${invite.fraction_type.toLowerCase()}`) }}</span>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-neutral-500">{{ $t('condo.invite_permilagem') }}</span>
          <span class="font-mono font-medium text-neutral-900 dark:text-neutral-100">{{ Number(invite.permilagem).toFixed(3) }} ‰</span>
        </div>
      </div>

      <!-- Success -->
      <div v-if="accepted" class="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 text-center">
        <p class="text-green-700 dark:text-green-400 font-medium">{{ $t('condo.invite_success') }}</p>
        <NuxtLink :to="localePath(`/org/${invite.condominium_slug}`)" class="text-sm text-primary hover:underline mt-2 inline-block">
          {{ $t('condo.title') }} →
        </NuxtLink>
      </div>

      <!-- Accept button -->
      <div v-else>
        <div v-if="!authStore.isAuthenticated" class="text-center mb-4">
          <UiButton variant="primary" :to="localePath('/login')" class="w-full justify-center">
            {{ $t('login.submit') }}
          </UiButton>
        </div>
        <div v-else>
          <UiAlert v-if="acceptError" variant="error" class="mb-3">{{ acceptError }}</UiAlert>
          <UiButton variant="primary" class="w-full justify-center" :loading="accepting" @click="accept">
            {{ $t('condo.invite_accept') }}
          </UiButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next'

const route = useRoute()
const { t } = useI18n()
const localePath = useLocalePath()
const authStore = useAuthStore()

const token = route.params.token as string

const { data: invite, pending, error: fetchError } = await useAsyncData(
  `condo-invite-${token}`,
  () => $fetch<any>(`/api/v1/geo/condominiums/invite/${token}/`)
)

useSeoMeta({
  title: () => invite.value?.condominium_name
    ? `${invite.value.condominium_name} — ${t('condo.invite_accept_title')}`
    : t('condo.meta_invite_title'),
  ogTitle: () => invite.value?.condominium_name
    ? `${invite.value.condominium_name} — ${t('condo.invite_accept_title')}`
    : t('condo.meta_invite_title'),
  description: () => t('condo.meta_invite_desc'),
  ogDescription: () => t('condo.meta_invite_desc'),
  ogImage: '/og-image.jpg',
  ogType: 'website',
  twitterCard: 'summary',
  robotsContent: 'noindex',
})

const accepting = ref(false)
const accepted = ref(false)
const acceptError = ref('')

const accept = async () => {
  accepting.value = true
  acceptError.value = ''
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/condominiums/invite/${token}/accept/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.accessToken}` },
    })
    accepted.value = true
  } catch (err: any) {
    acceptError.value = err?.data?.detail || err?.message || t('condo.invite_error')
  } finally {
    accepting.value = false
  }
}
</script>
