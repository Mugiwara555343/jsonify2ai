import { useEffect, useState } from 'react'
import './App.css'

type Status = { ok: boolean; counts: { chunks: number; images: number } }
type Hit = { id: string; score: number; text?: string; caption?: string; path?: string; idx?: number }
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8082"
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer: string; sources: Hit[] }

function App() {
  const [s, setS] = useState<Status | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<'text' | 'pdf' | 'image' | 'audio'>('text')
  const [res, setRes] = useState<Hit[]>([])
  const [msg, setMsg] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [askQ, setAskQ] = useState('')
  const [ans, setAns] = useState<AskResp | null>(null)
  const [uploadBusy, setUploadBusy] = useState<boolean>(false)
  const [lastCounts, setLastCounts] = useState<{total:number, byKind:Record<string,number>} | null>(null)

  useEffect(() => {
    fetchStatus()
  }, [])

  const fetchStatus = async () => {
    const res = await fetch(`${API_BASE}/status`)
    const j = await res.json()
    setS(j)
    // cache counts for later comparison
    try {
      const byKind = j?.counts_by_kind ?? j?.counts ?? {}
      const total = Object.values(byKind).reduce((a:any,b:any)=>a+(typeof b==='number'?b:0),0) as number
      setLastCounts({ total, byKind })
    } catch {}
  }

  async function doSearch(q: string, kind: string) {
    const k = 5;
    try {
      const url = `${API_BASE}/search?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&k=${k}`;
      const r = await fetch(url, { method: "GET" });
      if (r.ok) return await r.json();
      // fallback to POST body if GET not supported
      const r2 = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q, kind, k }),
      });
      return await r2.json();
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  const handleSearch = async () => {
    const resp = await doSearch(q, kind);
    setRes(resp.results ?? []);
  }

  const doUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    const before = lastCounts
    setUploadBusy(true)
    setMsg('')
    try {
      const r = await fetch(`${API_BASE}/upload`, { method: 'POST', body: fd })
      // swallow worker JSON; we rely on status polling
      try { await r.json() } catch {}
      // poll status for ~30s or until counts increase
      const started = Date.now()
      const maxMs = 30000
      let seenIncrease = false
      while (Date.now() - started < maxMs) {
        await new Promise(r => setTimeout(r, 3000))
        const sres = await fetch(`${API_BASE}/status`)
        const sj = await sres.json()
        setS(sj)
        const byKind = sj?.counts_by_kind ?? sj?.counts ?? {}
        const total = Object.values(byKind).reduce((a:any,b:any)=>a+(typeof b==='number'?b:0),0) as number
        if (before && total > before.total) { seenIncrease = true; break; }
      }
      // final refresh
      await fetchStatus()
      setMsg(seenIncrease ? 'Uploaded & processed' : 'Uploaded (processing...)')
    } catch {
      setMsg('Failed')
    } finally {
      setUploadBusy(false)
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
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <input type="file" onChange={doUpload} disabled={busy} />
          {uploadBusy && <span>ingesting…</span>}
        </div>
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
            const r = await fetch(`${API_BASE}/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: askQ, k: 6 }) })
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
          <option value="pdf">pdf</option>
          <option value="image">image</option>
          <option value="audio">audio</option>
        </select>
        <button
          onClick={handleSearch}
          style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }}
        >
          Search
        </button>
      </div>
      {res.length > 0 && (
        <div style={{ marginTop: 16, display: 'grid', gap: 8 }}>
          {res.map((h, i) => (
            <div key={i} className="mb-2 p-2 rounded border">
              <div className="text-sm opacity-70">score: {h.score?.toFixed?.(3) ?? "-"}</div>
              <div className="text-xs">
                <span className="inline-block px-2 py-0.5 bg-gray-100 rounded mr-2">{h.path}</span>
                <span className="inline-block px-2 py-0.5 bg-gray-100 rounded">idx: {h.idx}</span>
              </div>
              <div className="mt-1">{h.caption || h.text || '(no text)'}</div>
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>API: {API_BASE}</div>
    </div>
  )
}

export default App
