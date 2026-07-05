<template>
  <UiBadge variant="neutral" type="soft" class="inline-flex items-center gap-1">
    <component :is="icon" class="w-3.5 h-3.5" aria-hidden="true" />
    {{ label }}
  </UiBadge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Home, Building2, Church, Landmark, Map as MapIcon, Flag, Users } from 'lucide-vue-next'

const props = defineProps<{
  level?: string | null
  name?: string
}>()

const { t: $t } = useI18n()

const icon = computed(() => {
  switch (props.level) {
    case 'household': return Home
    case 'condominium': return Building2
    case 'parish': return Church
    case 'municipality': return Landmark
    case 'region': return MapIcon
    case 'country': return Flag
    default: return Users
  }
})

const label = computed(() => {
  const levelLabel = props.level ? $t(`civic.level.${props.level}`, props.level) : $t('civic.level.groups')
  return props.name ? `${levelLabel} · ${props.name}` : levelLabel
})
</script>
