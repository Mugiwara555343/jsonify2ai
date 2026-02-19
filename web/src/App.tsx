import { useEffect, useRef, useState } from 'react'
import './App.css'
import {
  askQuestion,
  fetchDocuments,
  fetchStatus,
  uploadFile,
} from './api'
import AssistantOutput from './AssistantOutput'
import { useModels } from './hooks/useModels'
import { Document } from './types'

type Status = {
  ok: boolean
  counts: { chunks: number; images: number; total?: number }
  llm?: { provider?: string; model?: string; reachable?: boolean }
}

type Hit = {
  id: string
  score: number
  text?: string
  caption?: string
  path?: string
  document_id?: string
  meta?: { title?: string; logical_path?: string }
}

type AskResp = {
  ok: boolean
  mode: 'search' | 'llm' | 'retrieve' | 'synthesize'
  answer?: string
  final?: string
  sources?: Hit[]
  answers?: Hit[]
  error?: string
}

type UploadResult = {
  filename: string
  status: 'uploading' | 'processed' | 'skipped' | 'error' | 'indexing'
  document_id?: string
  chunks?: number
  skip_reason?: string
  error?: string
}

const ACTIVE_DOC_STORAGE_KEY = 'jsonify2ai.activeDoc'
const ASK_SCOPE_STORAGE_KEY = 'jsonify2ai.askScope'

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function visible(): boolean {
  return typeof document !== 'undefined' ? document.visibilityState === 'visible' : true
}

async function waitForDocumentIndexed(documentId: string, timeoutMs = 15000): Promise<{ ok: boolean; chunks?: number }> {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutMs) {
    if (!visible()) {
      await sleep(500)
      continue
    }
    try {
      const docs = (await fetchDocuments()) as Document[]
      const doc = docs.find((d) => d.document_id === documentId)
      if (doc) {
        const chunks = Object.values(doc.counts || {}).reduce((sum, n) => sum + (typeof n === 'number' ? n : 0), 0)
        if (chunks > 0) return { ok: true, chunks }
      }
    } catch {
      // keep polling
    }
    await sleep(1500)
  }
  return { ok: false }
}

