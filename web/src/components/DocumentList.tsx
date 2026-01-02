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
          style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #ddd', fontSize: 14 }}
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
              style={{
                flex: '1 1 200px',
                minWidth: 150,
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid #ddd',
                fontSize: 13
              }}
            />
            <select
              value={docSortBy}
              onChange={(e) => onSetSort(e.target.value as 'newest' | 'oldest' | 'most-chunks')}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid #ddd',
                fontSize: 13
              }}
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
                  style={{
                    padding: 12,
                    border: '1px solid #eee',
                    borderRadius: 8,
                    position: 'relative',
                    cursor: 'pointer'
                  }}
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
                    <span style={{
                      padding: '3px 8px',
                      borderRadius: 6,
                      fontSize: 11,
                      fontWeight: 500,
                      background: status === 'indexed' ? '#c6f6d5' : '#fef3c7',
                      color: status === 'indexed' ? '#166534' : '#78350f'
                    }}>
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
                        <div data-menu-container style={{
                          position: 'absolute',
                          right: 0,
                          top: '100%',
                          marginTop: 4,
                          background: '#fff',
                          border: '1px solid #ddd',
                          borderRadius: 6,
                          boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                          zIndex: 1000,
                          minWidth: 150,
                          padding: '4px 0'
                        }}>
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              onSetOpenMenu(null);
                              handleSetActive(doc.document_id);
                            }}
                            style={{
                              width: '100%',
                              textAlign: 'left',
                              padding: '6px 12px',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              fontSize: 13
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                            style={{
                              width: '100%',
                              textAlign: 'left',
                              padding: '6px 12px',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              fontSize: 13
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                            style={{
                              width: '100%',
                              textAlign: 'left',
                              padding: '6px 12px',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              fontSize: 13
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                            style={{
                              width: '100%',
                              textAlign: 'left',
                              padding: '6px 12px',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              fontSize: 13
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = '#f5f5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                            style={{
                              width: '100%',
                              textAlign: 'left',
                              padding: '6px 12px',
                              border: 'none',
                              background: 'transparent',
                              cursor: 'pointer',
                              fontSize: 13,
                              color: '#dc2626'
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = '#fef2f2'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                    {doc.paths[0] && <div>Path: {doc.paths[0]}</div>}
                    <div>Counts: {Object.entries(doc.counts).map(([k, v]) => `${k}: ${v}`).join(', ')}</div>
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
        <div style={{
          padding: 24,
          textAlign: 'center',
          background: '#f9fafb',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          color: '#6b7280'
        }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: '#374151' }}>
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
