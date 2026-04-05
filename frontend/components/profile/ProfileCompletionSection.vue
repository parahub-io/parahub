<template>
  <AccordionSection
    section-id="completion"
    :title="$t('profile.recommendations.title')"
    :icon="ListTodo"
    :open-sections="openSections"
    :animation-enabled="animationEnabled"
    @toggle="emit('toggle', $event)"
  >
    <div class="space-y-4">
      <!-- Achievement Graph (Pentagon) -->
      <div v-if="achievements && achievements.length > 0" class="w-full flex justify-center mb-4">
        <DashboardAchievementGraph
          :achievements="achievements"
          :size="graphSize"
        />
      </div>

      <!-- Profile Progress Bar -->
      <ProfileProgressBar
        v-if="profileProgress !== undefined"
        :progress="profileProgress"
        :completed-count="completedCount"
        :total-count="totalCount"
        class="mb-4"
      />

      <!-- Subtitle -->
      <p class="text-sm text-neutral-600 dark:text-neutral-400">
        {{ $t('profile.recommendations.subtitle') }}
      </p>

      <!-- Actions List -->
      <div v-if="incompleteActions.length > 0" class="space-y-3">
        <button
          v-for="action in incompleteActions"
          :key="action.id"
          @click="emit('action-click', action.id)"
          class="w-full flex items-center gap-3 p-3 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded-lg hover:border-primary dark:hover:border-primary transition-all group"
        >
          <div class="w-6 h-6 border-2 border-primary rounded flex items-center justify-center flex-shrink-0 group-hover:bg-primary/10 transition-colors">
            <Square class="w-4 h-4 text-primary" />
          </div>
          <div class="flex-1 text-left">
            <p class="font-medium text-neutral-900 dark:text-neutral-100 text-sm">
              {{ action.title }}
            </p>
            <p class="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">
              {{ action.description }}
            </p>
          </div>
          <ChevronRight class="w-5 h-5 text-primary opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      </div>

      <!-- Completion message -->
      <UiAlert v-else variant="success">{{ $t('profile.progress.complete') }}</UiAlert>

      <!-- Hint -->
      <div class="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-700/50 rounded px-3 py-2">
        <Lightbulb class="w-4 h-4" />
        {{ $t('profile.recommendations.hint') }}
      </div>
    </div>
  </AccordionSection>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ListTodo, Square, ChevronRight, Lightbulb, CheckCircle2 } from 'lucide-vue-next'
import AccordionSection from './AccordionSection.vue'
import ProfileProgressBar from './ProfileProgressBar.vue'
import DashboardAchievementGraph from '~/components/Dashboard/AchievementGraph.vue'

export interface ProfileAction {
  id: string
  title: string
  description: string
  completed: boolean
  priority: number
}

interface Achievement {
  category: string
  level: number
  progress: number
  next_threshold: number | null
}

const props = defineProps<{
  actions: ProfileAction[]
  openSections: string[]
  animationEnabled?: boolean
  profileProgress?: number
  completedCount?: number
  totalCount?: number
  achievements?: Achievement[]
  graphSize?: number
}>()

const emit = defineEmits<{
  'toggle': [sectionId: string]
  'action-click': [actionId: string]
}>()

const incompleteActions = computed(() => {
  return props.actions
    .filter(action => !action.completed)
    .sort((a, b) => b.priority - a.priority)
})
</script>
