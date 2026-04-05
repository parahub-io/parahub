<template>
  <div>
    <Head>
      <Title>Hive - Parahub</Title>
    </Head>

    <!-- Access denied -->
    <div v-if="!isStaff" class="text-center py-20">
      <ShieldAlert class="w-12 h-12 text-neutral-400 mx-auto mb-4" />
      <p class="text-neutral-500">{{ $t('yellow_hive.admin_only') }}</p>
    </div>

    <div v-else class="gate" :style="agentCssVars">
      <h1 class="sr-only">Hive</h1>
      <!-- Header -->
      <div class="gate-header">
        <div class="flex items-center gap-2.5">
          <span class="hive-logo">HIVE</span>
          <div v-if="stats" class="hidden sm:flex items-center gap-4 text-xs text-neutral-400 ml-3">
            <span><strong class="text-neutral-600 dark:text-neutral-300">{{ stats.total_sessions }}</strong> runs</span>
            <span><strong class="text-neutral-600 dark:text-neutral-300">{{ stats.total_hours }}h</strong></span>
            <span :class="stats.success_rate >= 90 ? 'text-green-500' : ''"><strong>{{ stats.success_rate }}%</strong></span>
            <div class="flex items-end gap-px h-3" :title="$t('yellow_hive.stats')">
              <div
                v-for="day in stats.last_7_days"
                :key="day.date"
                class="w-1.5 rounded-sm transition-all"
                :class="day.sessions > 0 ? 'bg-primary/50' : 'bg-neutral-300 dark:bg-neutral-700'"
                :style="{ height: `${Math.max((day.sessions / maxDaySessions) * 12, 2)}px` }"
                :title="`${day.date.slice(5)}: ${day.sessions}`"
              />
            </div>
          </div>
        </div>
        <UiButton
          v-if="hasRunningAgents"
          variant="error"
          size="sm"
          :icon="Zap"
          :loading="emergencyStopping"
          :disabled="emergencyStopping"
          @click="showEmergencyStopConfirm = true"
          class="!bg-red-600 hover:!bg-red-700 !border-red-700 !text-white animate-pulse"
        >
          {{ $t('yellow_hive.emergency_stop') }}
        </UiButton>
      </div>

      <!-- CHARACTER SELECT BAR (fighting game roster) -->
      <div
        class="select-bar"
        role="listbox"
        aria-label="Select agent"
        data-gamepad-group="agents"
      >
        <button
          v-for="(agent, idx) in agents"
          :key="agent.name"
          role="option"
          :aria-selected="selectedAgent === agent.name"
          :data-agent-index="idx"
          :data-gamepad-selectable="true"
          tabindex="0"
          class="agent-slot"
          :class="{
            selected: selectedAgent === agent.name,
            running: agent.status === 'running',
          }"
          :style="slotVars(agent.name)"
          @mouseenter="onSlotHover"
          @click="selectedAgent = agent.name"
          @keydown.left.prevent="selectAdjacentAgent(-1)"
          @keydown.right.prevent="selectAdjacentAgent(1)"
          @keydown.enter.prevent="selectedAgent = agent.name"
        >
          <img :src="`/img/agents/${agent.name}.png`" :alt="agent.display_name" class="slot-img" />
          <span v-if="issueCountByAgent[agent.name]" class="slot-badge">{{ issueCountByAgent[agent.name] }}</span>
        </button>
      </div>

      <!-- CHARACTER SHOWCASE -->
      <div class="showcase">
        <div class="showcase-inner">
          <!-- Portrait side -->
          <div class="portrait-area" :class="{ 'is-running': currentAgent?.status === 'running' }">
            <div class="portrait-glow" />
            <div class="portrait-ring" />
            <Transition name="portrait" mode="out-in">
              <img
                :key="selectedAgent"
                :src="`/img/agents/${selectedAgent}.png`"
                :alt="currentAgent?.display_name"
                class="portrait-img"
                draggable="false"
              />
            </Transition>
            <!-- Status badge on portrait -->
            <div v-if="currentAgent" class="portrait-badge" :class="currentAgent.status">
              <span class="badge-dot" />
              {{ $t(`yellow_hive.status_${currentAgent.status}`) }}
            </div>
          </div>

          <!-- Info side -->
          <div class="info-panel">
            <Transition name="info" mode="out-in">
              <div :key="selectedAgent" class="info-content">
                <!-- Agent name (fighting game style) -->
                <h2 class="agent-name">{{ currentAgent?.display_name?.toUpperCase() }}</h2>
                <div class="agent-epithet">{{ currentProfile.title }}</div>

                <!-- Tags: specialty + schedule -->
                <div class="flex flex-wrap gap-2 mt-3 mb-4">
                  <span class="info-tag">
                    <Cpu class="w-3 h-3" />
                    {{ currentProfile.specialty }}
                  </span>
                  <span class="info-tag">
                    <Clock class="w-3 h-3" />
                    {{ currentProfile.schedule }}
                  </span>
                  <span v-if="currentAgent?.status === 'running'" class="info-tag running-tag">
                    <Zap class="w-3 h-3" />
                    ACTIVE
                  </span>
                </div>

                <!-- Bio (1-line, expandable) -->
                <p class="bio-text" :class="{ 'bio-collapsed': !bioExpanded }" @click="bioExpanded = !bioExpanded">{{ currentProfile.description }}</p>

                <!-- STAT BARS (or empty state) -->
                <div v-if="agentPerf && agentPerf.sessions > 0" class="stats-block">
                  <div
                    v-for="(stat, i) in realStats"
                    :key="stat.label"
                    class="stat-row"
                    :style="{ '--delay': `${0.1 + i * 0.06}s`, '--target': `${stat.bar}%` }"
                  >
                    <span class="stat-label">{{ stat.label }}</span>
                    <div class="stat-track">
                      <div class="stat-fill" />
                    </div>
                    <span class="stat-val">{{ stat.display }}</span>
                  </div>
                </div>
                <div v-else class="empty-state">
                  <span class="empty-text">AWAITING ORDERS</span>
                </div>
              </div>
            </Transition>

            <!-- Action panel (always visible, not inside Transition) -->
            <YellowGateAgentPanel v-if="currentAgent" :agent="currentAgent" class="mt-auto pt-3" @launched="activeTab = 'live_log'" />
          </div>
        </div>
      </div>

      <!-- TABS (gamepad: L1/R1 for tab switching) -->
      <UiTabs
        v-model="activeTab"
        :tabs="tabItems"
        class="mt-6 mb-4"
        data-gamepad-group="tabs"
      />

      <div class="min-h-[400px]">
        <YellowGateLiveLog v-if="activeTab === 'live_log'" :agent-name="selectedAgent" />
        <YellowGateSessionHistory v-else-if="activeTab === 'sessions'" :agent-name="selectedAgent" />
        <YellowGateTaskBoard v-else-if="activeTab === 'tasks'" :agent-name="selectedAgent" @launched="activeTab = 'live_log'" />
      </div>
    </div>
  </div>

  <UiConfirmModal
    v-model="showEmergencyStopConfirm"
    :title="$t('yellow_hive.emergency_stop')"
    :message="$t('yellow_hive.emergency_stop_confirm')"
    :icon="Zap"
    variant="error"
    :confirm-label="$t('yellow_hive.emergency_stop')"
    @confirm="handleEmergencyStop"
  />
