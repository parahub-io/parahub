export interface AgentSession {
  id: string
  object_type: string
  mode: string
  task_description: string
  gitea_issue_number: number | null
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  exit_code: number | null
  report_path: string
  screenshots: string[]
  commit_hashes: string[]
}

export interface AgentData {
  id: string
  object_type: string
  name: string
  display_name: string
  role: string
  avatar_url: string
  schedule_cron: string
  is_active: boolean
  voice_enabled: boolean
  status: 'running' | 'idle' | 'failed'
  last_session: AgentSession | null
}

export interface AgentMetrics {
  sessions: number
  hours: number
  success_rate: number
  tasks_completed: number
  tasks_failed: number
  tickets_closed: number
  avg_duration_min: number
}

export interface AgentStats {
  total_sessions: number
  total_hours: number
  success_rate: number
  by_agent: Record<string, AgentMetrics>
  last_7_days: { date: string; sessions: number; hours: number }[]
}

export const useAgentsStore = defineStore('agents', {
  state: () => ({
    agents: [] as AgentData[],
    sessions: {} as Record<string, AgentSession[]>,
    stats: null as AgentStats | null,
    issues: [] as any[],
    loading: false,
    error: null as string | null,
  }),

  getters: {
    getAgent: (state) => (name: string) => state.agents.find(a => a.name === name),
  },

  actions: {
    async getAuthHeaders() {
      const headers: Record<string, string> = {}
      const authStore = useAuthStore()
      await authStore.ensureToken()
      if (authStore.token) {
        headers.Authorization = `Bearer ${authStore.token}`
      }
      return headers
    },

    async fetchAgents() {
      this.loading = true
      this.error = null
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<AgentData[]>('/api/v1/agents/', {
          credentials: 'include',
          headers,
        })
        this.agents = data || []
      } catch (error: any) {
        this.error = error.data?.detail || error.message || 'Failed to load agents'
      } finally {
        this.loading = false
      }
    },

    async fetchSessions(agentName: string, limit = 20, offset = 0) {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<AgentSession[]>(`/api/v1/agents/${agentName}/sessions/`, {
          credentials: 'include',
          headers,
          params: { limit, offset },
        })
        this.sessions[agentName] = data || []
      } catch (error: any) {
        console.error(`Failed to load sessions for ${agentName}:`, error)
      }
    },

    async fetchStats() {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<AgentStats>('/api/v1/agents/stats/', {
          credentials: 'include',
          headers,
        })
        this.stats = data
      } catch (error: any) {
        console.error('Failed to load stats:', error)
      }
    },

    async fetchIssues(state = 'open') {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ issues: any[] }>('/api/v1/agents/issues/', {
          credentials: 'include',
          headers,
          params: { state },
        })
        this.issues = data.issues || []
      } catch (error: any) {
        console.error('Failed to load issues:', error)
      }
    },

    async fetchLog(agentName: string, lines = 50): Promise<string[]> {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ lines: string[] }>(`/api/v1/agents/${agentName}/log/`, {
          credentials: 'include',
          headers,
          params: { lines },
        })
        return data.lines || []
      } catch {
        return []
      }
    },

    updateAgentStatus(name: string, status: string) {
      const agent = this.agents.find(a => a.name === name)
      if (agent) agent.status = status as 'running' | 'idle' | 'failed'
    },

    async launchAgent(agentName: string, issueNumber?: number, count?: number): Promise<{ ok: boolean; message: string }> {
      try {
        const headers = await this.getAuthHeaders()
        const body: Record<string, any> = {}
        if (issueNumber) body.issue_number = issueNumber
        if (count && count > 1) body.count = count
        await $fetch(`/api/v1/agents/${agentName}/launch/`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body,
        })
        // Optimistic: set status immediately (WS will confirm)
        this.updateAgentStatus(agentName, 'running')
        const issueRef = issueNumber ? ` on #${issueNumber}` : ''
        const countRef = count && count > 1 ? ` (${count} tasks)` : ''
        return { ok: true, message: `${agentName} launched${issueRef}${countRef}` }
      } catch (error: any) {
        const msg = error.data?.error || error.data?.detail || 'Launch failed'
        return { ok: false, message: msg }
      }
    },

    async stopAgent(agentName?: string): Promise<{ ok: boolean; message: string }> {
      try {
        const headers = await this.getAuthHeaders()
        const params: Record<string, string> = {}
        if (agentName) params.name = agentName
        const data = await $fetch<{ message: string }>('/api/v1/agents/stop/', {
          method: 'POST',
          credentials: 'include',
          headers,
          params,
        })
        return { ok: true, message: data.message }
      } catch (error: any) {
        return { ok: false, message: error.data?.detail || 'Stop failed' }
      }
    },

    async emergencyStop(): Promise<{ ok: boolean; message: string }> {
      try {
        const headers = await this.getAuthHeaders()
        const data = await $fetch<{ message: string }>('/api/v1/agents/emergency-stop/', {
          method: 'POST',
          credentials: 'include',
          headers,
        })
        // Refresh agent status after kill
        setTimeout(() => this.fetchAgents(), 1000)
        return { ok: true, message: data.message }
      } catch (error: any) {
        return { ok: false, message: error.data?.detail || 'Emergency stop failed' }
      }
    },

    async fetchProgress(): Promise<{ running: boolean; agents: { agent: string; current: number; total: number }[] }> {
      try {
        const headers = await this.getAuthHeaders()
        return await $fetch('/api/v1/agents/progress/', {
          credentials: 'include',
          headers,
        })
      } catch {
        return { running: false, agents: [] }
      }
    },
  },
})
