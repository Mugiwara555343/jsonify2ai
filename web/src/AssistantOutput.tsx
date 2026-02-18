import { useState } from 'react'

type Status = {
  ok: boolean
  counts: { chunks: number; images: number; total?: number }
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number }
}

type Hit = {
  id: string
  score: number
  text?: string
  caption?: string
  path?: string
  idx?: number
  kind?: string
  document_id?: string
}

type AskResp = {
  ok: boolean
  mode: 'search' | 'llm' | 'retrieve' | 'synthesize'
  model?: string
  answer?: string
  final?: string
  sources?: Hit[]
  answers?: Hit[]
  error?: string
  stats?: { k: number; returned: number }
  synth_skipped_reason?: string
  top_score?: number
  min_synth_score?: number
}

type AssistantOutputProps = {
  result: AskResp | null
  status: Status | null
  loading: boolean
  error: string | null
  actionName?: string
  showToast?: (msg: string, isError?: boolean) => void
  scope?: 'doc' | 'all'
  activeDocFilename?: string
  onUseDoc?: (documentId: string, llmReachable: boolean) => void
  documents?: Array<{ document_id: string; paths: string[] }>
}

function copyToClipboard(text: string) {
  navigator.clipboard
    .writeText(text)
    .catch(() => {
      const textArea = document.createElement('textarea')
      textArea.value = text
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    })
}

function truncateId(id: string, maxLength = 12): string {
  if (id.length <= maxLength) return id
  return `${id.substring(0, maxLength)}...`
}

function truncatePath(path: string, maxLength = 50): string {
  if (path.length <= maxLength) return path
  return `...${path.substring(path.length - maxLength)}`
}