</template>

<script setup lang="ts">
import { ShieldAlert, Zap, Cpu, Clock } from 'lucide-vue-next'

definePageMeta({
  middleware: 'auth',
  keepalive: true,
})

const { t: $t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const isStaff = computed(() => authStore.user?.is_staff ?? false)
const agents = computed(() => {
  const byName = new Map(agentsStore.agents.map(a => [a.name, a]))
  return agentOrder.filter(name => byName.has(name)).map(name => byName.get(name)!)
})
const stats = computed(() => agentsStore.stats)

const selectedAgent = ref((route.query.agent as string) || 'vera')
const activeTab = ref('live_log')
const emergencyStopping = ref(false)
const showEmergencyStopConfirm = ref(false)
const bioExpanded = ref(false)

// Sync URL query param when switching agents
watch(selectedAgent, (name) => {
  bioExpanded.value = false
  router.replace({ query: { ...route.query, agent: name } })
})
const hasRunningAgents = computed(() => agents.value.some(a => a.status === 'running'))

// ── Character profiles (fighting game style) ──

type AgentName = 'kevin' | 'atlas' | 'iris' | 'forge' | 'pixel' | 'scout' | 'alice' | 'bob' | 'vera'

interface CharacterProfile {
  title: string
  color: string
  colorRgb: string
  description: string
  specialty: string
  schedule: string
}

// Display order: voice → analysis → product → build → QA → strategy
const agentOrder: AgentName[] = ['vera', 'atlas', 'iris', 'forge', 'pixel', 'scout', 'alice', 'bob', 'kevin']

const characterProfiles: Record<AgentName, CharacterProfile> = {
  kevin: {
    title: 'The Mastermind',
    color: '#e11d48',
    colorRgb: '225, 29, 72',
    description: 'Strategic visionary who sees the whole battlefield. Analyzes the competitive landscape, plans weekly operations, and distributes missions to the hive. Every task has a purpose, every agent a role.',
    specialty: 'Strategy & Planning',
    schedule: 'Weekly',
  },
  atlas: {
    title: 'The Analyst',
    color: '#1d4ed8',
    colorRgb: '29, 78, 216',
    description: 'Deep-code surgeon who reads the codebase like an open book. Profiles slow endpoints, hunts N+1 queries, and writes RFCs backed by hard numbers. If it\'s inefficient, Atlas will find it — with evidence.',
    specialty: 'Architecture & Profiling',
    schedule: 'Weekly',
  },
  iris: {
    title: 'The Visionary',
    color: '#7c3aed',
    colorRgb: '124, 58, 237',
    description: 'Walks every user journey with fresh eyes, counting clicks and questioning every empty state. Compares against the best in the industry, then writes feature proposals that put users first.',
    specialty: 'Product & UX',
    schedule: 'Weekly',
  },
  forge: {
    title: 'The Blacksmith',
    color: '#f59e0b',
    colorRgb: '245, 158, 11',
    description: 'Builder of unbreakable backends. Hammers out APIs and data models with the precision of a master blacksmith, ensuring every endpoint is solid as steel and every migration runs clean.',
    specialty: 'Backend & APIs',
    schedule: 'On demand',
  },
  pixel: {
    title: 'The Artisan',
    color: '#6366f1',
    colorRgb: '99, 102, 241',
    description: 'Master of pixels and visual harmony. Crafts interfaces that users love, catching every misaligned element and color inconsistency with an artist\'s eye. Armed with a palette of components and an obsession for perfect layouts.',
    specialty: 'Frontend & UI/UX',
    schedule: 'On demand',
  },
  scout: {
    title: 'The Explorer',
    color: '#10b981',
    colorRgb: '16, 185, 129',
    description: 'Tireless data hunter who ventures into the unknown. Discovers new data sources, maps uncharted territories, and brings fresh intelligence back to the hive. No feed is too remote, no format too obscure.',
    specialty: 'Data & Intelligence',
    schedule: 'On demand',
  },
  alice: {
    title: 'The Veteran',
    color: '#0891b2',
    colorRgb: '8, 145, 178',
    description: 'Battle-hardened QA warrior who knows every feature inside out. Tests edge cases, permission boundaries, mobile layouts, i18n quirks, and race conditions. If there\'s a crack in the armor, Alice will find it.',
    specialty: 'QA & Edge Cases',
    schedule: 'On demand',
  },
  bob: {
    title: 'The Newcomer',
    color: '#d946ef',
    colorRgb: '217, 70, 239',
    description: 'Approaches every screen like it\'s the first time. If Bob gets confused, it\'s a UX bug. Tests onboarding flows, empty states, and unclear labels — the fresh perspective the hive needs.',
    specialty: 'QA & Onboarding',
    schedule: 'On demand',
  },
  vera: {
    title: 'The Voice',
    color: '#64748b',
    colorRgb: '100, 116, 139',
    description: 'The hive\'s diplomat and secretary. Delivers voice briefings, delegates tasks through Matrix, researches the web, and handles email outreach. The bridge between the hive and the outside world.',
    specialty: 'Comms & Briefings',
    schedule: 'On demand',
  },
}

// ── Computed ──

const currentAgent = computed(() => agents.value.find(a => a.name === selectedAgent.value))
const currentProfile = computed(() => characterProfiles[selectedAgent.value as AgentName] || characterProfiles.pixel)
const agentPerf = computed(() => stats.value?.by_agent?.[selectedAgent.value] || null)

const openIssuesCount = computed(() => {
  return agentsStore.issues.filter(issue =>
    (issue.assignees || []).some((a: any) => a.login === selectedAgent.value)
  ).length
})

// Open issue count per agent (for roster badges)
const issueCountByAgent = computed(() => {
  const counts: Record<string, number> = {}
  for (const name of agentOrder) {
    counts[name] = agentsStore.issues.filter(issue =>
      (issue.assignees || []).some((a: any) => a.login === name)
    ).length
  }
  return counts
})

// Real stats for fighting-game-style bars (normalized 0-100 for bar width)
const realStats = computed(() => {
  const perf = agentPerf.value
  if (!perf) return []

  // Normalize across all agents for relative bars
  const allPerfs = stats.value ? Object.values(stats.value.by_agent) : []
  const maxSessions = Math.max(...allPerfs.map(p => p.sessions), 1)
  const maxTickets = Math.max(...allPerfs.map(p => p.tickets_closed), 1)
  const maxAvg = Math.max(...allPerfs.map(p => p.avg_duration_min), 1)

  // Count open issues per agent for relative bar
  const agentNames = Object.keys(stats.value?.by_agent || {})
  const issueCounts = agentNames.map(name =>
    agentsStore.issues.filter(issue => (issue.assignees || []).some((a: any) => a.login === name)).length
  )
  const maxOpenIssues = Math.max(...issueCounts, 1)
  const myOpenIssues = openIssuesCount.value

  return [
    {
      label: 'Queue',
      bar: Math.round((myOpenIssues / maxOpenIssues) * 100),
      display: myOpenIssues,
    },
    {
      label: 'Rate',
      bar: perf.success_rate,
      display: `${perf.success_rate}%`,
    },
    {
      label: 'Done',
      bar: Math.round((perf.tasks_completed / maxSessions) * 100),
      display: `${perf.tasks_completed}/${perf.sessions}`,
    },
    {
      label: 'Closed',
      bar: Math.round((perf.tickets_closed / maxTickets) * 100),
      display: perf.tickets_closed,
    },
    {
      label: 'Speed',
      bar: maxAvg > 0 ? Math.round(Math.max(100 - (perf.avg_duration_min / maxAvg) * 80, 20)) : 50,
      display: `${perf.avg_duration_min}m`,
    },
  ]
})

const agentCssVars = computed(() => ({
  '--agent-color': currentProfile.value.color,
  '--agent-rgb': currentProfile.value.colorRgb,
}))

const maxDaySessions = computed(() => {
  if (!stats.value) return 1
  return Math.max(...stats.value.last_7_days.map(d => d.sessions), 1)
})

const sessionCount = computed(() => (agentsStore.sessions[selectedAgent.value] || []).length || undefined)
const taskCount = computed(() => openIssuesCount.value || undefined)

const tabItems = computed(() => [
  { id: 'live_log', label: $t('yellow_hive.live_log') },
  { id: 'sessions', label: $t('yellow_hive.sessions'), badge: sessionCount.value },
  { id: 'tasks', label: $t('yellow_hive.tasks'), badge: taskCount.value },
])

// ── Hover sounds ──

const whooshSounds: HTMLAudioElement[] = []
if (import.meta.client) {
  for (const f of ['whoosh_low', 'whoosh_mid', 'whoosh_high']) {
    const a = new Audio(`/sounds/agents/${f}.mp3`)
    a.volume = 0.25
    a.preload = 'auto'
    whooshSounds.push(a)
  }
}

function onSlotHover() {
  if (!whooshSounds.length) return
  const sound = whooshSounds[Math.floor(Math.random() * whooshSounds.length)]
  sound.currentTime = 0
  sound.play().catch(() => {})
}

// ── Helpers ──

function slotVars(name: string) {
  const p = characterProfiles[name as AgentName]
  if (!p) return {}
  return { '--slot-color': p.color, '--slot-rgb': p.colorRgb }
}


function selectAdjacentAgent(dir: number) {
  const names = agents.value.map(a => a.name)
  const idx = names.indexOf(selectedAgent.value)
  const next = (idx + dir + names.length) % names.length
  selectedAgent.value = names[next]
}

async function handleEmergencyStop() {
  showEmergencyStopConfirm.value = false
  emergencyStopping.value = true
  const result = await agentsStore.emergencyStop()
  if (result.ok) toastStore.success(result.message)
  else toastStore.error(result.message)
  emergencyStopping.value = false
}

// ── WebSocket for real-time stats ──

let statsWs: WebSocket | null = null
let statsReconnectTimer: ReturnType<typeof setTimeout> | null = null

async function connectStatsWs() {
  if (!import.meta.client) return
  const authStore = useAuthStore()
  await authStore.ensureToken()
  if (!authStore.token) return

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/v1/realtime/?token=${authStore.token}`

  try {
    statsWs = new WebSocket(wsUrl)
    statsWs.onopen = () => {
      statsWs?.send(JSON.stringify({ type: 'join', room: 'agent_stats', id: 'global' }))
    }
    statsWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'agent_stats.initial_state' || data.type === 'agent_stats.update') {
          agentsStore.stats = {
            total_sessions: data.total_sessions,
            total_hours: data.total_hours,
            success_rate: data.success_rate,
            by_agent: data.by_agent,
            last_7_days: data.last_7_days,
          }
        } else if (data.type === 'agent.status_changed') {
          agentsStore.updateAgentStatus(data.agent, data.status)
        } else if (data.type === 'agent.session_completed') {
          agentsStore.fetchSessions(data.agent)
        } else if (data.type === 'agent.tasks_updated') {
          agentsStore.fetchIssues('open')
        }
      } catch {}
    }
    statsWs.onclose = () => {
      statsReconnectTimer = setTimeout(connectStatsWs, 10000)
    }
    statsWs.onerror = () => { statsWs?.close() }
  } catch {
    statsReconnectTimer = setTimeout(connectStatsWs, 10000)
  }
}

// ── Lifecycle ──

onMounted(() => {
  agentsStore.fetchAgents()
  agentsStore.fetchStats()
  agentsStore.fetchIssues('open')
  agentsStore.fetchSessions(selectedAgent.value)
  connectStatsWs()
})

// Pre-fetch sessions when agent changes (for tab badge)
watch(selectedAgent, (name) => {
  if (!agentsStore.sessions[name]) agentsStore.fetchSessions(name)
})

onUnmounted(() => {
  statsWs?.close()
  if (statsReconnectTimer) clearTimeout(statsReconnectTimer)
})

// ── Gamepad overrides (Yellow Gate-specific) ──

if (import.meta.client) {
  const isActive = ref(true)
  onActivated(() => { isActive.value = true })
  onDeactivated(() => { isActive.value = false })

  const { onButton, BUTTON } = useGamepad()

  // D-pad Left/Right — cycle agents (overrides global focus movement)
  onButton(BUTTON.DPAD_LEFT, () => {
    if (!isActive.value) return false
    selectAdjacentAgent(-1)
  })
  onButton(BUTTON.DPAD_RIGHT, () => {
    if (!isActive.value) return false
    selectAdjacentAgent(1)
  })

  // LB/RB — cycle tabs (overrides global nav cycling)
  onButton(BUTTON.LB, () => {
    if (!isActive.value) return false
    const tabs = tabItems.value
    const idx = tabs.findIndex(t => t.id === activeTab.value)
    activeTab.value = tabs[(idx - 1 + tabs.length) % tabs.length].id
  })
  onButton(BUTTON.RB, () => {
    if (!isActive.value) return false
    const tabs = tabItems.value
    const idx = tabs.findIndex(t => t.id === activeTab.value)
    activeTab.value = tabs[(idx + 1) % tabs.length].id
  })

  // Y — toggle launch/stop current agent
  onButton(BUTTON.Y, () => {
    if (!isActive.value) return false
    const agent = currentAgent.value
    if (!agent) return
    if (agent.status === 'running') {
      agentsStore.stopAgent()
    } else {
      agentsStore.launchAgent(agent.name).then(r => { if (r.ok) activeTab.value = 'live_log' })
    }
  })

  // Start — emergency stop (overrides global "go home")
  onButton(BUTTON.START, () => {
    if (!isActive.value) return false
    handleEmergencyStop()
  })
}
</script>

<style scoped>
/* ═══════════════════════════════════════════════
   HIVE — Fighting Game Character Select
   ═══════════════════════════════════════════════ */

.gate {
  @apply max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6;
}

/* ── Header ── */

.gate-header {
  @apply flex items-center justify-between gap-4 mb-5;
}

.hive-logo {
  @apply text-xl font-black tracking-[0.2em];
  background: linear-gradient(135deg, var(--agent-color) 0%, rgba(var(--agent-rgb), 0.6) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ── Character Select Bar (flush roster) ── */

.select-bar {
  @apply flex mb-4;
  @apply border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden;
}

.agent-slot {
  @apply relative flex-1 cursor-pointer;
  @apply flex items-end justify-center;
  @apply focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary;
  height: 80px;
  border-right: 1px solid rgb(229 231 235 / 1);
  box-sizing: border-box;
  box-shadow: inset 0 0 0 2px transparent;
}

:root.dark .agent-slot {
  border-right-color: rgb(64 64 64 / 1);
}

.agent-slot:last-child {
  border-right: none;
}

@media (max-width: 640px) {
  .select-bar {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
  }

  .agent-slot {
    flex: none;
    aspect-ratio: 1 / 1;
    height: auto;
    border-right: none;
    border-bottom: 1px solid rgb(229 231 235 / 1);
    border-right: 1px solid rgb(229 231 235 / 1);
  }

  :root.dark .agent-slot {
    border-bottom-color: rgb(64 64 64 / 1);
    border-right-color: rgb(64 64 64 / 1);
  }

  /* Remove right border on last column */
  .agent-slot:nth-child(5n) {
    border-right: none;
  }

  /* Remove bottom border on last row */
  .agent-slot:nth-last-child(-n+4),
  .agent-slot:last-child {
    border-bottom: none;
  }
}

/* Running agent: colored border outline */
.agent-slot.running {
  box-shadow: inset 0 0 0 2px rgba(var(--slot-rgb), 0.5);
}

/* Selected agent: strong colored border */
.agent-slot.selected {
  box-shadow: inset 0 0 0 3px var(--slot-color);
  background: rgba(var(--slot-rgb), 0.08);
}

.agent-slot.running.selected {
  box-shadow: inset 0 0 0 3px var(--slot-color);
  background: rgba(var(--slot-rgb), 0.12);
}

/* Hover highlight (non-selected) */
.agent-slot:not(.selected):hover {
  background: rgba(var(--slot-rgb), 0.06);
  box-shadow: inset 0 0 0 2px rgba(var(--slot-rgb), 0.35);
}

.agent-slot:not(.selected):hover .slot-img {
  filter: grayscale(0.1);
  opacity: 0.9;
}

/* Shine sweep on hover */
.agent-slot {
  overflow: hidden;
}

.agent-slot::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 30%,
    rgba(var(--slot-rgb), 0.15) 45%,
    rgba(255, 255, 255, 0.25) 50%,
    rgba(var(--slot-rgb), 0.15) 55%,
    transparent 70%
  );
  transform: translateX(-110%);
  pointer-events: none;
  z-index: 2;
}

.agent-slot:hover::after {
  animation: shine-sweep 0.2s ease-out forwards;
}

.slot-img {
  @apply w-auto object-contain pointer-events-none;
  max-height: 72px;
  filter: grayscale(0.3);
  opacity: 0.7;
}

.agent-slot.selected .slot-img,
.agent-slot.running .slot-img {
  filter: none;
  opacity: 1;
}

/* Issue count badge (unread-style) */
.slot-badge {
  @apply absolute top-1 right-1 z-10;
  @apply min-w-[18px] h-[18px] px-1;
  @apply flex items-center justify-center;
  @apply text-[10px] font-bold leading-none text-white;
  @apply rounded-full;
  background: var(--slot-color);
  box-shadow: 0 1px 4px rgba(var(--slot-rgb), 0.4);
}

.agent-slot:not(.selected):not(.running) .slot-badge {
  @apply bg-neutral-400 dark:bg-neutral-500;
  box-shadow: none;
}

@media (max-width: 640px) {
  .slot-img {
    max-height: 52px;
  }
}

/* ── Showcase ── */

.showcase {
  @apply rounded-2xl mb-4;
  @apply border border-neutral-200 dark:border-neutral-800;
  background:
    radial-gradient(ellipse at 20% 50%, rgba(var(--agent-rgb), 0.06) 0%, transparent 60%),
    linear-gradient(180deg, rgba(var(--agent-rgb), 0.02) 0%, transparent 40%);
  @apply bg-neutral-50 dark:bg-neutral-900/80;
}

.showcase-inner {
  @apply grid gap-6 p-6;
  grid-template-columns: 260px 1fr;
}

@media (max-width: 768px) {
  .showcase-inner {
    grid-template-columns: 1fr;
    padding: 1rem;
    gap: 1rem;
  }
}

/* ── Portrait ── */

.portrait-area {
  @apply relative flex items-center justify-center overflow-hidden;
  min-height: 300px;
}

.portrait-glow {
  position: absolute;
  inset: -40%;
  background: radial-gradient(ellipse at center, rgba(var(--agent-rgb), 0.12) 0%, transparent 65%);
  filter: blur(30px);
  animation: glow-breathe 4s ease-in-out infinite;
  pointer-events: none;
}

.portrait-area.is-running .portrait-glow {
  animation: glow-active 2s ease-in-out infinite;
}

.portrait-ring {
  position: absolute;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  border: 2px solid rgba(var(--agent-rgb), 0.1);
  pointer-events: none;
}

.portrait-area.is-running .portrait-ring {
  border-color: rgba(var(--agent-rgb), 0.3);
  animation: ring-pulse 2s ease-in-out infinite;
}

.portrait-img {
  position: relative;
  z-index: 1;
  max-height: 280px;
  width: auto;
  object-fit: contain;
  filter: drop-shadow(0 8px 24px rgba(var(--agent-rgb), 0.25));
}

.portrait-badge {
  @apply absolute bottom-1 left-1/2 -translate-x-1/2 z-10;
  @apply flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full;
  @apply bg-white/80 dark:bg-neutral-800/80 backdrop-blur-sm;
  @apply text-neutral-600 dark:text-neutral-400;
}

.portrait-badge .badge-dot {
  @apply w-2 h-2 rounded-full;
}

.portrait-badge.running { @apply text-green-600 dark:text-green-400; }
.portrait-badge.running .badge-dot { @apply bg-green-500 animate-pulse; }
.portrait-badge.idle .badge-dot { @apply bg-neutral-400; }
.portrait-badge.failed { @apply text-red-600 dark:text-red-400; }
.portrait-badge.failed .badge-dot { @apply bg-red-500; }

/* ── Info panel ── */

.info-panel {
  @apply flex flex-col justify-center min-w-0;
}

.info-content {
  @apply min-w-0;
}

.agent-name {
  @apply text-3xl sm:text-4xl font-black tracking-wider leading-none;
  background: linear-gradient(135deg, var(--agent-color) 20%, rgba(var(--agent-rgb), 0.5) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.agent-epithet {
  @apply text-xs font-bold tracking-[0.25em] uppercase mt-1;
  color: rgba(var(--agent-rgb), 0.6);
}

.info-tag {
  @apply inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full;
  @apply bg-neutral-200/70 dark:bg-neutral-700/50 text-neutral-600 dark:text-neutral-400;
}

.running-tag {
  @apply bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400;
  animation: tag-pulse 2s ease-in-out infinite;
}

.bio-text {
  @apply text-sm text-neutral-500 dark:text-neutral-400 leading-relaxed mb-5 cursor-pointer;
}

.bio-text.bio-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bio-text:hover {
  @apply text-neutral-600 dark:text-neutral-300;
}

/* ── Stat bars (fighting game style) ── */

.stats-block {
  @apply space-y-2 mb-5;
}

.stat-row {
  @apply flex items-center gap-2.5;
}

.stat-label {
  @apply w-12 text-[11px] font-bold uppercase tracking-wider text-right;
  color: rgba(var(--agent-rgb), 0.7);
}

.stat-track {
  @apply flex-1 h-2.5 rounded-sm overflow-hidden;
  @apply bg-neutral-200 dark:bg-neutral-700/80;
}

.stat-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--agent-color), rgba(var(--agent-rgb), 0.7));
  box-shadow: 0 0 10px rgba(var(--agent-rgb), 0.3);
  width: 0;
  animation: bar-fill 0.35s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  animation-delay: var(--delay);
}

.stat-val {
  @apply w-10 text-xs font-black font-mono text-right;
  @apply text-neutral-700 dark:text-neutral-300;
}

/* ── Empty state ── */

.empty-state {
  @apply flex items-center justify-center py-8 mb-5;
  @apply rounded-lg border border-dashed;
  border-color: rgba(var(--agent-rgb), 0.2);
  background: rgba(var(--agent-rgb), 0.03);
}

.empty-text {
  @apply text-sm font-black tracking-[0.3em] uppercase;
  color: rgba(var(--agent-rgb), 0.3);
  animation: empty-pulse 3s ease-in-out infinite;
}

/* ═══════════════════════════════════════════════
   ANIMATIONS
   ═══════════════════════════════════════════════ */

@keyframes bar-fill {
  from { width: 0; opacity: 0.5; }
  to { width: var(--target); opacity: 1; }
}

@keyframes glow-breathe {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.03); }
}

@keyframes glow-active {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.08); }
}

@keyframes ring-pulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.05); opacity: 0.6; }
}

@keyframes tag-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

@keyframes empty-pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.6; }
}

@keyframes shine-sweep {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(110%); }
}

/* ═══════════════════════════════════════════════
   TRANSITIONS (Vue) — 2x faster
   ═══════════════════════════════════════════════ */

/* Portrait: scale + fade */
.portrait-enter-active {
  transition: all 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}
.portrait-leave-active {
  transition: all 0.1s ease-in;
}
.portrait-enter-from {
  opacity: 0;
  transform: scale(0.88) translateY(12px);
}
.portrait-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Info: slide + fade */
.info-enter-active {
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
  transition-delay: 0.04s;
}
.info-leave-active {
  transition: all 0.08s ease-in;
}
.info-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.info-leave-to {
  opacity: 0;
  transform: translateX(-6px);
}
</style>
