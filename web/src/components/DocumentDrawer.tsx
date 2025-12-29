import { RefObject } from 'react';
import { Document } from './IngestionActivity';

type Hit = { id: string; score: number; text?: string; caption?: string; path?: string; idx?: number; kind?: string; document_id?: string };
type AskResp = { ok: boolean; mode: 'search' | 'llm'; model?: string; answer?: string; final?: string; sources?: Hit[]; answers?: Hit[]; error?: string };

interface DocumentDrawerProps {
  drawerDocId: string | null;
  docs: Document[];
  previewDocId: string | null;
  previewLines: string[] | null;
  ans: AskResp | null;
  askScope: 'doc' | 'all';
  activeDocId: string | null;
  llmReachable: boolean;
  askInputRef: RefObject<HTMLInputElement>;
  openMenuDocId: string | null;
  onClose: () => void;
  onUseThisDoc: (docId: string) => void;
  onPreviewDoc: (docId: string, collection: string) => Promise<void>;
  onExportJson: (docId: string, kind: string) => Promise<void>;
  onExportZip: (docId: string, kind: string) => Promise<void>;
  onDeleteDoc: (docId: string, filename: string) => Promise<void>;
  copyToClipboard: (text: string) => void;
  showToast: (msg: string, isError?: boolean) => void;
  getDocumentStatus: (doc: Document) => 'indexed' | 'pending';
  collectionForDoc: (doc: Document) => string;
}

