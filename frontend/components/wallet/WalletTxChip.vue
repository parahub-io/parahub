<template>
  <div
    class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
    :class="style.chip"
  >
    <component :is="style.icon" class="w-5 h-5" :class="style.glyph" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import {
  ArrowDownLeft, ArrowUpRight, Bitcoin, Gift, Megaphone,
  Ticket, User, Repeat, Heart, Zap,
} from 'lucide-vue-next'

// List-scale operation marker for wallet history rows: the tint groups the
// operation family at a glance (green in, red out, amber on-chain/ticket,
// indigo platform, yellow tip), the glyph names the exact kind up close.
// The illustrated emblem set (/design § Wallet Transaction Emblems) is for
// surfaces that render it at 48px and larger — it does not read at chip size.
const props = defineProps<{ kind?: string | null }>()

interface ChipStyle { icon: Component; chip: string; glyph: string }

const STYLES: Record<string, ChipStyle> = {
  receive:      { icon: ArrowDownLeft, chip: 'bg-success-100 dark:bg-success-900/30', glyph: 'text-success-700 dark:text-success-400' },
  send:         { icon: ArrowUpRight,  chip: 'bg-error-100 dark:bg-error-900/30', glyph: 'text-error-700 dark:text-error-400' },
  onchain:      { icon: Bitcoin,       chip: 'bg-warning-100 dark:bg-warning-900/30', glyph: 'text-warning-700 dark:text-warning-400' },
  tip:          { icon: Gift,          chip: 'bg-primary-100 dark:bg-primary-900/30', glyph: 'text-primary-800 dark:text-primary-400' },
  ad:           { icon: Megaphone,     chip: 'bg-secondary-100 dark:bg-secondary-900/30', glyph: 'text-secondary-700 dark:text-secondary-400' },
  ticket:       { icon: Ticket,        chip: 'bg-warning-100 dark:bg-warning-900/30', glyph: 'text-warning-700 dark:text-warning-400' },
  profile:      { icon: User,          chip: 'bg-secondary-100 dark:bg-secondary-900/30', glyph: 'text-secondary-700 dark:text-secondary-400' },
  subscription: { icon: Repeat,        chip: 'bg-secondary-100 dark:bg-secondary-900/30', glyph: 'text-secondary-700 dark:text-secondary-400' },
  donation:     { icon: Heart,         chip: 'bg-error-100 dark:bg-error-900/30', glyph: 'text-error-700 dark:text-error-400' },
}

const FALLBACK: ChipStyle = {
  icon: Zap,
  chip: 'bg-neutral-100 dark:bg-neutral-700/60',
  glyph: 'text-neutral-500 dark:text-neutral-400',
}

const style = computed(() => (props.kind && STYLES[props.kind]) || FALLBACK)
</script>