export default function AssistantOutput({
  result,
  status,
  loading,
  error,
  actionName,
  showToast,
  scope,
  activeDocFilename,
  onUseDoc,
  documents,
}: AssistantOutputProps) {
  const [showLibrarianView, setShowLibrarianView] = useState(false)

  if (!loading && !error && !result) {
    return (
      <div className="mt-3 rounded-lg border border-dashed border-slate-800 bg-slate-900/40 p-4 text-center text-slate-500">
        <div className="mb-1 text-sm font-medium text-slate-300">Ready to help</div>
        <div className="text-xs">Ask a question to get started.</div>
      </div>
    )
  }

  if (loading) {
    const loadingText = status?.llm?.reachable === true ? 'Thinking...' : 'Searching your data...'
    return <div className="mt-3 p-3 text-sm text-slate-400">{loadingText}</div>
  }

  if (error) {
    return (
      <div className="mt-3 rounded-lg border border-red-900/70 bg-red-950/30 p-3 text-sm text-red-300">
        {error}
      </div>
    )
  }

  if (!result) return null

  const title = actionName || 'Assistant Output'
  const mainText = result.final?.trim() || result.answer?.trim() || ''
  const sources = result.sources || result.answers || []
  const hasLLM = status?.llm?.provider === 'ollama' && status?.llm?.reachable === true
  const showLowConfidence = result.synth_skipped_reason === 'low_confidence'
  const showNoSources = result.synth_skipped_reason === 'no_sources'

  const buildMarkdown = (): string => {
    let md = `# ${title}\n\n`
    if (mainText) md += `${mainText}\n\n`
    if (sources.length > 0) {
      md += '## Citations\n\n'
      sources.forEach((source, i) => {
        const filename = source.path ? source.path.split('/').pop() || source.path : `Source ${i + 1}`
        const snippet = source.text || source.caption || ''
        const docId = source.document_id ? truncateId(source.document_id) : null
        md += `### ${filename}\n`
        if (docId) md += `Document ID: ${docId}\n`
        if (source.score !== undefined) md += `Score: ${source.score.toFixed(2)}\n`
        if (snippet) md += `\n${snippet}\n\n`
      })
    }
    return md
  }

  const handleCopy = () => {
    copyToClipboard(buildMarkdown())
    showToast?.('Output copied to clipboard')
  }

  const groupedDocs = (() => {
    if (scope !== 'all' || sources.length === 0) return []
    const grouped = new Map<string, { sources: Hit[]; bestScore: number; filename: string }>()
    sources.forEach((source) => {
      const docId = source.document_id || 'unknown'
      const filename = source.path ? source.path.split('/').pop() || source.path : 'Unknown'
      const score = source.score || 0
      if (!grouped.has(docId)) grouped.set(docId, { sources: [], bestScore: score, filename })
      const group = grouped.get(docId)!
      group.sources.push(source)
      group.bestScore = Math.max(group.bestScore, score)
    })
    return Array.from(grouped.entries())
      .map(([docId, data]) => ({ docId, ...data }))
      .sort((a, b) => b.bestScore - a.bestScore)
      .slice(0, 5)
  })()

  return (
    <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="text-sm font-semibold text-slate-300">{title}</div>
        {hasLLM && <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-400">local (ollama)</span>}
        {!hasLLM && sources.length > 0 && !showNoSources && (
          <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-500">Top matches below</span>
        )}
        {showLowConfidence && (
          <span className="rounded-full border border-amber-800 bg-amber-950/30 px-2 py-0.5 text-[11px] text-amber-300">
            Low confidence, showing retrieved matches
          </span>
        )}
        {showNoSources && (
          <span className="rounded-full border border-amber-800 bg-amber-950/30 px-2 py-0.5 text-[11px] text-amber-300">
            No matching sources found
          </span>
        )}
        {(mainText || sources.length > 0) && (
          <button
            onClick={handleCopy}
            className="ml-auto rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 hover:border-slate-500"
          >
            Copy output
          </button>
        )}
      </div>

      {showLowConfidence && result.top_score !== undefined && result.min_synth_score !== undefined && (
        <div className="mb-3 text-xs text-amber-300">
          Top score: {result.top_score.toFixed(2)} (threshold {result.min_synth_score.toFixed(2)})
        </div>
      )}

      {scope && (
        <div className="mb-4 text-xs text-slate-500">
          {scope === 'doc' && activeDocFilename
            ? `Using document: ${activeDocFilename}`
            : scope === 'doc'
              ? 'Using document: (no active document)'
              : 'Using all indexed documents'}
        </div>
      )}

      {mainText && (
        <div className="mb-4 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{mainText}</div>
        </div>
      )}

      {groupedDocs.length > 0 && (
        <div className="mb-4">
          <div className="mb-2 text-xs italic text-slate-500">Select a document to narrow follow-up actions.</div>
          <div className="space-y-2">
            {groupedDocs.map((group) => {
              const docExists = documents?.some((d) => d.document_id === group.docId)
              const llmReachable = status?.llm?.reachable === true
              return (
                <div key={group.docId} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                  <div className="min-w-52 flex-1">
                    <div className="mb-1 text-sm text-slate-300">{group.filename}</div>
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span>
                        {group.sources.length} {group.sources.length === 1 ? 'source' : 'sources'}
                      </span>
                      <span>best: {group.bestScore.toFixed(2)}</span>
                    </div>
                  </div>
                  {docExists && onUseDoc && (
                    <button
                      onClick={() => {
                        onUseDoc(group.docId, llmReachable)
                        showToast?.('Switched to document mode')
                      }}
                      className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 hover:border-slate-500"
                    >
                      Use this doc
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/40">
          <button
            type="button"
            onClick={() => setShowLibrarianView((prev) => !prev)}
            className="flex w-full items-center justify-between px-3 py-2 text-left"
          >
            <span className="text-sm font-medium text-slate-300">Librarian View</span>
            <span className="text-xs text-slate-500">
              {showLibrarianView ? 'Hide' : 'Show'} {sources.length} source{sources.length === 1 ? '' : 's'}
            </span>
          </button>

          {showLibrarianView && (
            <div className="space-y-2 border-t border-slate-800 p-3">
              {sources.map((source, i) => {
                const filename = source.path ? source.path.split('/').pop() || source.path : source.id || `Source ${i + 1}`
                const docId = source.document_id ? truncateId(source.document_id) : null
                const snippet = source.text || source.caption || '(empty snippet)'
                const score = source.score !== undefined ? source.score : null
                const path = source.path ? truncatePath(source.path) : null
                return (
                  <article key={`${source.id}-${i}`} className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
                    <div className="mb-1 text-sm text-slate-300">{filename}</div>
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      {path && <span className="font-mono">{path}</span>}
                      {docId && <code className="rounded bg-slate-900 px-1.5 py-0.5 text-slate-500">{docId}</code>}
                      {score !== null && <span>score: {score.toFixed(2)}</span>}
                    </div>
                    <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-400">{snippet}</div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      )}

      {sources.length === 0 && (
        <div className="rounded-md border border-slate-800 bg-slate-900/30 p-3 text-sm italic text-slate-500">
          No matching snippets yet. Try a different query or upload more files.
        </div>
      )}
    </div>
  )
}
