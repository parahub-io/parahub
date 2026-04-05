<template>
  <div>
    <div v-if="sessions.length === 0" class="text-neutral-500 text-sm italic py-8 text-center">
      {{ $t('yellow_hive.no_sessions_yet') }}
    </div>
    <div v-else class="space-y-0">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-neutral-200 dark:border-neutral-700 text-left text-neutral-500">
            <th class="py-2 pr-4 font-medium">Mode</th>
            <th class="py-2 pr-4 font-medium">Task</th>
            <th class="py-2 pr-4 font-medium">Started</th>
            <th class="py-2 pr-4 font-medium">Duration</th>
            <th class="py-2 pr-4 font-medium">Exit</th>
            <th class="py-2 pr-4 font-medium">Files</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id" class="border-b border-neutral-100 dark:border-neutral-800">
            <td class="py-2.5 pr-4">
              <UiBadge :variant="s.mode === 'task' ? 'secondary' : 'neutral'" type="soft">{{ s.mode }}</UiBadge>
            </td>
            <td class="py-2.5 pr-4 text-neutral-700 dark:text-neutral-300 max-w-xs truncate">
              {{ s.task_description || '—' }}
              <a
                v-if="s.gitea_issue_number"
                :href="`https://git.parahub.io/norn/parahub-yellow-gate/issues/${s.gitea_issue_number}`"
                target="_blank"
                class="text-secondary hover:underline ml-1"
                @click.stop
              >#{{ s.gitea_issue_number }}</a>
            </td>
            <td class="py-2.5 pr-4 text-neutral-500 whitespace-nowrap">
              {{ formatDate(s.started_at) }}
            </td>
            <td class="py-2.5 pr-4 text-neutral-500 whitespace-nowrap">
              {{ s.duration_seconds != null ? formatDuration(s.duration_seconds) : '...' }}
            </td>
            <td class="py-2.5 pr-4">
              <span v-if="s.exit_code === 0" class="text-green-600 dark:text-green-400 font-mono">0</span>
              <span v-else-if="s.exit_code != null" class="text-red-600 dark:text-red-400 font-mono">{{ s.exit_code }}</span>
              <span v-else class="text-neutral-400">—</span>
            </td>
            <td class="py-2.5 pr-4 flex items-center gap-2">
              <button
                v-if="s.report_path"
                class="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                :title="s.report_path"
                @click="toggleReport(s)"
              >
                <FileText :size="16" />
              </button>
              <button
                v-if="s.screenshots?.length"
                class="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
                :title="`${s.screenshots.length} screenshot(s)`"
                @click="toggleScreenshots(s)"
              >
                <Camera :size="16" />
                <span class="text-xs ml-0.5">{{ s.screenshots.length }}</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Expanded report panel -->
      <div v-if="expandedReport" class="mt-4 p-4 rounded-lg bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700">
        <div class="flex items-center justify-between mb-3">
          <span class="text-sm font-medium text-neutral-600 dark:text-neutral-400">
            {{ expandedReport.report_path }}
          </span>
          <button class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200" @click="expandedReport = null">
            <X :size="16" />
          </button>
        </div>
        <div v-if="reportLoading" class="text-sm text-neutral-500 italic">Loading...</div>
        <div v-else-if="reportContent" class="prose prose-sm dark:prose-invert max-w-none text-sm whitespace-pre-wrap font-mono leading-relaxed">{{ reportContent }}</div>
        <div v-else class="text-sm text-neutral-500 italic">Report not found</div>
      </div>

      <!-- Expanded screenshots panel -->
      <div v-if="expandedScreenshots" class="mt-4 p-4 rounded-lg bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700">
        <div class="flex items-center justify-between mb-3">
          <span class="text-sm font-medium text-neutral-600 dark:text-neutral-400">
            Screenshots ({{ expandedScreenshots.screenshots.length }})
          </span>
          <button class="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200" @click="expandedScreenshots = null">
            <X :size="16" />
          </button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <a
            v-for="url in expandedScreenshots.screenshots"
            :key="url"
            :href="url"
            target="_blank"
            class="block group"
          >
            <img
              :src="url"
              :alt="url.split('/').pop()"
              class="rounded border border-neutral-200 dark:border-neutral-700 w-full object-contain max-h-64 group-hover:border-primary transition-colors"
              loading="lazy"
            >
            <span class="text-xs text-neutral-500 mt-1 block truncate">{{ url.split('/').pop() }}</span>
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FileText, Camera, X } from 'lucide-vue-next'
import type { AgentSession } from '~/stores/agents'

const props = defineProps<{ agentName: string }>()

const { t: $t } = useI18n()
const agentsStore = useAgentsStore()
const authStore = useAuthStore()
const sessions = computed(() => agentsStore.sessions[props.agentName] || [])
const expandedReport = ref<AgentSession | null>(null)
const expandedScreenshots = ref<AgentSession | null>(null)
const reportContent = ref<string | null>(null)
const reportLoading = ref(false)

async function load() {
  await agentsStore.fetchSessions(props.agentName)
}

async function toggleReport(session: AgentSession) {
  if (expandedReport.value?.id === session.id) {
    expandedReport.value = null
    return
  }
  expandedReport.value = session
  expandedScreenshots.value = null
  reportContent.value = null
  reportLoading.value = true

  try {
    const filename = session.report_path.replace(/^reports\//, '')
    await authStore.ensureToken()
    const text = await $fetch<string>(`/api/v1/agents/reports/${filename}`, {
      credentials: 'include',
      headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {},
      responseType: 'text',
    })
    reportContent.value = text
  } catch {
    reportContent.value = null
  } finally {
    reportLoading.value = false
  }
}

function toggleScreenshots(session: AgentSession) {
  if (expandedScreenshots.value?.id === session.id) {
    expandedScreenshots.value = null
    return
  }
  expandedScreenshots.value = session
  expandedReport.value = null
}

watch(() => props.agentName, () => {
  load()
  expandedReport.value = null
  expandedScreenshots.value = null
})
onMounted(() => {
  load()
})

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}
</script>
