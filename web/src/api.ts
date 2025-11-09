// web/src/api.ts
// API utility functions with optional authentication

const envBase = import.meta.env.VITE_API_URL;

function hostDefault(): string {
  try {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8082";
  } catch {}
  return "http://api:8082";
}

export const API_BASE = envBase && envBase.trim() !== "" ? envBase : hostDefault();
const apiBase = API_BASE;

// Support both VITE_API_TOKEN (new) and VITE_API_AUTH_TOKEN (legacy) for backward compatibility
const authToken = import.meta.env.VITE_API_TOKEN || import.meta.env.VITE_API_AUTH_TOKEN;

function getHeaders(includeAuth = true): HeadersInit {
  const headers: HeadersInit = {};

  if (includeAuth && authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  return headers;
}

export async function apiRequest(
  endpoint: string,
  options: RequestInit = {},
  requireAuth = true
): Promise<Response> {
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
export async function uploadFile(file: File): Promise<any> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return postUpload(fd);
}

// Explicit upload helper that always includes Authorization when present
export async function postUpload(fd: FormData): Promise<any> {
  const res = await fetch(`${apiBase}/upload`, {
    method: "POST",
    headers: getHeaders(true), // Authorization only; do not set Content-Type
    body: fd
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`/upload failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function doSearch(q: string, kind: string, k = 5): Promise<any> {
  try {
    const url = `/search?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&k=${k}`;
    const r = await apiRequest(url, { method: "GET" }, true);
    if (r.ok) return await r.json();

    // fallback to POST body if GET not supported
    const r2 = await apiRequest("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q, kind, k }),
    }, true);
    return await r2.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function askQuestion(query: string, k = 6): Promise<any> {
  const r = await apiRequest("/ask", {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query, k })
  }, true);

  if (!r.ok) {
    const errorData = await r.json().catch(() => ({}));
    // Preserve error data for rate limiting detection
    const err = new Error(errorData?.error || errorData?.detail || `Ask failed (${r.status})`) as any;
    err.status = r.status;
    err.errorData = errorData;
    throw err;
  }

  return await r.json();
}

// Public endpoints (no auth required)
export async function fetchStatus(): Promise<any> {
  const res = await apiRequest("/status", {}, false);
  return await res.json();
}

export async function fetchDocuments(): Promise<any> {
  const res = await apiRequest("/documents", {}, false);
  return await res.json();
}

export function downloadJson(documentId: string, kind: string): void {
  const url = `${apiBase}/export?document_id=${documentId}&collection=${kind}`;
  window.open(url, '_blank');
}
