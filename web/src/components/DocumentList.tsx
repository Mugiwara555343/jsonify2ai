import React from 'react';
import BulkActionBar from './BulkActionBar';
import { Document } from './IngestionActivity';

function formatRelativeTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  } catch {
    return '';
  }
}

interface DocumentListProps {
  docs: Document[];
  activeDocId: string | null;
  previewDocId: string | null;
  selectedDocIds: Set<string>;
  openMenuDocId: string | null;
  docSearchFilter: string;
  docSortBy: 'newest' | 'oldest' | 'most-chunks';
  onSetActiveDoc: (docId: string) => void;
  saveActiveDocId: (docId: string) => void;
  setAskScope: (scope: 'doc' | 'all') => void;
  saveAskScope: (scope: 'doc' | 'all') => void;
  onOpenDrawer: (docId: string) => void;
  onPreviewDoc: (docId: string, collection: string) => Promise<void>;
  onExportJson: (docId: string, kind: string) => Promise<void>;
  onExportZip: (docId: string, kind: string) => Promise<void>;
  onDeleteDoc: (docId: string) => Promise<void>;
  onToggleSelection: (docId: string) => void;
  onSetOpenMenu: (docId: string | null) => void;
  onSetFilter: (filter: string) => void;
  onSetSort: (sort: 'newest' | 'oldest' | 'most-chunks') => void;
  onBulkDelete: () => Promise<void>;
  onClearSelection: () => void;
  onLoadDocuments: () => Promise<Document[]>;
  showToast: (msg: string, isError?: boolean) => void;
  getDocumentStatus: (doc: Document) => 'indexed' | 'pending';
  collectionForDoc: (doc: Document) => string;
}

