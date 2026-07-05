<template>
  <div class="w-full max-w-4xl mt-2 sm:mt-4">
    <div class="card p-3 sm:p-4 flex items-center gap-3 sm:gap-4">
      <!-- Avatar stack (most-recently-active, up to 5) -->
      <div v-if="users.length" class="flex items-center">
        <NuxtLink
          v-for="u in users"
          :key="u.id"
          :to="localePath(`/u/${u.local_name}`)"
          :title="u.name"
          class="-ml-2 first:ml-0 block hover:z-10 transition-transform hover:scale-110"
        >
          <img
            v-if="u.avatar"
            :src="u.avatar"
            :alt="u.name"
            class="w-8 h-8 sm:w-9 sm:h-9 rounded-full object-cover ring-2 ring-white dark:ring-neutral-900"
            loading="lazy"
          />
          <div
            v-else
            class="w-8 h-8 sm:w-9 sm:h-9 rounded-full ring-2 ring-white dark:ring-neutral-900 bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-[10px] sm:text-xs font-bold text-black"
          >
            {{ getInitials(u.name || u.hna) }}
          </div>
        </NuxtLink>

        <!-- Overflow count -->
        <div
          v-if="extra > 0"
          class="-ml-2 w-8 h-8 sm:w-9 sm:h-9 rounded-full ring-2 ring-white dark:ring-neutral-900 bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-[10px] sm:text-xs font-semibold text-neutral-600 dark:text-neutral-300"
        >
          +{{ extra }}
        </div>
      </div>

      <!-- Counts -->
      <div class="text-sm leading-tight">
        <span class="font-semibold text-neutral-900 dark:text-neutral-100">
          {{ $t('dashboard.online_people', { count: total }) }}
        </span>
        <span v-if="anon > 0" class="text-neutral-400 dark:text-neutral-500">
          · {{ $t('dashboard.online_guests', { count: anon }) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useOnlinePresence } from '~/composables/useOnlinePresence'

const localePath = useLocalePath()
const { total, anon, users } = useOnlinePresence()

// People online beyond the ones shown as avatars
const extra = computed(() => Math.max(0, total.value - users.value.length))

function getInitials(name: string): string {
  if (!name) return 'U'
  const parts = name.trim().split(/\s+/)
  return parts.length >= 2
    ? (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
    : name.substring(0, 2).toUpperCase()
}
</script>
