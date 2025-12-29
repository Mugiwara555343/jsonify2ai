import { RefObject } from 'react';
import { Document } from './IngestionActivity';

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
  generateSuggestionChips
}: AskPanelProps) {
  const handleAsk = async () => {
    if (!askQ.trim() || askLoading) return;
    await onAsk();
  };

  return (
    <div style={{
      marginTop: 24,
      padding: 20,
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      background: '#fafafa',
    }}>
      <h2 style={{ fontSize: 18, marginBottom: 8 }}>Ask</h2>
      {/* Scope and Answer Mode Toggles */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Scope:</div>
          <div style={{ display: 'flex', gap: 4, border: '1px solid #ddd', borderRadius: 6, padding: 2 }}>
            <button
              onClick={() => {
                onSetAskScope('doc');
                saveAskScope('doc');
              }}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                border: 'none',
                background: askScope === 'doc' ? '#1976d2' : 'transparent',
                color: askScope === 'doc' ? '#fff' : '#666',
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: askScope === 'doc' ? 500 : 400
              }}
            >
              This document
            </button>
            <button
              onClick={() => {
                onSetAskScope('all');
                saveAskScope('all');
              }}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                border: 'none',
                background: askScope === 'all' ? '#1976d2' : 'transparent',
                color: askScope === 'all' ? '#fff' : '#666',
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: askScope === 'all' ? 500 : 400
              }}
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
          <div style={{ fontSize: 12, opacity: 0.7 }}>Answer:</div>
          <div style={{ display: 'flex', gap: 4, border: '1px solid #ddd', borderRadius: 6, padding: 2 }}>
            <button
              onClick={() => {
                onSetAnswerMode('retrieve');
                saveAnswerMode('retrieve', askScope);
              }}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                border: 'none',
                background: answerMode === 'retrieve' ? '#1976d2' : 'transparent',
                color: answerMode === 'retrieve' ? '#fff' : '#666',
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: answerMode === 'retrieve' ? 500 : 400
              }}
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
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                border: 'none',
                background: answerMode === 'synthesize' ? '#1976d2' : 'transparent',
                color: answerMode === 'synthesize' ? '#fff' : (status?.llm?.reachable !== true ? '#999' : '#666'),
                cursor: status?.llm?.reachable !== true ? 'not-allowed' : 'pointer',
                fontSize: 12,
                fontWeight: answerMode === 'synthesize' ? 500 : 400,
                opacity: status?.llm?.reachable !== true ? 0.5 : 1
              }}
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
          <div style={{
            marginBottom: 12,
            padding: 12,
            background: '#f0f9ff',
            border: '1px solid #bae6fd',
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 auto' }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{filename}</span>
              <span style={{
                fontSize: 11,
                padding: '2px 6px',
                borderRadius: 12,
                background: '#e3f2fd',
                color: '#1976d2'
              }}>
                {kind}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button
                onClick={async () => {
                  await onPreviewDoc(activeDoc.document_id, collection);
                }}
                style={{
                  fontSize: 12,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid #ddd',
                  background: '#fff',
                  color: '#1976d2',
                  cursor: 'pointer'
                }}
              >
                Preview JSON
              </button>
              <button
                onClick={() => {
                  copyToClipboard(activeDoc.document_id);
                  showToast('Document ID copied');
                }}
                style={{
                  fontSize: 12,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid #ddd',
                  background: '#fff',
                  color: '#1976d2',
                  cursor: 'pointer'
                }}
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
                style={{
                  fontSize: 12,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid #ddd',
                  background: '#fff',
                  color: '#1976d2',
                  cursor: 'pointer'
                }}
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
                style={{
                  fontSize: 12,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid #ddd',
                  background: '#fff',
                  color: '#1976d2',
                  cursor: 'pointer'
                }}
              >
                Export ZIP
              </button>
              <button
                onClick={() => {
                  onClearActive();
                  showToast('Active document cleared');
                }}
                style={{
                  fontSize: 12,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: '1px solid #dc2626',
                  background: '#fff',
                  color: '#dc2626',
                  cursor: 'pointer'
                }}
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
                  style={{
                    fontSize: 12,
                    padding: '4px 8px',
                    borderRadius: 6,
                    border: '1px solid #ddd',
                    background: '#fff',
                    color: '#1976d2',
                    cursor: 'pointer',
                    textDecoration: 'none'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = '#f0f9ff';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = '#fff';
                  }}
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
          style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid #ddd' }}
        />
        <button
          onClick={handleAsk}
          disabled={askLoading}
          style={{
            padding: '12px 16px',
            borderRadius: 8,
            border: '1px solid #ddd',
            opacity: askLoading ? 0.6 : 1,
            cursor: askLoading ? 'not-allowed' : 'pointer'
          }}
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
            <div style={{
              marginTop: 8,
              padding: 8,
              fontSize: 12,
              color: '#6b7280',
              fontStyle: 'italic',
            }}>
              Synthesis is optional. You'll still get top matching sources + exports.
            </div>
          );
        } else if (provider === 'ollama' && !reachable) {
          return (
            <div style={{
              marginTop: 8,
              padding: 8,
              fontSize: 12,
              color: '#92400e',
              background: '#fef3c7',
              borderRadius: 6,
              border: '1px solid #fde68a',
            }}>
              Ollama configured but unreachable. Open the panel for steps.
            </div>
          );
        } else if (provider === 'ollama' && reachable) {
          return (
            <div style={{
              marginTop: 8,
              padding: 8,
              fontSize: 12,
              color: '#0369a1',
              background: '#e0f2fe',
              borderRadius: 6,
              border: '1px solid #bae6fd',
            }}>
              Answer generated locally with Ollama. Sources below.
            </div>
          );
        }
        return null;
      })()}
    </div>
  );
}