export default function DocumentList(props: DocumentListProps) {
  const {
    docs,
    activeDocId,
    previewDocId,
    selectedDocIds,
    openMenuDocId,
    docSearchFilter,
    docSortBy,
    onSetActiveDoc,
    saveActiveDocId,
    setAskScope,
    saveAskScope,
    onOpenDrawer,
    onPreviewDoc,
    onExportJson,
    onExportZip,
    onDeleteDoc,
    onToggleSelection,
    onSetOpenMenu,
    onSetFilter,
    onSetSort,
    onBulkDelete,
    onClearSelection,
    onLoadDocuments,
    showToast,
    getDocumentStatus,
    collectionForDoc
  } = props;

  const handleSetActive = (docId: string) => {
    onSetActiveDoc(docId);
    saveActiveDocId(docId);
    setAskScope('doc');
    saveAskScope('doc');
    showToast('Document set as active');
  };

  // Filter documents
  let filteredDocs = docs;
  if (docSearchFilter.trim()) {
    const filterLower = docSearchFilter.toLowerCase();
    filteredDocs = docs.filter(doc => {
      const path = doc.paths[0] || '';
      const filename = path.split('/').pop() || path;
      return filename.toLowerCase().includes(filterLower) || path.toLowerCase().includes(filterLower);
    });
  }

  // Sort documents
  const sortedDocs = [...filteredDocs].sort((a, b) => {
    if (docSortBy === 'newest') {
      return b.document_id.localeCompare(a.document_id);
    } else if (docSortBy === 'oldest') {
      return a.document_id.localeCompare(b.document_id);
    } else if (docSortBy === 'most-chunks') {
      const totalA = Object.values(a.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
      const totalB = Object.values(b.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
      return totalB - totalA;
    }
    return 0;
  });

  return (
    <div style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 18, marginBottom: 8 }}>Documents</h2>
      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 12 }}>
        When you upload a file, jsonify2ai splits it into text chunks. Each line in the exported .jsonl is one chunk with fields like id, document_id, text, and meta.
      </div>
      <div style={{ marginBottom: 12 }}>
        <button
          onClick={onLoadDocuments}
          className="px-4 py-2 rounded-lg border text-sm transition-colors bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Refresh documents
        </button>
      </div>
      {docs.length > 0 && (
        <>
          <BulkActionBar
            selectedDocIds={selectedDocIds}
            docs={docs}
            onSetActive={handleSetActive}
            onBulkDelete={onBulkDelete}
            onClearSelection={onClearSelection}
          />
          {/* Filter and Sort Toolbar */}
          <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="Search by filename..."
              value={docSearchFilter}
              onChange={(e) => onSetFilter(e.target.value)}
              className="px-3 py-1.5 rounded-md border text-sm bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              style={{
                flex: '1 1 200px',
                minWidth: 150
              }}
            />
            <select
              value={docSortBy}
              onChange={(e) => onSetSort(e.target.value as 'newest' | 'oldest' | 'most-chunks')}
              className="px-3 py-1.5 rounded-md border text-sm bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="most-chunks">Most chunks</option>
            </select>
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {sortedDocs.map((doc, i) => {
              const status = getDocumentStatus(doc);
              const totalChunks = Object.values(doc.counts || {}).reduce((sum: number, count: unknown) => sum + (typeof count === 'number' ? count : 0), 0);
              const isActive = activeDocId === doc.document_id || (previewDocId === doc.document_id && !activeDocId);
              return (
                <div
                  key={i}
                  className="p-3 border border-gray-200 dark:border-gray-800 rounded-lg relative cursor-pointer bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  onClick={() => {
                    onOpenDrawer(doc.document_id);
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <input
                      type="checkbox"
                      checked={selectedDocIds.has(doc.document_id)}
                      onChange={(e) => {
                        e.stopPropagation();
                        onToggleSelection(doc.document_id);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      style={{ cursor: 'pointer' }}
                    />
                    <code
                      style={{
                        fontSize: 12,
                        fontFamily: 'monospace',
                        background: '#f5f5f5',
                        padding: '2px 6px',
                        borderRadius: 4,
                        cursor: 'pointer'
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSetActive(doc.document_id);
                      }}
                      title="Click to set as active document"
                    >
                      {doc.document_id}
                    </code>
                    {((doc as any).meta?.source_system === "chatgpt" || doc.kinds.includes("chat")) && (
                      <>
                        {doc.document_id.startsWith('chatgpt:') && (
                          <span style={{
                            padding: '2px 6px',
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 500,
                            background: '#10b981',
                            color: '#fff',
                            marginLeft: 6
                          }}>
                            ChatGPT
                          </span>
                        )}
                        {isActive && (
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: 6,
                            fontSize: 11,
                            fontWeight: 500,
                            background: '#dbeafe',
                            color: '#1e40af'
                          }}>
                            Active
                          </span>
                        )}
                      </>
                    )}
                    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${status === 'indexed'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-200 dark:border-green-900/50'
                        : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-900/50'
                      }`}>
                      {status === 'indexed' ? `Indexed (${totalChunks} ${totalChunks === 1 ? 'chunk' : 'chunks'})` : 'Pending / not indexed yet'}
                    </span>
                    <div style={{ marginLeft: 'auto', position: 'relative' }} data-menu-container>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSetOpenMenu(openMenuDocId === doc.document_id ? null : doc.document_id);
                        }}
                        style={{
                          fontSize: 18,
                          padding: '2px 8px',
                          border: 'none',
                          background: 'transparent',
                          cursor: 'pointer',
                          opacity: 0.6,
                          color: '#666'
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.6'; }}
                        title="More options"
                      >
                        ⋯
                      </button>
                      {openMenuDocId === doc.document_id && (
                        <div data-menu-container className="absolute right-0 top-full mt-1 min-w-[160px] py-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-[1000]">
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              handleSetActive(doc.document_id);
                            }}
                            className="w-full text-left px-3 py-2 border-none bg-transparent cursor-pointer text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Set Active
                          </button>
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              const collection = collectionForDoc(doc);
                              await onPreviewDoc(doc.document_id, collection);
                            }}
                            className="w-full text-left px-3 py-2 border-none bg-transparent cursor-pointer text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Preview JSON
                          </button>
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              const kind = doc.kinds.includes('image') ? 'image' : 'text';
                              await onExportJson(doc.document_id, kind);
                            }}
                            className="w-full text-left px-3 py-2 border-none bg-transparent cursor-pointer text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Export JSON
                          </button>
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              const kind = doc.kinds.includes('image') ? 'image' : 'text';
                              await onExportZip(doc.document_id, kind);
                            }}
                            className="w-full text-left px-3 py-2 border-none bg-transparent cursor-pointer text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Export ZIP
                          </button>
                          <div style={{ borderTop: '1px solid #eee', margin: '4px 0' }} />
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              try {
                                await onDeleteDoc(doc.document_id);
                              } catch (err: any) {
                                const errorMsg = err?.message || err || 'Delete failed';
                                showToast(errorMsg, true);
                              }
                            }}
                            className="w-full text-left px-3 py-2 border-none bg-transparent cursor-pointer text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            Delete…
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
                    {doc.kinds.map((kind, j) => (
                      <span key={j} style={{ fontSize: 12, background: '#e3f2fd', color: '#1976d2', padding: '2px 6px', borderRadius: 12 }}>
                        {kind}
                      </span>
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
                    {(doc as any).meta?.title ? (
                      <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 4, color: '#374151' }}>
                        {(doc as any).meta.title}
                      </div>
                    ) : (
                      doc.paths[0] && <div>Path: {doc.paths[0]}</div>
                    )}
                    {(doc as any).meta?.logical_path && (
                      <div style={{ fontSize: 10, opacity: 0.6, marginTop: 2 }}>
                        {(doc as any).meta.logical_path}
                      </div>
                    )}
                    <div>Counts: {Object.entries(doc.counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</div>
                    {(doc as any).meta?.title && (
                      <div style={{ fontSize: 11, fontWeight: 500, marginTop: 4, color: '#374151' }}>
                        Title: {(doc as any).meta.title}
                      </div>
                    )}

                    {(doc as any).ingested_at && (
                      <div style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
                        Ingested: {formatRelativeTime((doc as any).ingested_at)}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
      {docs.length === 0 && (
        <div className="p-6 text-center bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg text-gray-500 dark:text-gray-400">
          <div className="text-base font-semibold mb-2 text-gray-700 dark:text-gray-200">
            No documents yet
          </div>
          <div style={{ fontSize: 14, marginBottom: 16 }}>
            Get started by uploading files or using the "Start here" button above.
          </div>
          <div style={{ fontSize: 12, opacity: 0.8 }}>
            Supported formats: .md, .txt, .pdf, .csv, .json, and more
          </div>
        </div>
      )}
    </div>
  );
}
