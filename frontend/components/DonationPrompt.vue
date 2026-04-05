<template>
  <div class="rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-950/20 p-3">
    <!-- First-time onboarding blurb -->
    <p v-if="!donation.isOnboarded.value" class="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
      {{ $t('income.onboarding_blurb') }}
      <button class="underline text-primary" @click="donation.markOnboarded()">{{ $t('common.ok') }}</button>
    </p>

    <div class="flex items-center justify-between gap-2">
      <span class="text-xs text-neutral-600 dark:text-neutral-400 whitespace-nowrap">
        <Heart class="w-3 h-3 inline -mt-0.5 text-amber-500" />
        {{ $t('income.support_parahub') }}
      </span>

      <div class="flex items-center gap-1">
        <button
          v-for="level in levels"
          :key="level"
          class="px-2 py-0.5 text-xs rounded-full transition-colors"
          :class="donation.supportLevel.value === level
            ? 'bg-amber-500 text-white'
            : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600'"
          @click="selectLevel(level)"
        >
          {{ level }}%
        </button>
      </div>
    </div>

    <!-- Donation amount display -->
    <div v-if="donationSats > 0" class="mt-1 text-right text-xs text-neutral-500 dark:text-neutral-400 font-mono">
      +{{ donationSats }} sats
      <span v-if="donationFiat">≈ {{ donationFiat }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Heart } from 'lucide-vue-next'

const props = defineProps<{
  sourceAmountSats: number
}>()

const levels = [0, 0.1, 1]
const donation = useDonation()

// Init sticky level on mount
onMounted(() => {
  donation.initSupportLevel()
  donation.loadConfig()
})

const donationSats = computed(() => donation.calcDonationSats(props.sourceAmountSats))
const donationFiat = computed(() => donation.formatDonationFiat(donationSats.value))

const selectLevel = (level: number) => {
  donation.setSupportLevel(level)
}
</script>