export default function DocumentDrawer({
  drawerDocId,
  docs,
  previewDocId,
  previewLines,
  ans,
  askScope,
  activeDocId,
  llmReachable,
  askInputRef,
  openMenuDocId,
  onClose,
  onUseThisDoc,
  onPreviewDoc,
  onExportJson,
  onExportZip,
  onDeleteDoc,
  copyToClipboard,
  showToast,
  getDocumentStatus,
  collectionForDoc
}: DocumentDrawerProps) {
  if (!drawerDocId) {
    return null;
  }

  const drawerDoc = docs.find(d => d.document_id === drawerDocId);
  if (!drawerDoc) {
    return null;
  }

  const filename = drawerDoc.paths[0] ? drawerDoc.paths[0].split('/').pop() || drawerDoc.paths[0] : 'Unknown';
  const kind = drawerDoc.kinds.includes('image') ? 'image' : 'text';
  const collection = collectionForDoc(drawerDoc);
  const status = getDocumentStatus(drawerDoc);
  const totalChunks = Object.values(drawerDoc.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);

  // Extract snippet - prioritize last Ask result, then previewLines
  let snippet = '';
  let snippetSource: 'ask_result' | 'preview' | 'none' = 'none';

  // Strategy 1: Use last Ask result if it's a global retrieve
  if (ans && ans.sources && ans.sources.length > 0) {
    // Find best matching source for this doc
    const matchingHits = ans.sources.filter(hit => hit.document_id === drawerDocId);
    if (matchingHits.length > 0) {
      // Sort by score, take highest
      matchingHits.sort((a, b) => (b.score || 0) - (a.score || 0));
      const bestHit = matchingHits[0];
      const fullText = bestHit.text || bestHit.caption || '';
      snippet = fullText.substring(0, 500);
      if (snippet.length < fullText.length) {
        snippet += '...';
      }
      snippetSource = 'ask_result';
    }
  }

  // Strategy 2: Fallback to previewLines
  if (!snippet && previewDocId === drawerDocId && previewLines && previewLines.length > 0) {
    try {
      const firstLine = previewLines[0];
      const obj = JSON.parse(firstLine);
      const fullText = obj.text || obj.caption || '';
      snippet = fullText.substring(0, 500);
      if (snippet.length < fullText.length) {
        snippet += '...';
      }
      snippetSource = 'preview';
    } catch {
      // Leave snippet empty
    }
  }

  // Strategy 3: Show hint if no snippet
  if (!snippet) {
    snippetSource = 'none';
  }

  return (
    <>
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          zIndex: 1000
        }}
        onClick={onClose}
      />
      <div
        style={{
          position: 'fixed',
          right: 0,
          top: 0,
          bottom: 0,
          width: '400px',
          maxWidth: '90vw',
          background: '#fff',
          boxShadow: '-2px 0 8px rgba(0,0,0,0.15)',
          zIndex: 1001,
          overflowY: 'auto',
          padding: 24
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, margin: 0 }}>Document Details</h2>
          <button
            onClick={onClose}
            style={{
              fontSize: 24,
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              padding: '4px 8px',
              lineHeight: 1
            }}
          >
            ×
          </button>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{filename}</div>
          <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
            {drawerDoc.paths[0]}
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            {drawerDoc.kinds.map((k, j) => (
              <span key={j} style={{
                fontSize: 11,
                padding: '2px 6px',
                borderRadius: 12,
                background: '#e3f2fd',
                color: '#1976d2'
              }}>
                {k}
              </span>
            ))}
            <span style={{
              padding: '3px 8px',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 500,
              background: status === 'indexed' ? '#c6f6d5' : '#fef3c7',
              color: status === 'indexed' ? '#166534' : '#78350f'
            }}>
              {status === 'indexed' ? `Indexed (${totalChunks} ${totalChunks === 1 ? 'chunk' : 'chunks'})` : 'Pending'}
            </span>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Document ID</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <code style={{
              fontSize: 11,
              fontFamily: 'monospace',
              background: '#f5f5f5',
              padding: '4px 8px',
              borderRadius: 4,
              flex: 1
            }}>
              {drawerDoc.document_id}
            </code>
            <button
              onClick={() => {
                copyToClipboard(drawerDoc.document_id);
                showToast('Document ID copied');
              }}
              style={{
                fontSize: 12,
                padding: '4px 8px',
                border: '1px solid #ddd',
                borderRadius: 4,
                background: '#fff',
                cursor: 'pointer'
              }}
            >
              Copy
            </button>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Chunk Counts</div>
          <div style={{ fontSize: 12, color: '#666' }}>
            {Object.entries(drawerDoc.counts).map(([k, v]) => (
              <div key={k}>{k}: {v}</div>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
            {snippetSource === 'ask_result' && 'Relevant excerpt (from last search)'}
            {snippetSource === 'preview' && 'Sample content'}
            {snippetSource === 'none' && 'Sample Content'}
          </div>
          {snippetSource === 'none' ? (
            <div style={{
              padding: 12,
              background: '#f9fafb',
              borderRadius: 6,
              fontSize: 12,
              color: '#6b7280',
              fontStyle: 'italic'
            }}>
              Preview JSON to see sample content
            </div>
          ) : (
            <div style={{
              padding: 12,
              background: '#f9fafb',
              borderRadius: 6,
              fontSize: 12,
              color: '#374151',
              maxHeight: '200px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}>
              {snippet}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            onClick={() => onUseThisDoc(drawerDoc.document_id)}
            style={{
              padding: '12px 16px',
              border: 'none',
              borderRadius: 6,
              background: '#1976d2',
              color: '#fff',
              cursor: 'pointer',
              fontSize: 14,
              fontWeight: 600
            }}
          >
            Use this doc
          </button>
          <button
            onClick={async () => {
              await onPreviewDoc(drawerDoc.document_id, collection);
            }}
            style={{
              padding: '8px 16px',
              border: '1px solid #ddd',
              borderRadius: 6,
              background: '#fff',
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            Preview JSON
          </button>
          <button
            onClick={async () => {
              await onExportJson(drawerDoc.document_id, kind);
            }}
            style={{
              padding: '8px 16px',
              border: '1px solid #ddd',
              borderRadius: 6,
              background: '#fff',
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            Export JSON
          </button>
          <button
            onClick={async () => {
              await onExportZip(drawerDoc.document_id, kind);
            }}
            style={{
              padding: '8px 16px',
              border: '1px solid #ddd',
              borderRadius: 6,
              background: '#fff',
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            Export ZIP
          </button>
          <button
            onClick={async () => {
              await onDeleteDoc(drawerDoc.document_id, filename);
            }}
            style={{
              padding: '8px 16px',
              border: '1px solid #dc2626',
              borderRadius: 6,
              background: '#fff',
              cursor: 'pointer',
              fontSize: 13,
              color: '#dc2626'
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </>
  );
}
