import { useState } from 'react'
import type { DocumentOut } from '../types'

interface Props {
  initialIdea: string
  documents: DocumentOut[]
  running: boolean
  onUpload: (file: File) => void
  onSubmit: (idea: string) => void
}

export function Composer({ initialIdea, documents, running, onUpload, onSubmit }: Props) {
  const [idea, setIdea] = useState(initialIdea)

  return (
    <div className="composer">
      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="Describe the product strategy idea to put before the council…"
        rows={3}
      />
      <div className="composer-row">
        <label className="file-btn">
          + Context doc
          <input
            type="file"
            hidden
            onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
          />
        </label>
        <div className="docs">
          {documents.map((d) => (
            <span key={d.id} className="chip" title={d.content_type ?? ''}>
              📎 {d.filename}
            </span>
          ))}
        </div>
        <button className="primary" disabled={running || !idea.trim()} onClick={() => onSubmit(idea)}>
          {running ? 'Council in session…' : 'Convene council'}
        </button>
      </div>
    </div>
  )
}
