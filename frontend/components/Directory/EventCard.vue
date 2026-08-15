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
          <span class="truncate">{{ categoryLabel }}</span>
        </div>
        <div class="flex items-center gap-1 flex-shrink-0">
          <DemoBadge :is-demo="event.is_demo" />
          <UiBadge :variant="eventTypeBadgeVariant" type="soft" size="sm" class="gap-1">
            <component :is="eventTypeIcon" :size="12" aria-hidden="true" />
            {{ eventTypeLabel }}
          </UiBadge>
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
          <!-- Act-as: the establishment is credited, the organizer stays visible next to it -->
          <img
            v-if="event.establishment_logo_url || event.organizer_avatar_url"
            :src="event.establishment_logo_url || event.organizer_avatar_url"
            :alt="event.establishment_name || event.organizer_display_name || event.organizer_hna"
            class="w-5 h-5 rounded-full object-cover flex-shrink-0"
          />
          <component :is="event.establishment_name ? Building2 : User" v-else :size="14" class="text-neutral-400 flex-shrink-0" />
          <span v-if="event.establishment_name" class="text-xs text-neutral-700 dark:text-neutral-200 font-medium truncate">
            {{ event.establishment_name }}
          </span>
          <span v-if="event.establishment_name" class="text-xs text-neutral-400 flex-shrink-0">·</span>
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
import { Building2, Calendar, CalendarDays, MapPin, Users, Video, Layers, User } from 'lucide-vue-next'

const { t, locale } = useI18n()

const props = defineProps({
  event: {
    type: Object,
    required: true
  },
  // slug -> localized name, built once by the list page from the category tree
  categoryLabels: {
    type: Object,
    default: () => ({})
  }
})

defineEmits(['click'])

// Reference data arrives in English; the localized name comes from the tree.
const categoryLabel = computed(() =>
  props.categoryLabels[props.event.category_slug] || props.event.category_name || ''
)

const eventTypeLabel = computed(() => {
  const labels = {
    OFFLINE: t('events.types.offline'),
    ONLINE: t('events.types.online'),
    HYBRID: t('events.types.hybrid')
  }
  return labels[props.event.event_type] || props.event.event_type
})

// Same categorical tokens as the detail page (pages/events/[id].vue) — glyph
// carries the meaning, colour only groups.
const eventTypeBadgeVariant = computed(() => {
  const variants = { OFFLINE: 'success', ONLINE: 'info', HYBRID: 'neutral' }
  return variants[props.event.event_type] || 'neutral'
})

const eventTypeIcon = computed(() => {
  const icons = { OFFLINE: MapPin, ONLINE: Video, HYBRID: Layers }
  return icons[props.event.event_type] || Calendar
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
