# AI Features

## Image Analysis

Multi-provider AI vision system for validating marketplace item images.

### Providers
- Claude Haiku 4.5 (Anthropic)
- GPT-5 (OpenAI)
- Google Gemini Flash

Provider selection configurable via admin settings (AISettings singleton model).

### Quota System
Daily limits (Redis counter):
- 30 analyses/day per account
- Check before processing, consume after success

### Two-Step Process
1. Upload image -> AI analyzes content (safety, relevance, description)
2. User reviews AI assessment -> publishes if appropriate

Real-time progress updates via WebSocket (`ai.analysis_progress` event).

## Zenith AI Assistant

Personal AI assistant powered by Google Gemini API.

### Knowledge Base
Stored in Gitea repository. Context-aware responses about the platform, its features, and how to use them.

### Configuration
- `ZenithSettings` model (per-profile) for personal preferences
- `ZenithQueryLog` for audit trail
- API: `parahub/endpoints/zenith.py`

## Yellow Gate (AI Agent Automation)

Nine AI agents that autonomously work on the codebase, powered by Claude Opus 4.6:

| Agent | Role | Dev Slot | Color |
|-------|------|----------|-------|
| **Pixel** | Frontend development | :8003/:3005 | Indigo |
| **Forge** | Backend development | :8004/:3004 | Amber |
| **Scout** | Data and research | :8005/:3006 | Emerald |
| **Kevin** | Strategy and planning | N/A (no code) | Violet |
| **Vera** | Secretary and outreach | N/A | Rose |
| **Alice** | QA power user | N/A | Cyan |
| **Bob** | QA newcomer | N/A | Orange |
| **Atlas** | Architect and code review | N/A | Slate |
| **Iris** | Product owner | N/A | Pink |

### How It Works
1. Tasks created as Gitea issues with priority labels (P1/P2/P3) and agent assignment
2. `run.sh` picks highest-priority issue via **intelligent task picker** (fetches all open assigned + unassigned issues, deduplicates, auto-selects or asks agent to choose)
3. Agent runs Claude Code CLI with project context + agent profile + shared knowledge
4. Agent commits changes, posts report to Gitea issue, closes on success
5. If no issues exist, agent patrols backlog.md or does autonomous maintenance

### Kevin (Strategist)
Kevin creates strategy issues and decomposes them into actionable task issues for other agents. Does not write code. Always runs with `RUN_COUNT=1`. Uses `strategy` label in Gitea.

### Vera (Secretary)
Daily briefings, Matrix daemon for DM responses, web research, and email outreach via Mailcow. Platform identity with Parahub account + Matrix + email (vera@parahub.io).

### Gitea MCP Integration
Agents use native Gitea MCP tools (`list_issues`, `issue_read`, `issue_write`, `label_read`, etc.) instead of raw API calls. Per-agent token via `YELLOWGATE_AGENT` env var.

### Features
- **Per-agent dev slots**: isolated build/test environments via cookie routing (`parahub_dev=N`)
- **Post-commit hooks**: auto-restart only the committer's dev slot, stale-mark other slots
- **Process isolation**: setsid + systemd-run scopes, per-agent flock, crash recovery
- **Configurable timeout**: 59 minutes default, up to 4 hours for developer/analyst agents
- **WebSocket dashboard**: real-time Redis log streaming with syntax highlighting
- **Emergency stop**: per-agent or global stop from UI

### Monitoring
`monitor.sh` (bash, 30min cycle): NetData alarms, Uptime Kuma health checks, auto-heal (systemd restart, disk cleanup, cert renewal), GTFS-RT vehicle count validation, journalctl error tracking. Metrics to `.agents/metrics.log`, alerts to `.agents/alerts.log`.

### Dashboard
Staff-only UI at `/yellow-gate` with fighting game character select aesthetic. Per-agent color theming. Components: AgentPanel, LiveLog, SessionHistory, StatsPanel, TaskBoard.

## Technical Details

- **AI Vision**: `parahub/services/vision_ai.py`, `parahub/services/quota.py`
- **Zenith**: `parahub/services/zenith_service.py`, `parahub/endpoints/zenith.py`
- **Agents**: `agents/models.py` (Agent, AgentSession), `agents/api.py`, `.agents/` (profiles, run.sh)
- **Frontend**: `components/IoT/HiveCard.vue`, `pages/yellow-gate/` (AgentPanel, LiveLog, SessionHistory, StatsPanel, TaskBoard)
