// web/src/api.ts
// API utility functions with optional authentication

const envBase = import.meta.env.VITE_API_URL;

function hostDefault(): string {
  try {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8082";
  } catch { }
  return "http://api:8082";
}

export const API_BASE = envBase && envBase.trim() !== "" ? envBase : hostDefault();
const apiBase = API_BASE;

// API token from environment - Vite reads VITE_API_TOKEN at build/dev server startup
// Token is optional: in local mode (AUTH_MODE=local), no token is required
const API_TOKEN = import.meta.env.VITE_API_TOKEN || import.meta.env.VITE_API_AUTH_TOKEN;

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

// Helper to parse skip reasons from error responses
function parseSkipReason(errorData: any, status: number): string | undefined {
  if (status === 400) {
    const detail = errorData?.detail_snippet || errorData?.detail || errorData?.error || "";
    const detailLower = detail.toLowerCase();

    if (detailLower.includes("ignored extension") || detailLower.includes("unsupported")) {
      return "unsupported_extension";
    }
    if (detailLower.includes("failed to parse") || detailLower.includes("extraction failed")) {
      return "extraction_failed";
    }
    if (detailLower.includes("no content") || detailLower.includes("empty")) {
      return "empty_file";
    }
    if (detailLower.includes("worker_reject") || detailLower.includes("processing")) {
      return "processing_failed";
    }
  }
  return undefined;
}

// Explicit upload helper that includes Authorization when token is available
export async function postUpload(fd: FormData): Promise<any> {
  // Use apiRequest for consistency - do NOT set Content-Type header
  // (browser will set it automatically with boundary for FormData)
  const res = await apiRequest("/upload", {
    method: "POST",
    body: fd
    // No Content-Type header - let browser set it automatically
  }, true);

  if (!res.ok) {
    let errorData: any = {};
    try {
      const text = await res.text();
      try {
        errorData = JSON.parse(text);
      } catch {
        errorData = { error: text };
      }
    } catch {
      errorData = { error: `HTTP ${res.status}` };
    }

    // Check if this is a skip case (400 status with specific error patterns)
    const skipReason = parseSkipReason(errorData, res.status);
    if (skipReason) {
      return {
        ok: true,
        accepted: false,
        skipped: true,
        skip_reason: skipReason,
        details: errorData?.detail_snippet || errorData?.detail || errorData?.error || "File was skipped"
      };
    }

    // Otherwise, throw error
    throw new Error(`/upload failed: ${res.status} ${errorData?.error || errorData?.detail || JSON.stringify(errorData)}`);
  }

  const data = await res.json();

  // Normalize successful response
  if (data.ok && data.document_id) {
    return {
      ok: true,
      accepted: true,
      skipped: false,
      document_id: data.document_id,
      chunks: data.chunks || data.upserted || 0,
      collection: data.collection,
      embedded: data.embedded,
      upserted: data.upserted
    };
  }

  // Return as-is for backward compatibility
  return data;
}

