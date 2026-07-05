<template>
  <!-- GDPR Art. 9 explicit consent, plain words. Copy discipline (A2): never claims
       "anonymous" — states depersonalized storage and its honest limits. -->
  <div class="card p-4 border-secondary/40">
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
      <ShieldCheck class="w-5 h-5 text-secondary dark:text-secondary-400" aria-hidden="true" />
      {{ $t('civic.consent.title') }}
    </h2>
    <div class="space-y-3 text-sm text-neutral-700 dark:text-neutral-300">
      <p>{{ $t('civic.consent.p1') }}</p>
      <p>{{ $t('civic.consent.p2') }}</p>
      <p class="text-neutral-500 dark:text-neutral-400">{{ $t('civic.consent.p3') }}</p>
    </div>
    <div class="flex flex-col sm:flex-row gap-2 mt-4">
      <UiButton variant="primary" :loading="loading" @click="$emit('accept')">
        {{ $t('civic.consent.accept') }}
      </UiButton>
      <UiButton variant="ghost" :disabled="loading" @click="$emit('decline')">
        {{ $t('civic.consent.decline') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldCheck } from 'lucide-vue-next'

defineProps<{ loading?: boolean }>()
defineEmits<{ accept: []; decline: [] }>()

const { t: $t } = useI18n()
</script>
