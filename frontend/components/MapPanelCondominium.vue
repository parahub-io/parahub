<template>
  <div class="px-4 pt-2 space-y-4">
    <template v-if="condominiumData">
      <!-- Address -->
      <div v-if="condominiumData.full_address" class="text-sm text-neutral-600 dark:text-neutral-400">
        {{ condominiumData.full_address }}
      </div>

      <!-- Stats -->
      <div class="grid grid-cols-2 gap-3">
        <div class="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-3 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ condominiumData.fraction_count }}</div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ t('map.condo.fractions') }}</div>
        </div>
        <div class="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-3 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ condominiumData.member_count }}</div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ t('map.condo.members') }}</div>
        </div>
      </div>

      <!-- Coordinates -->
      <div v-if="condominiumData.lngLat" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.coordinates') }}</span>
        <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100">{{ condominiumData.lngLat.lat?.toFixed(5) }}, {{ condominiumData.lngLat.lng?.toFixed(5) }}</span>
      </div>

      <!-- View details button -->
      <button
        v-if="condominiumData.slug"
        @click="navigateToCondominium(condominiumData.slug)"
        class="w-full px-4 py-2.5 bg-primary hover:bg-primary-400 text-neutral-900 font-medium rounded-lg transition text-sm"
      >
        {{ t('map.condo.view_details') }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

defineProps<{
  condominiumData: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

function navigateToCondominium(slug: string) {
  emit('close')
  router.push(localePath(`/condo/${slug}/fractions`))
}
</script>
