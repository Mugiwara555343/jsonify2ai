import { useEffect, useState } from 'react'
import './App.css'

type Status = { ok: boolean; counts: { chunks: number; images: number; total?: number } }
type Hit = { id: string; score: number; text?: string; caption?: string; path?: string; idx?: number; kind?: string; document_id?: string }
const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8082"
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer: string; sources: Hit[] }

async function uploadFile(file: File): Promise<any> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch(`${apiBase}/upload`, { method: "POST", body: fd });
  // API proxies worker response; assume JSON
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `Upload failed (${res.status})`);
  return data; // expect {"ok":true, ...}
}

async function waitForProcessed(oldTotal: number, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const s = await fetch(`${apiBase}/status`).then(r => r.json());
    const total = s?.counts?.total ?? 0;
    if (total > oldTotal) return { ok: true, total };
    await new Promise(r => setTimeout(r, 1000));
  }
  return { ok: false };
}

function downloadJson(documentId: string, kind: string | undefined) {
  const collection = kind === 'image' ? 'images' : 'chunks'
  const url = `${apiBase}/export?document_id=${encodeURIComponent(documentId)}&collection=${collection}`
  window.open(url, '_blank')
}

function App() {
  const [s, setS] = useState<Status | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<'text' | 'pdf' | 'image' | 'audio'>('text')
  const [res, setRes] = useState<Hit[]>([])
  const [msg, setMsg] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [askQ, setAskQ] = useState('')
  const [ans, setAns] = useState<AskResp | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  const fetchStatus = async () => {
    const res = await fetch(`${apiBase}/status`)
    const j = await res.json()
    setS(j)
  }

  async function doSearch(q: string, kind: string) {
    const k = 5;
    try {
      const url = `${apiBase}/search?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&k=${k}`;
      const r = await fetch(url, { method: "GET" });
      if (r.ok) return await r.json();
      // fallback to POST body if GET not supported
      const r2 = await fetch(`${apiBase}/search`, {
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

  async function onUploadChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    const file = e.target.files[0]
    setUploadBusy(true)
    try {
      const s0 = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => ({counts:{total:0}}))
      const baseTotal = s0?.counts?.total ?? 0
      await uploadFile(file)
      const done = await waitForProcessed(baseTotal, 20000)
      showToast(done.ok ? "Processed ✓" : "Uploaded (pending…)") // non-blocking fallback
      // optional: trigger a refresh of search results here
    } catch (err:any) {
      showToast(`Upload failed: ${err?.message || err}`)
    } finally {
      setUploadBusy(false)
      e.target.value = "" // reset input
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
      <div className="mb-4 flex items-center gap-3">
        <input type="file" onChange={onUploadChange} disabled={uploadBusy} />
        {uploadBusy && <span className="text-sm opacity-70">Uploading…</span>}
        {toast && <span className="text-sm text-green-600">{toast}</span>}
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
            const r = await fetch(`${apiBase}/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: askQ, k: 6 }) })
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
                <span className="inline-block px-2 py-0.5 bg-gray-100 rounded mr-2">idx: {h.idx}</span>
              </div>
              <div className="text-xs opacity-60">
                {h.kind === "image" ? "images" : "chunks"} • idx: {h.idx}
              </div>
              <div className="mt-1">{h.caption || h.text || '(no text)'}</div>
              {h.document_id && (
                <div className="mt-1">
                  <button
                    className="text-xs underline opacity-70 hover:opacity-100"
                    onClick={() => downloadJson((h as any).document_id, h.kind)}
                  >
                    Download JSON
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>API: {apiBase}</div>
    </div>
  )
}

export default App
