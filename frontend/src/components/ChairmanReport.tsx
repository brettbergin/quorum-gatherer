import ReactMarkdown from 'react-markdown'

export function ChairmanReport({
  markdown,
  synthesizing,
}: {
  markdown: string | null
  synthesizing: boolean
}) {
  return (
    <div className="report-card">
      <div className="report-head">
        <span className="chair-badge">⚖️ The Chairman</span>
        {synthesizing && !markdown && <span className="badge running">synthesizing…</span>}
      </div>
      {markdown ? (
        <div className="report-body">
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </div>
      ) : (
        <div className="muted report-empty">
          {synthesizing
            ? 'The Chairman is weighing the council and drafting the final recommendation…'
            : 'The final recommendation will appear here once the council has deliberated.'}
        </div>
      )}
    </div>
  )
}
