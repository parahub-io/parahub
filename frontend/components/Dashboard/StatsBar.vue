<template>
  <div class="stats-bar-wrapper">
    <div class="stats-bar">
      <div class="max-w-7xl mx-auto flex items-center justify-between gap-2 sm:gap-8 text-sm">
        <!-- Verifications with Progress Bar -->
        <div class="stat-item group flex-col items-center sm:items-start gap-0.5 sm:gap-1">
          <template v-if="stats.verifications_count < 3">
            <div class="flex items-center gap-1.5 sm:gap-2">
              <ShieldCheck class="w-4 h-4 group-hover:text-success dark:group-hover:text-success-300 transition-colors" />
              <span class="font-medium">{{ stats.verifications_count }}/3</span>
            </div>
            <div class="w-full h-1 sm:h-1.5 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
              <div
                class="h-full bg-success transition-all duration-300"
                :style="{ width: `${(stats.verifications_count / 3) * 100}%` }"
              ></div>
            </div>
            <span class="stat-label">{{ $t('dashboard.stats_verifications') }}</span>
          </template>
          <template v-else>
            <div class="flex items-center gap-1.5 sm:gap-2">
              <ShieldCheck class="w-4 h-4 text-success dark:text-success-300" />
              <span class="font-medium text-success dark:text-success-300">{{ $t('dashboard.stats_verified') }}</span>
            </div>
            <span class="stat-label">{{ stats.verifications_count }} {{ $t('dashboard.stats_confirmations') }}</span>
          </template>
        </div>

        <!-- Reputation -->
        <div class="stat-item group flex-col items-center gap-0.5 sm:flex-row sm:gap-2">
          <div class="flex items-center gap-1.5 sm:gap-2">
            <Award class="w-4 h-4 group-hover:text-secondary dark:group-hover:text-secondary-400 transition-colors" />
            <span class="font-medium">{{ formatReputation(stats.reputation_score) }}</span>
          </div>
          <span class="stat-label">{{ $t('dashboard.stats_reputation') }}</span>
        </div>

        <!-- Active Deals -->
        <div class="stat-item group flex-col items-center gap-0.5 sm:flex-row sm:gap-2">
          <div class="flex items-center gap-1.5 sm:gap-2">
            <Handshake class="w-4 h-4 group-hover:text-secondary dark:group-hover:text-secondary-400 transition-colors" />
            <span class="font-medium">{{ stats.active_deals_count }}</span>
          </div>
          <span class="stat-label">{{ $t('dashboard.stats_deals') }}</span>
        </div>

        <!-- Partners (you added) -->
        <div class="stat-item group flex-col items-center gap-0.5 sm:flex-row sm:gap-2">
          <div class="flex items-center gap-1.5 sm:gap-2">
            <Users class="w-4 h-4 group-hover:text-purple-500 dark:group-hover:text-purple-400 transition-colors" />
            <span class="font-medium">{{ stats.partners_count }}</span>
          </div>
          <span class="stat-label">{{ $t('dashboard.stats_partners') }}</span>
        </div>

        <!-- Partnered By (who added you) -->
        <div class="stat-item group flex-col items-center gap-0.5 sm:flex-row sm:gap-2">
          <div class="flex items-center gap-1.5 sm:gap-2">
            <UserPlus class="w-4 h-4 group-hover:text-secondary dark:group-hover:text-secondary-400 transition-colors" />
            <span class="font-medium">{{ stats.partnered_by_count }}</span>
          </div>
          <span class="stat-label">{{ $t('dashboard.stats_following') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldCheck, Award, Handshake, Users, UserPlus } from 'lucide-vue-next'

interface DashboardStats {
  verifications_count: number
  reputation_score: number
  active_deals_count: number
  partners_count: number
  partnered_by_count: number
}

defineProps<{
  stats: DashboardStats
}>()

function formatReputation(score: number): string {
  if (score >= 1000000) return `${(score / 1000000).toFixed(1)}M`
  if (score >= 1000) return `${(score / 1000).toFixed(1)}k`
  return score.toFixed(0)
}
</script>

<style scoped>
.stats-bar-wrapper {
  width: 100%;
  position: relative;
  perspective: 1000px;
  padding: 0 1rem;
}

.stats-bar {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border-top: 1px solid rgb(229 229 229); /* neutral-200 */
  padding: 0.75rem 1.5rem;
  border-radius: 50% 50% 0 0 / 20px 20px 0 0;
  transform: rotateX(-2deg);
  transform-style: preserve-3d;
  box-shadow: 0 -2px 15px rgba(0, 0, 0, 0.05);
}

:root.dark .stats-bar {
  background: rgba(20, 10, 5, 0.7);
  border-top-color: rgba(180, 140, 100, 0.2);
  box-shadow:
    0 -2px 15px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(180, 140, 100, 0.1);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: rgb(64 64 64); /* neutral-700 */
  transition: color 0.2s ease;
}

.stat-item:hover {
  color: rgb(23 23 23); /* neutral-900 */
}

:root.dark .stat-item {
  color: rgba(220, 190, 160, 0.85);
}

:root.dark .stat-item:hover {
  color: rgba(255, 220, 180, 1);
}

.stat-label {
  color: rgb(115 115 115); /* neutral-500 */
  font-size: 0.625rem; /* 10px on mobile */
  line-height: 1;
}

@media (min-width: 640px) {
  .stat-label {
    font-size: 0.875rem;
  }
}

:root.dark .stat-label {
  color: rgba(180, 140, 100, 0.7);
}

@media (max-width: 640px) {
  .stats-bar {
    transform: none;
    border-radius: 0;
    padding: 0.75rem 0.5rem;
    background: rgba(255, 255, 255, 0.9);
  }

  :root.dark .stats-bar {
    background: rgba(20, 10, 5, 0.8);
  }

  .stats-bar-wrapper {
    perspective: none;
    padding: 0;
  }

  .stat-item {
    gap: 0.375rem;
    font-weight: 500;
  }
}
</style>
