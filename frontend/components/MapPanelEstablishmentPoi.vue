<template>
  <div>
    <!-- POI icon blueprint -->
    <MapFeatureImage
      v-if="!hasImage"
      :poi-class="poiClass"
      class="flex-shrink-0"
    />

    <div class="px-4 pt-2 space-y-4">
      <template v-if="establishmentData">
        <!-- Municipality -->
        <div v-if="establishmentData.municipality" class="text-sm text-neutral-600 dark:text-neutral-400">
          {{ establishmentData.municipality }}
        </div>

        <!-- Coordinates -->
        <div v-if="establishmentData.lngLat" class="flex items-center justify-between py-1.5 text-sm">
          <span class="text-neutral-500 dark:text-neutral-400">{{ t('map.transit.coordinates') }}</span>
          <span class="font-mono text-xs text-neutral-900 dark:text-neutral-100">{{ establishmentData.lngLat.lat?.toFixed(5) }}, {{ establishmentData.lngLat.lng?.toFixed(5) }}</span>
        </div>

        <!-- View details button -->
        <button
          v-if="establishmentData.slug"
          @click="navigateToEstablishment(establishmentData.slug)"
          class="w-full px-4 py-2.5 bg-primary hover:bg-primary-400 text-neutral-900 font-medium rounded-lg transition text-sm"
        >
          {{ t('map.establishment.view_details', 'View details') }}
        </button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MapFeatureImage from '~/components/MapFeatureImage.vue'

const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

const props = defineProps<{
  establishmentData: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const hasImage = false // Internal POI markers never have uploaded photos

const poiClass = computed(() => {
  if (!props.establishmentData) return null
  const cat = (props.establishmentData.category_label || '').toLowerCase()
  if (cat.includes('church') || cat.includes('iglesia') || cat.includes('igreja') || cat.includes('храм') || cat.includes('kirche') || cat.includes('église')) return 'place_of_worship'
  return 'townhall'
})

function navigateToEstablishment(slug: string) {
  emit('close')
  router.push(localePath(`/org/${slug}`))
}
</script>
