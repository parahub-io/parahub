<template>
  <span
    v-if="shown.length"
    class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300 align-middle whitespace-nowrap"
    :title="titleText"
    :aria-label="titleText"
  >
    <ArrowLeftRight class="w-3 h-3 flex-shrink-0" aria-hidden="true" />
    <template v-for="m in shown" :key="m">
      <img :src="modeIcon(m)" :alt="modeLabel(m)" :class="iconClass" class="flex-shrink-0" />
      <span v-if="label" class="text-xs font-medium">{{ modeLabel(m) }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeftRight } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  /** Transport modes reachable at this location (backend interchange_modes). */
  modes: string[]
  /** Mode(s) to drop from the marker — pass the current route's route_type on a
   *  route page so it shows only what you can transfer TO. Omit on cards/headers
   *  to show every mode present. */
  exclude?: number | string | string[]
  /** Show localized mode names next to the icons (headers); icons-only otherwise. */
  label?: boolean
  iconClass?: string
}>(), {
  label: false,
  iconClass: 'w-4 h-4',
})

const { t } = useI18n()
const { modeOf, modeRouteType, modeIcon } = useTransitHelpers()

const excludeSet = computed(() => {
  const e = props.exclude
  if (e == null) return new Set<string>()
  if (Array.isArray(e)) return new Set(e)
  if (typeof e === 'number') return new Set([modeOf(e)])
  return new Set([e])
})

const shown = computed(() => (props.modes || []).filter(m => !excludeSet.value.has(m)))

function modeLabel(mode: string): string {
  return t(`transit.route_types.${modeRouteType(mode)}`, mode)
}

const titleText = computed(
  () => `${t('transit.interchange')}: ${shown.value.map(modeLabel).join(', ')}`,
)
</script>
