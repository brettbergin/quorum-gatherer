export interface AgentState {
  status: 'pending' | 'running' | 'completed' | 'failed'
  text: string
  provider?: string | null
  model?: string | null
  error?: string
}

export function AgentPanel({ name, state }: { name: string; state: AgentState }) {
  return (
    <div className={`agent-panel ${state.status}`}>
      <div className="agent-head">
        <span className="agent-name">{name}</span>
        <span className={`badge ${state.status}`}>{state.status}</span>
      </div>
      {state.provider && (
        <div className="agent-meta">
          {state.provider} · {state.model}
        </div>
      )}
      <div className="agent-body">
        {state.error ? (
          <span className="err">{state.error}</span>
        ) : state.text ? (
          state.text
        ) : (
          <span className="muted">waiting to deliberate…</span>
        )}
        {state.status === 'running' && <span className="cursor">▍</span>}
      </div>
    </div>
  )
}
