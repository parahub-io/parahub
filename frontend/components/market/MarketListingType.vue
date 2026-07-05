<script setup lang="ts">
import { computed } from 'vue'
import { PackageCheck, PackageSearch } from 'lucide-vue-next'

// Single source of truth for the market listing-direction identity (offer ↔ want).
//   CREDIT = offer ("I have it", supply)     → teal   + PackageCheck
//   DEBIT  = want  ("I'm seeking it", demand) → violet + PackageSearch
// Render this everywhere instead of hand-rolling the badge, so colour + icon + label
// stay consistent across the whole site (cards, detail, my-items, barter…). The hues
// are dedicated `offer`/`want` tokens (tailwind.config.js) owned only by this axis, so
// they never collide with success/links/active. See PK/design-system.md.
interface Props {
  itemType: string                  // 'CREDIT' | 'DEBIT'
  display?: 'badge' | 'eyebrow'     // soft pill (default) | compact coloured eyebrow (no fill)
  size?: 'sm' | 'md' | 'lg'
  iconOnly?: boolean                // drop the word on dense surfaces; label kept as aria-label
}

const props = withDefaults(defineProps<Props>(), {
  display: 'badge',
  size: 'md',
  iconOnly: false,
})

const isOffer = computed(() => props.itemType === 'CREDIT')
const icon = computed(() => (isOffer.value ? PackageCheck : PackageSearch))
const variant = computed<'offer' | 'want'>(() => (isOffer.value ? 'offer' : 'want'))
const labelKey = computed(() => (isOffer.value ? 'market.item.offer' : 'market.item.request'))

const iconSize = computed(() =>
  props.size === 'lg' ? 'w-4 h-4' : props.size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'
)

// Eyebrow: coloured text + icon, no fill — the quiet, low-footprint form for the detail
// page (sits inline with the breadcrumb instead of a stand-alone pill on its own row).
const eyebrowText = computed(() =>
  isOffer.value ? 'text-offer-700 dark:text-offer-300' : 'text-want-700 dark:text-want-300'
)
const eyebrowSize = computed(() => (props.size === 'sm' ? 'text-[11px]' : 'text-xs'))
</script>

<template>
  <span
    v-if="display === 'eyebrow'"
    :class="['inline-flex items-center gap-1 font-semibold uppercase tracking-wide', eyebrowText, eyebrowSize]"
    :aria-label="iconOnly ? $t(labelKey) : undefined"
  >
    <component :is="icon" :class="iconSize" />
    <span v-if="!iconOnly">{{ $t(labelKey) }}</span>
  </span>

  <UiBadge
    v-else
    :variant="variant"
    type="soft"
    :size="size"
    :aria-label="iconOnly ? $t(labelKey) : undefined"
  >
    <component :is="icon" :class="[iconSize, iconOnly ? '' : 'mr-1']" />
    <span v-if="!iconOnly">{{ $t(labelKey) }}</span>
  </UiBadge>
</template>
