import { RefObject, useState, useEffect } from 'react';

export type IngestionEvent = {
  timestamp: number;
  filename: string;
  status: 'uploading' | 'indexing' | 'processed' | 'skipped' | 'error';
  chunks?: number;
  images?: number; // For image files
  skip_reason?: string;
  skip_message?: string;
  error?: string;
  document_id?: string;
};

export type Document = {
  document_id: string;
  kinds: string[];
  paths: string[];
  counts: Record<string, number>;
};

interface IngestionActivityProps {
  activityFeed: IngestionEvent[];
  docs: Document[];
  askInputRef: RefObject<HTMLInputElement>;
  onClearActivity: () => void;
  onSetActiveDoc: (docId: string) => void;
  saveActiveDocId: (docId: string) => void;
  setAskScope: (scope: 'doc' | 'all') => void;
  saveAskScope: (scope: 'doc' | 'all') => void;
  showToast: (msg: string, isError?: boolean) => void;
}

export default function IngestionActivity({
  activityFeed,
  docs,
  askInputRef,
  onClearActivity,
  onSetActiveDoc,
  saveActiveDocId,
  setAskScope,
  saveAskScope,
  showToast
}: IngestionActivityProps) {
  // Load persisted state from localStorage
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem('ui.ingestionActivityCollapsed');
    return stored !== null ? stored === 'true' : true; // Default collapsed
  });

  // Sync collapsed state to localStorage
  useEffect(() => {
    localStorage.setItem('ui.ingestionActivityCollapsed', String(isCollapsed));
  }, [isCollapsed]);

  // Calculate badge text
  const hasRunning = activityFeed.some(e => e.status === 'indexing' || e.status === 'uploading');
  const badgeText = activityFeed.length > 0
    ? hasRunning
      ? `(${activityFeed.length}, running)`
      : `(${activityFeed.length})`
    : '';

  const handleClear = () => {
    onClearActivity();
    localStorage.setItem('ui.hideIngestionActivity', 'true');
  };

  return (
    <div style={{
      padding: 16,
      borderRadius: 12,
      boxShadow: '0 1px 4px rgba(0,0,0,.08)',
      marginBottom: 16,
      background: 'var(--bg)',
      border: '1px solid rgba(0,0,0,.1)'
    }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: isCollapsed ? 0 : 12,
          cursor: 'pointer'
        }}
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, opacity: 0.5 }}>
            {isCollapsed ? '▶' : '▼'}
          </span>
          <div style={{ fontSize: 13, fontWeight: 600, opacity: 0.7 }}>
            Ingestion activity {badgeText && <span style={{ opacity: 0.6 }}>{badgeText}</span>}
          </div>
        </div>
        {!isCollapsed && activityFeed.length > 0 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleClear();
            }}
            style={{
              fontSize: 11,
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid #ddd',
              background: '#fff',
              color: '#666',
              cursor: 'pointer'
            }}
          >
            Clear activity
          </button>
        )}
      </div>
      {!isCollapsed && (
        activityFeed.length === 0 ? (
          <div style={{ fontSize: 12, color: '#9ca3af', fontStyle: 'italic' }}>
            No ingestion activity yet. Upload files to see activity here.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {activityFeed.map((event, idx) => {
            const timestamp = new Date(event.timestamp);
            const timeStr = timestamp.toLocaleTimeString();
            const getSkipMessage = () => {
              // Map reason codes to human-readable messages
              const reason = event.skip_reason || event.error || '';
              if (reason === 'unsupported_extension') return 'Unsupported extension';
              if (reason === 'empty_file') return 'File is empty';
              if (reason === 'parse_failed') return 'Extraction failed';
              if (reason === 'extraction_failed') return 'Extraction failed';
              if (reason === 'processing_failed') return 'Processing failed';
              if (reason === 'audio_dev_mode') return 'Audio dev-mode: transcription skipped';
              if (reason === 'dev_mode_no_embed') return 'Dev-mode: vector embeddings skipped';
              if (reason === 'ok') return 'Ingested successfully';
              if (reason === 'worker_error') return 'Processing error';
              // Fallback to original logic for backward compatibility
              if (event.skip_reason === 'unsupported_extension') return 'Unsupported file type. Try .txt/.md/.pdf/.csv/.json';
              if (event.skip_reason === 'empty_file') return 'File is empty';
              if (event.skip_reason === 'extraction_failed') return `Extraction failed: ${event.error || 'Check worker logs'}`;
              if (event.skip_reason === 'processing_failed') return `Processing failed: ${event.error || 'Check worker logs'}`;
              return event.skip_message || event.error || event.skip_reason || 'Skipped';
            };
            return (
              <div
                key={idx}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: '1px solid #e5e7eb',
                  background: '#fafafa',
                  cursor: event.document_id ? 'pointer' : 'default'
                }}
                onClick={async () => {
                  if (!event.document_id) return;
                  const eventDocId = event.document_id;
                  // Find document - handle case where document_id might be shortened (first 8 chars)
                  const doc = docs.find(d =>
                    d.document_id === eventDocId ||
                    d.document_id.startsWith(eventDocId) ||
                    (eventDocId.length <= 8 && d.document_id.startsWith(eventDocId))
                  );
                  if (doc) {
                    onSetActiveDoc(doc.document_id);
                    saveActiveDocId(doc.document_id);
                    setAskScope('doc');
                    saveAskScope('doc');
                    // Scroll to Ask section
                    setTimeout(() => {
                      askInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      setTimeout(() => {
                        askInputRef.current?.focus();
                      }, 300);
                    }, 100);
                  } else {
                    showToast('Document no longer exists.', true);
                  }
                }}
                onMouseEnter={(e) => {
                  if (event.document_id) {
                    e.currentTarget.style.background = '#f0f9ff';
                    e.currentTarget.style.borderColor = '#bae6fd';
                  }
                }}
                onMouseLeave={(e) => {
                  if (event.document_id) {
                    e.currentTarget.style.background = '#fafafa';
                    e.currentTarget.style.borderColor = '#e5e7eb';
                  }
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                      {event.filename}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 500,
                        background:
                          event.status === 'processed' ? '#c6f6d5' :
                          event.status === 'uploading' ? '#dbeafe' :
                          event.status === 'indexing' ? '#fed7aa' :
                          event.status === 'skipped' ? '#fef3c7' :
                          '#fed7d7',
                        color:
                          event.status === 'processed' ? '#166534' :
                          event.status === 'uploading' ? '#1e40af' :
                          event.status === 'indexing' ? '#92400e' :
                          event.status === 'skipped' ? '#78350f' :
                          '#991b1b'
                      }}>
                        {event.status === 'processed' ? 'Processed' :
                         event.status === 'uploading' ? 'Uploading…' :
                         event.status === 'indexing' ? 'Indexing…' :
                         event.status === 'skipped' ? 'Skipped' :
                         'Error'}
                      </span>
                      {event.status === 'processed' && (
                        <>
                          {event.chunks !== undefined && (
                            <span style={{ fontSize: 11, opacity: 0.7 }}>
                              {event.chunks} {event.chunks === 1 ? 'chunk' : 'chunks'}
                            </span>
                          )}
                          {event.images !== undefined && (
                            <span style={{ fontSize: 11, opacity: 0.7 }}>
                              {event.images} {event.images === 1 ? 'image' : 'images'}
                            </span>
                          )}
                        </>
                      )}
                      {event.document_id && (
                        <code style={{ fontSize: 10, fontFamily: 'monospace', background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
                          {event.document_id}
                        </code>
                      )}
                    </div>
                    {event.skip_reason && (
                      <div style={{ fontSize: 11, marginTop: 6, color: '#92400e' }}>
                        {getSkipMessage()}
                      </div>
                    )}
                    {event.error && event.status === 'error' && (
                      <div style={{ fontSize: 11, marginTop: 6, color: '#dc2626' }}>
                        {event.error}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: '#9ca3af', marginLeft: 8 }}>
                    {timeStr}
                  </div>
                </div>
              </div>
            );
          })}
          </div>
        )
      )}
    </div>
  );
}
