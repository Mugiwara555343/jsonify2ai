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

// API token from environment - Vite reads VITE_API_TOKEN at build/dev server startup
const API_TOKEN = import.meta.env.VITE_API_TOKEN || import.meta.env.VITE_API_AUTH_TOKEN;

// Warn if token is missing at module load
if (!API_TOKEN) {
  console.warn("[jsonify2ai] WARNING: VITE_API_TOKEN is not set. Authenticated API calls will fail.");
  console.warn("[jsonify2ai] Run scripts/ensure_tokens.ps1 or scripts/ensure_tokens.sh to generate tokens.");
}

function getHeaders(includeAuth = true): HeadersInit {
  const headers: HeadersInit = {};

  if (includeAuth && API_TOKEN) {
    headers['Authorization'] = `Bearer ${API_TOKEN}`;
  }

  return headers;
}

export async function apiRequest(
  endpoint: string,
  options: RequestInit = {},
  requireAuth = true
): Promise<Response> {
  const url = `${apiBase}${endpoint}`;

  // Build headers: auth headers first, then options.headers (so options can override if needed)
  const authHeaders = getHeaders(requireAuth);

  // For FormData, we must NOT set Content-Type (browser sets it with boundary automatically)
  // So we build headers carefully - start with auth, then merge options headers
  const mergedHeaders: HeadersInit = {
    ...authHeaders,
  };

  // Merge options.headers if provided (but browser will override Content-Type for FormData)
  if (options.headers) {
    if (options.headers instanceof Headers) {
      // Convert Headers to plain object
      const headersObj: Record<string, string> = {};
      options.headers.forEach((value, key) => {
        if (options.body instanceof FormData && key.toLowerCase() === 'content-type') {
          // Skip Content-Type for FormData
          return;
        }
        headersObj[key] = value;
      });
      Object.assign(mergedHeaders, headersObj);
    } else if (Array.isArray(options.headers)) {
      // Convert array to plain object
      const headersObj: Record<string, string> = {};
      options.headers.forEach(([key, value]) => {
        if (options.body instanceof FormData && key.toLowerCase() === 'content-type') {
          // Skip Content-Type for FormData
          return;
        }
        headersObj[key] = value;
      });
      Object.assign(mergedHeaders, headersObj);
    } else {
      // Plain object - merge but skip Content-Type for FormData
      const headersObj = options.headers as Record<string, string>;
      Object.keys(headersObj).forEach(key => {
        if (options.body instanceof FormData && key.toLowerCase() === 'content-type') {
          // Skip Content-Type for FormData
          return;
        }
        (mergedHeaders as Record<string, string>)[key] = headersObj[key];
      });
    }
  }

  // Debug logging only for upload endpoint
  if (requireAuth && endpoint === "/upload") {
    const authHeader = (mergedHeaders as Record<string, string>)['Authorization'];
    if (authHeader) {
      console.log("[jsonify2ai-debug] apiRequest /upload auth header =>", authHeader.slice(0, 20) + "...");
    } else {
      console.warn("[jsonify2ai-debug] apiRequest /upload auth header => NONE");
    }
  }

  return fetch(url, {
    ...options,
    headers: mergedHeaders,
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
  console.log('[jsonify2ai-debug] upload via apiRequest, auth=', true);

  // Use apiRequest for consistency - do NOT set Content-Type header
  // (browser will set it automatically with boundary for FormData)
  const res = await apiRequest("/upload", {
    method: "POST",
    body: fd
    // No Content-Type header - let browser set it automatically
  }, true);

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

  if (!res.ok) {
    // Try to read error message, but handle non-JSON responses
    const contentType = res.headers.get("content-type") || "";
    let errorText = "";
    try {
      if (contentType.includes("application/json")) {
        const errorData = await res.json().catch(() => ({}));
        errorText = errorData?.error || errorData?.detail || `HTTP ${res.status}`;
      } else {
        errorText = await res.text().catch(() => `HTTP ${res.status}`);
        // Limit error text length for logging
        if (errorText.length > 200) {
          errorText = errorText.substring(0, 200) + "...";
        }
      }
    } catch (e) {
      errorText = `HTTP ${res.status}`;
    }
    throw new Error(`Failed to fetch documents: ${errorText}`);
  }

  // Check if response is JSON before parsing
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await res.text().catch(() => "");
    throw new Error(`Expected JSON but got ${contentType}. Response: ${text.substring(0, 200)}`);
  }

  return await res.json();
}

export function downloadJson(documentId: string, kind: string): void {
  const url = `${apiBase}/export?document_id=${documentId}&collection=${kind}`;
  window.open(url, '_blank');
}
