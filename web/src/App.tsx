import { useEffect, useState, useRef } from 'react'
import ThemeControls from "./ThemeControls";
import { applyTheme, loadTheme } from "./theme";
import './App.css'
import { uploadFile, doSearch, askQuestion, fetchStatus, fetchDocuments, exportJson, exportZip, apiRequest, fetchJsonPreview, collectionForKind, deleteDocument } from './api'
import { API_BASE } from './api';
import QuickActions from './QuickActions';
import AssistantOutput from './AssistantOutput';
import LLMOnboardingPanel from './LLMOnboardingPanel';
import IngestionActivity from './components/IngestionActivity';
import AskPanel from './components/AskPanel';
import DocumentList from './components/DocumentList';
import DocumentDrawer from './components/DocumentDrawer';

const BUILD_STAMP = "beast-2 / 2025-12-23 / commit 39ed9bb";

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
  // LLM status
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
}
type Hit = { id: string; score: number; text?: string; caption?: string; path?: string; idx?: number; kind?: string; document_id?: string }

type Document = { document_id: string; kinds: string[]; paths: string[]; counts: Record<string, number> }
const apiBase = API_BASE
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer?: string; final?: string; sources?: Hit[]; answers?: Hit[]; error?: string }

type IngestionEvent = {
  timestamp: number; // Date.now()
  filename: string;
  status: 'uploading' | 'indexing' | 'processed' | 'skipped' | 'error';
  chunks?: number;
  skip_reason?: string;
  skip_message?: string;
  error?: string;
  document_id?: string; // short version (first 8 chars)
}


function HealthChip() {
  const [state, setState] = useState<"checking"|"ok"|"warn">("checking");
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/health/full`, { method: "GET" });
        if (!alive) return;
        setState(r.ok ? "ok" : "warn");
      } catch { setState("warn"); }
    })();
    return () => { alive = false; };
  }, []);
  const bg = state==="ok" ? "#c6f6d5" : state==="checking" ? "#fefcbf" : "#fed7d7";
  const label = state==="ok" ? "API: healthy" : state==="checking" ? "API: checking" : "API: unreachable";
  return <span style={{background:bg, padding:"2px 8px", borderRadius:12, fontSize:12, marginLeft:8}}>{label}</span>;
}

function LLMChip({ status }: { status: Status | null }) {
  if (!status || !status.llm) {
    return null; // Non-blocking: show nothing if LLM status is missing
  }

  const provider = status.llm.provider || "none";
  const reachable = status.llm.reachable === true;

  // Determine state: on, offline, or off
  let isOn = false;
  let isOffline = false;
  let label = "LLM: off";

  if (provider === "ollama") {
    if (reachable) {
      isOn = true;
      label = "LLM: on (ollama)";
    } else {
      isOffline = true;
      label = "LLM: offline";
    }
  }

  const bg = isOn ? "#e0f2fe" : isOffline ? "#fef3c7" : "#f3f4f6";
  const color = isOn ? "#0369a1" : isOffline ? "#92400e" : "#6b7280";
  const borderColor = isOn ? "#bae6fd" : isOffline ? "#fde68a" : "#d1d5db";

  return <span style={{background:bg, color:color, padding:"2px 8px", borderRadius:12, fontSize:12, marginLeft:8, border:`1px solid ${borderColor}`}}>{label}</span>;
}

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
    const s = await fetchStatus().catch(() => null);
    const total = s?.counts?.total ?? 0;
    if (total > oldTotal) return { ok: true, total };
    await sleep(intervalMs);
  }
  return { ok: false };
}

async function waitForDocumentIndexed(document_id: string, timeoutMs = 15000): Promise<{ok: boolean, chunks?: number}> {
  const t0 = Date.now();
  const pollInterval = 1500; // Poll every 1.5 seconds
  while (Date.now() - t0 < timeoutMs) {
    if (!visible()) { await sleep(500); continue; }
    try {
      const docs = await fetchDocuments();
      const doc = docs.find((d: Document) => d.document_id === document_id);
      if (doc) {
        // Calculate total chunks from counts object
        const totalChunks = Object.values(doc.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
        if (totalChunks > 0) {
          return { ok: true, chunks: totalChunks };
        }
      }
    } catch (err) {
      // Continue polling on error
    }
    await sleep(pollInterval);
  }
  return { ok: false };
}


async function downloadZip(documentId: string, collection: string = 'jsonify2ai_chunks') {
  try {
    const url = `/export/archive?document_id=${encodeURIComponent(documentId)}&collection=${encodeURIComponent(collection)}`
    const response = await apiRequest(url, { method: 'GET' }, true)
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`)
    }
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    window.open(blobUrl, '_blank')
    // Clean up blob URL after a delay
    setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000)
  } catch (err) {
    console.error('Export ZIP failed:', err)
  }
}

function collectionForDoc(d: Document) {
  return (d.kinds || []).includes("image") ? "jsonify2ai_images_768" : "jsonify2ai_chunks";
}

