import { useEffect, useState, useRef } from 'react'
import ThemeToggle from "./components/ThemeToggle";
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
import { useModels } from './hooks/useModels';

const BUILD_STAMP = "beast-2 / 2025-12-23 / commit 39ed9bb";

type IngestActivityItem = {
  id: string;
  filename: string;
  status: 'processed' | 'skipped' | 'error' | 'processing';
  reason: string;
  chunks: number;
  images: number;
  started_at: string;
  finished_at?: string;
  kind: string;
  path: string;
}

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
  // Recent ingest activity (optional)
  ingest_recent?: IngestActivityItem[];
  // LLM status
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
}
type Hit = {
  id: string;
  score: number;
  text?: string;
  caption?: string;
  path?: string;
  idx?: number;
  kind?: string;
  document_id?: string;
  meta?: {
    ingested_at?: string;
    ingested_at_ts?: number;
    source_system?: string;
    title?: string;
    logical_path?: string;
    conversation_id?: string;
    source_file?: string;
    [k: string]: any;
  };
}

type Document = { document_id: string; kinds: string[]; paths: string[]; counts: Record<string, number> }
const apiBase = API_BASE
type AskResp = {
  ok: boolean;
  mode: 'search' | 'llm' | 'retrieve' | 'synthesize';
  model?: string;
  answer?: string;
  final?: string;
  sources?: Hit[];
  answers?: Hit[];
  error?: string;
  stats?: { k: number; returned: number };
}

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
  const [state, setState] = useState<"checking" | "ok" | "warn">("checking");
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

  const getClasses = () => {
    switch (state) {
      case "ok": return "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800";
      case "warn": return "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800";
      default: return "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800";
    }
  };

  const label = state === "ok" ? "API: healthy" : state === "checking" ? "API: checking" : "API: unreachable";
  return <span className={`ml-2 px-2 py-0.5 rounded-full text-xs border ${getClasses()}`}>{label}</span>;
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

  const getClasses = () => {
    if (isOn) return "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-800";
    if (isOffline) return "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800";
    return "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700";
  };

  return <span className={`ml-2 px-2 py-0.5 rounded-full text-xs border ${getClasses()}`}>{label}</span>;
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

