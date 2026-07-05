<template>
  <!-- Open-ballot list («кто как проголосовал») — audience-only, backend-gated -->
  <div v-if="visible" class="card p-4">
    <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4 flex items-center gap-2">
      <Eye class="w-5 h-5" aria-hidden="true" />
      {{ $t('civic.openBallots.title') }}
    </h2>

    <div v-if="ballots.length === 0" class="py-6 text-center text-sm text-neutral-500 dark:text-neutral-400">
      {{ $t('civic.openBallots.empty') }}
    </div>

    <div v-else class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700">
      <div v-for="b in ballots" :key="b.voter_id" class="px-4 py-2.5 flex items-center justify-between gap-3 text-sm">
        <div class="flex items-center gap-2 min-w-0">
          <User class="w-4 h-4 text-neutral-400 shrink-0" aria-hidden="true" />
          <span class="font-medium text-neutral-800 dark:text-neutral-200 truncate">
            {{ b.display_name || b.hna.split('@')[0] }}
          </span>
          <span v-if="b.on_behalf_count" class="text-xs text-neutral-500 dark:text-neutral-400 whitespace-nowrap">
            {{ $t('civic.openBallots.onBehalf', { n: b.on_behalf_count }) }}
          </span>
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <UiBadge variant="secondary" type="soft">{{ b.option_text }}</UiBadge>
          <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ formatTime(b.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Eye, User } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const props = defineProps<{ pollId: string }>()

const { t: $t, locale } = useI18n()
const authStore = useAuthStore()

const ballots = ref<any[]>([])
const visible = ref(false)

async function load() {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    ballots.value = await $fetch(`/api/v1/governance/civic/polls/${props.pollId}/open-ballots/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    visible.value = true
  } catch {
    visible.value = false // not audience — section stays hidden
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

defineExpose({ load })
onMounted(load)
</script>
