import { Document } from './IngestionActivity';

interface BulkActionBarProps {
  selectedDocIds: Set<string>;
  docs: Document[];
  onSetActive: (docId: string) => void;
  onBulkDelete: () => Promise<void>;
  onClearSelection: () => void;
}

export default function BulkActionBar({
  selectedDocIds,
  docs,
  onSetActive,
  onBulkDelete,
  onClearSelection
}: BulkActionBarProps) {
  if (selectedDocIds.size === 0) {
    return null;
  }

  return (
    <div className="mb-3 p-3 rounded-lg flex items-center gap-3 flex-wrap bg-blue-50 dark:bg-slate-900 border border-blue-200 dark:border-slate-700">
      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
        {selectedDocIds.size} {selectedDocIds.size === 1 ? 'document' : 'documents'} selected
      </span>
      <button
        onClick={async () => {
          if (selectedDocIds.size === 1) {
            const docId = Array.from(selectedDocIds)[0];
            const doc = docs.find(d => d.document_id === docId);
            if (doc) {
              onSetActive(docId);
              onClearSelection();
            }
          }
        }}
        disabled={selectedDocIds.size !== 1}
        className={`px-3 py-1.5 rounded-md border text-xs transition-colors ${selectedDocIds.size === 1
            ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer'
            : 'bg-gray-100 dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
          }`}
      >
        Set Active
      </button>
      <button
        disabled
        title="Export ZIP works per-document. Select one document."
        className="px-3 py-1.5 rounded-md border text-xs bg-gray-100 dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50"
      >
        Export ZIP
      </button>
      <button
        onClick={onBulkDelete}
        className="px-3 py-1.5 rounded-md border text-xs bg-white dark:bg-gray-800 border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 cursor-pointer"
      >
        Delete selected…
      </button>
      <button
        onClick={onClearSelection}
        className="px-3 py-1.5 rounded-md border text-xs bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
      >
        Clear selection
      </button>
    </div>
  );
}
