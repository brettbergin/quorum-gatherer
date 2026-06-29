// REST + WebSocket client. /api and /ws are proxied to the backend by Vite (vite.config.ts).

import type {
  AgentInfo,
  ChatDetail,
  ChatOut,
  DocumentOut,
  ProviderSetting,
  ReportOut,
  SettingsOut,
  WsEvent,
} from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listAgents: () => fetch('/api/agents').then(json<AgentInfo[]>),

  listChats: () => fetch('/api/chats').then(json<ChatOut[]>),

  createChat: (body: { title?: string; idea?: string }) =>
    fetch('/api/chats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(json<ChatOut>),

  getChat: (id: string) => fetch(`/api/chats/${id}`).then(json<ChatDetail>),

  uploadDocument: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`/api/chats/${id}/documents`, { method: 'POST', body: form }).then(
      json<DocumentOut>,
    )
  },

  submitItem: (id: string, idea: string) =>
    fetch(`/api/chats/${id}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea }),
    }).then(json<{ status: string; chat_id: string }>),

  getResult: (id: string) => fetch(`/api/chats/${id}/result`).then(json<ReportOut>),

  getSettings: () => fetch('/api/settings/providers').then(json<SettingsOut>),

  // Validate the key with a real call, then save + enable on success.
  applyProvider: (body: {
    provider: string
    api_key?: string | null
    default_model?: string | null
  }) =>
    fetch('/api/settings/providers/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(json<ProviderSetting>),

  disableProvider: (provider: string) =>
    fetch('/api/settings/providers/disable', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    }).then(json<ProviderSetting>),
}

export function openChatSocket(chatId: string, onEvent: (ev: WsEvent) => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/chats/${chatId}`)
  ws.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as WsEvent)
    } catch {
      // ignore malformed frames
    }
  }
  return ws
}
