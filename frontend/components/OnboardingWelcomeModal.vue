<template>
  <Modal v-model="show" :title="$t('onboarding.title')" :icon="Sparkles" size="md" :show-close="false" :close-on-backdrop="false">
    <div class="space-y-5">
      <!-- Intro -->
      <p class="text-sm text-neutral-600 dark:text-neutral-300">
        {{ $t('onboarding.intro') }}
      </p>

      <!-- Key actions -->
      <div class="space-y-3">
        <NuxtLink
          v-for="action in actions"
          :key="action.to"
          :to="action.to"
          class="card p-3 flex items-center gap-3 hover:border-primary transition-colors cursor-pointer"
          @click="dismiss"
        >
          <div class="flex-shrink-0 w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
            <component :is="action.icon" class="w-5 h-5 text-neutral-700 dark:text-neutral-200" />
          </div>
          <div class="min-w-0">
            <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ action.label }}</div>
            <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ action.desc }}</div>
          </div>
        </NuxtLink>
      </div>

      <!-- WoT explanation -->
      <div class="rounded-lg bg-secondary/5 border border-secondary/20 p-3">
        <div class="flex items-start gap-2">
          <ShieldCheck class="w-4 h-4 text-secondary dark:text-secondary-400 flex-shrink-0 mt-0.5" />
          <div class="min-w-0">
            <p class="text-xs text-neutral-600 dark:text-neutral-300">
              {{ $t('onboarding.wot_hint') }}
            </p>
            <NuxtLink :to="localePath('/docs/wot')" class="text-xs font-medium text-secondary hover:underline mt-1.5 inline-block" @click="dismiss">
              {{ $t('onboarding.wot_learn_how') }}
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <UiButton variant="primary" @click="dismiss">
        {{ $t('onboarding.start') }}
      </UiButton>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { Sparkles, User, Building2, ShoppingBag, ShieldCheck } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()

const show = defineModel<boolean>({ required: true })

const actions = computed(() => [
  {
    to: localePath('/profile'),
    icon: User,
    label: t('onboarding.action_profile'),
    desc: t('onboarding.action_profile_desc'),
  },
  {
    to: localePath('/directory'),
    icon: Building2,
    label: t('onboarding.action_directory'),
    desc: t('onboarding.action_directory_desc'),
  },
  {
    to: localePath('/market'),
    icon: ShoppingBag,
    label: t('onboarding.action_market'),
    desc: t('onboarding.action_market_desc'),
  },
])

const dismiss = () => {
  show.value = false
  localStorage.setItem('parahub_onboarding_seen', '1')
}
</script>
