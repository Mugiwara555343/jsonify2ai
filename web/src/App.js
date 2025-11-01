import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import './App.css';
import { doSearch, askQuestion, fetchStatus, fetchDocuments, downloadJson } from './api';
const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8082";
function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}
function visible() {
    return typeof document !== "undefined" ? document.visibilityState === "visible" : true;
}
async function waitForProcessed(oldTotal, timeoutMs = 20000, intervalMs = 4000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
        if (!visible()) {
            await sleep(500);
            continue;
        }
        const s = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => null);
        const total = s?.counts?.total ?? 0;
        if (total > oldTotal)
            return { ok: true, total };
        await sleep(intervalMs);
    }
    return { ok: false };
}
function downloadZip(documentId, kind) {
    const collection = kind === 'image' ? 'images' : 'chunks';
    const url = `${apiBase}/export/archive?document_id=${encodeURIComponent(documentId)}&collection=${collection}`;
    window.open(url, '_blank');
}
function collectionForDoc(d) {
    return (d.kinds || []).includes("image") ? "jsonify2ai_images_768" : "jsonify2ai_chunks_768";
}
function copyToClipboard(text) {
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
    const [s, setS] = useState(null);
    const [q, setQ] = useState('');
    const [kind, setKind] = useState('text');
    const [res, setRes] = useState([]);
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);
    const [askQ, setAskQ] = useState('');
    const [ans, setAns] = useState(null);
    const [uploadBusy, setUploadBusy] = useState(false);
    const [toast, setToast] = useState(null);
    const [lastDoc, setLastDoc] = useState(null);
    const [docs, setDocs] = useState([]);
    const [recentDocs, setRecentDocs] = useState([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [askLoading, setAskLoading] = useState(false);
    function showToast(msg, isError = false) {
        setToast(msg);
        setTimeout(() => setToast(null), isError ? 5000 : 3000);
    }
    useEffect(() => {
        loadStatus();
        loadDocuments();
        loadRecentDocuments();
    }, []);
    const loadStatus = async () => {
        const j = await fetchStatus();
        setS(j);
    };
    const loadDocuments = async () => {
        try {
            const j = await fetchDocuments();
            setDocs(j);
        }
        catch (err) {
            console.error('Failed to fetch documents:', err);
        }
    };
    const loadRecentDocuments = async () => {
        try {
            // Use search with empty query to get recent documents
            const resp = await doSearch('', 'text');
            if (resp.ok && resp.results) {
                // Group by document_id and take the first hit from each document
                const seen = new Set();
                const recent = resp.results.filter((hit) => {
                    if (!hit.document_id || seen.has(hit.document_id))
                        return false;
                    seen.add(hit.document_id);
                    return true;
                }).slice(0, 5); // Limit to 5
                setRecentDocs(recent);
            }
        }
        catch (err) {
            console.error('Failed to fetch recent documents:', err);
        }
    };
    async function performSearch(q, kind) {
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
                showToast(`Search failed: ${resp.error || 'Unknown error'}`, true);
                setRes([]);
            }
            else {
                setRes(resp.results ?? []);
                if ((resp.results ?? []).length === 0) {
                    showToast("No results found. Try different keywords or check if documents are processed.");
                }
            }
        }
        catch (err) {
            showToast(`Search error: ${err?.message || err}`, true);
            setRes([]);
        }
        finally {
            setSearchLoading(false);
        }
    };
    async function onUploadChange(e) {
        if (!e.target.files?.length)
            return;
        const file = e.target.files[0];
        setUploadBusy(true);
        try {
            const s0 = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => ({ counts: { total: 0 } }));
            const baseTotal = s0?.counts?.total ?? 0;
            const fd = new FormData();
            fd.append("file", file, file.name);
            const res = await fetch(`${apiBase}/upload`, { method: "POST", body: fd });
            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData?.error || errorData?.detail || `Upload failed (${res.status})`);
            }
            const data = await res.json();
            // if API returns worker JSON, we'll have document_id and collection
            const docId = data?.document_id;
            const coll = (data?.collection || "");
            const kind = coll.includes("images") ? "image" : "text"; // images vs chunks
            if (docId)
                setLastDoc({ id: docId, kind });
            const done = await waitForProcessed(baseTotal, 20000, 4000);
            showToast(done.ok ? "Processed ✓" : "Uploaded (pending…)");
        }
        catch (err) {
            showToast(`Upload failed: ${err?.message || err}`, true);
        }
        finally {
            setUploadBusy(false);
            e.target.value = ""; // reset input
        }
    }
    return (_jsxs("div", { style: { fontFamily: 'ui-sans-serif', padding: 24, maxWidth: 720, margin: '0 auto' }, children: [_jsx("h1", { style: { fontSize: 24, marginBottom: 12 }, children: "jsonify2ai \u2014 Status" }), !s && _jsx("div", { children: "Loading\u2026" }), s && (_jsxs("div", { style: { display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }, children: [_jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Text Chunks" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.chunks })] }), _jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Images" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.images })] })] })), s && (s.uptime_s !== undefined || s.ingest_total !== undefined || s.ingest_failed !== undefined || s.watcher_triggers_total !== undefined || s.export_total !== undefined) && (_jsxs("div", { style: { marginTop: 16 }, children: [_jsx("div", { style: { fontSize: 14, opacity: .6, marginBottom: 8 }, children: "Telemetry" }), _jsxs("div", { style: { display: 'flex', gap: 8, flexWrap: 'wrap' }, children: [s.uptime_s !== undefined && (_jsxs("div", { style: { fontSize: 12, background: '#f0f9ff', color: '#0369a1', padding: '4px 8px', borderRadius: 12, border: '1px solid #bae6fd' }, children: ["Uptime: ", Math.floor(s.uptime_s / 3600), "h ", Math.floor((s.uptime_s % 3600) / 60), "m"] })), s.ingest_total !== undefined && (_jsxs("div", { style: { fontSize: 12, background: '#f0fdf4', color: '#166534', padding: '4px 8px', borderRadius: 12, border: '1px solid #bbf7d0' }, children: ["Ingested: ", s.ingest_total] })), s.ingest_failed !== undefined && s.ingest_failed > 0 && (_jsxs("div", { style: { fontSize: 12, background: '#fef2f2', color: '#dc2626', padding: '4px 8px', borderRadius: 12, border: '1px solid #fecaca' }, children: ["Failed: ", s.ingest_failed] })), s.watcher_triggers_total !== undefined && (_jsxs("div", { style: { fontSize: 12, background: '#fefce8', color: '#a16207', padding: '4px 8px', borderRadius: 12, border: '1px solid #fde68a' }, children: ["Watcher: ", s.watcher_triggers_total] })), s.export_total !== undefined && (_jsxs("div", { style: { fontSize: 12, background: '#f3e8ff', color: '#7c3aed', padding: '4px 8px', borderRadius: 12, border: '1px solid #d8b4fe' }, children: ["Exported: ", s.export_total] }))] })] })), recentDocs.length > 0 && (_jsxs("div", { style: { marginTop: 16 }, children: [_jsx("div", { style: { fontSize: 14, opacity: .6, marginBottom: 8 }, children: "Recent Documents" }), _jsx("div", { style: { display: 'grid', gap: 8 }, children: recentDocs.map((doc, i) => (_jsxs("div", { style: { padding: 12, border: '1px solid #eee', borderRadius: 8, background: '#fafafa' }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }, children: [_jsxs("code", { style: { fontSize: 11, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }, children: [doc.document_id?.substring(0, 8), "..."] }), doc.path && (_jsx("span", { style: { fontSize: 12, opacity: .7, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: doc.path.split('/').pop() }))] }), _jsxs("div", { style: { display: 'flex', gap: 8, alignItems: 'center' }, children: [_jsx("span", { style: { fontSize: 11, opacity: .6 }, children: doc.kind === 'image' ? 'images' : 'chunks' }), _jsxs("div", { style: { display: 'flex', gap: 4 }, children: [_jsx("button", { onClick: () => downloadJson(doc.document_id, doc.kind === 'image' ? 'images' : 'chunks'), style: { fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }, children: "Export JSON" }), _jsx("button", { onClick: () => downloadZip(doc.document_id, doc.kind), style: { fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }, children: "Export ZIP" })] })] })] }, i))) })] })), _jsxs("div", { className: "mb-4 flex items-center gap-3", children: [_jsx("input", { type: "file", onChange: onUploadChange, disabled: uploadBusy }), uploadBusy && _jsx("span", { className: "text-sm opacity-70", children: "Uploading\u2026" }), toast && (_jsx("span", { className: "text-sm", style: {
                            color: toast.includes('failed') || toast.includes('error') || toast.includes('Error') ? '#dc2626' : '#16a34a'
                        }, children: toast })), lastDoc && (_jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx("button", { className: "text-xs underline opacity-70 hover:opacity-100", onClick: () => downloadJson(lastDoc.id, lastDoc.kind === 'image' ? 'images' : 'chunks'), children: "Download JSON" }), _jsx("button", { className: "text-xs underline opacity-70 hover:opacity-100", onClick: () => downloadZip(lastDoc.id, lastDoc.kind), children: "Download ZIP" })] }))] }), _jsxs("div", { style: { marginTop: 24 }, children: [_jsx("h2", { style: { fontSize: 18, marginBottom: 8 }, children: "Ask" }), _jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx("input", { value: askQ, onChange: (e) => setAskQ(e.target.value), placeholder: "ask your data\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsx("button", { onClick: async () => {
                                    if (!askQ.trim()) {
                                        showToast("Please enter a question", true);
                                        return;
                                    }
                                    setAskLoading(true);
                                    try {
                                        const j = await askQuestion(askQ, 6);
                                        if (j.ok === false) {
                                            showToast(`Ask failed: ${j.error || 'Unknown error'}`, true);
                                            setAns(null);
                                        }
                                        else {
                                            setAns(j);
                                        }
                                    }
                                    catch (err) {
                                        showToast(`Ask error: ${err?.message || err}`, true);
                                        setAns(null);
                                    }
                                    finally {
                                        setAskLoading(false);
                                    }
                                }, disabled: askLoading, style: {
                                    padding: '12px 16px',
                                    borderRadius: 8,
                                    border: '1px solid #ddd',
                                    opacity: askLoading ? 0.6 : 1,
                                    cursor: askLoading ? 'not-allowed' : 'pointer'
                                }, children: askLoading ? 'Asking...' : 'Ask' })] }), ans && (_jsxs("div", { style: { marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }, children: [_jsxs("div", { style: { fontSize: 12, opacity: .6, marginBottom: 6 }, children: ["mode: ", ans.mode, ans.model ? ` (${ans.model})` : ''] }), ans.final && ans.final.trim() && (_jsxs("div", { style: { marginBottom: 12, padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fafafa' }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }, children: [_jsx("div", { style: { fontWeight: 600 }, children: "Answer" }), _jsx("span", { style: { fontSize: 11, padding: '2px 6px', borderRadius: 999, background: '#eef2ff', color: '#3730a3' }, children: "local (ollama)" })] }), _jsx("div", { style: { whiteSpace: 'pre-wrap', lineHeight: 1.4 }, children: ans.final })] })), (ans.answer || ans.sources || ans.answers) && (_jsxs(_Fragment, { children: [ans.answer && ans.answer.trim() && (_jsx("div", { style: { whiteSpace: 'pre-wrap', marginBottom: ans.sources?.length || ans.answers?.length ? 10 : 0 }, children: ans.answer })), (ans.sources && ans.sources.length > 0) || (ans.answers && ans.answers.length > 0) ? (_jsx("div", { style: { marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }, children: (ans.sources || ans.answers || []).map((h, i) => (_jsx("span", { style: { fontSize: 12, opacity: .75, border: '1px solid #eee', padding: '2px 6px', borderRadius: 999 }, children: h.path?.split('/').pop() || h.id }, i))) })) : (_jsx("div", { style: { color: '#666', fontSize: 13, marginTop: 8 }, children: "No matching snippets." }))] }))] }))] }), _jsxs("div", { style: { marginTop: 24, display: 'flex', gap: 8 }, children: [_jsx("input", { value: q, onChange: (e) => setQ(e.target.value), placeholder: "search\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsxs("select", { value: kind, onChange: e => setKind(e.target.value), style: { padding: 12, borderRadius: 8, border: '1px solid #ddd' }, children: [_jsx("option", { value: "text", children: "text" }), _jsx("option", { value: "pdf", children: "pdf" }), _jsx("option", { value: "image", children: "image" }), _jsx("option", { value: "audio", children: "audio" })] }), _jsx("button", { onClick: handleSearch, disabled: searchLoading, style: {
                            padding: '12px 16px',
                            borderRadius: 8,
                            border: '1px solid #ddd',
                            opacity: searchLoading ? 0.6 : 1,
                            cursor: searchLoading ? 'not-allowed' : 'pointer'
                        }, children: searchLoading ? 'Searching...' : 'Search' })] }), res.length > 0 && (_jsx("div", { style: { marginTop: 16, display: 'grid', gap: 8 }, children: res.map((h, i) => (_jsxs("div", { className: "mb-2 p-2 rounded border", children: [_jsxs("div", { className: "text-sm opacity-70", children: ["score: ", h.score?.toFixed?.(3) ?? "-"] }), _jsxs("div", { className: "text-xs", children: [_jsx("span", { className: "inline-block px-2 py-0.5 bg-gray-100 rounded mr-2", children: h.path }), _jsxs("span", { className: "inline-block px-2 py-0.5 bg-gray-100 rounded mr-2", children: ["idx: ", h.idx] })] }), _jsxs("div", { className: "text-xs opacity-60", children: [h.kind === "image" ? "images" : "chunks", " \u2022 idx: ", h.idx] }), _jsx("div", { className: "mt-1", children: h.caption || h.text || '(no text)' }), h.document_id && (_jsx("div", { className: "mt-1", children: _jsx("button", { className: "text-xs underline opacity-70 hover:opacity-100", onClick: () => downloadJson(h.document_id, h.kind === 'image' ? 'images' : 'chunks'), children: "Download JSON" }) }))] }, i))) })), _jsxs("div", { style: { marginTop: 24 }, children: [_jsx("h2", { style: { fontSize: 18, marginBottom: 8 }, children: "Documents" }), _jsx("div", { style: { marginBottom: 12 }, children: _jsx("button", { onClick: fetchDocuments, style: { padding: '8px 16px', borderRadius: 8, border: '1px solid #ddd', fontSize: 14 }, children: "Refresh documents" }) }), docs.length > 0 && (_jsx("div", { style: { display: 'grid', gap: 8 }, children: docs.map((doc, i) => (_jsxs("div", { style: { padding: 12, border: '1px solid #eee', borderRadius: 8 }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }, children: [_jsx("code", { style: { fontSize: 12, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }, children: doc.document_id }), _jsx("button", { onClick: () => {
                                                copyToClipboard(doc.document_id);
                                                showToast('Document ID copied');
                                            }, style: { fontSize: 12, color: '#666', textDecoration: 'underline' }, children: "Copy ID" })] }), _jsx("div", { style: { display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }, children: doc.kinds.map((kind, j) => (_jsx("span", { style: { fontSize: 12, background: '#e3f2fd', color: '#1976d2', padding: '2px 6px', borderRadius: 12 }, children: kind }, j))) }), _jsxs("div", { style: { fontSize: 12, color: '#666', marginBottom: 8 }, children: [doc.paths[0] && _jsxs("div", { children: ["Path: ", doc.paths[0]] }), _jsxs("div", { children: ["Counts: ", Object.entries(doc.counts).map(([k, v]) => `${k}: ${v}`).join(', ')] })] }), _jsxs("div", { style: { display: 'flex', gap: 8, flexWrap: 'wrap' }, children: [_jsx("button", { onClick: () => {
                                                const collection = collectionForDoc(doc);
                                                const url = `${apiBase}/export?document_id=${encodeURIComponent(doc.document_id)}&collection=${collection}`;
                                                window.open(url, '_blank');
                                            }, style: { fontSize: 12, color: '#1976d2', textDecoration: 'underline' }, children: "Export JSON" }), _jsx("button", { onClick: () => {
                                                const collection = collectionForDoc(doc);
                                                const url = `${apiBase}/export/archive?document_id=${encodeURIComponent(doc.document_id)}&collection=${collection}`;
                                                window.open(url, '_blank');
                                            }, style: { fontSize: 12, color: '#1976d2', textDecoration: 'underline' }, children: "Export ZIP" }), _jsx("button", { onClick: () => {
                                                const collection = collectionForDoc(doc);
                                                const cmd = `Invoke-WebRequest "http://localhost:8082/export?document_id=${doc.document_id}&collection=${collection}" -OutFile "export_${doc.document_id}.jsonl"`;
                                                copyToClipboard(cmd);
                                                showToast('Export command copied');
                                            }, style: { fontSize: 12, color: '#1976d2', textDecoration: 'underline' }, children: "Copy export cmd" })] })] }, i))) })), docs.length === 0 && (_jsx("div", { style: { color: '#666', fontSize: 14 }, children: "No documents found. Upload some files to see them here." }))] }), _jsxs("div", { style: { marginTop: 16, opacity: .7, fontSize: 12 }, children: ["API: ", apiBase] })] }));
}
export default App;
