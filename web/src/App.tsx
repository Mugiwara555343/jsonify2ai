import { useEffect, useState } from 'react'
import './App.css'
import { uploadFile, doSearch, askQuestion, fetchStatus, fetchDocuments, downloadJson } from './api'

type Status = {
  ok: boolean;
  counts: { chunks: number; images: number; total?: number };
  // Telemetry fields (optional)
  uptime_s?: number;
  ingest_total?: number;
  ingest_failed?: number;
  watcher_triggers_total?: number;
  export_total?: number;
  ask_synth_total?: number;
}
type Hit = { id: string; score: number; text?: string; caption?: string; path?: string; idx?: number; kind?: string; document_id?: string }
type Document = { document_id: string; kinds: string[]; paths: string[]; counts: Record<string, number> }
const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8082"
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer?: string; final?: string; sources?: Hit[]; answers?: Hit[]; error?: string }


function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

function visible(): boolean {
  return typeof document !== "undefined" ? document.visibilityState === "visible" : true;
}

async function waitForProcessed(oldTotal: number, timeoutMs = 20000, intervalMs = 4000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (!visible()) { await sleep(500); continue; }
    const s = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => null);
    const total = s?.counts?.total ?? 0;
    if (total > oldTotal) return { ok: true, total };
    await sleep(intervalMs);
  }
  return { ok: false };
}


function downloadZip(documentId: string, kind: string | undefined) {
  const collection = kind === 'image' ? 'images' : 'chunks'
  const url = `${apiBase}/export/archive?document_id=${encodeURIComponent(documentId)}&collection=${collection}`
  window.open(url, '_blank')
}

