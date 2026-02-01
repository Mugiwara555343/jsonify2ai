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
    <div className="p-4 rounded-xl shadow-sm mb-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
      <div
        className="flex justify-between items-center cursor-pointer select-none"
        style={{ marginBottom: isCollapsed ? 0 : 12 }}
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs opacity-50 dark:text-gray-400">
            {isCollapsed ? '▶' : '▼'}
          </span>
          <div className="text-sm font-semibold opacity-70 text-gray-900 dark:text-gray-100">
            Ingestion activity {badgeText && <span className="opacity-60">{badgeText}</span>}
          </div>
        </div>
        {!isCollapsed && activityFeed.length > 0 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleClear();
            }}
            className="text-[11px] px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            Clear activity
          </button>
        )}
      </div>
      {!isCollapsed && (
        activityFeed.length === 0 ? (
          <div className="text-xs text-gray-400 italic">
            No ingestion activity yet. Upload files to see activity here.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {activityFeed.map((event, idx) => {
              const timestamp = new Date(event.timestamp);
              const timeStr = timestamp.toLocaleTimeString();
              const getSkipMessage = () => {
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
                if (event.skip_reason === 'unsupported_extension') return 'Unsupported file type. Try .txt/.md/.pdf/.csv/.json';
                if (event.skip_reason === 'empty_file') return 'File is empty';
                if (event.skip_reason === 'extraction_failed') return `Extraction failed: ${event.error || 'Check worker logs'}`;
                if (event.skip_reason === 'processing_failed') return `Processing failed: ${event.error || 'Check worker logs'}`;
                return event.skip_message || event.error || event.skip_reason || 'Skipped';
              };

              const isClickable = !!event.document_id;

              return (
                <div
                  key={idx}
                  className={`p-3 rounded-lg border transition-colors ${isClickable
                    ? 'cursor-pointer hover:bg-blue-50 dark:hover:bg-gray-800 border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50'
                    : 'cursor-default border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50'
                    }`}
                  onClick={async () => {
                    if (!event.document_id) return;
                    const eventDocId = event.document_id;
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
                >
                  <div className="flex justify-between items-start mb-1.5">
                    <div className="flex-1">
                      <div className="text-sm font-semibold mb-1 text-gray-900 dark:text-gray-100">
                        {event.filename}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${event.status === 'processed' ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' :
                          event.status === 'uploading' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300' :
                            event.status === 'indexing' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300' :
                              event.status === 'skipped' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300' :
                                'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
                          }`}>
                          {event.status === 'processed' ? 'Processed' :
                            event.status === 'uploading' ? 'Uploading…' :
                              event.status === 'indexing' ? 'Indexing…' :
                                event.status === 'skipped' ? 'Skipped' :
                                  'Error'}
                        </span>
                        {event.status === 'processed' && (
                          <>
                            {event.chunks !== undefined && (
                              <span className="text-[11px] opacity-70 text-gray-600 dark:text-gray-400">
                                {event.chunks} {event.chunks === 1 ? 'chunk' : 'chunks'}
                              </span>
                            )}
                            {event.images !== undefined && (
                              <span className="text-[11px] opacity-70 text-gray-600 dark:text-gray-400">
                                {event.images} {event.images === 1 ? 'image' : 'images'}
                              </span>
                            )}
                          </>
                        )}
                        {event.document_id && (
                          <code className="text-[10px] font-mono py-0.5 px-1.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700">
                            {event.document_id}
                          </code>
                        )}
                      </div>
                      {event.skip_reason && (
                        <div className="text-[11px] mt-1.5 text-yellow-700 dark:text-yellow-500">
                          {getSkipMessage()}
                        </div>
                      )}
                      {event.error && event.status === 'error' && (
                        <div className="text-[11px] mt-1.5 text-red-600 dark:text-red-400">
                          {event.error}
                        </div>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-400 ml-2 whitespace-nowrap">
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
