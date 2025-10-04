import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import './App.css';
const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8082";
async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const res = await fetch(`${apiBase}/upload`, { method: "POST", body: fd });
    // API proxies worker response; assume JSON
    const data = await res.json().catch(() => ({}));
    if (!res.ok)
        throw new Error(data?.detail || `Upload failed (${res.status})`);
    return data; // expect {"ok":true, ...}
}
async function waitForProcessed(oldTotal, timeoutMs = 15000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
        const s = await fetch(`${apiBase}/status`).then(r => r.json());
        const total = s?.counts?.total ?? 0;
        if (total > oldTotal)
            return { ok: true, total };
        await new Promise(r => setTimeout(r, 1000));
    }
    return { ok: false };
}
function downloadJson(documentId, kind) {
    const collection = kind === 'image' ? 'images' : 'chunks';
    const url = `${apiBase}/export?document_id=${encodeURIComponent(documentId)}&collection=${collection}`;
    window.open(url, '_blank');
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
    function showToast(msg) {
        setToast(msg);
        setTimeout(() => setToast(null), 3000);
    }
    useEffect(() => {
        fetchStatus();
    }, []);
    const fetchStatus = async () => {
        const res = await fetch(`${apiBase}/status`);
        const j = await res.json();
        setS(j);
    };
    async function doSearch(q, kind) {
        const k = 5;
        try {
            const url = `${apiBase}/search?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&k=${k}`;
            const r = await fetch(url, { method: "GET" });
            if (r.ok)
                return await r.json();
            // fallback to POST body if GET not supported
            const r2 = await fetch(`${apiBase}/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ q, kind, k }),
            });
            return await r2.json();
        }
        catch (e) {
            return { ok: false, error: String(e) };
        }
    }
    const handleSearch = async () => {
        const resp = await doSearch(q, kind);
        setRes(resp.results ?? []);
    };
    async function onUploadChange(e) {
        if (!e.target.files?.length)
            return;
        const file = e.target.files[0];
        setUploadBusy(true);
        try {
            const s0 = await fetch(`${apiBase}/status`).then(r => r.json()).catch(() => ({ counts: { total: 0 } }));
            const baseTotal = s0?.counts?.total ?? 0;
            await uploadFile(file);
            const done = await waitForProcessed(baseTotal, 20000);
            showToast(done.ok ? "Processed ✓" : "Uploaded (pending…)"); // non-blocking fallback
            // optional: trigger a refresh of search results here
        }
        catch (err) {
            showToast(`Upload failed: ${err?.message || err}`);
        }
        finally {
            setUploadBusy(false);
            e.target.value = ""; // reset input
        }
    }
    return (_jsxs("div", { style: { fontFamily: 'ui-sans-serif', padding: 24, maxWidth: 720, margin: '0 auto' }, children: [_jsx("h1", { style: { fontSize: 24, marginBottom: 12 }, children: "jsonify2ai \u2014 Status" }), !s && _jsx("div", { children: "Loading\u2026" }), s && (_jsxs("div", { style: { display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }, children: [_jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Text Chunks" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.chunks })] }), _jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Images" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.images })] })] })), _jsxs("div", { className: "mb-4 flex items-center gap-3", children: [_jsx("input", { type: "file", onChange: onUploadChange, disabled: uploadBusy }), uploadBusy && _jsx("span", { className: "text-sm opacity-70", children: "Uploading\u2026" }), toast && _jsx("span", { className: "text-sm text-green-600", children: toast })] }), _jsxs("div", { style: { marginTop: 24 }, children: [_jsx("h2", { style: { fontSize: 18, marginBottom: 8 }, children: "Ask" }), _jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx("input", { value: askQ, onChange: (e) => setAskQ(e.target.value), placeholder: "ask your data\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsx("button", { onClick: async () => {
                                    const r = await fetch(`${apiBase}/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: askQ, k: 6 }) });
                                    const j = await r.json();
                                    setAns(j);
                                }, style: { padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }, children: "Ask" })] }), ans && (_jsxs("div", { style: { marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }, children: [_jsxs("div", { style: { fontSize: 12, opacity: .6, marginBottom: 6 }, children: ["mode: ", ans.mode, ans.model ? ` (${ans.model})` : ''] }), _jsx("div", { style: { whiteSpace: 'pre-wrap' }, children: ans.answer }), ans.sources?.length > 0 && (_jsx("div", { style: { marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }, children: ans.sources.map((h, i) => (_jsx("span", { style: { fontSize: 12, opacity: .75, border: '1px solid #eee', padding: '2px 6px', borderRadius: 999 }, children: h.path?.split('/').pop() || h.id }, i))) }))] }))] }), _jsxs("div", { style: { marginTop: 24, display: 'flex', gap: 8 }, children: [_jsx("input", { value: q, onChange: (e) => setQ(e.target.value), placeholder: "search\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsxs("select", { value: kind, onChange: e => setKind(e.target.value), style: { padding: 12, borderRadius: 8, border: '1px solid #ddd' }, children: [_jsx("option", { value: "text", children: "text" }), _jsx("option", { value: "pdf", children: "pdf" }), _jsx("option", { value: "image", children: "image" }), _jsx("option", { value: "audio", children: "audio" })] }), _jsx("button", { onClick: handleSearch, style: { padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }, children: "Search" })] }), res.length > 0 && (_jsx("div", { style: { marginTop: 16, display: 'grid', gap: 8 }, children: res.map((h, i) => (_jsxs("div", { className: "mb-2 p-2 rounded border", children: [_jsxs("div", { className: "text-sm opacity-70", children: ["score: ", h.score?.toFixed?.(3) ?? "-"] }), _jsxs("div", { className: "text-xs", children: [_jsx("span", { className: "inline-block px-2 py-0.5 bg-gray-100 rounded mr-2", children: h.path }), _jsxs("span", { className: "inline-block px-2 py-0.5 bg-gray-100 rounded mr-2", children: ["idx: ", h.idx] })] }), _jsxs("div", { className: "text-xs opacity-60", children: [h.kind === "image" ? "images" : "chunks", " \u2022 idx: ", h.idx] }), _jsx("div", { className: "mt-1", children: h.caption || h.text || '(no text)' }), h.document_id && (_jsx("div", { className: "mt-1", children: _jsx("button", { className: "text-xs underline opacity-70 hover:opacity-100", onClick: () => downloadJson(h.document_id, h.kind), children: "Download JSON" }) }))] }, i))) })), _jsxs("div", { style: { marginTop: 16, opacity: .7, fontSize: 12 }, children: ["API: ", apiBase] })] }));
}
export default App;
