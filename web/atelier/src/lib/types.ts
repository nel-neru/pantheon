// バックエンド API のレスポンス形（web/server.py に対応）。

export type OrgSummary = {
  id: string
  name: string
  purpose: string
  target_repo_path: string | null
  status: string
  health_score: number
  autonomy_score: number
  improvement_velocity: number
  total_agents: number
  pending_proposals: number
  last_active: string
  is_system: boolean
  icon_data: string | null
}

export type OrchestraAgent = {
  agent_id: string | null
  title: string | null
  role: string | null
  status: string | null
  exit_code: number | null
}

export type OrchestraSession = {
  id: string
  name: string
  status: string
  driver: string
  agents: OrchestraAgent[]
}

export type OrchestraHandoff = {
  id: string
  source: string
  target: string
  kind: string
  status: string
  title: string
  priority: string
}

export type OrchestraData = {
  sessions: OrchestraSession[]
  handoffs: OrchestraHandoff[]
  counts: {
    sessions: number
    active_sessions: number
    agents: number
    handoffs: number
    pending_handoffs: number
  }
}

export type Palette = {
  primary?: string
  secondary?: string
  background?: string
  accent?: string
}

export type DesignStyle = {
  id: string
  name: string
  description: string
  palette: Palette
  font_family: string
}

export type Persona = {
  id: string
  name: string
  role: string
}

export type Trend = {
  source: string
  url: string
  title: string
  summary: string
  topics: string[]
  genre: string
  score: number
  raw_excerpt: string
  collected_at: string
  hash: string
}

export type UsageWindow = {
  window_hours: number
  calls: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  total_tokens: number
  total_cost_usd: number
  measured_calls: number
  estimated_calls: number
}

export type Governor = {
  enabled: boolean
  level: 'ok' | 'soft_limit' | 'hard_limit' | 'rate_limited' | string
  window_hours: number
  window_tokens: number
  soft_limit_tokens: number
  hard_limit_tokens: number
}

export type UsageSummary = {
  usage?: { session_5h?: UsageWindow; weekly_7d?: UsageWindow }
  governor?: Governor
  rate_limited?: boolean
  retry_at?: string | null
}

export type DaemonStatus = {
  name: string
  running?: boolean
  pid?: number | null
  healthy?: boolean
  enabled?: boolean
  stale?: boolean
  [key: string]: unknown
}

export type DaemonsPayload = {
  daemons: DaemonStatus[]
  rate_limited?: boolean
  retry_at?: string | null
}

export type HandoffFull = {
  handoff_id: string
  source_org: string
  target_org: string
  kind: string
  status: string
  title: string
  priority: string
  note?: string
  created_at?: string
  [key: string]: unknown
}

export type Proposal = {
  id?: string
  proposal_id?: string
  title?: string
  description?: string
  status?: string
  category?: string
  priority?: string | number
  diff_text?: string
  approval_notes?: string
  created_at?: string
  [key: string]: unknown
}

// /api/inbox — 投稿承認・公開確認キュー
export type InboxItem = {
  kind: string
  id: string
  org_name: string
  title: string
  category: string
  priority: string
  platform?: string
  scheduled_at?: string | null
  status?: 'queued' | 'handed_off' | string
  route?: string
}

export type InboxPayload = {
  items: InboxItem[]
  counts: Record<string, number>
}
