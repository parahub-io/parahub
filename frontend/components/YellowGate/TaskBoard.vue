<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <UiTabs v-model="state" :tabs="stateTabs" variant="pills" @update:modelValue="loadIssues" />
      <a
        href="https://git.parahub.io/norn/parahub-yellow-gate/issues"
        target="_blank"
        class="text-sm text-secondary hover:underline flex items-center gap-1"
      >
        {{ $t('yellow_hive.open_in_gitea') }}
        <ExternalLink class="w-3.5 h-3.5" />
      </a>
    </div>

    <div v-if="issues.length === 0 && unassignedIssues.length === 0" class="text-neutral-500 text-sm italic py-8 text-center">
      {{ $t('yellow_hive.no_issues') }}
    </div>
    <template v-else>
      <!-- Assigned to this agent -->
      <div class="space-y-2">
        <div
          v-for="issue in issues"
          :key="issue.number"
          class="flex items-start gap-3 p-3 rounded-lg bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700"
        >
          <a
            :href="`https://git.parahub.io/norn/parahub-yellow-gate/issues/${issue.number}`"
            target="_blank"
            class="text-neutral-400 hover:text-secondary font-mono text-sm shrink-0"
            @click.stop
          >#{{ issue.number }}</a>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ issue.title }}</div>
            <div class="flex items-center gap-2 mt-1">
              <span v-if="issue.created_at" class="text-[11px] text-neutral-400 whitespace-nowrap">{{ formatTime(issue.created_at) }}</span>
            </div>
            <div class="flex flex-wrap gap-1.5 mt-1">
              <span
                v-for="label in issue.labels"
                :key="label.id"
                class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                :style="{ backgroundColor: label.color + '22', color: label.color }"
              >
                {{ label.name }}
              </span>
            </div>
          </div>
          <UiButton
            v-if="state === 'open'"
            size="sm"
            variant="outline"
            :icon="Play"
            :loading="launchingIssue === issue.number"
            :disabled="launchingIssue === issue.number || anyAgentRunning"
            :title="anyAgentRunning ? $t('yellow_hive.agent_busy') : `Run ${props.agentName}`"
            class="shrink-0"
            @click="runIssue(issue)"
          >Run</UiButton>
        </div>
      </div>

      <!-- Unassigned issues -->
      <div v-if="unassignedIssues.length > 0 && state === 'open'" class="mt-6">
        <div class="text-xs font-semibold uppercase tracking-wider text-neutral-400 mb-2">{{ $t('yellow_hive.unassigned') }}</div>
        <div class="space-y-2">
          <div
            v-for="issue in unassignedIssues"
            :key="issue.number"
            class="flex items-start gap-3 p-3 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-600"
          >
            <a
              :href="`https://git.parahub.io/norn/parahub-yellow-gate/issues/${issue.number}`"
              target="_blank"
              class="text-neutral-400 hover:text-secondary font-mono text-sm shrink-0"
              @click.stop
            >#{{ issue.number }}</a>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ issue.title }}</div>
              <div class="flex items-center gap-2 mt-1">
                <span v-if="issue.created_at" class="text-[11px] text-neutral-400 whitespace-nowrap">{{ formatTime(issue.created_at) }}</span>
              </div>
              <div class="flex flex-wrap gap-1.5 mt-1">
                <span
                  v-for="label in issue.labels"
                  :key="label.id"
                  class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :style="{ backgroundColor: label.color + '22', color: label.color }"
                >
                  {{ label.name }}
                </span>
              </div>
            </div>
            <UiButton
              size="sm"
              variant="outline"
              :icon="Play"
              :loading="launchingIssue === issue.number"
              :disabled="launchingIssue === issue.number || anyAgentRunning"
              :title="anyAgentRunning ? $t('yellow_hive.agent_busy') : `Run ${props.agentName}`"
              class="shrink-0"
              @click="runIssue(issue)"
            >Run</UiButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ExternalLink, Play } from 'lucide-vue-next'

const props = defineProps<{ agentName: string }>()
const emit = defineEmits<{ launched: [] }>()

const { t: $t } = useI18n()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const state = ref('open')
const stateTabs = [
  { id: 'open', label: 'Open' },
  { id: 'closed', label: 'Closed' },
]
function getPriority(issue: any): number {
  const labels = (issue.labels || []).map((l: any) => l.name)
  if (labels.includes('P1')) return 1
  if (labels.includes('P2')) return 2
  if (labels.includes('P3')) return 3
  return 4
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return d.toLocaleDateString()
}

const issues = computed(() =>
  agentsStore.issues
    .filter(issue => (issue.assignees || []).some((a: any) => a.login === props.agentName))
    .sort((a, b) => getPriority(a) - getPriority(b) || a.number - b.number)
)

const unassignedIssues = computed(() =>
  agentsStore.issues
    .filter(issue => !issue.assignees || issue.assignees.length === 0)
    .sort((a, b) => getPriority(a) - getPriority(b) || a.number - b.number)
)
const launchingIssue = ref<number | null>(null)

const anyAgentRunning = computed(() => {
  const running = agentsStore.agents.filter(a => a.status === 'running')
  // Only block if THIS agent is running (others can run in parallel)
  return running.some(a => a.name === props.agentName)
})

async function runIssue(issue: any) {
  launchingIssue.value = issue.number
  const result = await agentsStore.launchAgent(props.agentName, issue.number)
  if (result.ok) {
    toastStore.success(result.message)
    emit('launched')
  } else {
    toastStore.error(result.message)
  }
  launchingIssue.value = null
}

async function loadIssues() {
  await agentsStore.fetchIssues(state.value)
}

onMounted(loadIssues)
</script>
