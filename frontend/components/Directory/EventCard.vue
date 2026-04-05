<template>
  <div
    class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden cursor-pointer hover:border-primary transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
    role="button"
    tabindex="0"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
    @keydown.space.prevent="$emit('click')"
  >
    <!-- Cover image -->
    <div
      v-if="event.cover_image_url"
      class="h-36 bg-cover bg-center"
      :style="{ backgroundImage: `url(${event.cover_image_url})` }"
    />
    <div
      v-else
      class="h-36 bg-gradient-to-br from-neutral-100 to-neutral-200 dark:from-neutral-700 dark:to-neutral-800 flex items-center justify-center"
    >
      <Calendar class="w-10 h-10 text-neutral-300 dark:text-neutral-600" />
    </div>

    <!-- Content -->
    <div class="p-4 space-y-2.5">
      <!-- Category + Type badge -->
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 min-w-0">
          <span v-if="event.category_icon" class="text-sm flex-shrink-0">{{ event.category_icon }}</span>
          <span class="truncate">{{ event.category_name }}</span>
        </div>
        <div class="flex items-center gap-1 flex-shrink-0">
          <DemoBadge :is-demo="event.is_demo" />
          <span
            :class="eventTypeBadgeClass"
            class="px-2 py-0.5 rounded-full text-xs font-medium"
          >
            {{ eventTypeLabel }}
          </span>
        </div>
      </div>

      <!-- Title -->
      <h3 class="font-semibold text-neutral-900 dark:text-neutral-100 line-clamp-2 leading-snug">
        {{ event.title }}
      </h3>

      <!-- Date -->
      <div class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
        <CalendarDays :size="15" class="flex-shrink-0" />
        <span>{{ formattedDate }}</span>
      </div>

      <!-- Location -->
      <div v-if="event.location_display" class="flex items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
        <MapPin :size="15" class="flex-shrink-0" />
        <span class="truncate">{{ event.location_display }}</span>
      </div>

      <!-- Online badge -->
      <div v-if="event.event_type !== 'OFFLINE'" class="flex items-center gap-2 text-sm text-secondary dark:text-secondary-400">
        <Video :size="15" class="flex-shrink-0" />
        <span>{{ $t('events.online_available') }}</span>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between pt-2.5 border-t border-neutral-100 dark:border-neutral-700">
        <div v-if="event.organizer_hna" class="flex items-center gap-1.5 min-w-0">
          <img
            v-if="event.organizer_avatar_url"
            :src="event.organizer_avatar_url"
            :alt="event.organizer_display_name || event.organizer_hna"
            class="w-5 h-5 rounded-full flex-shrink-0"
          />
          <User v-else :size="14" class="text-neutral-400 flex-shrink-0" />
          <span class="text-xs text-neutral-500 truncate">{{ event.organizer_display_name || event.organizer_hna?.split('@')[0] }}</span>
        </div>

        <div class="flex items-center gap-1.5 flex-shrink-0">
          <Users :size="14" class="text-neutral-400" />
          <span class="text-xs text-neutral-500">
            <template v-if="event.max_participants">
              {{ event.participants_count }}/{{ event.max_participants }}
            </template>
            <template v-else>
              {{ event.participants_count }}
            </template>
          </span>
          <span
            v-if="event.is_full"
            class="ml-1 px-1.5 py-0.5 bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400 rounded text-xs font-medium"
          >
            {{ $t('events.full') }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Calendar, CalendarDays, MapPin, Users, Video, User } from 'lucide-vue-next'

const { t, locale } = useI18n()

const props = defineProps({
  event: {
    type: Object,
    required: true
  }
})

defineEmits(['click'])

const eventTypeLabel = computed(() => {
  const labels = {
    OFFLINE: t('events.types.offline'),
    ONLINE: t('events.types.online'),
    HYBRID: t('events.types.hybrid')
  }
  return labels[props.event.event_type] || props.event.event_type
})

const eventTypeBadgeClass = computed(() => {
  const classes = {
    OFFLINE: 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400',
    ONLINE: 'bg-secondary-100 dark:bg-secondary-900/50 text-secondary-700 dark:text-secondary-400',
    HYBRID: 'bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-400'
  }
  return classes[props.event.event_type] || 'bg-neutral-100 text-neutral-700'
})

const formattedDate = computed(() => {
  if (!props.event.starts_at) return ''
  const date = new Date(props.event.starts_at)
  return date.toLocaleDateString(locale.value, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  })
})
</script>
