import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ProviderSetting, SettingsOut } from '../types'

type Status = 'idle' | 'applying' | 'ok' | 'error'

function errText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  const i = m.indexOf('{')
  if (i >= 0) {
    try {
      return JSON.parse(m.slice(i)).detail ?? m
    } catch {
      /* fall through */
    }
  }
  return m
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<SettingsOut | null>(null)
  const [provider, setProvider] = useState<string>('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [message, setMessage] = useState('')

  const settingFor = (p: string, d = data): ProviderSetting | undefined =>
    d?.settings.find((s) => s.provider === p)
  const specFor = (p: string, d = data) => d?.providers.find((s) => s.key === p)

  const selectProvider = (p: string, d = data) => {
    setProvider(p)
    setApiKey('')
    setModel(settingFor(p, d)?.default_model ?? '')
    setStatus('idle')
    setMessage('')
  }

  const load = (keepSelection = false) =>
    api.getSettings().then((d) => {
      setData(d)
      if (!keepSelection) {
        const first = d.settings.find((s) => s.is_enabled)?.provider ?? d.providers[0]?.key ?? ''
        selectProvider(first, d)
      }
    })

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const current = settingFor(provider)
  const spec = specFor(provider)

  const apply = async () => {
    setStatus('applying')
    setMessage('Validating key with the provider…')
    try {
      await api.applyProvider({ provider, api_key: apiKey || null, default_model: model || null })
      await load(true)
      setApiKey('')
      setStatus('ok')
      setMessage('Key validated — provider enabled.')
    } catch (e) {
      setStatus('error')
      setMessage(errText(e))
    }
  }

  const disable = async () => {
    setStatus('applying')
    setMessage('')
    try {
      await api.disableProvider(provider)
      await load(true)
      setStatus('idle')
      setMessage('Provider disabled.')
    } catch (e) {
      setStatus('error')
      setMessage(errText(e))
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>AI provider</h2>
          <button className="ghost" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="muted">
          Choose a provider, paste its API key, and Apply. The key is validated with a real
          call before it’s saved and enabled.
        </p>

        {!data ? (
          <div className="muted">Loading…</div>
        ) : (
          <div className="settings-form">
            <label className="field">
              <span>Provider</span>
              <select value={provider} onChange={(e) => selectProvider(e.target.value)}>
                {data.providers.map((p) => {
                  const s = settingFor(p.key)
                  const tag = s?.is_enabled ? ' ✓ enabled' : s?.has_key ? ' (disabled)' : ''
                  return (
                    <option key={p.key} value={p.key}>
                      {p.label}
                      {tag}
                    </option>
                  )
                })}
              </select>
            </label>

            <label className="field">
              <span>API key</span>
              <input
                type="password"
                placeholder={
                  current?.has_key ? '•••••••• stored — leave blank to reuse' : 'Paste API key'
                }
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>

            <label className="field">
              <span>Model</span>
              <input
                list="model-suggestions"
                placeholder={spec?.default_model ?? ''}
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
              <datalist id="model-suggestions">
                {spec?.suggested_models.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </label>

            <div className="settings-actions">
              <div className="settings-state">
                {current?.is_enabled ? (
                  <span className="badge completed">enabled</span>
                ) : current?.has_key ? (
                  <span className="badge">disabled</span>
                ) : (
                  <span className="badge">not configured</span>
                )}
              </div>
              <button
                className="ghost"
                disabled={status === 'applying' || !current?.has_key}
                onClick={disable}
              >
                Disable
              </button>
              <button className="primary" disabled={status === 'applying'} onClick={apply}>
                {status === 'applying' ? 'Validating…' : 'Apply'}
              </button>
            </div>

            {message && (
              <div className={`status-line ${status}`}>
                {status === 'applying' && '⏳ '}
                {status === 'ok' && '✓ '}
                {status === 'error' && '⚠ '}
                {message}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
