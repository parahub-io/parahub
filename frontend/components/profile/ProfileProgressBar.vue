<template>
  <div class="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg border border-neutral-200 dark:border-neutral-700 p-3">
    <div class="flex items-center justify-between gap-3 mb-2">
      <div class="flex items-center gap-2 flex-1 min-w-0">
        <div class="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-primary">
          <CheckCircle2 v-if="progress === 100" class="w-4 h-4 text-black" />
          <Target v-else class="w-4 h-4 text-black" />
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
            {{ $t('profile.progress.title') }}
          </p>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
            {{ progress === 100
              ? $t('profile.progress.complete')
              : $t('profile.progress.incomplete')
            }}
          </p>
        </div>
      </div>
      <div class="text-right flex-shrink-0">
        <div class="text-xl font-bold text-secondary dark:text-secondary-400">
          {{ progress }}%
        </div>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
          {{ completedCount }}/{{ totalCount }} {{ $t('profile.progress.sections') }}
        </p>
      </div>
    </div>

    <!-- Progress Bar -->
    <div class="relative h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
      <div
        class="absolute inset-0 transition-all duration-700 ease-out bg-primary"
        :style="{ width: `${progress}%` }"
      >
        <!-- Animated shine effect -->
        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer"></div>
      </div>
    </div>

    <!-- Completion message -->
    <div v-if="progress === 100" class="mt-2 flex items-center gap-1.5 text-xs font-medium text-green-700 dark:text-green-400">
      <Sparkles class="w-3.5 h-3.5 flex-shrink-0" />
      <span class="truncate">{{ $t('profile.progress.congrats') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle2, Target, Sparkles } from 'lucide-vue-next'

const props = defineProps<{
  progress: number
  completedCount: number
  totalCount: number
}>()

const { t } = useI18n()
</script>

<style scoped>
@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.animate-shimmer {
  animation: shimmer 2s infinite;
}
</style>
