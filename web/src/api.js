// web/src/api.ts
// API utility functions with optional authentication
const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8082";
const authToken = import.meta.env.VITE_API_TOKEN;
function getHeaders(includeAuth = true) {
    const headers = {};
    if (includeAuth && authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    return headers;
}
export async function apiRequest(endpoint, options = {}, requireAuth = true) {
    const url = `${apiBase}${endpoint}`;
    const headers = {
        ...getHeaders(requireAuth),
        ...options.headers,
    };
    return fetch(url, {
        ...options,
        headers,
    });
}
// Specific API functions for protected endpoints
export async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const res = await apiRequest("/upload", {
        method: "POST",
        body: fd
    }, true);
    const data = await res.json().catch(() => ({}));
    if (!res.ok)
        throw new Error(data?.detail || `Upload failed (${res.status})`);
    return data;
}
export async function doSearch(q, kind, k = 5) {
    try {
        const url = `/search?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&k=${k}`;
        const r = await apiRequest(url, { method: "GET" }, true);
        if (r.ok)
            return await r.json();
        // fallback to POST body if GET not supported
        const r2 = await apiRequest("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ q, kind, k }),
        }, true);
        return await r2.json();
    }
    catch (e) {
        return { ok: false, error: String(e) };
    }
}
export async function askQuestion(query, k = 6) {
    const r = await apiRequest("/ask", {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ query, k })
    }, true);
    if (!r.ok) {
        const errorData = await r.json().catch(() => ({}));
        throw new Error(errorData?.error || errorData?.detail || `Ask failed (${r.status})`);
    }
    return await r.json();
}
// Public endpoints (no auth required)
export async function fetchStatus() {
    const res = await apiRequest("/status", {}, false);
    return await res.json();
}
export async function fetchDocuments() {
    const res = await apiRequest("/documents", {}, false);
    return await res.json();
}
export function downloadJson(documentId, kind) {
    const url = `${apiBase}/export?document_id=${documentId}&collection=${kind}`;
    window.open(url, '_blank');
}
