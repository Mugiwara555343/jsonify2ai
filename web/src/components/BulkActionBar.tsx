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
      <span style={{ fontSize: 13, fontWeight: 600 }}>
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
        style={{
          padding: '6px 12px',
          border: '1px solid #ddd',
          borderRadius: 6,
          background: selectedDocIds.size === 1 ? '#fff' : '#f5f5f5',
          cursor: selectedDocIds.size === 1 ? 'pointer' : 'not-allowed',
          fontSize: 12,
          opacity: selectedDocIds.size === 1 ? 1 : 0.5
        }}
      >
        Set Active
      </button>
      <button
        disabled
        title="Export ZIP works per-document. Select one document."
        style={{
          padding: '6px 12px',
          border: '1px solid #ddd',
          borderRadius: 6,
          background: '#f5f5f5',
          cursor: 'not-allowed',
          fontSize: 12,
          opacity: 0.5
        }}
      >
        Export ZIP
      </button>
      <button
        onClick={onBulkDelete}
        style={{
          padding: '6px 12px',
          border: '1px solid #dc2626',
          borderRadius: 6,
          background: '#fff',
          cursor: 'pointer',
          fontSize: 12,
          color: '#dc2626'
        }}
      >
        Delete selected…
      </button>
      <button
        onClick={onClearSelection}
        style={{
          padding: '6px 12px',
          border: '1px solid #ddd',
          borderRadius: 6,
          background: '#fff',
          cursor: 'pointer',
          fontSize: 12
        }}
      >
        Clear selection
      </button>
    </div>
  );
}