function getDocumentStatus(doc: Document): 'indexed' | 'pending' {
  const totalChunks = Object.values(doc.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
  return totalChunks > 0 ? 'indexed' : 'pending';
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

function generateSuggestionChips(
  askScope: 'doc' | 'all',
  activeDoc: Document | null
): string[] {
  if (askScope === 'doc' && activeDoc) {
    // Get filename and extension
    const path = activeDoc.paths[0] || '';
    const filename = path.split('/').pop() || path;
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const kind = activeDoc.kinds[0] || 'text';

    // Generate file-type-specific prompts
    if (ext === 'md' || ext === 'txt' || kind === 'text') {
      return [
        `Summarize ${filename}`,
        `What are the key points in ${filename}?`,
        `Extract action items from ${filename}`,
        `Create a checklist from ${filename}`,
        `What is the main topic of ${filename}?`
      ];
    } else if (ext === 'pdf' || kind === 'pdf') {
      return [
        `Summarize ${filename}`,
        `What are the key requirements in ${filename}?`,
        `Extract important points from ${filename}`,
        `What topics are covered in ${filename}?`,
        `Create a glossary from ${filename}`
      ];
    } else {
      // Generic for other types
      return [
        `Summarize ${filename}`,
        `What are the key points in ${filename}?`,
        `Extract important information from ${filename}`
      ];
    }
  } else {
    // Global scope: retrieval-first questions
    return [
      "Which documents mention this topic?",
      "Show the best matching excerpts about this",
      "List top related files for this query",
      "Find documents containing this information",
      "What files discuss this subject?"
    ];
  }
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
  const [askError, setAskError] = useState<string | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [lastDoc, setLastDoc] = useState<{id:string, kind:string} | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [recentDocs, setRecentDocs] = useState<Hit[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [askLoading, setAskLoading] = useState(false)
  const [previewDocId, setPreviewDocId] = useState<string | null>(null)
  const [previewLines, setPreviewLines] = useState<string[] | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [quickActionResult, setQuickActionResult] = useState<AskResp | null>(null)
  const [quickActionsLoading, setQuickActionsLoading] = useState<string | null>(null)
  const [quickActionName, setQuickActionName] = useState<string | null>(null)
  const [quickActionError, setQuickActionError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<{
    filename: string;
    status: 'uploading' | 'processed' | 'skipped' | 'error' | 'indexing';
    document_id?: string;
    chunks?: number;
    skip_reason?: string;
    error?: string;
  } | null>(null)
  const [activityFeed, setActivityFeed] = useState<IngestionEvent[]>([])
  const [showDropzoneHelp, setShowDropzoneHelp] = useState(false)
  const [activeDocId, setActiveDocId] = useState<string | null>(null)
  const [askScope, setAskScope] = useState<'doc' | 'all'>('all')
  const [answerMode, setAnswerMode] = useState<'retrieve' | 'synthesize'>('retrieve')
  const [showWhatIsThis, setShowWhatIsThis] = useState(false)
  const [docSearchFilter, setDocSearchFilter] = useState('')
  const [docSortBy, setDocSortBy] = useState<'newest' | 'oldest' | 'most-chunks'>('newest')
  const [openMenuDocId, setOpenMenuDocId] = useState<string | null>(null)
  const [drawerDocId, setDrawerDocId] = useState<string | null>(null)
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set())
  const currentFetchDocIdRef = useRef<string | null>(null)
  const askInputRef = useRef<HTMLInputElement>(null)

  // Apply saved theme on mount
  useEffect(() => { try { applyTheme(loadTheme()); } catch {} }, [])

  // Log build stamp on app start
  useEffect(() => {
    console.log("[jsonify2ai] BUILD:", BUILD_STAMP);
  }, [])

  function showToast(msg: string, isError = false) {
    setToast(msg);
    setTimeout(() => setToast(null), isError ? 5000 : 3000);
  }

  // Activity feed localStorage helpers
  const ACTIVITY_STORAGE_KEY = "jsonify2ai.activity";
  const MAX_ACTIVITY_EVENTS = 10;

  function loadActivityFeed(): IngestionEvent[] {
    try {
      const raw = localStorage.getItem(ACTIVITY_STORAGE_KEY);
      if (raw) {
        const events = JSON.parse(raw) as IngestionEvent[];
        // Limit to MAX_ACTIVITY_EVENTS, newest first
        return events.slice(0, MAX_ACTIVITY_EVENTS);
      }
    } catch {}
    return [];
  }

  function saveActivityFeed(events: IngestionEvent[]) {
    try {
      // Limit to MAX_ACTIVITY_EVENTS, newest first
      const limited = events.slice(0, MAX_ACTIVITY_EVENTS);
      localStorage.setItem(ACTIVITY_STORAGE_KEY, JSON.stringify(limited));
    } catch {}
  }

  function addActivityEvent(event: IngestionEvent) {
    setActivityFeed(prev => {
      // Add new event at the beginning (newest first)
      const updated = [event, ...prev].slice(0, MAX_ACTIVITY_EVENTS);
      saveActivityFeed(updated);
      return updated;
    });
  }

  function updateActivityEvent(filename: string, updates: Partial<IngestionEvent>) {
    setActivityFeed(prev => {
      // Find the first (most recent) event with matching filename
      const index = prev.findIndex(e => e.filename === filename);
      if (index === -1) {
        // Event not found, return unchanged
        return prev;
      }
      // Update only the first matching event (most recent)
      const updated = [...prev];
      updated[index] = { ...updated[index], ...updates };
      saveActivityFeed(updated);
      return updated;
    });
  }

  function clearActivityFeed() {
    setActivityFeed([]);
    try {
      localStorage.removeItem(ACTIVITY_STORAGE_KEY);
    } catch {}
  }

  // Active document localStorage helpers
  const ACTIVE_DOC_STORAGE_KEY = "jsonify2ai.activeDoc";
  const ASK_SCOPE_STORAGE_KEY = "jsonify2ai.askScope";
  const ANSWER_MODE_STORAGE_KEY = "jsonify2ai.answerMode";

  function loadActiveDocId(): string | null {
    try {
      const raw = localStorage.getItem(ACTIVE_DOC_STORAGE_KEY);
      if (raw) {
        return raw;
      }
    } catch {}
    return null;
  }

  function saveActiveDocId(docId: string | null) {
    try {
      if (docId) {
        localStorage.setItem(ACTIVE_DOC_STORAGE_KEY, docId);
      } else {
        localStorage.removeItem(ACTIVE_DOC_STORAGE_KEY);
      }
    } catch {}
  }

  function loadAskScope(): 'doc' | 'all' {
    try {
      const raw = localStorage.getItem(ASK_SCOPE_STORAGE_KEY);
      if (raw === 'doc' || raw === 'all') {
        return raw;
      }
    } catch {}
    return 'all'; // Default to 'all' for backward compatibility
  }

  function saveAskScope(scope: 'doc' | 'all') {
    try {
      localStorage.setItem(ASK_SCOPE_STORAGE_KEY, scope);
    } catch {}
  }

  function loadAnswerMode(llmReachable: boolean, scope: 'doc' | 'all'): 'retrieve' | 'synthesize' {
    try {
      // Use scope-specific key to store preferences per scope
      const scopeKey = `${ANSWER_MODE_STORAGE_KEY}.${scope}`;
      const raw = localStorage.getItem(scopeKey);
      if (raw === 'retrieve' || raw === 'synthesize') {
        // If LLM is off, force retrieve
        if (!llmReachable && raw === 'synthesize') {
          return 'retrieve';
        }
        return raw;
      }
    } catch {}
    // Default behavior based on scope and LLM
    if (scope === 'all') {
      return 'retrieve';
    } else {
      // Doc scope: synthesize if LLM is on, else retrieve
      return llmReachable ? 'synthesize' : 'retrieve';
    }
  }

  function saveAnswerMode(mode: 'retrieve' | 'synthesize', scope: 'doc' | 'all') {
    try {
      // Store preference per scope
      const scopeKey = `${ANSWER_MODE_STORAGE_KEY}.${scope}`;
      localStorage.setItem(scopeKey, mode);
    } catch {}
  }

  // Helper function to get active document based on priority
  // When strictMode is true (doc scope), only returns doc if explicitly selected (previewDocId or activeDocId)
  function getActiveDocument(strictMode: boolean = false): Document | null {
    // Priority 1: previewDocId if exists and doc found
    if (previewDocId) {
      const doc = docs.find(d => d.document_id === previewDocId);
      if (doc) return doc;
    }
    // Priority 2: activeDocId from state if set and doc exists
    if (activeDocId) {
      const doc = docs.find(d => d.document_id === activeDocId);
      if (doc) return doc;
    }
    // Priority 3: Most recent doc (first in list) - only if not in strict mode
    if (!strictMode && docs.length > 0) {
      return docs[0];
    }
    return null;
  }

  const handleQuickActionComplete = (result: AskResp, actionName: string) => {
    setQuickActionResult(result);
    setQuickActionName(actionName);
    setQuickActionsLoading(null);
    setQuickActionError(null); // Clear any previous errors on success
  }

  const handleQuickActionError = (error: string, actionName: string) => {
    // If error is empty string, clear the error state (used when starting new action)
    if (error === '') {
      setQuickActionError(null);
      setQuickActionResult(null);
      return;
    }
    setQuickActionError(error);
    setQuickActionName(actionName);
    setQuickActionsLoading(null);
    setQuickActionResult(null); // Clear any previous results on error
  }

  useEffect(() => {
    loadStatus()
    loadDocuments()
    loadRecentDocuments()
    // Load activity feed from localStorage
    const saved = loadActivityFeed();
    setActivityFeed(saved);
    // Load active doc and scope from localStorage
    const savedActiveDoc = loadActiveDocId();
    const savedScope = loadAskScope();
    setActiveDocId(savedActiveDoc);
    setAskScope(savedScope);
    // Load answerMode (will be updated when status loads)
    const llmReachable = s?.llm?.reachable === true;
    const initialAnswerMode = loadAnswerMode(llmReachable, savedScope);
    setAnswerMode(initialAnswerMode);
  }, [])

  // Update answerMode when scope or LLM status changes
  useEffect(() => {
    const llmReachable = s?.llm?.reachable === true;
    const newMode = loadAnswerMode(llmReachable, askScope);
    // Only update if different to avoid unnecessary saves
    if (newMode !== answerMode) {
      setAnswerMode(newMode);
      saveAnswerMode(newMode, askScope);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askScope, s?.llm?.reachable])

  // Validate activeDocId exists in docs list after docs load
  useEffect(() => {
    if (activeDocId) {
      if (docs.length === 0) {
        // All documents deleted, clear activeDocId and reset scope
        setActiveDocId(null);
        saveActiveDocId(null);
        if (askScope === 'doc') {
          setAskScope('all');
          saveAskScope('all');
        }
      } else {
        // Check if the active doc still exists
        const docExists = docs.some(d => d.document_id === activeDocId);
        if (!docExists) {
          // Active doc no longer exists, clear it
          setActiveDocId(null);
          saveActiveDocId(null);
          // Reset askScope to 'all' if it was set to 'doc'
          if (askScope === 'doc') {
            setAskScope('all');
            saveAskScope('all');
          }
        }
      }
    }
  }, [docs, activeDocId, askScope])

  // Close overflow menu on outside click
  useEffect(() => {
    if (openMenuDocId) {
      const handleClickOutside = (e: MouseEvent) => {
        const target = e.target as HTMLElement;
        if (!target.closest('[data-menu-container]')) {
          setOpenMenuDocId(null);
        }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [openMenuDocId])

  // Close drawer if document no longer exists
  useEffect(() => {
    if (drawerDocId) {
      const docExists = docs.some(d => d.document_id === drawerDocId);
      if (!docExists) {
        setDrawerDocId(null);
      }
    }
  }, [drawerDocId, docs])

  const loadStatus = async () => {
    const j = await fetchStatus()
    setS(j)
  }

  const loadDocuments = async (): Promise<Document[]> => {
    try {
      const j = await fetchDocuments()
      setDocs(j)
      return j
    } catch (err: any) {
      // Log detailed error information for debugging
      const errorMsg = err?.message || String(err);
      const statusMatch = errorMsg.match(/HTTP (\d+)/);
      const statusCode = statusMatch ? statusMatch[1] : 'unknown';

      console.error('Failed to fetch documents:', {
        error: errorMsg,
        statusCode: statusCode,
        fullError: err
      });

      // Set docs to empty array to avoid showing stale data
      setDocs([]);

      // Show user-friendly error message
      if (statusCode === '401' || statusCode === '403') {
        showToast('Failed to load documents: Authentication required', true);
      } else if (statusCode === '500') {
        showToast('Failed to load documents: Server error', true);
      } else {
        showToast(`Failed to load documents: ${errorMsg}`, true);
      }
      return []
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

  const handleAsk = async () => {
    if (!askQ.trim()) {
      showToast("Please enter a question", true);
      return;
    }

    // Check scope: if "doc" and no active doc, show toast and return
    if (askScope === 'doc') {
      const activeDoc = getActiveDocument(true); // strictMode = true for doc scope
      if (!activeDoc) {
        showToast("Preview or upload a document first", true);
        return;
      }
    }

    setAskLoading(true);
    setAskError(null);
    try {
      // Determine documentId based on scope
      const documentId = askScope === 'doc' ? getActiveDocument(true)?.document_id : undefined; // strictMode = true for doc scope
      const j: AskResp = await askQuestion(askQ, 6, documentId, answerMode);
      if (j.ok === false) {
        const errorMsg = j.error === "rate_limited"
          ? "Rate limited — try again in a few seconds."
          : `Ask failed: ${j.error || 'Unknown error'}`;
        setAskError(errorMsg);
        setAns(null);
        if (j.error === "rate_limited") {
          showToast(errorMsg, true);
        }
      } else {
        setAns(j);
        setAskError(null);
      }
    } catch (err: any) {
      // Check if it's a 429 rate limit error
      const errorMsg = (err?.status === 429 || err?.errorData?.error === "rate_limited")
        ? "Rate limited — try again in a few seconds."
        : `Ask error: ${err?.message || err}`;
      setAskError(errorMsg);
      setAns(null);
      if (err?.status === 429 || err?.errorData?.error === "rate_limited") {
        showToast(errorMsg, true);
      }
    } finally {
      setAskLoading(false);
    }
  };

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

  const handleBulkDelete = async () => {
    const userInput = window.prompt(`Type "DELETE" to confirm deletion of ${selectedDocIds.size} document(s):`);
    if (userInput !== 'DELETE') {
      return;
    }

    const ids = Array.from(selectedDocIds);
    let successCount = 0;
    let failCount = 0;
    let deleteDisabled = false;

    for (let i = 0; i < ids.length; i++) {
      const docId = ids[i];
      const doc = docs.find(d => d.document_id === docId);
      const filename = doc?.paths[0] ? doc.paths[0].split('/').pop() || doc.paths[0] : docId;
      try {
        showToast(`Deleting ${filename}... (${i + 1}/${ids.length})`);
        await deleteDocument(docId);
        successCount++;
        if (activeDocId === docId) {
          setActiveDocId(null);
          saveActiveDocId(null);
          if (askScope === 'doc') {
            setAskScope('all');
            saveAskScope('all');
          }
        }
        if (previewDocId === docId) {
          setPreviewDocId(null);
          setPreviewLines(null);
          setPreviewError(null);
        }
        if (drawerDocId === docId) {
          setDrawerDocId(null);
        }
        if (openMenuDocId === docId) {
          setOpenMenuDocId(null);
        }
      } catch (err: any) {
        failCount++;
        const errorMsg = err?.message || err;
        if (errorMsg.includes('not enabled') || errorMsg.includes('403')) {
          showToast('Delete not enabled. Set AUTH_MODE=local or ENABLE_DOC_DELETE=true', true);
          deleteDisabled = true;
          break; // Stop if delete is not enabled
        } else {
          showToast(`Failed to delete ${filename}: ${errorMsg}`, true);
        }
      }
    }
    // Refresh documents list once after all deletions complete
    if (successCount > 0 || failCount > 0) {
      await loadDocuments();
    }
    if (successCount > 0) {
      showToast(`Deleted ${successCount} document(s)${failCount > 0 ? `, ${failCount} failed` : ''}`);
    }
    if (!deleteDisabled) {
      setSelectedDocIds(new Set());
    }
  }

  async function loadDemoData(skipLoadingState: boolean = false) {
    if (!skipLoadingState) {
      setDemoLoading(true);
    }
    const demoFiles = [
      {
        name: 'demo_qdrant.md',
        content: `# Qdrant in jsonify2ai

Qdrant is the vector database used by jsonify2ai for semantic search.

## Key Features

- **768-dimensional vectors**: All text chunks are embedded into 768-dim vectors using nomic-embed-text
- **Semantic search**: Enables natural language queries that find relevant content by meaning, not just keywords
- **Collection structure**:
  - \`jsonify2ai_chunks_768\` for text/PDF/audio chunks
  - \`jsonify2ai_images_768\` for image embeddings (when IMAGES_CAPTION is enabled)

## How it works

When you upload a file, the worker:
1. Splits content into chunks
2. Generates embeddings (768-dim vectors)
3. Stores chunks + vectors in Qdrant
4. Makes them searchable via the /search and /ask endpoints

The Search and Ask features both query the same Qdrant collections to find relevant chunks.`
      },
      {
        name: 'demo_export.md',
        content: `# Export Features

jsonify2ai provides two export formats for your indexed documents.

## Export JSON

Downloads a JSONL file containing all chunks for a document:
- Each line is one JSON object
- Fields include: \`id\`, \`document_id\`, \`text\`, \`path\`, \`idx\`, \`meta\`
- Use this to inspect the exact data stored in Qdrant

## Export ZIP

Downloads a ZIP archive containing:
- \`export_<document_id>.jsonl\` - All chunks (same as JSON export)
- \`manifest.json\` - Document metadata (paths, counts, kinds)
- Original source file (if available in the data directory)

The manifest.json includes:
- \`document_id\`: Unique identifier
- \`paths\`: Array of source file paths
- \`kinds\`: Array of content types (text, image, etc.)
- \`counts\`: Object with chunk/image counts per kind

Use Export ZIP when you need a complete snapshot of a document with its metadata.`
      },
      {
        name: 'demo_env_toggles.md',
        content: `# Environment Toggles

jsonify2ai supports several environment variables to control behavior during development and testing.

## Embedding Toggles

- **EMBED_DEV_MODE**: Set to \`1\` to skip embeddings and use dummy vectors. Useful for testing without running embedding models.
- **EMBEDDINGS_MODEL**: Model name for embeddings (default: \`nomic-embed-text\`)

## Audio Toggles

- **AUDIO_DEV_MODE**: Set to \`1\` to skip audio transcription. Audio files will be ingested but not transcribed.

## Image Toggles

- **IMAGES_CAPTION**: Set to \`1\` to enable image captioning. When enabled, images are processed and stored in \`jsonify2ai_images_768\` collection.

## LLM Toggles

- **LLM_PROVIDER**: Set to \`ollama\` to enable LLM synthesis for Ask feature
- **OLLAMA_HOST**: Ollama service URL (default: \`http://localhost:11434\`)
- **OLLAMA_MODEL**: Model name for Ask synthesis (default: \`qwen2.5:3b-instruct-q4_K_M\`)
- **ASK_MODE**: Control Ask behavior (\`search\` or \`llm\`)

## Auth Toggles

- **AUTH_MODE**: \`local\` (no auth) or \`strict\` (requires tokens)

These toggles make it easy to test different features without changing code.`
      }
    ];

    try {
      const s0 = await fetchStatus().catch(() => ({counts:{total:0}}))
      const baseTotal = s0?.counts?.total ?? 0
      let lastDocId: string | undefined = undefined;
      let lastFileName: string | undefined = undefined;
      let currentTotal = baseTotal;

      for (let i = 0; i < demoFiles.length; i++) {
        const demo = demoFiles[i];
        showToast(`Loading demo doc ${i + 1}/${demoFiles.length}...`);

        // Update upload result for current file
        setUploadResult({
          filename: demo.name,
          status: 'uploading'
        });

        // Add activity event for upload start
        addActivityEvent({
          timestamp: Date.now(),
          filename: demo.name,
          status: 'uploading'
        });

        // Create Blob and File object
        const blob = new Blob([demo.content], { type: 'text/markdown' });
        const file = new File([blob], demo.name, { type: 'text/markdown' });

        // Upload using existing uploadFile function
        const data = await uploadFile(file);

        // Handle skipped files
        if (data?.skipped === true || (data?.ok === true && data?.accepted === false)) {
          const skipReason = data?.skip_reason || "unknown";
          const details = data?.details || "File was skipped";
          setUploadResult({
            filename: demo.name,
            status: 'skipped',
            skip_reason: skipReason,
            error: details
          });
          // Update activity event for skipped
          updateActivityEvent(demo.name, {
            status: 'skipped',
            skip_reason: skipReason,
            skip_message: details
          });
          throw new Error(`Demo upload skipped: ${details}`);
        }

        // Check for upload errors
        if (data?.ok === false || data?.error) {
          const errorMsg = data?.error || String(data);
          setUploadResult({
            filename: demo.name,
            status: 'error',
            error: errorMsg
          });
          // Update activity event for error
          updateActivityEvent(demo.name, {
            status: 'error',
            error: errorMsg
          });
          throw new Error(`Demo upload failed: ${errorMsg}`);
        }

        const docId = data?.document_id as string | undefined;
        if (docId) {
          lastDocId = docId;
          lastFileName = demo.name;

          // Update status to indexing
          setUploadResult({
            filename: demo.name,
            status: 'indexing',
            document_id: docId,
            chunks: data?.chunks || 0
          });

          // Update activity event for indexing
          updateActivityEvent(demo.name, {
            status: 'indexing',
            document_id: docId.substring(0, 8)
          });
        }

        // Wait for processing before next upload
        if (i < demoFiles.length - 1) {
          const done = await waitForProcessed(currentTotal, 20000, 4000);
          if (done.ok) {
            currentTotal = done.total;
          }
        }
      }

      // Wait for final processing and check indexing status
      if (lastDocId && lastFileName) {
        setUploadResult({
          filename: lastFileName,
          status: 'indexing',
          document_id: lastDocId
        });

        const indexed = await waitForDocumentIndexed(lastDocId, 15000);

        if (indexed.ok && indexed.chunks !== undefined) {
          setUploadResult({
            filename: lastFileName,
            status: 'processed',
            document_id: lastDocId,
            chunks: indexed.chunks
          });

          // Update activity event for processed
          updateActivityEvent(lastFileName, {
            status: 'processed',
            chunks: indexed.chunks,
            document_id: lastDocId.substring(0, 8)
          });

          showToast("Demo data loaded ✓");
        } else {
          setUploadResult({
            filename: lastFileName,
            status: 'indexing',
            document_id: lastDocId
          });
          showToast("Demo data uploaded (still indexing…)", true);
        }
      } else {
        const finalDone = await waitForProcessed(currentTotal, 20000, 4000);
        if (finalDone.ok) {
          showToast("Demo data loaded ✓");
        } else {
          showToast("Demo data uploaded (processing may still be in progress)", true);
        }
      }

      // Refresh documents and update activity events for all demo files
      const refreshedDocsBefore = await loadDocuments();
      for (let i = 0; i < demoFiles.length; i++) {
        const demo = demoFiles[i];
        // Find the document for this demo file
        const demoDoc = refreshedDocsBefore.find(d => d.paths.some(p => p.includes(demo.name)));
        if (demoDoc) {
          const totalChunks = Object.values(demoDoc.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
          if (totalChunks > 0) {
            // Update activity event for processed if not already updated
            updateActivityEvent(demo.name, {
              status: 'processed',
              chunks: totalChunks,
              document_id: demoDoc.document_id.substring(0, 8)
            });
          }
        }
      }

      // Refresh documents list
      const refreshedDocs = await loadDocuments();

      // Auto-preview the last uploaded doc
      if (lastDocId) {
        const uploadedDoc = refreshedDocs.find(d => d.document_id === lastDocId);
        if (uploadedDoc) {
          const collection = collectionForDoc(uploadedDoc);
          const requestedDocId = uploadedDoc.document_id;
          currentFetchDocIdRef.current = requestedDocId;
          setPreviewDocId(requestedDocId);
          // Set as active document
          setActiveDocId(requestedDocId);
          saveActiveDocId(requestedDocId);
          // Auto-switch to document scope
          setAskScope('doc');
          saveAskScope('doc');
          setPreviewLoading(true);
          setPreviewError(null);
          setPreviewLines(null);
          try {
            const result = await fetchJsonPreview(requestedDocId, collection, 5);
            if (currentFetchDocIdRef.current === requestedDocId) {
              setPreviewLines(result.lines);
            }
          } catch (err: any) {
            if (currentFetchDocIdRef.current === requestedDocId) {
              setPreviewError(err?.message || 'Failed to load JSON preview');
            }
          } finally {
            if (currentFetchDocIdRef.current === requestedDocId) {
              setPreviewLoading(false);
            }
          }
        }
      }
    } catch (err: any) {
      const errorMsg = err?.message || String(err);
      if (uploadResult) {
        setUploadResult({
          ...uploadResult,
          status: 'error',
          error: errorMsg
        });
      }
      showToast(`Demo load failed: ${errorMsg}. Check API/worker logs for details.`, true);
    } finally {
      if (!skipLoadingState) {
        setDemoLoading(false);
      }
    }
  }

  async function handleStartHere() {
    setDemoLoading(true);
    try {
      // Check if demo docs already exist
      const currentDocs = await loadDocuments();
      const demoDocs = currentDocs.filter(d => d.paths.some(p => p.includes('demo_')));

      let targetDocId: string | null = null;

      if (demoDocs.length > 0) {
        // Demo docs exist, use the most recent one (first in list)
        targetDocId = demoDocs[0].document_id;
        showToast("Using existing demo data");
      } else {
        // No demo docs, load them
        // Pass skipLoadingState=true so handleStartHere manages the loading state
        await loadDemoData(true);
        // After loadDemoData completes, refresh docs to get the new ones
        const refreshedDocs = await loadDocuments();
        const newDemoDocs = refreshedDocs.filter(d => d.paths.some(p => p.includes('demo_')));
        if (newDemoDocs.length > 0) {
          targetDocId = newDemoDocs[0].document_id;
        }
      }

      // Set up the active document, preview, scope, and answer mode
      if (targetDocId) {
        const targetDoc = (await loadDocuments()).find(d => d.document_id === targetDocId);
        if (targetDoc) {
          const collection = collectionForDoc(targetDoc);
          currentFetchDocIdRef.current = targetDocId;
          setPreviewDocId(targetDocId);
          setActiveDocId(targetDocId);
          saveActiveDocId(targetDocId);
          setAskScope('doc');
          saveAskScope('doc');

          // Set answer mode based on LLM availability
          const llmReachable = s?.llm?.reachable === true;
          const newAnswerMode = llmReachable ? 'synthesize' : 'retrieve';
          setAnswerMode(newAnswerMode);
          saveAnswerMode(newAnswerMode, 'doc');

          // Load preview
          setPreviewLoading(true);
          setPreviewError(null);
          setPreviewLines(null);
          try {
            const result = await fetchJsonPreview(targetDocId, collection, 5);
            if (currentFetchDocIdRef.current === targetDocId) {
              setPreviewLines(result.lines);
            }
          } catch (err: any) {
            if (currentFetchDocIdRef.current === targetDocId) {
              setPreviewError(err?.message || 'Failed to load JSON preview');
            }
          } finally {
            if (currentFetchDocIdRef.current === targetDocId) {
              setPreviewLoading(false);
            }
          }

          // Scroll to Ask panel and focus input
          setTimeout(() => {
            askInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
              askInputRef.current?.focus();
            }, 300);
          }, 100);
        }
      } else {
        showToast("No demo document found", true);
      }
    } catch (err: any) {
      const errorMsg = err?.message || String(err);
      showToast(`Start Here failed: ${errorMsg}`, true);
    } finally {
      setDemoLoading(false);
    }
  }

  async function onUploadChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    const file = e.target.files[0]
    setUploadBusy(true)

    // Initialize upload result state
    setUploadResult({
      filename: file.name,
      status: 'uploading'
    })

    // Add activity event for upload start
    addActivityEvent({
      timestamp: Date.now(),
      filename: file.name,
      status: 'uploading'
    });

    try {
      const data = await uploadFile(file);

      // Handle skipped files
      if (data?.skipped === true || (data?.ok === true && data?.accepted === false)) {
        const skipReason = data?.skip_reason || "unknown";
        const details = data?.details || "File was skipped";

        setUploadResult({
          filename: file.name,
          status: 'skipped',
          skip_reason: skipReason,
          error: details
        });

        // Update activity event for skipped
        updateActivityEvent(file.name, {
          status: 'skipped',
          skip_reason: skipReason,
          skip_message: details
        });

        showToast("File skipped. See upload results below.", true);
        return;
      }

      // Handle upload errors
      if (data?.ok === false || data?.error) {
        const errorMsg = data?.error || String(data);
        setUploadResult({
          filename: file.name,
          status: 'error',
          error: errorMsg
        });

        // Update activity event for error
        updateActivityEvent(file.name, {
          status: 'error',
          error: errorMsg
        });

        if (errorMsg.includes("rate_limited") || errorMsg.includes("429")) {
          showToast("Rate limited — try again in a few seconds.", true);
        } else {
          showToast(`Upload failed: ${errorMsg}`, true);
        }
        return;
      }

      // if API returns worker JSON, we'll have document_id and collection
      const docId = data?.document_id as string | undefined;
      const coll  = (data?.collection || "") as string;
      const kind  = coll.includes("images") ? "image" : "text"; // images vs chunks

      if (docId) {
        setLastDoc({ id: docId, kind });

        // Update status to indexing
        setUploadResult({
          filename: file.name,
          status: 'indexing',
          document_id: docId,
          chunks: data?.chunks || 0
        });

        // Update activity event for indexing
        updateActivityEvent(file.name, {
          status: 'indexing',
          document_id: docId.substring(0, 8)
        });

        // Poll for document indexing
        const indexed = await waitForDocumentIndexed(docId, 15000);

        if (indexed.ok && indexed.chunks !== undefined) {
          // Document is indexed
          setUploadResult({
            filename: file.name,
            status: 'processed',
            document_id: docId,
            chunks: indexed.chunks
          });

          // Update activity event for processed
          updateActivityEvent(file.name, {
            status: 'processed',
            chunks: indexed.chunks,
            document_id: docId.substring(0, 8)
          });

          showToast("Processed ✓");

          // Auto-preview: refresh documents and open preview for the uploaded document
          const refreshedDocs = await loadDocuments();
          const uploadedDoc = refreshedDocs.find(d => d.document_id === docId);
          if (uploadedDoc) {
            const collection = collectionForDoc(uploadedDoc);
            const requestedDocId = uploadedDoc.document_id;
            currentFetchDocIdRef.current = requestedDocId;
            setPreviewDocId(requestedDocId);
            // Set as active document
            setActiveDocId(requestedDocId);
            saveActiveDocId(requestedDocId);
            // Auto-switch to document scope
            setAskScope('doc');
            saveAskScope('doc');
            setPreviewLoading(true);
            setPreviewError(null);
            setPreviewLines(null);
            try {
              const result = await fetchJsonPreview(requestedDocId, collection, 5);
              if (currentFetchDocIdRef.current === requestedDocId) {
                setPreviewLines(result.lines);
              }
            } catch (err: any) {
              if (currentFetchDocIdRef.current === requestedDocId) {
                setPreviewError(err?.message || 'Failed to load JSON preview');
              }
            } finally {
              if (currentFetchDocIdRef.current === requestedDocId) {
                setPreviewLoading(false);
              }
            }
          }
        } else {
          // Timeout - document not indexed yet
          setUploadResult({
            filename: file.name,
            status: 'indexing',
            document_id: docId,
            chunks: data?.chunks || 0
          });
          showToast("Uploaded (still indexing…)", true);
        }
      } else {
        // No document_id returned - unexpected
        setUploadResult({
          filename: file.name,
          status: 'error',
          error: "Upload succeeded but no document ID returned"
        });

        // Update activity event for error
        updateActivityEvent(file.name, {
          status: 'error',
          error: "Upload succeeded but no document ID returned"
        });

        showToast("Upload completed but document ID missing.", true);
      }
    } catch (err:any) {
      const errorMsg = err?.message || String(err);
      setUploadResult({
        filename: file.name,
        status: 'error',
        error: errorMsg
      });

      // Update activity event for error
      updateActivityEvent(file.name, {
        status: 'error',
        error: errorMsg
      });

      if (errorMsg.includes("rate_limited") || errorMsg.includes("429")) {
        showToast("Rate limited — try again in a few seconds.", true);
      } else {
        showToast(`Upload failed: ${errorMsg}`, true);
      }
    } finally {
      setUploadBusy(false)
      e.target.value = "" // reset input
    }
  }

  return (
    <div style={{ fontFamily: 'ui-sans-serif', padding: 24, maxWidth: 720, margin: '0 auto', background: 'var(--bg)', color: 'var(--fg)', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>jsonify2ai — Status <HealthChip /><LLMChip status={s} /></h1>
      <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8, fontStyle: 'italic' }}>
        Upload files → JSONL chunks → semantic search → exports
      </div>

      {/* 3-Step How it Works Strip */}
      <div style={{ marginBottom: 16, display: 'flex', gap: 16, flexWrap: 'wrap', padding: 12, background: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' }}>
        <div style={{ flex: '1 1 200px', minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#1976d2' }}>1) Upload</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>Drop files anywhere or use the optional hot folder.</div>
        </div>
        <div style={{ flex: '1 1 200px', minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#1976d2' }}>2) Ask</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>Use This document for precise answers.</div>
        </div>
        <div style={{ flex: '1 1 200px', minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#1976d2' }}>3) Export</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>Download JSONL or a ZIP snapshot.</div>
        </div>
      </div>

      {/* Start Here Button */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={handleStartHere}
          disabled={demoLoading || uploadBusy}
          style={{
            fontSize: 14,
            fontWeight: 600,
            padding: '12px 24px',
            borderRadius: 8,
            border: 'none',
            background: demoLoading || uploadBusy ? '#9ca3af' : '#1976d2',
            color: '#fff',
            cursor: demoLoading || uploadBusy ? 'not-allowed' : 'pointer',
            boxShadow: demoLoading || uploadBusy ? 'none' : '0 2px 4px rgba(0,0,0,0.1)',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            if (!demoLoading && !uploadBusy) {
              e.currentTarget.style.background = '#1565c0';
            }
          }}
          onMouseLeave={(e) => {
            if (!demoLoading && !uploadBusy) {
              e.currentTarget.style.background = '#1976d2';
            }
          }}
        >
          {demoLoading ? 'Loading demo…' : 'Start here'}
        </button>
      </div>

      {/* What is this? Collapsible */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => setShowWhatIsThis(!showWhatIsThis)}
          style={{
            fontSize: 13,
            fontWeight: 500,
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid #e5e7eb',
            background: '#fff',
            color: '#374151',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: '100%',
            textAlign: 'left'
          }}
        >
          <span style={{ transform: showWhatIsThis ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▶</span>
          <span>What is this?</span>
        </button>
        {showWhatIsThis && (
          <div style={{ marginTop: 8, padding: 12, background: '#f9fafb', borderRadius: 6, border: '1px solid #e5e7eb', fontSize: 13, lineHeight: 1.6 }}>
            <ul style={{ margin: 0, paddingLeft: 20, color: '#374151' }}>
              <li style={{ marginBottom: 6 }}>Local-first indexing into JSONL chunks</li>
              <li style={{ marginBottom: 6 }}>Vectors stored in Qdrant for semantic search</li>
              <li style={{ marginBottom: 6 }}>Optional local LLM synthesis (Ollama)</li>
              <li style={{ marginBottom: 8 }}>Export JSON / ZIP for portability</li>
            </ul>
            <div style={{ marginTop: 8, padding: 8, background: '#fef3c7', borderRadius: 4, fontSize: 12, color: '#92400e' }}>
              <strong>Privacy note:</strong> data stays on your machine unless you expose ports publicly.
            </div>
          </div>
        )}
      </div>

      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 16, fontFamily: 'monospace' }}>
        Build: {BUILD_STAMP}
      </div>
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

      {/* Theme controls */}
      <div style={{ marginTop: 10 }}>
        <ThemeControls />
      </div>

      {/* What you're seeing info panel */}
      <div style={{ marginTop: 16, padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#f9fafb' }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>What you're seeing</div>
        <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, lineHeight: 1.6, color: '#374151' }}>
          <li style={{ marginBottom: 4 }}>Uploads are normalized into a unified JSONL schema (chunks).</li>
          <li style={{ marginBottom: 4 }}>Chunks are embedded (768-dim vectors) and stored in Qdrant for semantic search.</li>
          <li style={{ marginBottom: 4 }}>Search + Ask read from the same Qdrant collection.</li>
          <li style={{ marginBottom: 4 }}>The JSON preview and export buttons show you exactly what's in the index.</li>
          <li style={{ marginBottom: 4 }}>If LLM is enabled, 'Answer' is synthesized locally using your chunks as context.</li>
          {s && s.counts && (
            <li style={{ marginBottom: 4, marginTop: 8, fontWeight: 500 }}>
              Currently indexed: {s.counts.total || (s.counts.chunks + s.counts.images)} chunks
            </li>
          )}
        </ul>
      </div>

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
                Watcher triggers: {s.watcher_triggers_total}
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
                      onClick={() => {
                        if (doc.document_id) {
                          copyToClipboard(doc.document_id)
                          showToast('Document ID copied')
                        }
                      }}
                      style={{ fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }}
                    >
                      Copy ID
                    </button>
                    <button
                      onClick={async () => {
                        if (!doc.document_id) return;
                        try {
                          await exportJson(doc.document_id, doc.kind === 'image' ? 'image' : 'text');
                        } catch (err: any) {
                          showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                        }
                      }}
                      style={{ fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }}
                    >
                      Export JSON ({doc.kind === 'image' ? 'images.jsonl' : 'chunks.jsonl'})
                    </button>
                    <button
                      onClick={async () => {
                        if (!doc.document_id) return;
                        try {
                          await exportZip(doc.document_id, doc.kind === 'image' ? 'image' : 'text');
                        } catch (err: any) {
                          showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                        }
                      }}
                      style={{ fontSize: 11, color: '#1976d2', textDecoration: 'underline', padding: '2px 4px' }}
                    >
                      Export ZIP (manifest + JSON)
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
          Upload from anywhere (recommended).
        </div>
      </div>
      <div className="mb-4 flex items-center gap-3">
        <input type="file" onChange={onUploadChange} disabled={uploadBusy || demoLoading} />
        {uploadBusy && <span className="text-sm opacity-70">Uploading…</span>}
        {demoLoading && <span className="text-sm opacity-70">Loading demo data…</span>}
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
        <button
          onClick={() => loadDemoData()}
          disabled={uploadBusy || demoLoading}
          title="Inject a few tiny example docs."
          style={{
            fontSize: 12,
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid #ddd',
            background: demoLoading ? '#f3f4f6' : '#fff',
            color: demoLoading ? '#9ca3af' : '#1976d2',
            cursor: demoLoading ? 'not-allowed' : 'pointer',
            opacity: (uploadBusy || demoLoading) ? 0.6 : 1
          }}
        >
          Load demo data
        </button>
      </div>

      {/* Upload Results Panel */}
      {uploadResult && (
        <div style={{
          padding: 16,
          borderRadius: 12,
          boxShadow: '0 1px 4px rgba(0,0,0,.08)',
          marginBottom: 16,
          background: 'var(--bg)',
          border: '1px solid rgba(0,0,0,.1)'
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, opacity: 0.7 }}>
            Upload results
          </div>
          <div style={{ fontSize: 14, marginBottom: 8 }}>
            <strong>{uploadResult.filename}</strong>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{
              padding: '4px 8px',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 500,
              background:
                uploadResult.status === 'processed' ? '#c6f6d5' :
                uploadResult.status === 'uploading' ? '#dbeafe' :
                uploadResult.status === 'indexing' ? '#fed7aa' :
                uploadResult.status === 'skipped' ? '#fef3c7' :
                '#fed7d7',
              color:
                uploadResult.status === 'processed' ? '#166534' :
                uploadResult.status === 'uploading' ? '#1e40af' :
                uploadResult.status === 'indexing' ? '#92400e' :
                uploadResult.status === 'skipped' ? '#78350f' :
                '#991b1b'
            }}>
              {uploadResult.status === 'processed' ? 'Processed' :
               uploadResult.status === 'uploading' ? 'Uploading…' :
               uploadResult.status === 'indexing' ? 'Indexing…' :
               uploadResult.status === 'skipped' ? 'Skipped' :
               'Error'}
            </span>
            {uploadResult.chunks !== undefined && uploadResult.status === 'processed' && (
              <span style={{ fontSize: 12, opacity: 0.7 }}>
                {uploadResult.chunks} {uploadResult.chunks === 1 ? 'chunk' : 'chunks'}
              </span>
            )}
          </div>
          {uploadResult.skip_reason && (
            <div style={{ fontSize: 12, marginTop: 8, color: '#92400e' }}>
              {uploadResult.skip_reason === 'unsupported_extension' && 'Unsupported file type. Try .txt/.md/.pdf/.csv/.json'}
              {uploadResult.skip_reason === 'empty_file' && 'File is empty'}
              {uploadResult.skip_reason === 'extraction_failed' && `Extraction failed: ${uploadResult.error || 'Check worker logs'}`}
              {uploadResult.skip_reason === 'processing_failed' && `Processing failed: ${uploadResult.error || 'Check worker logs'}`}
              {!['unsupported_extension', 'empty_file', 'extraction_failed', 'processing_failed'].includes(uploadResult.skip_reason) &&
                `Skipped: ${uploadResult.error || uploadResult.skip_reason}`}
            </div>
          )}
          {uploadResult.error && uploadResult.status === 'error' && (
            <div style={{ fontSize: 12, marginTop: 8, color: '#dc2626' }}>
              Upload failed: {uploadResult.error}
            </div>
          )}
          {uploadResult.status === 'indexing' && (
            <div style={{ fontSize: 12, marginTop: 8, color: '#92400e', fontStyle: 'italic' }}>
              Indexing… try Refresh documents
            </div>
          )}
        </div>
      )}

      {/* Ingestion Activity Feed */}
      <IngestionActivity
        activityFeed={activityFeed}
        docs={docs}
        askInputRef={askInputRef}
        onClearActivity={clearActivityFeed}
        onSetActiveDoc={setActiveDocId}
        saveActiveDocId={saveActiveDocId}
        setAskScope={setAskScope}
        saveAskScope={saveAskScope}
        showToast={showToast}
      />

      <div style={{ display: 'flex', gap: 8 }}>
          {(() => {
            const previewedDoc = previewDocId ? docs.find(d => d.document_id === previewDocId) : null;
            const isEnabled = previewedDoc !== null;
            const kind = previewedDoc ? (previewedDoc.kinds.includes('image') ? 'image' : 'text') : 'text';

            return (
              <>
                <button
                  className="text-xs underline opacity-70 hover:opacity-100"
                  disabled={!isEnabled}
                  title={isEnabled ? undefined : "Preview a document first"}
                  onClick={async () => {
                    if (!previewedDoc) return;
                    try {
                      await exportJson(previewedDoc.document_id, kind);
                    } catch (err: any) {
                      showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                    }
                  }}
                  style={{
                    opacity: isEnabled ? 0.7 : 0.3,
                    cursor: isEnabled ? 'pointer' : 'not-allowed'
                  }}
                >
                  Download JSON
                </button>
                <button
                  className="text-xs underline opacity-70 hover:opacity-100"
                  disabled={!isEnabled}
                  title={isEnabled ? undefined : "Preview a document first"}
                  onClick={async () => {
                    if (!previewedDoc) return;
                    try {
                      await exportZip(previewedDoc.document_id, kind);
                    } catch (err: any) {
                      showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                    }
                  }}
                  style={{
                    opacity: isEnabled ? 0.7 : 0.3,
                    cursor: isEnabled ? 'pointer' : 'not-allowed'
                  }}
                >
                  Download ZIP
                </button>
              </>
            );
          })()}
        </div>
      {/* Dropzone/Watcher Help */}
      <div style={{ marginTop: 12, marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
          Dropzone is optional. Watcher only monitors the dropzone folder for new files.
        </div>
        <button
          onClick={() => setShowDropzoneHelp(!showDropzoneHelp)}
          style={{
            fontSize: 11,
            padding: '4px 8px',
            borderRadius: 6,
            border: '1px solid #ddd',
            background: '#fff',
            color: '#1976d2',
            cursor: 'pointer',
            textDecoration: 'underline'
          }}
        >
          Where is dropzone?
        </button>
        {showDropzoneHelp && (
          <div style={{
            marginTop: 8,
            padding: 12,
            borderRadius: 8,
            border: '1px solid #e5e7eb',
            background: '#f9fafb'
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>
              Optional hot folder for auto-ingest
            </div>
            <div style={{ fontSize: 12, marginBottom: 6 }}>
              <strong>Inside Docker:</strong> <code style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: 4 }}>/data/dropzone</code>
            </div>
            <div style={{ fontSize: 12, marginBottom: 8 }}>
              <strong>On your machine:</strong> Host path is configured in docker-compose.yml under the worker volume for /data/dropzone.
            </div>
            <button
              onClick={() => {
                const text = `/data/dropzone\n(Host path configured in docker-compose.yml)`;
                copyToClipboard(text);
                showToast('Dropzone path copied');
              }}
              style={{
                fontSize: 11,
                padding: '4px 8px',
                borderRadius: 6,
                border: '1px solid #ddd',
                background: '#fff',
                color: '#1976d2',
                cursor: 'pointer'
              }}
            >
              Copy dropzone path
            </button>
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, opacity: 0.6, marginTop: 8 }}>
        Works best with: .md, .txt, .pdf, .csv, .json. Other formats may be skipped by the worker.
      </div>
      <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
        Optional: You can also drop files into data/dropzone/ on disk; the watcher will ingest them automatically.
      </div>
      <LLMOnboardingPanel
        status={s}
        onStatusRefresh={loadStatus}
      />
      <AskPanel
        askScope={askScope}
        answerMode={answerMode}
        askQ={askQ}
        askLoading={askLoading}
        activeDocId={activeDocId}
        docs={docs}
        status={s}
        askInputRef={askInputRef}
        onSetAskScope={setAskScope}
        saveAskScope={saveAskScope}
        onSetAnswerMode={setAnswerMode}
        saveAnswerMode={saveAnswerMode}
        onSetAskQ={setAskQ}
        onAsk={handleAsk}
        onClearActive={() => {
          setActiveDocId(null);
          saveActiveDocId(null);
          setAskScope('all');
          saveAskScope('all');
        }}
        onPreviewDoc={async (docId: string, collection: string) => {
          currentFetchDocIdRef.current = docId;
          setPreviewDocId(docId);
          setActiveDocId(docId);
          saveActiveDocId(docId);
          setAskScope('doc');
          saveAskScope('doc');
          setPreviewLoading(true);
          setPreviewError(null);
          setPreviewLines(null);
          try {
            const result = await fetchJsonPreview(docId, collection, 5);
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLines(result.lines);
            }
          } catch (err: any) {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewError(err?.message || 'Failed to load JSON preview');
            }
          } finally {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLoading(false);
            }
          }
        }}
        exportJson={exportJson}
        exportZip={exportZip}
        copyToClipboard={copyToClipboard}
        showToast={showToast}
        getActiveDocument={getActiveDocument}
        collectionForDoc={collectionForDoc}
        generateSuggestionChips={generateSuggestionChips}
      />
      {askScope === 'doc' ? (
          <QuickActions
            previewDocId={previewDocId}
            documents={docs}
            status={s}
            onActionComplete={handleQuickActionComplete}
            onActionError={handleQuickActionError}
            loading={quickActionsLoading}
            setLoading={setQuickActionsLoading}
            showToast={showToast}
            activeDocId={activeDocId}
            askScope={askScope}
            answerMode={answerMode}
          />
        ) : (
          <div style={{ marginTop: 16, marginBottom: 16, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>
            Global mode is for finding relevant documents. Use 'Use this doc' in the results below to enable Quick Actions.
          </div>
        )}
        <AssistantOutput
          result={quickActionResult}
          status={s}
          loading={quickActionsLoading !== null}
          error={quickActionError}
          actionName={quickActionName || undefined}
          showToast={showToast}
          scope={askScope}
          activeDocFilename={(() => {
            if (askScope === 'doc') {
              const activeDoc = getActiveDocument(true); // strictMode = true for doc scope
              if (activeDoc && activeDoc.paths[0]) {
                return activeDoc.paths[0].split('/').pop() || activeDoc.paths[0];
              }
            }
            return undefined;
          })()}
          onUseDoc={(documentId, llmReachable) => {
            setActiveDocId(documentId);
            saveActiveDocId(documentId);
            setAskScope('doc');
            saveAskScope('doc');
            if (llmReachable) {
              setAnswerMode('synthesize');
              saveAnswerMode('synthesize', 'doc');
            }
          }}
          documents={docs}
        />
      {/* Existing Ask results (for backward compatibility) */}
      {askLoading && (
          <div style={{ marginTop: 12, padding: 12, color: '#666', fontSize: 14 }}>
            Searching your data…
          </div>
        )}
        {askError && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #fecaca', borderRadius: 8, background: '#fef2f2', color: '#dc2626', fontSize: 14 }}>
            {askError}
          </div>
        )}
        {!askLoading && !askError && !ans && (
          <div style={{ marginTop: 12, padding: 12, color: '#999', fontSize: 13, fontStyle: 'italic' }}>
            Run a question to see answers and sources here.
          </div>
        )}
        {!askLoading && ans && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }}>
            {(ans.final && ans.final.trim()) || (ans.answer && ans.answer.trim()) ? (
              <div style={{ marginBottom: 16, padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fafafa' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, fontSize: 16 }}>Answer</div>
                  {s && s.llm?.provider === "ollama" && s.llm?.reachable === true ? (
                    <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 999, background: '#eef2ff', color: '#3730a3' }}>local (ollama)</span>
                  ) : (
                    <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 999, background: '#f3f4f6', color: '#6b7280' }}>Top matches below</span>
                  )}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: 14 }}>
                  {ans.final && ans.final.trim() ? ans.final : (ans.answer || '')}
                </div>
              </div>
            ) : null}
            <div>
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12 }}>Sources</div>
              {(() => {
                const sources = ans.sources || ans.answers || [];
                if (sources.length === 0) {
                  return (
                    <div style={{ color: '#666', fontSize: 14, padding: 12, background: '#f9fafb', borderRadius: 6 }}>
                      No matching snippets yet. Try a different query or upload more files.
                    </div>
                  );
                }
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {sources.map((h, i) => {
                      const filename = h.path ? h.path.split('/').pop() || h.path : (h.id || `Source ${i + 1}`);
                      const docId = h.document_id ? h.document_id.substring(0, 12) : null;
                      const snippet = h.text || h.caption || '';
                      const score = h.score !== undefined ? h.score : null;

                      return (
                        <div key={i} style={{ padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 500, fontSize: 13 }}>{filename}</span>
                            {docId && (
                              <code style={{ fontSize: 11, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
                                {docId}...
                              </code>
                            )}
                            {score !== null && (
                              <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: '#f0f9ff', color: '#0369a1' }}>
                                score: {score.toFixed(2)}
                              </span>
                            )}
                          </div>
                          {snippet && (
                            <div style={{
                              fontSize: 13,
                              lineHeight: 1.5,
                              color: '#374151',
                              fontFamily: 'ui-monospace, monospace',
                              background: '#f9fafb',
                              padding: 8,
                              borderRadius: 4,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word'
                            }}>
                              {snippet}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          </div>
        )}
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
                    onClick={async () => {
                      if (!h.document_id) return;
                      try {
                        await exportJson(h.document_id, h.kind === 'image' ? 'image' : 'text');
                      } catch (err: any) {
                        showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                      }
                    }}
                  >
                    Export JSON ({h.kind === 'image' ? 'images.jsonl' : 'chunks.jsonl'})
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <DocumentList
        docs={docs}
        activeDocId={activeDocId}
        previewDocId={previewDocId}
        selectedDocIds={selectedDocIds}
        openMenuDocId={openMenuDocId}
        docSearchFilter={docSearchFilter}
        docSortBy={docSortBy}
        onSetActiveDoc={(docId: string) => {
          setActiveDocId(docId);
          saveActiveDocId(docId);
          setAskScope('doc');
          saveAskScope('doc');
          showToast('Document set as active');
        }}
        saveActiveDocId={saveActiveDocId}
        setAskScope={setAskScope}
        saveAskScope={saveAskScope}
        onOpenDrawer={setDrawerDocId}
        onPreviewDoc={async (docId: string, collection: string) => {
          currentFetchDocIdRef.current = docId;
          setPreviewDocId(docId);
          setActiveDocId(docId);
          saveActiveDocId(docId);
          setAskScope('doc');
          saveAskScope('doc');
          setPreviewLoading(true);
          setPreviewError(null);
          setPreviewLines(null);
          try {
            const result = await fetchJsonPreview(docId, collection, 5);
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLines(result.lines);
            }
          } catch (err: any) {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewError(err?.message || 'Failed to load JSON preview');
            }
          } finally {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLoading(false);
            }
          }
        }}
        onExportJson={async (docId: string, kind: string) => {
          try {
            await exportJson(docId, kind);
          } catch (err: any) {
            showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
          }
        }}
        onExportZip={async (docId: string, kind: string) => {
          try {
            await exportZip(docId, kind);
          } catch (err: any) {
            showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
          }
        }}
        onDeleteDoc={async (docId: string) => {
          const doc = docs.find(d => d.document_id === docId);
          const filename = doc?.paths[0] ? doc.paths[0].split('/').pop() || doc.paths[0] : docId;
          const confirmed = window.confirm(`Are you sure you want to delete "${filename}"?\n\nThis will remove all chunks and images for this document from the index.`);
          if (!confirmed) return;

          try {
            await deleteDocument(docId);
            showToast('Document deleted successfully');
            setSelectedDocIds(prev => {
              const next = new Set(prev);
              next.delete(docId);
              return next;
            });
            await loadDocuments();
            if (activeDocId === docId) {
              setActiveDocId(null);
              saveActiveDocId(null);
              if (askScope === 'doc') {
                setAskScope('all');
                saveAskScope('all');
              }
            }
            if (previewDocId === docId) {
              setPreviewDocId(null);
              setPreviewLines(null);
              setPreviewError(null);
            }
            if (drawerDocId === docId) {
              setDrawerDocId(null);
            }
            if (openMenuDocId === docId) {
              setOpenMenuDocId(null);
            }
          } catch (err: any) {
            const errorMsg = err?.message || err;
            if (errorMsg.includes('not enabled') || errorMsg.includes('403')) {
              showToast('Delete not enabled. Set AUTH_MODE=local or ENABLE_DOC_DELETE=true', true);
            } else {
              showToast(`Delete failed: ${errorMsg}`, true);
            }
          }
        }}
        onToggleSelection={(docId: string) => {
          setSelectedDocIds(prev => {
            const next = new Set(prev);
            if (next.has(docId)) {
              next.delete(docId);
            } else {
              next.add(docId);
            }
            return next;
          });
        }}
        onSetOpenMenu={setOpenMenuDocId}
        onSetFilter={setDocSearchFilter}
        onSetSort={setDocSortBy}
        onBulkDelete={handleBulkDelete}
        onClearSelection={() => setSelectedDocIds(new Set())}
        onLoadDocuments={loadDocuments}
        showToast={showToast}
        getDocumentStatus={getDocumentStatus}
        collectionForDoc={collectionForDoc}
      />
      {previewDocId && (() => {
        const previewedDoc = docs.find(d => d.document_id === previewDocId);
        const collection = previewedDoc ? collectionForDoc(previewedDoc) : '';
        const truncatedId = previewDocId.length > 40 ? previewDocId.substring(0, 40) + '...' : previewDocId;
        const previewStatus = previewedDoc ? getDocumentStatus(previewedDoc) : null;

        return (
          <section style={{ marginTop: 24, padding: 16, border: '1px solid #ddd', borderRadius: 8, background: '#fafafa' }}>
            <h3 style={{ fontSize: 16, marginBottom: 4, fontFamily: 'monospace' }}>Preview: {truncatedId}</h3>
            {collection && (
              <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
                Collection: {collection} {previewLines && previewLines.length > 0 && `• Showing ${previewLines.length} lines (JSONL preview)`}
              </p>
            )}
            {previewStatus && (
              <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
                Status: {previewStatus === 'indexed' ? 'Indexed' : 'Pending'}
              </p>
            )}
            <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
              Each line below is one JSON chunk. This is what gets stored in Qdrant.
            </p>
            {previewLoading && <p style={{ fontSize: 14, opacity: 0.7 }}>Loading JSON preview…</p>}
            {previewError && (
              <p style={{ color: '#dc2626', fontSize: 14 }}>Failed to load JSON preview: {previewError}</p>
            )}
            {!previewLoading && !previewError && (!previewLines || previewLines.length === 0) && (
              <p style={{ fontSize: 14, opacity: 0.7, fontStyle: 'italic' }}>
                No JSON rows yet. The document may not be fully indexed. Try Refresh documents.
              </p>
            )}
            {previewLines && previewLines.length > 0 && (
              <pre style={{
                background: '#fff',
                padding: 12,
                borderRadius: 4,
                border: '1px solid #e5e7eb',
                overflow: 'auto',
                fontSize: 12,
                lineHeight: 1.5,
                maxHeight: '400px',
                fontFamily: 'monospace'
              }}>
{previewLines.map((line, idx) => {
                  try {
                    const obj = JSON.parse(line);
                    return JSON.stringify(obj, null, 2) + (idx < previewLines.length - 1 ? '\n\n' : '');
                  } catch {
                    return line + (idx < previewLines.length - 1 ? '\n\n' : '');
                  }
                }).join('')}
              </pre>
            )}
            <button
              onClick={() => {
                setPreviewDocId(null);
                setPreviewLines(null);
                setPreviewError(null);
                setPreviewLoading(false);
              }}
              style={{
                marginTop: 12,
                padding: '8px 16px',
                borderRadius: 6,
                border: '1px solid #ddd',
                background: '#fff',
                cursor: 'pointer',
                fontSize: 14
              }}
            >
              Close
            </button>
          </section>
        );
      })()}
      <DocumentDrawer
        drawerDocId={drawerDocId}
        docs={docs}
        previewDocId={previewDocId}
        previewLines={previewLines}
        ans={ans}
        askScope={askScope}
        activeDocId={activeDocId}
        llmReachable={s?.llm?.reachable === true}
        askInputRef={askInputRef}
        openMenuDocId={openMenuDocId}
        onClose={() => setDrawerDocId(null)}
        onUseThisDoc={(docId: string) => {
          setDrawerDocId(null);
          setActiveDocId(docId);
          saveActiveDocId(docId);
          setAskScope('doc');
          saveAskScope('doc');
          const llmReachable = s?.llm?.reachable === true;
          if (llmReachable) {
            setAnswerMode('synthesize');
            saveAnswerMode('synthesize', 'doc');
          }
          showToast('Document ready — Ask panel focused');

          // Scroll to Ask and focus input
          setTimeout(() => {
            askInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
              askInputRef.current?.focus();
            }, 300);
          }, 100);
        }}
        onPreviewDoc={async (docId: string, collection: string) => {
          setDrawerDocId(null);
          currentFetchDocIdRef.current = docId;
          setPreviewDocId(docId);
          setActiveDocId(docId);
          saveActiveDocId(docId);
          setAskScope('doc');
          saveAskScope('doc');
          setPreviewLoading(true);
          setPreviewError(null);
          setPreviewLines(null);
          try {
            const result = await fetchJsonPreview(docId, collection, 5);
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLines(result.lines);
            }
          } catch (err: any) {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewError(err?.message || 'Failed to load JSON preview');
            }
          } finally {
            if (currentFetchDocIdRef.current === docId) {
              setPreviewLoading(false);
            }
          }
        }}
        onExportJson={async (docId: string, kind: string) => {
          setDrawerDocId(null);
          try {
            await exportJson(docId, kind);
          } catch (err: any) {
            showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
          }
        }}
        onExportZip={async (docId: string, kind: string) => {
          setDrawerDocId(null);
          try {
            await exportZip(docId, kind);
          } catch (err: any) {
            showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
          }
        }}
        onDeleteDoc={async (docId: string, filename: string) => {
          setDrawerDocId(null);
          const confirmed = window.confirm(`Are you sure you want to delete "${filename}"?\n\nThis will remove all chunks and images for this document from the index.`);
          if (!confirmed) return;

          try {
            await deleteDocument(docId);
            showToast('Document deleted successfully');
            setSelectedDocIds(prev => {
              const next = new Set(prev);
              next.delete(docId);
              return next;
            });
            await loadDocuments();
            if (activeDocId === docId) {
              setActiveDocId(null);
              saveActiveDocId(null);
              if (askScope === 'doc') {
                setAskScope('all');
                saveAskScope('all');
              }
            }
            if (previewDocId === docId) {
              setPreviewDocId(null);
              setPreviewLines(null);
              setPreviewError(null);
            }
            if (openMenuDocId === docId) {
              setOpenMenuDocId(null);
            }
          } catch (err: any) {
            const errorMsg = err?.message || err;
            if (errorMsg.includes('not enabled') || errorMsg.includes('403')) {
              showToast('Delete not enabled. Set AUTH_MODE=local or ENABLE_DOC_DELETE=true', true);
            } else {
              showToast(`Delete failed: ${errorMsg}`, true);
            }
          }
        }}
        copyToClipboard={copyToClipboard}
        showToast={showToast}
        getDocumentStatus={getDocumentStatus}
        collectionForDoc={collectionForDoc}
      />
      <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>API: {apiBase}</div>
    </div>
  )
}

export default App
