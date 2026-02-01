import { RefObject } from 'react';
import { Document } from './IngestionActivity';
import ModelSelector from './ModelSelector';

type Status = {
  ok: boolean;
  counts: { chunks: number; images: number; total?: number };
  uptime_s?: number;
  ingest_total?: number;
  ingest_failed?: number;
  watcher_triggers_total?: number;
  export_total?: number;
  ask_synth_total?: number;
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
};

interface AskPanelProps {
  askScope: 'doc' | 'all';
  answerMode: 'retrieve' | 'synthesize';
  askQ: string;
  askLoading: boolean;
  activeDocId: string | null;
  docs: Document[];
  status: Status | null;
  askInputRef: RefObject<HTMLInputElement>;
  onSetAskScope: (scope: 'doc' | 'all') => void;
  saveAskScope: (scope: 'doc' | 'all') => void;
  onSetAnswerMode: (mode: 'retrieve' | 'synthesize') => void;
  saveAnswerMode: (mode: 'retrieve' | 'synthesize', scope: 'doc' | 'all') => void;
  onSetAskQ: (q: string) => void;
  onAsk: () => Promise<void>;
  onClearActive: () => void;
  onPreviewDoc: (docId: string, collection: string) => Promise<void>;
  exportJson: (docId: string, kind: string) => Promise<void>;
  exportZip: (docId: string, kind: string) => Promise<void>;
  copyToClipboard: (text: string) => void;
  showToast: (msg: string, isError?: boolean) => void;
  getActiveDocument: (strictMode: boolean) => Document | null;
  collectionForDoc: (doc: Document) => string;
  generateSuggestionChips: (scope: 'doc' | 'all', activeDoc: Document | null) => string[];
  models: any[];
  activeModel: string | null;
  onSelectModel: (model: string | null) => void;
  modelsLoading: boolean;
}

