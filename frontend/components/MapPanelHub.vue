<template>
  <div class="px-4 pt-2 space-y-4">
    <template v-if="hubData">
      <!-- Stats -->
      <div class="grid grid-cols-2 gap-3">
        <div class="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-3 text-center">
          <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">{{ hubData.hub_capacity || '—' }}</div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ t('map.hub.capacity') }}</div>
        </div>
        <div class="bg-neutral-50 dark:bg-neutral-800 rounded-lg p-3 text-center">
          <div class="text-sm font-bold text-neutral-900 dark:text-neutral-100">{{ hubData.hub_storage_fee_daily !== '0' ? `${hubData.hub_storage_fee_daily}€` : t('map.hub.free') }}</div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{{ t('map.hub.fee_daily') }}</div>
        </div>
      </div>

      <!-- Accepted sizes -->
      <div v-if="hubData.hub_accepted_sizes" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.hub.accepted_sizes') }}</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ hubData.hub_accepted_sizes }}</span>
      </div>

      <!-- Opening hours -->
      <div v-if="hubData.opening_hours && hubData.opening_hours !== '{}'" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.hub.hours') }}</span>
        <span class="text-neutral-900 dark:text-neutral-100">{{ hubData.opening_hours }}</span>
      </div>

      <!-- Phone -->
      <div v-if="hubData.phone" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.hub.phone') }}</span>
        <a :href="`tel:${hubData.phone}`" class="text-neutral-900 dark:text-neutral-100 hover:text-secondary">{{ hubData.phone }}</a>
      </div>

      <!-- Coordinates -->
      <div v-if="hubData.lngLat" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.coordinates') }}</span>
        <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100">{{ hubData.lngLat.lat?.toFixed(5) }}, {{ hubData.lngLat.lng?.toFixed(5) }}</span>
      </div>

      <!-- View details button -->
      <button
        v-if="hubData.slug"
        @click="navigateToHub(hubData.slug)"
        class="w-full px-4 py-2.5 bg-primary hover:bg-primary-400 text-neutral-900 font-medium rounded-lg transition text-sm"
      >
        {{ t('map.hub.view_details') }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

defineProps<{
  hubData: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

function navigateToHub(slug: string) {
  emit('close')
  router.push(localePath(`/org/${slug}`))
}
</script>
