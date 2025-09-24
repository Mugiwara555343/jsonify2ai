import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import './App.css';
const WORKER = import.meta.env.VITE_API_URL || 'http://localhost:8082';
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
    const [lastCounts, setLastCounts] = useState(null);
    useEffect(() => {
        fetchStatus();
    }, []);
    const fetchStatus = async () => {
        const res = await fetch(`${WORKER}/status`);
        const j = await res.json();
        setS(j);
        // cache counts for later comparison
        try {
            const byKind = j?.counts_by_kind ?? j?.counts ?? {};
            const total = Object.values(byKind).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0);
            setLastCounts({ total, byKind });
        }
        catch { }
    };
    const doSearch = async () => {
        const r = await fetch(`${WORKER}/search?q=${encodeURIComponent(q)}&kind=${kind}&k=8`);
        const j = await r.json();
        setRes(j.results || []);
    };
    const doUpload = async (e) => {
        const f = e.target.files?.[0];
        if (!f)
            return;
        const fd = new FormData();
        fd.append('file', f);
        const before = lastCounts;
        setUploadBusy(true);
        setMsg('');
        try {
            const r = await fetch(`${WORKER}/upload`, { method: 'POST', body: fd });
            // swallow worker JSON; we rely on status polling
            try {
                await r.json();
            }
            catch { }
            // poll status for ~30s or until counts increase
            const started = Date.now();
            const maxMs = 30000;
            let seenIncrease = false;
            while (Date.now() - started < maxMs) {
                await new Promise(r => setTimeout(r, 3000));
                const sres = await fetch(`${WORKER}/status`);
                const sj = await sres.json();
                setS(sj);
                const byKind = sj?.counts_by_kind ?? sj?.counts ?? {};
                const total = Object.values(byKind).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0);
                if (before && total > before.total) {
                    seenIncrease = true;
                    break;
                }
            }
            // final refresh
            await fetchStatus();
            setMsg(seenIncrease ? 'Uploaded & processed' : 'Uploaded (processing...)');
        }
        catch {
            setMsg('Failed');
        }
        finally {
            setUploadBusy(false);
        }
    };
    return (_jsxs("div", { style: { fontFamily: 'ui-sans-serif', padding: 24, maxWidth: 720, margin: '0 auto' }, children: [_jsx("h1", { style: { fontSize: 24, marginBottom: 12 }, children: "jsonify2ai \u2014 Status" }), !s && _jsx("div", { children: "Loading\u2026" }), s && (_jsxs("div", { style: { display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }, children: [_jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Text Chunks" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.chunks })] }), _jsxs("div", { style: { padding: 16, borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }, children: [_jsx("div", { style: { opacity: .6, marginBottom: 6 }, children: "Images" }), _jsx("div", { style: { fontSize: 28, fontWeight: 700 }, children: s.counts.images })] })] })), _jsxs("div", { style: { marginTop: 24 }, children: [_jsx("div", { style: { marginBottom: 8, opacity: .7 }, children: "Upload to drop\u2011zone" }), _jsxs("div", { style: { display: "flex", alignItems: "center", gap: 12 }, children: [_jsx("input", { type: "file", onChange: doUpload, disabled: busy }), uploadBusy && _jsx("span", { children: "ingesting\u2026" })] }), msg && _jsx("div", { style: { marginTop: 6, fontSize: 12, opacity: .8 }, children: msg })] }), _jsxs("div", { style: { marginTop: 24 }, children: [_jsx("h2", { style: { fontSize: 18, marginBottom: 8 }, children: "Ask" }), _jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx("input", { value: askQ, onChange: (e) => setAskQ(e.target.value), placeholder: "ask your data\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsx("button", { onClick: async () => {
                                    const r = await fetch(`${WORKER}/ask`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: askQ, k: 6 }) });
                                    const j = await r.json();
                                    setAns(j);
                                }, style: { padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }, children: "Ask" })] }), ans && (_jsxs("div", { style: { marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }, children: [_jsxs("div", { style: { fontSize: 12, opacity: .6, marginBottom: 6 }, children: ["mode: ", ans.mode, ans.model ? ` (${ans.model})` : ''] }), _jsx("div", { style: { whiteSpace: 'pre-wrap' }, children: ans.answer }), ans.sources?.length > 0 && (_jsx("div", { style: { marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }, children: ans.sources.map((h, i) => (_jsx("span", { style: { fontSize: 12, opacity: .75, border: '1px solid #eee', padding: '2px 6px', borderRadius: 999 }, children: h.path?.split('/').pop() || h.id }, i))) }))] }))] }), _jsxs("div", { style: { marginTop: 24, display: 'flex', gap: 8 }, children: [_jsx("input", { value: q, onChange: (e) => setQ(e.target.value), placeholder: "search\u2026", style: { flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' } }), _jsxs("select", { value: kind, onChange: e => setKind(e.target.value), style: { padding: 12, borderRadius: 8, border: '1px solid #ddd' }, children: [_jsx("option", { value: "text", children: "text" }), _jsx("option", { value: "images", children: "images" })] }), _jsx("button", { onClick: doSearch, style: { padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd' }, children: "Search" })] }), res.length > 0 && (_jsx("div", { style: { marginTop: 16, display: 'grid', gap: 8 }, children: res.map((h, i) => (_jsxs("div", { style: { padding: 12, border: '1px solid #eee', borderRadius: 10 }, children: [_jsxs("div", { style: { fontSize: 12, opacity: .6 }, children: ["score ", (h.score || 0).toFixed(3)] }), _jsx("div", { style: { marginTop: 4 }, children: h.caption || h.text || '(no text)' }), h.path && _jsx("div", { style: { fontSize: 12, opacity: .6, marginTop: 4 }, children: h.path })] }, i))) })), _jsxs("div", { style: { marginTop: 16, opacity: .7, fontSize: 12 }, children: ["Worker: ", WORKER] })] }));
}
export default App;