function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [askQ, setAskQ] = useState('')
  const [ans, setAns] = useState<AskResp | null>(null)
  const [askError, setAskError] = useState<string | null>(null)
  const [askLoading, setAskLoading] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [activeDocId, setActiveDocId] = useState<string | null>(null)
  const [askScope, setAskScope] = useState<'doc' | 'all'>('all')
  const [answerMode, setAnswerMode] = useState<'retrieve' | 'synthesize'>('synthesize')
  const [topK, setTopK] = useState(6)
  const [temp, setTemp] = useState(0.2)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isWindowDragActive, setIsWindowDragActive] = useState(false)
  const [isDropzoneHover, setIsDropzoneHover] = useState(false)
  const { models, loading: modelsLoading } = useModels()
  const [activeModel, setActiveModel] = useState<string | null>(null)

  const askInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)

  const activeDoc = (activeDocId ? docs.find((d) => d.document_id === activeDocId) : null) || docs[0] || null
  const activeDocFilename = activeDoc?.paths?.[0]?.split('/').pop() || undefined

  const showToast = (message: string, isError = false) => {
    setToast(message)
    setTimeout(() => setToast(null), isError ? 5000 : 3000)
  }

  const loadStatus = async () => setStatus(await fetchStatus())

  const loadDocuments = async (): Promise<Document[]> => {
    try {
      const list = (await fetchDocuments()) as Document[]
      setDocs(list)
      return list
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      showToast(`Failed to load documents: ${msg}`, true)
      setDocs([])
      return []
    }
  }

  useEffect(() => {
    void loadStatus()
    void loadDocuments()
    try {
      setActiveDocId(localStorage.getItem(ACTIVE_DOC_STORAGE_KEY))
      const savedScope = localStorage.getItem(ASK_SCOPE_STORAGE_KEY)
      if (savedScope === 'doc' || savedScope === 'all') setAskScope(savedScope)
    } catch {
      // no-op
    }
  }, [])

  useEffect(() => {
    if (!activeModel && models.length > 0) {
      const preferred = models.find((m) => {
        const n = m.name.toLowerCase()
        return n.includes('qwen') || n.includes('llama')
      })
      setActiveModel((preferred || models[0]).name)
    }
  }, [activeModel, models])

  useEffect(() => {
    if (!activeDocId) return
    if (!docs.some((d) => d.document_id === activeDocId)) {
      setActiveDocId(null)
      setAskScope('all')
      try {
        localStorage.removeItem(ACTIVE_DOC_STORAGE_KEY)
        localStorage.setItem(ASK_SCOPE_STORAGE_KEY, 'all')
      } catch {
        // no-op
      }
    }
  }, [activeDocId, docs])

  useEffect(() => {
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types?.includes('Files')

    const onDragEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      dragCounterRef.current += 1
      setIsWindowDragActive(true)
    }

    const onDragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      setIsWindowDragActive(true)
    }

    const onDragLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
      if (dragCounterRef.current === 0) setIsWindowDragActive(false)
    }

    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      dragCounterRef.current = 0
      setIsWindowDragActive(false)
      const file = e.dataTransfer?.files?.[0]
      if (file) void processFileUpload(file)
    }

    window.addEventListener('dragenter', onDragEnter)
    window.addEventListener('dragover', onDragOver)
    window.addEventListener('dragleave', onDragLeave)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('dragenter', onDragEnter)
      window.removeEventListener('dragover', onDragOver)
      window.removeEventListener('dragleave', onDragLeave)
      window.removeEventListener('drop', onDrop)
    }
  }, [])

  const activateDocumentScope = (docId: string) => {
    setActiveDocId(docId)
    setAskScope('doc')
    try {
      localStorage.setItem(ACTIVE_DOC_STORAGE_KEY, docId)
      localStorage.setItem(ASK_SCOPE_STORAGE_KEY, 'doc')
    } catch {
      // no-op
    }
  }

  const processFileUpload = async (file: File) => {
    setUploadBusy(true)
    setUploadResult({ filename: file.name, status: 'uploading' })
    try {
      const data = await uploadFile(file)
      if (data?.skipped === true || (data?.ok === true && data?.accepted === false)) {
        setUploadResult({
          filename: file.name,
          status: 'skipped',
          skip_reason: data?.skip_reason || 'unknown',
          error: data?.details || 'File was skipped',
        })
        showToast('File skipped', true)
        return
      }
      if (data?.ok === false || data?.error) {
        const errorMsg = data?.error || String(data)
        setUploadResult({ filename: file.name, status: 'error', error: errorMsg })
        showToast(`Upload failed: ${errorMsg}`, true)
        return
      }

      const docId = data?.document_id as string | undefined
      if (!docId) {
        setUploadResult({ filename: file.name, status: 'error', error: 'Missing document ID' })
        showToast('Upload completed but document ID missing', true)
        return
      }

      setUploadResult({ filename: file.name, status: 'indexing', document_id: docId, chunks: data?.chunks || 0 })
      const indexed = await waitForDocumentIndexed(docId)
      if (indexed.ok) {
        setUploadResult({ filename: file.name, status: 'processed', document_id: docId, chunks: indexed.chunks || 0 })
        showToast('Processed')
        await loadDocuments()
        activateDocumentScope(docId)
      } else {
        showToast('Uploaded, still indexing', true)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setUploadResult({ filename: file.name, status: 'error', error: msg })
      showToast(`Upload failed: ${msg}`, true)
    } finally {
      setUploadBusy(false)
    }
  }

  const onUploadChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await processFileUpload(file)
    e.target.value = ''
  }

  const handleAsk = async () => {
    if (!askQ.trim()) {
      showToast('Enter a question', true)
      return
    }
    if (askScope === 'doc' && !activeDoc) {
      showToast('Preview or upload a document first', true)
      return
    }

    setAskLoading(true)
    setAskError(null)
    try {
      const requestMode = status?.llm?.reachable === true ? answerMode : 'retrieve'
      const response: AskResp = await askQuestion(
        askQ,
        topK,
        askScope === 'doc' ? activeDoc?.document_id : undefined,
        requestMode,
        undefined,
        undefined,
        activeModel || undefined,
        temp,
      )
      if (response.ok === false) {
        setAskError(response.error || 'Unknown ask error')
        setAns(null)
      } else {
        setAns(response)
      }
    } catch (err: unknown) {
      setAskError(err instanceof Error ? err.message : String(err))
      setAns(null)
    } finally {
      setAskLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <input ref={fileInputRef} type="file" className="hidden" onChange={onUploadChange} disabled={uploadBusy} />

      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-6 sm:px-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-300">jsonify2ai</h1>
            <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">API: {status ? 'up' : '...'}</span>
            <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">
              LLM: {status?.llm?.reachable ? 'on' : 'off'}
            </span>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/80 px-2 py-1">
            <span className="text-[11px] text-slate-400">Model</span>
            <select
              value={activeModel || ''}
              onChange={(e) => setActiveModel(e.target.value)}
              className="min-w-40 border-none bg-slate-900 text-xs text-slate-300 outline-none"
              disabled={modelsLoading || models.length === 0}
            >
              {models.length === 0 && <option value="">{modelsLoading ? 'Loading...' : 'No models'}</option>}
              {models.map((m) => (
                <option key={m.name} value={m.name} className="bg-slate-900 text-slate-300">
                  {m.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          className={`mb-6 rounded-2xl border border-dashed p-5 text-center transition ${
            isWindowDragActive || isDropzoneHover
              ? 'border-sky-400 bg-sky-500/10 text-sky-200'
              : 'border-slate-800 bg-slate-900/40 text-slate-400'
          }`}
          onDragOver={(e) => {
            e.preventDefault()
            setIsDropzoneHover(true)
          }}
          onDragEnter={(e) => {
            e.preventDefault()
            setIsDropzoneHover(true)
          }}
          onDragLeave={(e) => {
            e.preventDefault()
            setIsDropzoneHover(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setIsDropzoneHover(false)
            const file = e.dataTransfer.files?.[0]
            if (file) void processFileUpload(file)
          }}
        >
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Dropzone</div>
          <div className="mt-2 text-sm">Drag a file here, or</div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="mt-3 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
          >
            Choose file
          </button>
          {uploadBusy && <div className="mt-2 text-xs text-slate-400">Uploading...</div>}
        </div>

        <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900/40 p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>{docs.length} docs indexed</span>
            {askScope === 'doc' && activeDocFilename && (
              <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-slate-300">doc: {activeDocFilename}</span>
            )}
            {uploadResult && (
              <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-slate-300">
                {uploadResult.status}: {uploadResult.filename}
              </span>
            )}
            {toast && <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-slate-300">{toast}</span>}
          </div>

          <AssistantOutput
            result={ans}
            status={status}
            loading={askLoading}
            error={askError}
            actionName={answerMode === 'synthesize' ? 'Synthesis' : 'Retrieval'}
            showToast={showToast}
            scope={askScope}
            activeDocFilename={activeDocFilename}
            onUseDoc={(documentId, llmReachable) => {
              setActiveDocId(documentId)
              setAskScope('doc')
              try {
                localStorage.setItem(ACTIVE_DOC_STORAGE_KEY, documentId)
                localStorage.setItem(ASK_SCOPE_STORAGE_KEY, 'doc')
              } catch {
                // no-op
              }
              if (llmReachable) setAnswerMode('synthesize')
            }}
            documents={docs}
          />
        </div>

        <div className="mt-4">
          <div className="mb-3 flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/80 p-1">
            <button
              type="button"
              onClick={() => setAnswerMode('retrieve')}
              className={`rounded-lg px-3 py-1.5 text-xs transition ${
                answerMode === 'retrieve' ? 'bg-slate-800 text-slate-300' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Retrieve
            </button>
            <button
              type="button"
              onClick={() => setAnswerMode('synthesize')}
              className={`rounded-lg px-3 py-1.5 text-xs transition ${
                answerMode === 'synthesize' ? 'bg-slate-800 text-slate-300' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Synthesize
            </button>
          </div>
        </div>

        <div className="sticky bottom-0 border-t border-slate-800 bg-slate-950/95 pb-2 pt-3 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center gap-2 rounded-2xl border border-slate-700 bg-slate-900 px-3 py-2">
            <button
              type="button"
              onClick={() => setShowAdvanced(true)}
              className="rounded-md border border-slate-700 p-2 text-slate-300 hover:border-slate-500"
              aria-label="Open advanced controls"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" />
                <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a1 1 0 0 1 0 1.4l-1.2 1.2a1 1 0 0 1-1.4 0l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a1 1 0 0 1-1 1h-1.8a1 1 0 0 1-1-1v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a1 1 0 0 1-1.4 0L4.3 18a1 1 0 0 1 0-1.4l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H3.5a1 1 0 0 1-1-1V12a1 1 0 0 1 1-1h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a1 1 0 0 1 0-1.4l1.2-1.2a1 1 0 0 1 1.4 0l.1.1a1 1 0 0 0 1.1.2 1 1 0 0 0 .6-.9V4a1 1 0 0 1 1-1h1.8a1 1 0 0 1 1 1v.2a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a1 1 0 0 1 1.4 0l1.2 1.2a1 1 0 0 1 0 1.4l-.1.1a1 1 0 0 0-.2 1.1 1 1 0 0 0 .9.6h.2a1 1 0 0 1 1 1v1.8a1 1 0 0 1-1 1h-.2a1 1 0 0 0-.9.6Z" />
              </svg>
            </button>

            <input
              ref={askInputRef}
              value={askQ}
              onChange={(e) => setAskQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void handleAsk()
                }
              }}
              placeholder="Ask the library"
              className="flex-1 bg-transparent px-1 text-sm text-slate-300 placeholder-slate-500 outline-none"
            />

            <button
              type="button"
              onClick={() => void handleAsk()}
              disabled={askLoading}
              className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {askLoading ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>
      </div>

      {showAdvanced && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-4 sm:items-center" onClick={() => setShowAdvanced(false)}>
          <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wide text-slate-200">Advanced Controls</h2>
              <button
                type="button"
                className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500"
                onClick={() => setShowAdvanced(false)}
              >
                Close
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                  <span>Top-K Retrieval</span>
                  <span>{topK}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={30}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="w-full accent-sky-400"
                />
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                  <span>Temperature</span>
                  <span>{temp.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={temp}
                  onChange={(e) => setTemp(Number(e.target.value))}
                  className="w-full accent-sky-400"
                />
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

export default App