async function waitForDocumentIndexed(document_id: string, timeoutMs = 15000): Promise<{ ok: boolean, chunks?: number }> {
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
  const [lastDoc, setLastDoc] = useState<{ id: string, kind: string } | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [recentDocs, setRecentDocs] = useState<Hit[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [askLoading, setAskLoading] = useState(false)
  const [previewDocId, setPreviewDocId] = useState<string | null>(null)
  const [previewLines, setPreviewLines] = useState<string[] | null>(null)
  const [previewTotal, setPreviewTotal] = useState<number | null>(null)
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
  const [timeFilter, setTimeFilter] = useState<'all' | '24h' | '7d' | '30d'>('all')
  const [openMenuDocId, setOpenMenuDocId] = useState<string | null>(null)
  const [drawerDocId, setDrawerDocId] = useState<string | null>(null)
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set())
  const currentFetchDocIdRef = useRef<string | null>(null)
  const askInputRef = useRef<HTMLInputElement>(null)

  // Models integration
  const { models, loading: modelsLoading } = useModels();
  const [activeModel, setActiveModel] = useState<string | null>(null);

  // Set default model if available and none selected
  useEffect(() => {
    if (!activeModel && models.length > 0) {
      // Prefer Qwen or Llama, otherwise first
      const preferred = models.find(m => m.name.toLowerCase().includes('qwen') || m.name.toLowerCase().includes('llama'));
      setActiveModel(preferred ? preferred.name : models[0].name);
    }
  }, [models, activeModel]);



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

  // Robust localStorage boolean helpers
  function getLSBool(key: string, defaultVal: boolean): boolean {
    try {
      const v = localStorage.getItem(key);
      if (v === null) return defaultVal;
      return v === 'true';
    } catch {
      return defaultVal;
    }
  }

  function setLSBool(key: string, v: boolean) {
    try {
      localStorage.setItem(key, v ? 'true' : 'false');
    } catch { }
  }

  function loadActivityFeed(): IngestionEvent[] {
    try {
      const raw = localStorage.getItem(ACTIVITY_STORAGE_KEY);
      if (raw) {
        const events = JSON.parse(raw) as IngestionEvent[];
        // Limit to MAX_ACTIVITY_EVENTS, newest first
        return events.slice(0, MAX_ACTIVITY_EVENTS);
      }
    } catch { }
    return [];
  }

  function saveActivityFeed(events: IngestionEvent[]) {
    try {
      // Limit to MAX_ACTIVITY_EVENTS, newest first
      const limited = events.slice(0, MAX_ACTIVITY_EVENTS);
      localStorage.setItem(ACTIVITY_STORAGE_KEY, JSON.stringify(limited));
    } catch { }
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
    setHideIngestionActivity(true);
    setLSBool('ui.hideIngestionActivity', true);
    try {
      localStorage.removeItem(ACTIVITY_STORAGE_KEY);
    } catch { }
  }

  // Check if ingestion activity should be hidden
  const [hideIngestionActivity, setHideIngestionActivity] = useState(() =>
    getLSBool('ui.hideIngestionActivity', false)
  );

  // Show activity link handler
  const showIngestionActivity = () => {
    setHideIngestionActivity(false);
    setLSBool('ui.hideIngestionActivity', false);
    // Reload status to populate activity feed
    loadStatus();
  };

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
    } catch { }
    return null;
  }

  function saveActiveDocId(docId: string | null) {
    try {
      if (docId) {
        localStorage.setItem(ACTIVE_DOC_STORAGE_KEY, docId);
      } else {
        localStorage.removeItem(ACTIVE_DOC_STORAGE_KEY);
      }
    } catch { }
  }

  function loadAskScope(): 'doc' | 'all' {
    try {
      const raw = localStorage.getItem(ASK_SCOPE_STORAGE_KEY);
      if (raw === 'doc' || raw === 'all') {
        return raw;
      }
    } catch { }
    return 'all'; // Default to 'all' for backward compatibility
  }

  function saveAskScope(scope: 'doc' | 'all') {
    try {
      localStorage.setItem(ASK_SCOPE_STORAGE_KEY, scope);
    } catch { }
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
    } catch { }
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
    } catch { }
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

  // Re-match document_ids in activityFeed when docs change
  useEffect(() => {
    if (docs.length === 0) return;
    setActivityFeed(prev => {
      return prev.map(event => {
        if (event.document_id) return event; // Already matched
        // Try to match by filename
        const matchedDoc = docs.find(d =>
          d.paths.some(p => {
            const pathParts = p.split('/');
            const filename = pathParts[pathParts.length - 1];
            return filename === event.filename;
          })
        );
        if (matchedDoc) {
          return { ...event, document_id: matchedDoc.document_id };
        }
        return event;
      });
    });
  }, [docs])

  const loadStatus = async () => {
    const j = await fetchStatus()
    setS(j)


    // Merge ingest_recent from status into activityFeed only if activity is not hidden
    if (j?.ingest_recent && Array.isArray(j.ingest_recent) && !hideIngestionActivity) {
      // Merge ingest_recent from status into activityFeed

      const newEvents: IngestionEvent[] = j.ingest_recent.map((item: IngestActivityItem) => {
        // Map worker activity to IngestionEvent format
        const timestamp = item.finished_at || item.started_at;
        const timestampMs = timestamp ? new Date(timestamp).getTime() : Date.now();

        // Try to find document_id by matching path with existing documents
        let document_id: string | undefined;
        if (item.path && docs.length > 0) {
          // Try to match by path (remove "data/dropzone/" prefix if present)
          const cleanPath = item.path.replace(/^data\/dropzone\//, '');
          const matchedDoc = docs.find(d =>
            d.paths.some(p => {
              const docPath = p.replace(/^data\/dropzone\//, '');
              return docPath === cleanPath || docPath.includes(cleanPath) || cleanPath.includes(docPath);
            })
          );
          if (matchedDoc) {
            document_id = matchedDoc.document_id;
          }
        }

        return {
          timestamp: timestampMs,
          filename: item.filename,
          status: item.status === 'processing' ? 'indexing' : item.status,
          chunks: item.chunks > 0 ? item.chunks : undefined,
          images: item.images > 0 ? item.images : undefined, // Add images count for image files
          skip_reason: item.status === 'skipped' ? item.reason : undefined,
          error: item.status === 'error' ? item.reason : undefined,
          document_id: document_id,
          activity_id: item.id, // Store activity_id for deduplication
        } as IngestionEvent & { activity_id?: string; images?: number };
      });

      // Merge with existing activityFeed, avoiding duplicates by activity_id
      setActivityFeed(prev => {
        const existingIds = new Set(prev.map(e => (e as any).activity_id).filter(Boolean));
        const newUnique = newEvents.filter(e => {
          const aid = (e as any).activity_id;
          return aid && !existingIds.has(aid);

          return !aid || !existingIds.has(aid);
        });
        // Keep most recent first, limit to last 100
        const merged = [...newUnique, ...prev].slice(0, 100);
        // Re-match document_ids now that we have the full list
        return merged.map(event => {
          if (event.document_id || !(event as any).activity_id) return event;
          // Try to match by filename if path matching didn't work
          const matchedDoc = docs.find(d =>
            d.paths.some(p => {
              const pathParts = p.split('/');
              const filename = pathParts[pathParts.length - 1];
              return filename === event.filename;
            })
          );
          if (matchedDoc) {
            return { ...event, document_id: matchedDoc.document_id };
          }
          return event;
        });
      });
    }
  }

  // Helper to compute ISO-8601 UTC timestamp for time filters
  const getTimeFilterISO = (filter: 'all' | '24h' | '7d' | '30d'): string | undefined => {
    if (filter === 'all') return undefined;
    const now = new Date();
    const hoursAgo = filter === '24h' ? 24 : filter === '7d' ? 24 * 7 : 24 * 30;
    const past = new Date(now.getTime() - hoursAgo * 60 * 60 * 1000);
    return past.toISOString();
  };

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
    const ingestedAfter = getTimeFilterISO(timeFilter);
    return await doSearch(q, kind, 5, ingestedAfter, undefined);
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
      const ingestedAfter = getTimeFilterISO(timeFilter);
      const j: AskResp = await askQuestion(askQ, 6, documentId, answerMode, ingestedAfter, undefined, activeModel || undefined);
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
        const errorMsg = err?.message || err || 'Unknown error';

        // Check for CORS/network errors
        if (errorMsg.includes('Network error') || errorMsg.includes('CORS')) {
          showToast(`Delete failed: Network/CORS error. Check browser console.`, true);
          deleteDisabled = true;
          break; // Stop on CORS errors
        }

        // Check for delete disabled (403)
        if (errorMsg.includes('not enabled') || errorMsg.includes('403') || errorMsg.includes('Delete is disabled')) {
          showToast('Delete is disabled (set AUTH_MODE=local or ENABLE_DOC_DELETE=true)', true);
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
      const s0 = await fetchStatus().catch(() => ({ counts: { total: 0 } }))
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
          setPreviewTotal(null);
          try {
            const result = await fetchJsonPreview(requestedDocId, collection, 100);
            if (currentFetchDocIdRef.current === requestedDocId) {
              setPreviewLines(result.lines);
              if (result.total !== undefined) {
                setPreviewTotal(result.total);
              }
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
          setPreviewTotal(null);
          try {
            const result = await fetchJsonPreview(targetDocId, collection, 100);
            if (currentFetchDocIdRef.current === targetDocId) {
              setPreviewLines(result.lines);
              if (result.total !== undefined) {
                setPreviewTotal(result.total);
              }
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
      const coll = (data?.collection || "") as string;
      const kind = coll.includes("images") ? "image" : "text"; // images vs chunks
      const documentsCreated = data?.documents_created as number | undefined;
      const results = data?.results as Array<{ document_id: string, chunks: number }> | undefined;

      // Check for multi-document response (ChatGPT export, etc.)
      if (documentsCreated && documentsCreated > 1) {
        // Multi-document upload
        setUploadResult({
          filename: file.name,
          status: 'processed',
          document_id: docId || '',
          chunks: data?.chunks || 0
        });

        // Update activity event
        updateActivityEvent(file.name, {
          status: 'processed',
          chunks: data?.chunks || 0,
          document_id: docId ? docId.substring(0, 8) : ''
        });

        showToast(`Created ${documentsCreated} documents from ${file.name} ✓`);

        // Refresh documents list to show all new documents
        await loadDocuments();
        return;
      }

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
            setPreviewTotal(null);
            try {
              const result = await fetchJsonPreview(requestedDocId, collection, 100);
              if (currentFetchDocIdRef.current === requestedDocId) {
                setPreviewLines(result.lines);
                if (result.total !== undefined) {
                  setPreviewTotal(result.total);
                }
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
    } catch (err: any) {
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
    <div className="App min-h-screen bg-white dark:bg-black text-slate-900 dark:text-gray-100 transition-colors duration-300" style={{ fontFamily: 'ui-sans-serif', padding: 24, margin: '0 auto' }}>
      <div className="max-w-3xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 style={{ fontSize: 24, marginBottom: 8 }}>jsonify2ai <HealthChip /><LLMChip status={s} /></h1>
          <ThemeToggle />
        </div>
        <div className="text-sm mb-2 italic text-gray-500 dark:text-gray-400">
          Upload files → JSONL chunks → semantic search → exports
        </div>

        {/* 3-Step How it Works Strip */}
        {/* 3-Step How it Works Strip */}
        <div className="mb-4 flex gap-4 flex-wrap p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 text-gray-900 dark:text-gray-100">
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <div className="text-sm font-semibold mb-1 text-blue-600 dark:text-blue-400">1) Upload</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Drop files anywhere or use the optional hot folder.</div>
          </div>
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <div className="text-sm font-semibold mb-1 text-blue-600 dark:text-blue-400">2) Ask</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Use This document for precise answers.</div>
          </div>
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <div className="text-sm font-semibold mb-1 text-blue-600 dark:text-blue-400">3) Export</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Download JSONL or a ZIP snapshot.</div>
          </div>
        </div>

        {/* Start Here Button */}
        <div style={{ marginBottom: 16 }}>
          <button
            onClick={handleStartHere}
            disabled={demoLoading || uploadBusy}
            className={`px-6 py-3 rounded-lg font-semibold text-sm transition-all shadow-sm ${demoLoading || uploadBusy
              ? 'bg-gray-400 cursor-not-allowed text-white'
              : 'bg-blue-600 hover:bg-blue-700 text-white shadow-md hover:shadow-lg'
              }`}
          >
            {demoLoading ? 'Loading demo…' : 'Start here'}
          </button>
        </div>

        {/* What is this? Collapsible */}
        <div style={{ marginBottom: 16 }}>
          <button
            onClick={() => setShowWhatIsThis(!showWhatIsThis)}
            className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-md border text-sm font-medium transition-colors bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <span style={{ transform: showWhatIsThis ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▶</span>
            <span>What is this?</span>
          </button>
          {showWhatIsThis && (
            <div className="mt-2 p-3 bg-gray-50 dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-800 text-sm leading-relaxed">
              <ul className="m-0 pl-5 text-gray-700 dark:text-gray-300">
                <li style={{ marginBottom: 6 }}>Local-first indexing into JSONL chunks</li>
                <li style={{ marginBottom: 6 }}>Vectors stored in Qdrant for semantic search</li>
                <li style={{ marginBottom: 6 }}>Optional local LLM synthesis (Ollama)</li>
                <li style={{ marginBottom: 8 }}>Export JSON / ZIP for portability</li>
              </ul>
              <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded border border-yellow-200 dark:border-yellow-900/50 text-xs text-yellow-800 dark:text-yellow-200">
                <strong>Privacy note:</strong> data stays on your machine unless you expose ports publicly.
              </div>
            </div>
          )}
        </div>

        <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 16, fontFamily: 'monospace' }}>
          Build: {BUILD_STAMP}
        </div>
        <details className="mb-8 p-4 bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800">
          <summary className="cursor-pointer font-medium text-gray-600 dark:text-gray-300 select-none hover:text-gray-900 dark:hover:text-white transition-colors">System Status & Ingestion Activity</summary>
          <div className="mt-4 space-y-6">

            {/* Status Counts */}
            {!s && <div>Loading…</div>}
            {s && (
              <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }}>
                <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700">
                  <div style={{ opacity: .6, marginBottom: 6 }} className="dark:text-gray-400">Text Chunks</div>
                  <div style={{ fontSize: 28, fontWeight: 700 }}>{s.counts.chunks}</div>
                </div>
                <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700">
                  <div style={{ opacity: .6, marginBottom: 6 }} className="dark:text-gray-400">Images</div>
                  <div style={{ fontSize: 28, fontWeight: 700 }}>{s.counts.images}</div>
                </div>
              </div>
            )}

            {/* Telemetry Chips */}
            {s && (s.uptime_s !== undefined || s.ingest_total !== undefined || s.ingest_failed !== undefined || s.watcher_triggers_total !== undefined || s.export_total !== undefined || s.ask_synth_total !== undefined) && (
              <div>
                <div style={{ fontSize: 14, opacity: .6, marginBottom: 8 }} className="dark:text-gray-400">Telemetry</div>
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

            {/* Ingestion Activity Feed */}
            <div className="mt-4">
              <h3 className="text-sm font-semibold mb-2 opacity-70">Activity Log</h3>
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
            </div>

          </div>
        </details>

        {/* Build Info */}
        <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 16, fontFamily: 'monospace' }}>
          Build: {BUILD_STAMP}
        </div>

        {/* Recent Documents Panel */}
        {recentDocs.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 14, opacity: .6, marginBottom: 8 }}>Recent Documents</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {recentDocs.map((doc, i) => (
                <div key={i} className="p-3 border border-gray-200 dark:border-gray-800 rounded-lg bg-gray-50 dark:bg-gray-900">
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
          <input
            type="file"
            onChange={onUploadChange}
            disabled={uploadBusy || demoLoading}
            className="block w-full text-sm text-gray-500 dark:text-gray-400
              file:mr-4 file:py-2 file:px-4
              file:rounded-full file:border-0
              file:text-sm file:font-semibold
              file:bg-blue-50 file:text-blue-700
              dark:file:bg-blue-900/30 dark:file:text-blue-300
              hover:file:bg-blue-100 dark:hover:file:bg-blue-900/50
              cursor-pointer file:cursor-pointer"
          />
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
            className={`px-3 py-2 rounded-md border text-xs transition-colors ${demoLoading
              ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 border-gray-200 dark:border-gray-700 cursor-not-allowed'
              : 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
              } ${uploadBusy || demoLoading ? 'opacity-60' : ''}`}
          >
            Load demo data
          </button>
        </div>

        {/* Upload Results Panel */}
        {uploadResult && (
          <div className="p-4 mb-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900">
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
            className="text-xs px-2 py-1 rounded border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400 cursor-pointer hover:underline"
          >
            Where is dropzone?
          </button>
          {showDropzoneHelp && (
            <div className="mt-2 p-3 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900">
              <div className="text-xs font-semibold mb-2 text-gray-900 dark:text-gray-100">
                Optional hot folder for auto-ingest
              </div>
              <div className="text-xs mb-1.5 text-gray-700 dark:text-gray-300">
                <strong>Inside Docker:</strong> <code className="bg-gray-100 dark:bg-black px-1 py-0.5 rounded text-gray-800 dark:text-gray-200">/data/dropzone</code>
              </div>
              <div className="text-xs mb-2 text-gray-700 dark:text-gray-300">
                <strong>On your machine:</strong> Host path is configured in docker-compose.yml under the worker volume for /data/dropzone.
              </div>
              <button
                onClick={() => {
                  const text = `/data/dropzone\n(Host path configured in docker-compose.yml)`;
                  copyToClipboard(text);
                  showToast('Dropzone path copied');
                }}
                className="px-2 py-1 rounded border text-xs bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400 cursor-pointer"
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
            setPreviewTotal(null);
            try {
              const result = await fetchJsonPreview(docId, collection, 100);
              if (currentFetchDocIdRef.current === docId) {
                setPreviewLines(result.lines);
                if (result.total !== undefined) {
                  setPreviewTotal(result.total);
                }
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
          models={models}
          activeModel={activeModel}
          onSelectModel={setActiveModel}
          modelsLoading={modelsLoading}
        />
        {askScope === 'all' && (
          <div style={{ marginTop: 16, marginBottom: 16, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>
            Global mode is for finding relevant documents.
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
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12 }}>
                {ans.mode === 'retrieve' ? 'Retrieved sources' : 'Sources'}
              </div>
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
                    {sources.map((h: any, i: number) => {
                      // Use standardized Source shape: id, document_id, text, meta, score, path, kind, idx
                      const sourceId = h.id || `source-${i}`;
                      const docId = h.document_id || '';
                      const title = h.meta?.title || (h.path ? h.path.split('/').pop() || h.path : docId.substring(0, 12) || `Source ${i + 1}`);
                      const logicalPath = h.meta?.logical_path;
                      const path = h.path;
                      const kind = h.kind;
                      const snippet = h.text || h.caption || '';
                      const score = h.score !== undefined ? h.score : null;
                      const chunkIdx = h.idx !== undefined ? h.idx : null;

                      return (
                        <div key={i} style={{ padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 500, fontSize: 13 }}>{title}</span>
                            {kind && (
                              <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: '#e3f2fd', color: '#1976d2', fontWeight: 500 }}>
                                {kind}
                              </span>
                            )}
                            {docId && (
                              <code style={{ fontSize: 11, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
                                {docId.substring(0, 12)}...
                              </code>
                            )}
                            {score !== null && (
                              <span style={{ fontSize: 11, padding: '2px 6px', borderRadius: 4, background: '#f0f9ff', color: '#0369a1' }}>
                                score: {score.toFixed(2)}
                              </span>
                            )}
                            <button
                              onClick={() => {
                                copyToClipboard(sourceId);
                                showToast('Chunk ID copied');
                              }}
                              style={{
                                fontSize: 10,
                                padding: '2px 6px',
                                borderRadius: 4,
                                border: '1px solid #ddd',
                                background: '#fff',
                                color: '#666',
                                cursor: 'pointer',
                                marginLeft: 'auto'
                              }}
                              title={`Copy chunk ID: ${sourceId}`}
                            >
                              Copy ID
                            </button>
                          </div>
                          {(logicalPath || path) && (
                            <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6 }}>
                              {logicalPath || path}
                            </div>
                          )}
                          {chunkIdx !== null && (
                            <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 6 }}>
                              Chunk index: {chunkIdx}
                            </div>
                          )}
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
            className="flex-1 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            value={kind}
            onChange={e => setKind(e.target.value as any)}
            className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="text">text</option>
            <option value="pdf">pdf</option>
            <option value="image">image</option>
            <option value="audio">audio</option>
          </select>
          <button
            onClick={handleSearch}
            disabled={searchLoading}
            className={`px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 font-medium transition-colors ${searchLoading
              ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed'
              : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
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

        <div style={{ marginTop: 24, marginBottom: 12 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: '#666' }}>Time filter:</span>
            {(['all', '24h', '7d', '30d'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => {
                  setTimeFilter(filter);
                  // Reload documents and refresh search if needed
                  loadDocuments();
                }}
                className={`px-3 py-1 rounded-md text-xs border transition-colors ${timeFilter === filter
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
              >
                {filter === 'all' ? 'All' : filter === '24h' ? 'Last 24h' : filter === '7d' ? 'Last 7d' : 'Last 30d'}
              </button>
            ))}
          </div>
        </div>
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
            setPreviewTotal(null);
            try {
              const result = await fetchJsonPreview(docId, collection, 100);
              if (currentFetchDocIdRef.current === docId) {
                setPreviewLines(result.lines);
                if (result.total !== undefined) {
                  setPreviewTotal(result.total);
                }
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
              const errorMsg = err?.message || String(err) || "Unknown error";
              showToast(errorMsg, true);
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
        {/* JSON Preview Modal */}
        {previewDocId && (() => {
          const previewedDoc = docs.find(d => d.document_id === previewDocId);
          const collection = previewedDoc ? collectionForDoc(previewedDoc) : '';
          const docTitle = previewedDoc && (previewedDoc as any).meta?.title
            ? (previewedDoc as any).meta.title
            : previewDocId.length > 40 ? previewDocId.substring(0, 40) + '...' : previewDocId;
          const previewStatus = previewedDoc ? getDocumentStatus(previewedDoc) : null;
          const linesLoaded = previewLines ? previewLines.length : 0;
          const hasMore = previewTotal !== null ? linesLoaded < previewTotal : true;

          const handleLoadMore = async () => {
            if (!previewDocId || !collection) return;
            setPreviewLoading(true);
            try {
              const result = await fetchJsonPreview(previewDocId, collection, 100, linesLoaded);
              if (result.lines && result.lines.length > 0) {
                setPreviewLines(prev => [...(prev || []), ...result.lines]);
                if (result.total !== undefined) {
                  setPreviewTotal(result.total);
                }
              }
            } catch (err: any) {
              setPreviewError(err?.message || 'Failed to load more lines');
            } finally {
              setPreviewLoading(false);
            }
          };

          const handleClose = () => {
            setPreviewDocId(null);
            setPreviewLines(null);
            setPreviewTotal(null);
            setPreviewError(null);
            setPreviewLoading(false);
          };

          return (
            <div
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'rgba(0, 0, 0, 0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                padding: 20
              }}
              onClick={(e) => {
                if (e.target === e.currentTarget) handleClose();
              }}
            >
              <div
                style={{
                  borderRadius: 12,
                  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                  maxWidth: '90vw',
                  maxHeight: '90vh',
                  width: '800px',
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden'
                }}
                className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Modal Header */}
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-start">
                  <div style={{ flex: 1 }}>
                    <h3 className="text-base font-semibold font-mono mb-1 text-gray-900 dark:text-gray-100">
                      Preview: {docTitle}
                    </h3>
                    {collection && (
                      <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
                        Collection: {collection}
                      </p>
                    )}
                    {previewStatus && (
                      <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 4 }}>
                        Status: {previewStatus === 'indexed' ? 'Indexed' : 'Pending'}
                      </p>
                    )}
                    {previewLines && previewLines.length > 0 && (
                      <p style={{ fontSize: 12, opacity: 0.7 }}>
                        {previewTotal !== null
                          ? `Showing ${linesLoaded} of ${previewTotal} lines`
                          : `Showing ${linesLoaded} lines`}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={handleClose}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 6,
                      border: '1px solid #ddd',
                      background: '#fff',
                      cursor: 'pointer',
                      fontSize: 14,
                      marginLeft: 16
                    }}
                  >
                    ✕
                  </button>
                </div>

                {/* Modal Content */}
                <div style={{
                  padding: 16,
                  overflow: 'auto',
                  flex: 1,
                  minHeight: 0
                }}>
                  {previewLoading && linesLoaded === 0 && (
                    <p style={{ fontSize: 14, opacity: 0.7 }}>Loading JSON preview…</p>
                  )}
                  {previewError && (
                    <p style={{ color: '#dc2626', fontSize: 14 }}>Failed to load JSON preview: {previewError}</p>
                  )}
                  {!previewLoading && !previewError && (!previewLines || previewLines.length === 0) && (
                    <p style={{ fontSize: 14, opacity: 0.7, fontStyle: 'italic' }}>
                      No JSON rows yet. The document may not be fully indexed. Try Refresh documents.
                    </p>
                  )}
                  {previewLines && previewLines.length > 0 && (
                    <>
                      <p style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
                        Each line below is one JSON chunk. This is what gets stored in Qdrant.
                      </p>
                      <pre className="p-3 bg-gray-50 dark:bg-gray-950 rounded border border-gray-200 dark:border-gray-800 text-xs text-gray-800 dark:text-gray-200 overflow-auto max-h-[60vh] font-mono mb-3">
                        {previewLines.map((line, idx) => {
                          try {
                            const obj = JSON.parse(line);
                            return JSON.stringify(obj, null, 2) + (idx < previewLines.length - 1 ? '\n\n' : '');
                          } catch {
                            return line + (idx < previewLines.length - 1 ? '\n\n' : '');
                          }
                        }).join('')}
                      </pre>
                      {hasMore && (
                        <button
                          onClick={handleLoadMore}
                          disabled={previewLoading}
                          style={{
                            padding: '8px 16px',
                            borderRadius: 6,
                            border: '1px solid #ddd',
                            background: previewLoading ? '#f3f4f6' : '#fff',
                            cursor: previewLoading ? 'not-allowed' : 'pointer',
                            fontSize: 14,
                            opacity: previewLoading ? 0.6 : 1
                          }}
                        >
                          {previewLoading ? 'Loading...' : 'Load more'}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
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
            setPreviewTotal(null);
            try {
              const result = await fetchJsonPreview(docId, collection, 100);
              if (currentFetchDocIdRef.current === docId) {
                setPreviewLines(result.lines);
                if (result.total !== undefined) {
                  setPreviewTotal(result.total);
                }
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
              const errorMsg = err?.message || String(err) || "Unknown error";
              showToast(errorMsg, true);
            }
          }}
          copyToClipboard={copyToClipboard}
          showToast={showToast}
          getDocumentStatus={getDocumentStatus}
          collectionForDoc={collectionForDoc}
        />
        <div style={{ marginTop: 16, opacity: .7, fontSize: 12 }}>API: {apiBase}</div>
      </div>
    </div>
  );
}

export default App