function collectionForDoc(d: Document) {
  return (d.kinds || []).includes("image") ? "jsonify2ai_images_768" : "jsonify2ai_chunks_768";
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    // Toast will be shown by caller
  }).catch(() => {
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
  });
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
  const [lastDoc, setLastDoc] = useState<{id:string, kind:string} | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [recentDocs, setRecentDocs] = useState<Hit[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [askLoading, setAskLoading] = useState(false)

  function showToast(msg: string, isError = false) {
    setToast(msg);
    setTimeout(() => setToast(null), isError ? 5000 : 3000);
  }

  useEffect(() => {
    loadStatus()
    loadDocuments()
    loadRecentDocuments()
  }, [])

  const loadStatus = async () => {
    const j = await fetchStatus()
    setS(j)
  }

  const loadDocuments = async () => {
    try {
      const j = await fetchDocuments()
      setDocs(j)
    } catch (err) {
      console.error('Failed to fetch documents:', err)
    }
  }

  const loadRecentDocuments = async () => {
    try {
      // Use search with empty query to get recent documents
      const resp = await doSearch('', 'text')
      if (resp.ok && resp.results) {
        // Group by document_id and take the first hit from each document
        const seen = new Set<string>()
        const recent = resp.results.filter((hit: Hit) => {
          if (!hit.document_id || seen.has(hit.document_id)) return false
          seen.add(hit.document_id)
          return true
        }).slice(0, 5) // Limit to 5
        setRecentDocs(recent)
      }
    } catch (err) {
      console.error('Failed to fetch recent documents:', err)
    }
  }

  async function performSearch(q: string, kind: string) {
    return await doSearch(q, kind);
  }

  const handleSearch = async () => {
    if (!q.trim()) {
      showToast("Please enter a search query", true);
      return;
    }

    setSearchLoading(true);
    try {
      const resp = await performSearch(q, kind);
      if (resp.ok === false) {
        if (resp.error === "rate_limited") {
          showToast("Rate limited — try again in a few seconds.", true);
        } else {
          showToast(`Search failed: ${resp.error || 'Unknown error'}`, true);
        }
        setRes([]);
      } else {
        setRes(resp.results ?? []);
        if ((resp.results ?? []).length === 0) {
          showToast("No results found. Try different keywords or check if documents are processed.");
        }
      }
    } catch (err: any) {
      showToast(`Search error: ${err?.message || err}`, true);
      setRes([]);
    } finally {
      setSearchLoading(false);
    }
  }

  async function onUploadChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    const file = e.target.files[0]
    setUploadBusy(true)
    try {
      const s0 = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => ({counts:{total:0}}))
      const baseTotal = s0?.counts?.total ?? 0

      const fd = new FormData();
      fd.append("file", file, file.name);
      const res = await fetch(`${apiBase}/upload`, { method: "POST", body: fd });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        if (res.status === 429 && errorData?.error === "rate_limited") {
          showToast("Rate limited — try again in a few seconds.", true);
          return;
        }
        throw new Error(errorData?.error || errorData?.detail || `Upload failed (${res.status})`);
      }

      const data = await res.json();

      // if API returns worker JSON, we'll have document_id and collection
      const docId = data?.document_id as string | undefined;
      const coll  = (data?.collection || "") as string;
      const kind  = coll.includes("images") ? "image" : "text"; // images vs chunks

      if (docId) setLastDoc({ id: docId, kind });

      const done = await waitForProcessed(baseTotal, 20000, 4000);
      showToast(done.ok ? "Processed ✓" : "Uploaded (pending…)");
    } catch (err:any) {
      showToast(`Upload failed: ${err?.message || err}`, true)
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

      {/* Telemetry Chips */}
      {s && (s.uptime_s !== undefined || s.ingest_total !== undefined || s.ingest_failed !== undefined || s.watcher_triggers_total !== undefined || s.export_total !== undefined || s.ask_synth_total !== undefined) && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 14, opacity: .6, marginBottom: 8 }}>Telemetry</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {s.uptime_s !== undefined && (
              <div style={{ fontSize: 12, background: '#f0f9ff', color: '#0369a1', padding: '4px 8px', borderRadius: 12, border: '1px solid #bae6fd' }}>
                Uptime: {Math.floor(s.uptime_s / 3600)}h {Math.floor((s.uptime_s % 3600) / 60)}m
              </div>
            )}
            {s.ingest_total !== undefined && (
              <div style={{ fontSize: 12, background: '#f0fdf4', color: '#166534', padding: '4px 8px', borderRadius: 12, border: '1px solid #bbf7d0' }}>
                Ingested: {s.ingest_total}
              </div>
            )}
            {s.ingest_failed !== undefined && s.ingest_failed > 0 && (
              <div style={{ fontSize: 12, background: '#fef2f2', color: '#dc2626', padding: '4px 8px', borderRadius: 12, border: '1px solid #fecaca' }}>
                Failed: {s.ingest_failed}
              </div>
            )}
            {s.watcher_triggers_total !== undefined && (
              <div style={{ fontSize: 12, background: '#fefce8', color: '#a16207', padding: '4px 8px', borderRadius: 12, border: '1px solid #fde68a' }}>
                Watcher: {s.watcher_triggers_total}
              </div>
            )}
            {s.export_total !== undefined && (
              <div style={{ fontSize: 12, background: '#f3e8ff', color: '#7c3aed', padding: '4px 8px', borderRadius: 12, border: '1px solid #d8b4fe' }}>
                Exported: {s.export_total}
              </div>
            )}
            {s.ask_synth_total !== undefined && (
              <div style={{ fontSize: 12, background: '#fef3c7', color: '#92400e', padding: '4px 8px', borderRadius: 12, border: '1px solid #fde68a' }}>
                Ask Synth: {s.ask_synth_total}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recent Documents Panel */}
      {recentDocs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 14, opacity: .6, marginBottom: 8 }}>Recent Documents</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {recentDocs.map((doc, i) => (
              <div key={i} style={{ padding: 12, border: '1px solid #eee', borderRadius: 8, background: '#fafafa' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <code style={{ fontSize: 11, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
                    {doc.document_id?.substring(0, 8)}...
                  </code>
                  {doc.path && (
                    <span style={{ fontSize: 12, opacity: .7, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.path.split('/').pop()}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 11, opacity: .6 }}>
                    {doc.kind === 'image' ? 'images' : 'chunks'}
                  </span>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => downloadJson(doc.document_id!, doc.kind === 'image' ? 'images' : 'chunks')}
                      style={{ fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }}
                    >
                      Export JSON
                    </button>
                    <button
                      onClick={() => downloadZip(doc.document_id!, doc.kind)}
                      style={{ fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }}
                    >
                      Export ZIP
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="mb-4 flex items-center gap-3">
        <input type="file" onChange={onUploadChange} disabled={uploadBusy} />
        {uploadBusy && <span className="text-sm opacity-70">Uploading…</span>}
        {toast && (
          <span
            className="text-sm"
            style={{
              color: toast.includes('failed') || toast.includes('error') || toast.includes('Error') ? '#dc2626' : '#16a34a'
            }}
          >
            {toast}
          </span>
        )}
        {lastDoc && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="text-xs underline opacity-70 hover:opacity-100"
              onClick={() => downloadJson(lastDoc.id, lastDoc.kind === 'image' ? 'images' : 'chunks')}
            >
              Download JSON
            </button>
            <button
              className="text-xs underline opacity-70 hover:opacity-100"
              onClick={() => downloadZip(lastDoc.id, lastDoc.kind)}
            >
              Download ZIP
            </button>
          </div>
        )}
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
          <button
            onClick={async () => {
              if (!askQ.trim()) {
                showToast("Please enter a question", true);
                return;
              }

              setAskLoading(true);
              try {
                const j: AskResp = await askQuestion(askQ, 6);
                if (j.ok === false) {
                  if (j.error === "rate_limited") {
                    showToast("Rate limited — try again in a few seconds.", true);
                  } else {
                    showToast(`Ask failed: ${j.error || 'Unknown error'}`, true);
                  }
                  setAns(null);
                } else {
                  setAns(j);
                }
              } catch (err: any) {
                // Check if it's a 429 rate limit error
                if (err?.status === 429 || err?.errorData?.error === "rate_limited") {
                  showToast("Rate limited — try again in a few seconds.", true);
                } else {
                  showToast(`Ask error: ${err?.message || err}`, true);
                }
                setAns(null);
              } finally {
                setAskLoading(false);
              }
            }}
            disabled={askLoading}
            style={{
              padding: '12px 16px',
              borderRadius: 8,
              border: '1px solid #ddd',
              opacity: askLoading ? 0.6 : 1,
              cursor: askLoading ? 'not-allowed' : 'pointer'
            }}
          >
            {askLoading ? 'Asking...' : 'Ask'}
          </button>
        </div>
        {ans && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ fontSize: 12, opacity: .6, marginBottom: 6 }}>mode: {ans.mode}{ans.model ? ` (${ans.model})` : ''}</div>
            {ans.final && ans.final.trim() && (
              <div style={{ marginBottom: 12, padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fafafa' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <div style={{ fontWeight: 600 }}>Answer</div>
                  <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 999, background: '#eef2ff', color: '#3730a3' }}>local (ollama)</span>
                </div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>{ans.final}</div>
              </div>
            )}
            {(ans.answer || ans.sources || ans.answers) && (
              <>
                {ans.answer && ans.answer.trim() && (
                  <div style={{ whiteSpace: 'pre-wrap', marginBottom: ans.sources?.length || ans.answers?.length ? 10 : 0 }}>{ans.answer}</div>
                )}
                {(ans.sources && ans.sources.length > 0) || (ans.answers && ans.answers.length > 0) ? (
                  <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {(ans.sources || ans.answers || []).map((h, i) => (
                      <span key={i} style={{ fontSize: 12, opacity: .75, border: '1px solid #eee', padding: '2px 6px', borderRadius: 999 }}>{h.path?.split('/').pop() || h.id}</span>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: '#666', fontSize: 13, marginTop: 8 }}>No matching snippets.</div>
                )}
              </>
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
          disabled={searchLoading}
          style={{
            padding: '12px 16px',
            borderRadius: 8,
            border: '1px solid #ddd',
            opacity: searchLoading ? 0.6 : 1,
            cursor: searchLoading ? 'not-allowed' : 'pointer'
          }}
        >
          {searchLoading ? 'Searching...' : 'Search'}
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
                    onClick={() => downloadJson((h as any).document_id, h.kind === 'image' ? 'images' : 'chunks')}
                  >
                    Download JSON
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Documents</h2>
        <div style={{ marginBottom: 12 }}>
          <button
            onClick={fetchDocuments}
            style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #ddd', fontSize: 14 }}
          >
            Refresh documents
          </button>
        </div>
        {docs.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            {docs.map((doc, i) => (
              <div key={i} style={{ padding: 12, border: '1px solid #eee', borderRadius: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <code style={{ fontSize: 12, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
                    {doc.document_id}
                  </code>
                  <button
                    onClick={() => {
                      copyToClipboard(doc.document_id);
                      showToast('Document ID copied');
                    }}
                    style={{ fontSize: 12, color: '#666', textDecoration: 'underline' }}
                  >
                    Copy ID
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
                  {doc.kinds.map((kind, j) => (
                    <span key={j} style={{ fontSize: 12, background: '#e3f2fd', color: '#1976d2', padding: '2px 6px', borderRadius: 12 }}>
                      {kind}
                    </span>
                  ))}
                </div>
                <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                  {doc.paths[0] && <div>Path: {doc.paths[0]}</div>}
                  <div>Counts: {Object.entries(doc.counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    onClick={() => {
                      const collection = collectionForDoc(doc);
                      const url = `${apiBase}/export?document_id=${encodeURIComponent(doc.document_id)}&collection=${collection}`;
                      window.open(url, '_blank');
                    }}
                    style={{ fontSize: 12, color: '#1976d2', textDecoration: 'underline' }}
                  >
                    Export JSON
                  </button>
                  <button
                    onClick={() => {
                      const collection = collectionForDoc(doc);
                      const url = `${apiBase}/export/archive?document_id=${encodeURIComponent(doc.document_id)}&collection=${collection}`;
                      window.open(url, '_blank');
                    }}
                    style={{ fontSize: 12, color: '#1976d2', textDecoration: 'underline' }}
                  >
                    Export ZIP
                  </button>
                  <button
                    onClick={() => {
                      const collection = collectionForDoc(doc);
                      const cmd = `Invoke-WebRequest "http://localhost:8082/export?document_id=${doc.document_id}&collection=${collection}" -OutFile "export_${doc.document_id}.jsonl"`;
                      copyToClipboard(cmd);
                      showToast('Export command copied');
                    }}
                    style={{ fontSize: 12, color: '#1976d2', textDecoration: 'underline' }}
                  >
                    Copy export cmd
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {docs.length === 0 && (
          <div style={{ color: '#666', fontSize: 14 }}>No documents found. Upload some files to see them here.</div>
        )}
      </div>
      <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>API: {apiBase}</div>
    </div>
  )
}

export default App
