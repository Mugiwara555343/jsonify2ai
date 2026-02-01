import { RefObject } from 'react';
import { Document } from './IngestionActivity';

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
};
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
};

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
          boxShadow: '-2px 0 8px rgba(0,0,0,0.15)',
          zIndex: 1001,
          overflowY: 'auto',
          padding: 24
        }}
        className="bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800 text-gray-900 dark:text-gray-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, margin: 0 }}>Document Details</h2>
          <button
            onClick={onClose}
            className="text-2xl border-none bg-transparent cursor-pointer p-2 leading-none text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
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
              <span key={j} className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                {k}
              </span>
            ))}
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${status === 'indexed'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-900/50'
              : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-900/50'
              }`}>
              {status === 'indexed' ? `Indexed (${totalChunks} ${totalChunks === 1 ? 'chunk' : 'chunks'})` : 'Pending'}
            </span>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Document ID</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <code className="flex-1 px-2 py-1 rounded text-xs font-mono bg-gray-100 dark:bg-black text-gray-800 dark:text-gray-200 break-all">
              {drawerDoc.document_id}
            </code>
            <button
              onClick={() => {
                copyToClipboard(drawerDoc.document_id);
                showToast('Document ID copied');
              }}
              className="px-2 py-1 text-xs border rounded bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
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
            <div className="p-3 rounded-md text-xs italic bg-gray-50 dark:bg-gray-800/50 text-gray-500 dark:text-gray-400">
              Preview JSON to see sample content
            </div>
          ) : (
            <div className="p-3 rounded-md text-xs max-h-[200px] overflow-y-auto whitespace-pre-wrap break-words bg-gray-50 dark:bg-slate-900 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700 font-mono">
              {snippet}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            onClick={() => onUseThisDoc(drawerDoc.document_id)}
            className="w-full py-2.5 px-4 rounded-md text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 border border-transparent shadow-sm transition-colors"
          >
            Use this doc
          </button>
          <button
            onClick={async () => {
              await onPreviewDoc(drawerDoc.document_id, collection);
            }}
            className="px-4 py-2 border rounded-md text-sm cursor-pointer bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Preview JSON
          </button>
          <button
            onClick={async () => {
              await onExportJson(drawerDoc.document_id, kind);
            }}
            className="px-4 py-2 border rounded-md text-sm cursor-pointer bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Export JSON
          </button>
          <button
            onClick={async () => {
              await onExportZip(drawerDoc.document_id, kind);
            }}
            className="px-4 py-2 border rounded-md text-sm cursor-pointer bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Export ZIP
          </button>
          <button
            onClick={async () => {
              await onDeleteDoc(drawerDoc.document_id, filename);
            }}
            className="px-4 py-2 border border-red-200 dark:border-red-900/50 rounded-md text-sm cursor-pointer bg-white dark:bg-gray-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10"
          >
            Delete
          </button>
        </div>
      </div >
    </>
  );
}