export async function doSearch(
  q: string,
  kind: string,
  k = 5,
  ingestedAfter?: string,
  ingestedBefore?: string
): Promise<any> {
  // Guard against empty query
  if (!q || q.trim() === '') {
    return { ok: true, kind, q: '', results: [] };
  }

  try {
    // Hybrid search now uses POST /search to support query translation
    const body: any = { query: q, kind, k };
    if (ingestedAfter) body.ingested_after = ingestedAfter;
    if (ingestedBefore) body.ingested_before = ingestedBefore;

    const r = await apiRequest("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, true);
    return await r.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function askQuestion(
  query: string,
  k = 6,
  documentId?: string,
  answerMode?: 'retrieve' | 'synthesize',
  ingestedAfter?: string,
  ingestedBefore?: string,
  model?: string
): Promise<any> {
  // Build URL with optional query parameters
  let url = "/ask";
  const queryParams: string[] = [];
  if (documentId) {
    queryParams.push(`document_id=${encodeURIComponent(documentId)}`);
  }
  if (ingestedAfter) {
    queryParams.push(`ingested_after=${encodeURIComponent(ingestedAfter)}`);
  }
  if (ingestedBefore) {
    queryParams.push(`ingested_before=${encodeURIComponent(ingestedBefore)}`);
  }
  if (queryParams.length > 0) {
    url += `?${queryParams.join('&')}`;
  }

  const body: any = { query, k };
  if (answerMode) {
    body.answer_mode = answerMode;
  }
  if (ingestedAfter) {
    body.ingested_after = ingestedAfter;
  }
  if (ingestedBefore) {
    body.ingested_before = ingestedBefore;
  }
  if (model) {
    body.model = model;
  }

  const r = await apiRequest(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
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

export function collectionForKind(kind: string): string {
  return kind === "image" || kind === "images"
    ? "jsonify2ai_images_768"
    : "jsonify2ai_chunks";
}

export async function exportJson(documentId: string, kind: string): Promise<void> {
  const collection = collectionForKind(kind);
  const url = `/export?document_id=${encodeURIComponent(documentId)}&collection=${encodeURIComponent(collection)}`;
  const response = await apiRequest(url, { method: "GET" }, true);
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `${documentId}.${kind === "image" || kind === "images" ? "images" : "chunks"}.jsonl`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
}

export async function exportZip(documentId: string, kind: string): Promise<void> {
  const collection = collectionForKind(kind);
  const url = `/export/archive?document_id=${encodeURIComponent(documentId)}&collection=${encodeURIComponent(collection)}`;
  const response = await apiRequest(url, { method: "GET" }, true);
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `${documentId}.archive.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
}

// Legacy function - kept for backward compatibility but should use exportJson instead
export function downloadJson(documentId: string, kind: string): void {
  const url = `${apiBase}/export?document_id=${documentId}&collection=${kind}`;
  window.open(url, '_blank');
}

export async function fetchJsonPreview(
  documentId: string,
  collection: string,
  maxLines = 100,
  offset = 0
): Promise<{ lines: string[]; total?: number }> {
  const res = await apiRequest(
    `/export?document_id=${encodeURIComponent(documentId)}&collection=${encodeURIComponent(collection)}`,
    { method: 'GET' },
    true
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch JSON preview: ${res.status}`);
  }
  const text = await res.text();
  const allLines = text.split('\n').filter(Boolean);
  const total = allLines.length;
  const lines = allLines.slice(offset, offset + maxLines);
  return { lines, total };
}

export async function deleteDocument(documentId: string): Promise<void> {
  let response: Response;
  try {
    response = await apiRequest(
      `/documents/${encodeURIComponent(documentId)}`,
      { method: 'DELETE' },
      true
    );
  } catch (err: any) {
    // Handle network/CORS errors that occur before response
    if (err?.message?.includes('Failed to fetch') || err?.message?.includes('NetworkError') || err?.name === 'TypeError') {
      throw new Error('Delete failed: Network error. Check CORS configuration.');
    }
    throw err;
  }

  if (!response.ok) {
    let errorData: any = {};
    let errorMsg = `Delete failed: ${response.status}`;

    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        errorData = await response.json().catch(() => ({}));
      } else {
        const text = await response.text().catch(() => "");
        errorData = { error: text || `HTTP ${response.status}` };
      }
    } catch (e) {
      // If we can't parse the response, use status code
      errorData = { error: `HTTP ${response.status}` };
    }

    // Extract error message with priority: detail > error > status
    errorMsg = errorData?.detail || errorData?.error || errorMsg;

    // Provide specific messages for common status codes
    if (response.status === 403) {
      if (errorMsg.includes('not enabled') || errorMsg.includes('Delete not enabled')) {
        errorMsg = 'Delete is disabled (set AUTH_MODE=local or ENABLE_DOC_DELETE=true)';
      } else {
        errorMsg = errorMsg || 'Delete is disabled (set AUTH_MODE=local or ENABLE_DOC_DELETE=true)';
      }
    } else if (response.status === 404) {
      errorMsg = 'Document not found';
    }

    throw new Error(errorMsg);
  }
}
