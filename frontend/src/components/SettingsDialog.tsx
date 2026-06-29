import { useEffect, useState } from 'react'
import { api } from '../api'
import type { SettingsOut } from '../types'

interface Draft {
  api_key: string
  default_model: string
  is_enabled: boolean
}

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<SettingsOut | null>(null)
  const [draft, setDraft] = useState<Record<string, Draft>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const load = () =>
    api.getSettings().then((d) => {
      setData(d)
      const next: Record<string, Draft> = {}
      for (const spec of d.providers) {
        const existing = d.settings.find((s) => s.provider === spec.key)
        next[spec.key] = {
          api_key: '',
          default_model: existing?.default_model ?? '',
          is_enabled: existing?.is_enabled ?? true,
        }
      }
      setDraft(next)
    })

  useEffect(() => {
    load()
  }, [])

  const save = async (provider: string) => {
    setSaving(provider)
    try {
      const d = draft[provider]
      await api.putProvider({
        provider,
        api_key: d.api_key ? d.api_key : null,
        default_model: d.default_model || null,
        is_enabled: d.is_enabled,
      })
      await load()
    } finally {
      setSaving(null)
    }
  }

  const patch = (p: string, patch: Partial<Draft>) =>
    setDraft((prev) => ({ ...prev, [p]: { ...prev[p], ...patch } }))

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>AI provider settings</h2>
          <button className="ghost" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="muted">
          Configure an API key for any provider. Agents use their own default provider when a
          key is available, otherwise the first configured provider.
        </p>
        {!data && <div className="muted">Loading…</div>}
        {data?.providers.map((spec) => {
          const existing = data.settings.find((s) => s.provider === spec.key)
          const d = draft[spec.key]
          if (!d) return null
          return (
            <div key={spec.key} className="provider-row">
              <div className="provider-top">
                <strong>{spec.label}</strong>
                {existing?.has_key && <span className="badge completed">key set</span>}
              </div>
              <div className="provider-fields">
                <input
                  type="password"
                  placeholder={existing?.has_key ? '•••••••• (leave blank to keep)' : 'API key'}
                  value={d.api_key}
                  onChange={(e) => patch(spec.key, { api_key: e.target.value })}
                />
                <input
                  list={`models-${spec.key}`}
                  placeholder={spec.default_model}
                  value={d.default_model}
                  onChange={(e) => patch(spec.key, { default_model: e.target.value })}
                />
                <datalist id={`models-${spec.key}`}>
                  {spec.suggested_models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <label className="enabled">
                  <input
                    type="checkbox"
                    checked={d.is_enabled}
                    onChange={(e) => patch(spec.key, { is_enabled: e.target.checked })}
                  />
                  enabled
                </label>
                <button className="primary" disabled={saving === spec.key} onClick={() => save(spec.key)}>
                  {saving === spec.key ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
