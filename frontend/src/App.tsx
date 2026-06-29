import { useEffect, useRef, useState } from 'react'
import { api, openChatSocket } from './api'
import { AgentPanel, type AgentState } from './components/AgentPanel'
import { ChairmanReport } from './components/ChairmanReport'
import { Composer } from './components/Composer'
import { SettingsDialog } from './components/SettingsDialog'
import type { AgentInfo, ChatDetail, ChatOut, WsEvent } from './types'

export default function App() {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [chats, setChats] = useState<ChatOut[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ChatDetail | null>(null)
  const [perAgent, setPerAgent] = useState<Record<string, AgentState>>({})
  const [phase, setPhase] = useState<string | null>(null)
  const [report, setReport] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const members = agents.filter((a) => a.role === 'council_member')

  const refreshChats = () => api.listChats().then(setChats)

  useEffect(() => {
    api.listAgents().then(setAgents).catch((e) => setError(String(e)))
    refreshChats().catch((e) => setError(String(e)))
    return () => wsRef.current?.close()
  }, [])

  const selectChat = async (id: string) => {
    wsRef.current?.close()
    setActiveId(id)
    setReport(null)
    setPhase(null)
    setRunning(false)
    setError(null)
    const d = await api.getChat(id)
    setDetail(d)
    const pa: Record<string, AgentState> = {}
    for (const r of d.agent_runs) {
      if (r.phase === 'deliberation') {
        pa[r.agent_key] = {
          status: r.status,
          text: r.output_text ?? '',
          provider: r.provider,
          model: r.model,
          error: r.error ?? undefined,
        }
      }
    }
    setPerAgent(pa)
    if (d.report?.markdown) setReport(d.report.markdown)
  }

  const newChat = async () => {
    const c = await api.createChat({ title: 'New council session' })
    await refreshChats()
    await selectChat(c.id)
  }

  const upload = async (file: File) => {
    if (!activeId) return
    await api.uploadDocument(activeId, file)
    setDetail(await api.getChat(activeId))
  }

  const onEvent = (ev: WsEvent) => {
    switch (ev.type) {
      case 'phase_changed':
        setPhase(ev.phase)
        break
      case 'agent_joined':
        setPerAgent((p) =>
          p[ev.agent_key] ? p : { ...p, [ev.agent_key]: { status: 'pending', text: '' } },
        )
        break
      case 'agent_run_started':
        setPerAgent((p) => ({
          ...p,
          [ev.agent_key]: {
            ...(p[ev.agent_key] ?? { text: '' }),
            status: 'running',
            provider: ev.provider,
            model: ev.model,
            text: p[ev.agent_key]?.text ?? '',
          },
        }))
        break
      case 'agent_token':
        setPerAgent((p) => ({
          ...p,
          [ev.agent_key]: {
            ...(p[ev.agent_key] ?? { status: 'running' }),
            status: 'running',
            text: (p[ev.agent_key]?.text ?? '') + ev.delta,
          },
        }))
        break
      case 'agent_run_complete':
        setPerAgent((p) => ({
          ...p,
          [ev.agent_key]: { ...(p[ev.agent_key] ?? {}), status: 'completed', text: ev.text },
        }))
        break
      case 'agent_run_failed':
        setPerAgent((p) => ({
          ...p,
          [ev.agent_key]: {
            ...(p[ev.agent_key] ?? { text: '' }),
            status: 'failed',
            error: ev.error,
          },
        }))
        break
      case 'council_report':
        setReport(ev.markdown)
        setRunning(false)
        refreshChats()
        wsRef.current?.close()
        break
      case 'error':
        setError(ev.message)
        setRunning(false)
        break
    }
  }

  const submit = async (idea: string) => {
    if (!activeId) return
    setRunning(true)
    setReport(null)
    setError(null)
    const pa: Record<string, AgentState> = {}
    members.forEach((m) => (pa[m.key] = { status: 'pending', text: '' }))
    setPerAgent(pa)
    setPhase('deliberation')

    const ws = openChatSocket(activeId, onEvent)
    wsRef.current = ws
    ws.onopen = () => {
      api.submitItem(activeId, idea).catch((e) => {
        setError(String(e))
        setRunning(false)
      })
    }
    ws.onerror = () => setError('WebSocket connection failed')
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          ⚖️ quorum<span className="brand-dim">-gatherer</span>
        </div>
        <button className="primary block" onClick={newChat}>
          + New council session
        </button>
        <div className="chat-list">
          {chats.map((c) => (
            <button
              key={c.id}
              className={`chat-item ${c.id === activeId ? 'active' : ''}`}
              onClick={() => selectChat(c.id)}
            >
              <div className="chat-item-title">{c.title || 'Untitled'}</div>
              <div className="chat-item-sub">
                <span className={`dot ${c.status}`} /> {c.status}
              </div>
            </button>
          ))}
        </div>
        <button className="ghost block" onClick={() => setShowSettings(true)}>
          ⚙ Provider settings
        </button>
      </aside>

      <main className="main">
        {!activeId ? (
          <div className="empty-state">
            <h1>Product Strategy Council</h1>
            <p className="muted">
              Start a new council session. Eight expert agents deliberate your idea
              independently, then the Chairman synthesizes one decision-grade recommendation.
            </p>
            <button className="primary" onClick={newChat}>
              + New council session
            </button>
          </div>
        ) : (
          <>
            <header className="chat-header">
              <h1>{detail?.title || 'Council session'}</h1>
              {phase && <span className={`phase-tag ${phase}`}>{phase}</span>}
            </header>

            {error && <div className="error-bar">{error}</div>}

            <Composer
              initialIdea={detail?.idea ?? ''}
              documents={detail?.documents ?? []}
              running={running}
              onUpload={upload}
              onSubmit={submit}
            />

            <section className="council-grid">
              {members.map((m) => (
                <AgentPanel
                  key={m.key}
                  name={m.name}
                  state={perAgent[m.key] ?? { status: 'pending', text: '' }}
                />
              ))}
            </section>

            <ChairmanReport markdown={report} synthesizing={phase === 'synthesis' || running} />
          </>
        )}
      </main>

      {showSettings && <SettingsDialog onClose={() => setShowSettings(false)} />}
    </div>
  )
}
