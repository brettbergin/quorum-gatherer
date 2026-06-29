// Types mirroring the backend Pydantic schemas (app/schemas/api.py).

export interface AgentInfo {
  key: string
  name: string
  role: 'council_member' | 'chairman'
  phase: string
  order: number
  default_provider: string
  default_model: string
  owned_sections: string[]
}

export interface ChatOut {
  id: string
  title: string | null
  idea: string | null
  status: 'created' | 'running' | 'completed' | 'failed'
  created_at: string
}

export interface DocumentOut {
  id: string
  filename: string
  content_type: string | null
  created_at: string
}

export interface AgentRun {
  id: string
  agent_key: string
  agent_name: string
  phase: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  provider: string | null
  model: string | null
  output_text: string | null
  output: Record<string, unknown> | null
  error: string | null
  created_at: string
}

export interface ReportOut {
  content: Record<string, unknown>
  markdown: string | null
  created_at: string
}

export interface ChatDetail extends ChatOut {
  documents: DocumentOut[]
  agent_runs: AgentRun[]
  messages: unknown[]
  report: ReportOut | null
}

export interface ProviderSpec {
  key: string
  label: string
  default_model: string
  suggested_models: string[]
}

export interface ProviderSetting {
  provider: string
  default_model: string | null
  is_enabled: boolean
  has_key: boolean
}

export interface SettingsOut {
  providers: ProviderSpec[]
  settings: ProviderSetting[]
}

// WebSocket events emitted by the orchestrator.
export type WsEvent =
  | { type: 'phase_changed'; phase: 'deliberation' | 'synthesis' }
  | { type: 'agent_joined'; agent_key: string; name: string }
  | { type: 'agent_run_started'; agent_key: string; name: string; run_id: string; provider: string; model: string }
  | { type: 'agent_token'; agent_key: string; run_id: string; delta: string }
  | { type: 'agent_run_complete'; agent_key: string; run_id: string; text: string }
  | { type: 'agent_run_failed'; agent_key: string; run_id: string; error: string }
  | { type: 'council_report'; agent_key: string; run_id: string; content: Record<string, unknown>; markdown: string }
  | { type: 'error'; message: string }
