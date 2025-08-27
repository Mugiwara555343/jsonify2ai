import { useEffect, useState } from 'react'
import './App.css'

type Status = { ok: boolean; counts: { chunks: number; images: number } }
type Hit = { id: string; score: number; text?: string; caption?: string; path?: string }
const WORKER = import.meta.env.VITE_WORKER_URL || 'http://localhost:8090'
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer: string; sources: Hit[] }

function App() {
  const [s, setS] = useState<Status | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<'text' | 'images'>('text')
  const [res, setRes] = useState<Hit[]>([])
  const [msg, setMsg] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [askQ, setAskQ] = useState('')
  const [ans, setAns] = useState<AskResp | null>(null)

  useEffect(() => {
    fetch(`${WORKER}/status`)
      .then(r => r.json())
      .then(setS)
      .catch(() => setS(null))
  }, [])

  const doSearch = async () => {
    const r = await fetch(`${WORKER}/search?q=${encodeURIComponent(q)}&kind=${kind}&k=8`)
    const j = await r.json()
    setRes(j.results || [])
  }

  const doUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    setBusy(true)
    setMsg('')
    try {
      const r = await fetch(`${WORKER}/upload`, { method: 'POST', body: fd })
      const j = await r.json()
      setMsg(j.ok ? 'Uploaded' : 'Failed')
      // refresh status after a moment (watcher/ingest may update counts)
      setTimeout(() => {
        fetch(`${WORKER}/status`)
          .then(r => r.json())
          .then(setS)
          .catch(() => {})
      }, 1200)
    } catch {
      setMsg('Failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ fontFamily: 'ui-sans-serif', padding: 24, maxWidth: 720, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, marginBottom: 12 }}>jsonify2ai — Status</h1>
      {!s && <div>Loading…</div>}
      {s && (
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }}>
          <div style={{ padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }}>
            <div style={{ opacity: .6, marginBottom: 6 }}>Text Chunks</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{s.counts.chunks}</div>
          </div>
          <div style={{ padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }}>
            <div style={{ opacity: .6, marginBottom: 6 }}>Images</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{s.counts.images}</div>
          </div>
        </div>
      )}
      <div style={{ marginTop: 24 }}>
        <div style={{ marginBottom: 8, opacity: .7 }}>Upload to drop‑zone</div>
        <input type="file" onChange={doUpload} disabled={busy} />
        {msg && <div style={{ marginTop: 6, fontSize: 12, opacity: .8 }}>{msg}</div>}
      </div>
      <div style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Ask</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={askQ}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAskQ(e.target.value)}
            placeholder="ask your data…"
            style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' }}
          />
          <button onClick={async () => {
            const r = await fetch(`${WORKER}/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: askQ, k: 6 }) })
            const j: AskResp = await r.json()
            setAns(j)
          }} style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }}>Ask</button>
        </div>
        {ans && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ fontSize: 12, opacity: .6, marginBottom: 6 }}>mode: {ans.mode}{ans.model ? ` (${ans.model})` : ''}</div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{ans.answer}</div>
            {ans.sources?.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {ans.sources.map((h, i) => (<span key={i} style={{ fontSize: 12, opacity: .75, border: '1px solid #eee', padding: '2px 6px', borderRadius: 999 }}>{h.path?.split('/').pop() || h.id}</span>))}
              </div>
            )}
          </div>
        )}
      </div>
      <div style={{ marginTop: 24, display: 'flex', gap: 8 }}>
        <input
          value={q}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setQ(e.target.value)}
          placeholder="search…"
          style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' }}
        />
        <select
          value={kind}
          onChange={e => setKind(e.target.value as any)}
          style={{ padding: 12, borderRadius: 8, border: '1px solid #ddd' }}
        >
          <option value="text">text</option>
          <option value="images">images</option>
        </select>
        <button
          onClick={doSearch}
          style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }}
        >
          Search
        </button>
      </div>
      {res.length > 0 && (
        <div style={{ marginTop: 16, display: 'grid', gap: 8 }}>
          {res.map((h, i) => (
            <div key={i} style={{ padding: 12, border: '1px solid #eee', borderRadius: 10 }}>
              <div style={{ fontSize: 12, opacity: .6 }}>score {(h.score || 0).toFixed(3)}</div>
              <div style={{ marginTop: 4 }}>{h.caption || h.text || '(no text)'}</div>
              {h.path && <div style={{ fontSize: 12, opacity: .6, marginTop: 4 }}>{h.path}</div>}
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>Worker: {WORKER}</div>
    </div>
  )
}

export default App
