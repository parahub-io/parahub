<template>
  <NuxtLink
    :to="localePath(`/u/${partner.local_name}`)"
    class="relative group block"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- Card -->
    <div
      class="relative card rounded-lg overflow-hidden transition-all duration-300 cursor-pointer"
      :class="{
        'border-primary': isHovered,
      }"
    >
      <!-- Avatar/Portrait - compact on mobile -->
      <div class="relative aspect-[3/4] bg-neutral-100 dark:bg-neutral-800">
        <!-- Uploaded photo -->
        <img
          v-if="partner.avatar_url"
          :src="partner.avatar_url"
          :alt="partner.display_name"
          class="absolute inset-0 w-full h-full object-cover"
          loading="lazy"
        />
        <!-- Initials fallback (gradient, consistent with directory) -->
        <div
          v-else
          class="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-primary to-secondary"
        >
          <span class="text-2xl sm:text-3xl font-bold text-black">
            {{ getInitials(partner.display_name || partner.hna) }}
          </span>
        </div>

        <!-- Verified badge - icon only on mobile -->
        <div
          v-if="partner.is_verified_wot"
          class="absolute top-0.5 right-0.5 sm:top-2 sm:right-2 bg-green-700 text-white text-xs px-0.5 sm:px-2 py-0.5 sm:py-1 rounded-full font-medium flex items-center gap-0.5 sm:gap-1"
        >
          <CheckCircle2 class="w-2.5 h-2.5 sm:w-3 sm:h-3" />
          <span class="hidden sm:inline">{{ $t('directory.users.verified') }}</span>
        </div>

        <!-- Reputation score - compact on mobile -->
        <div class="absolute bottom-0.5 left-0.5 right-0.5 sm:bottom-2 sm:left-2 sm:right-2 bg-black/60 dark:bg-black/60 backdrop-blur-sm rounded px-0.5 sm:px-2 py-0.5 sm:py-1 text-xs text-white text-center">
          <span class="font-medium">{{ formatReputation(partner.reputation_score) }}</span>
          <span class="ml-0.5 sm:ml-1 hidden sm:inline">{{ $t('directory.users.reputation_short', 'rep') }}</span>
        </div>
      </div>

      <!-- Info section - minimal on mobile -->
      <div class="p-1 sm:p-3 space-y-0.5 sm:space-y-1">
        <!-- Name -->
        <div class="font-semibold text-neutral-900 dark:text-neutral-100 text-sm truncate">
          {{ partner.display_name }}
        </div>

        <!-- HNA - hidden on mobile -->
        <div class="hidden sm:block text-xs text-neutral-600 dark:text-neutral-400 truncate">
          {{ partner.hna }}
        </div>

        <!-- Stats -->
        <div class="flex justify-between items-center text-xs text-neutral-600 dark:text-neutral-400 pt-0.5 sm:pt-2 border-t border-neutral-200 dark:border-neutral-700">
          <div class="flex items-center gap-0.5 sm:gap-1">
            <ShieldCheck class="w-2.5 h-2.5 sm:w-3 sm:h-3" />
            <span>{{ partner.verifications_count }}</span>
          </div>
          <div class="flex items-center gap-0.5 sm:gap-1">
            <Package class="w-2.5 h-2.5 sm:w-3 sm:h-3" />
            <span>{{ partner.items_count }}</span>
          </div>
        </div>
      </div>

      <!-- Delete button (shown on hover or when pending confirmation) -->
      <Transition
        enter-active-class="transition-opacity duration-200"
        leave-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <button
          v-if="isHovered || pending"
          @click.stop.prevent="$emit('remove', partner.id)"
          class="absolute top-2 left-2 text-white p-1.5 rounded-full transition-colors"
          :class="pending ? 'bg-error animate-pulse' : 'bg-error/90 hover:bg-error'"
          :title="pending ? $t('common.confirm') : $t('common.remove')"
        >
          <component :is="pending ? Check : X" class="w-4 h-4" />
        </button>
      </Transition>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, ShieldCheck, Package, X, Check } from 'lucide-vue-next'

interface Partner {
  id: string
  local_name: string
  hna: string
  display_name: string
  reputation_score: number
  is_verified_wot: boolean
  verifications_count: number
  items_count: number
  avatar_url?: string | null
}

const props = defineProps<{
  partner: Partner
  pending?: boolean
}>()

defineEmits<{
  remove: [id: string]
}>()

const localePath = useLocalePath()
const isHovered = ref(false)

function formatReputation(score: number): string {
  if (score >= 1000) return `${(score / 1000).toFixed(1)}k`
  return Number.isInteger(score) ? score.toString() : Math.round(score).toString()
}

function getInitials(name: string): string {
  if (!name) return 'U'
  const parts = name.trim().split(/\s+/)
  return parts.length >= 2
    ? (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
    : name.substring(0, 2).toUpperCase()
}
</script>