export default function AskPanel({
  askScope,
  answerMode,
  askQ,
  askLoading,
  activeDocId,
  docs,
  status,
  askInputRef,
  onSetAskScope,
  saveAskScope,
  onSetAnswerMode,
  saveAnswerMode,
  onSetAskQ,
  onAsk,
  onClearActive,
  onPreviewDoc,
  exportJson,
  exportZip,
  copyToClipboard,
  showToast,
  getActiveDocument,
  collectionForDoc,
  generateSuggestionChips,
  models,
  activeModel,
  onSelectModel,
  modelsLoading
}: AskPanelProps) {
  const handleAsk = async () => {
    if (!askQ.trim() || askLoading) return;
    await onAsk();
  };

  return (
    <div className="mt-6 p-5 border border-gray-200 dark:border-gray-800 rounded-xl bg-gray-50 dark:bg-gray-900 transition-colors">
      <h2 className="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Ask</h2>
      {/* Scope and Answer Mode Toggles */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Scope:</div>
          <div className="flex gap-1 border border-gray-200 dark:border-gray-700 rounded-md p-0.5 bg-white dark:bg-gray-800">
            <button
              onClick={() => {
                onSetAskScope('doc');
                saveAskScope('doc');
              }}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${askScope === 'doc'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
            >
              This document
            </button>
            <button
              onClick={() => {
                onSetAskScope('all');
                saveAskScope('all');
              }}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${askScope === 'all'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
            >
              All documents
            </button>
          </div>
          {askScope === 'doc' && (() => {
            const activeDoc = getActiveDocument(true);
            if (activeDoc) {
              const filename = activeDoc.paths[0] ? activeDoc.paths[0].split('/').pop() || activeDoc.paths[0] : 'Unknown';
              return (
                <span style={{ fontSize: 11, opacity: 0.7, fontStyle: 'italic' }}>
                  ({filename})
                </span>
              );
            }
            return (
              <span style={{ fontSize: 11, color: '#dc2626', fontStyle: 'italic' }}>
                (No active document)
              </span>
            );
          })()}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <ModelSelector
            models={models || []}
            selectedModel={activeModel}
            onSelect={(m: string) => onSelectModel(m === "" ? null : m)}
            loading={modelsLoading}
          />
          <div style={{ width: 1, height: 20, background: '#eee', margin: '0 4px' }} />
          <div style={{ fontSize: 12, opacity: 0.7 }}>Answer:</div>
          <div className="flex gap-1 border border-gray-200 dark:border-gray-700 rounded-md p-0.5 bg-white dark:bg-gray-800">
            <button
              onClick={() => {
                onSetAnswerMode('retrieve');
                saveAnswerMode('retrieve', askScope);
              }}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${answerMode === 'retrieve'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
            >
              Retrieve
            </button>
            <button
              onClick={() => {
                const llmReachable = status?.llm?.reachable === true;
                if (!llmReachable) {
                  showToast('LLM unavailable — Retrieve only', true);
                  return;
                }
                onSetAnswerMode('synthesize');
                saveAnswerMode('synthesize', askScope);
              }}
              disabled={status?.llm?.reachable !== true}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${answerMode === 'synthesize'
                ? 'bg-blue-600 text-white shadow-sm'
                : status?.llm?.reachable !== true
                  ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
            >
              Synthesize
            </button>
          </div>
          {status?.llm?.reachable !== true && (
            <span style={{ fontSize: 11, color: '#92400e', fontStyle: 'italic' }}>
              LLM unavailable — Retrieve only
            </span>
          )}
        </div>
      </div>
      {/* Active Document Action Bar */}
      {askScope === 'doc' && (() => {
        const activeDoc = getActiveDocument(true);
        if (!activeDoc) return null;

        const filename = activeDoc.paths[0] ? activeDoc.paths[0].split('/').pop() || activeDoc.paths[0] : 'Unknown';
        const kind = activeDoc.kinds.includes('image') ? 'image' : 'text';
        const collection = collectionForDoc(activeDoc);

        return (
          <div className="mb-3 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 flex-auto">
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{filename}</span>
              <span style={{
                fontSize: 11,
                padding: '2px 6px',
                borderRadius: 12,
                background: '#e3f2fd',
                color: '#1976d2'
              }} className="dark:bg-blue-900/30 dark:text-blue-300">
                {kind}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button
                onClick={async () => {
                  await onPreviewDoc(activeDoc.document_id, collection);
                }}
                style={{}}
                className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
              >
                Preview JSON
              </button>
              <button
                onClick={() => {
                  copyToClipboard(activeDoc.document_id);
                  showToast('Document ID copied');
                }}
                style={{}}
                className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
              >
                Copy ID
              </button>
              <button
                onClick={async () => {
                  try {
                    await exportJson(activeDoc.document_id, kind);
                  } catch (err: any) {
                    showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                  }
                }}
                style={{}}
                className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
              >
                Export JSON
              </button>
              <button
                onClick={async () => {
                  try {
                    await exportZip(activeDoc.document_id, kind);
                  } catch (err: any) {
                    showToast("Export failed: not found or not yet indexed. Try again or check logs.", true);
                  }
                }}
                style={{}}
                className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
              >
                Export ZIP
              </button>
              <button
                onClick={() => {
                  onClearActive();
                  showToast('Active document cleared');
                }}
                style={{}}
                className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 cursor-pointer"
              >
                Clear
              </button>
            </div>
          </div>
        );
      })()}
      {(() => {
        const activeDoc = askScope === 'doc' ? getActiveDocument(true) : null;
        const chips = generateSuggestionChips(askScope, activeDoc);
        return (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>
              {askScope === 'doc' && activeDoc
                ? `Try these questions about ${activeDoc.paths[0]?.split('/').pop() || 'this document'}:`
                : 'Try these questions (retrieval-first):'}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {chips.map((example, i) => (
                <button
                  key={i}
                  onClick={() => {
                    onSetAskQ(example);
                    // Focus the input after setting the value
                    setTimeout(() => {
                      if (askInputRef.current) {
                        askInputRef.current.focus();
                      }
                    }, 0);
                  }}
                  style={{}}
                  className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-blue-200 dark:border-gray-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-gray-700 cursor-pointer transition-colors"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        );
      })()}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          ref={askInputRef}
          value={askQ}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onSetAskQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !askLoading && askQ.trim()) {
              e.preventDefault();
              handleAsk();
            }
          }}
          placeholder="ask your data…"
          className="flex-1 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleAsk}
          disabled={askLoading}
          style={{}}
          className={`px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 text-sm font-medium transition-colors ${askLoading
            ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed'
            : 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
        >
          {askLoading ? 'Asking...' : 'Ask'}
        </button>
      </div>
      {(() => {
        const llm = status?.llm;
        const provider = llm?.provider || 'none';
        const reachable = llm?.reachable === true;

        if (!llm || provider === 'none') {
          return (
            <div className="mt-2 p-2 text-xs italic text-gray-500 dark:text-gray-400">
              Synthesis is optional. You'll still get top matching sources + exports.
            </div>
          );
        } else if (provider === 'ollama' && !reachable) {
          return (
            <div className="mt-2 p-2 text-xs rounded-md border bg-yellow-50 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 border-yellow-200 dark:border-yellow-800">
              Ollama configured but unreachable. Open the panel for steps.
            </div>
          );
        } else if (provider === 'ollama' && reachable) {
          return (
            <div className="mt-2 p-2 text-xs rounded-md border bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700">
              Answer generated locally with Ollama. Sources below.
            </div>
          );
        }
        return null;
      })()}
    </div>
  );
}
