import { askQuestion } from './api';

type Status = {
  ok: boolean;
  counts: { chunks: number; images: number; total?: number };
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
};

type Document = {
  document_id: string;
  kinds: string[];
  paths: string[];
  counts: Record<string, number>;
};

type AskResp = {
  ok: boolean;
  mode: 'search' | 'llm';
  model?: string;
  answer?: string;
  final?: string;
  sources?: Array<{
    id: string;
    score: number;
    text?: string;
    caption?: string;
    path?: string;
    idx?: number;
    kind?: string;
    document_id?: string;
  }>;
  answers?: Array<{
    id: string;
    score: number;
    text?: string;
    caption?: string;
    path?: string;
    idx?: number;
    kind?: string;
    document_id?: string;
  }>;
  error?: string;
};

type QuickActionsProps = {
  previewDocId: string | null;
  documents: Document[];
  status: Status | null;
  onActionComplete: (result: AskResp, actionName: string) => void;
  onActionError: (error: string, actionName: string) => void;
  loading: string | null;
  setLoading: (actionName: string | null) => void;
  showToast: (msg: string, isError?: boolean) => void;
};

export default function QuickActions({
  previewDocId,
  documents,
  status,
  onActionComplete,
  onActionError,
  loading,
  setLoading,
  showToast,
}: QuickActionsProps) {
  const getTargetDocument = (): Document | null => {
    // Primary: Use previewDocId if available and document exists
    if (previewDocId) {
      const doc = documents.find((d) => d.document_id === previewDocId);
      if (doc) return doc;
    }
    // Fallback: Use most recent document (first in list)
    if (documents.length > 0) {
      return documents[0];
    }
    return null;
  };

  const handleAction = async (actionName: string, prompt: string) => {
    const targetDoc = getTargetDocument();
    if (!targetDoc) {
      showToast('Upload or preview a document first.', true);
      return;
    }

    // Clear any previous errors when starting a new action
    onActionError('', actionName); // This will clear the error state
    setLoading(actionName);
    try {
      const result: AskResp = await askQuestion(prompt, 6, targetDoc.document_id);
      if (result.ok === false) {
        const errorMsg = result.error === 'rate_limited'
          ? 'Rate limited — try again in a few seconds.'
          : `Action failed: ${result.error || 'Unknown error'}`;
        showToast(errorMsg, true);
        onActionError(errorMsg, actionName);
      } else {
        onActionComplete(result, actionName);
      }
    } catch (err: any) {
      const errorMsg = (err?.status === 429 || err?.errorData?.error === 'rate_limited')
        ? 'Rate limited — try again in a few seconds.'
        : `Action error: ${err?.message || err}`;
      showToast(errorMsg, true);
      onActionError(errorMsg, actionName);
    } finally {
      // Always reset loading state, even if callbacks throw or fail
      setLoading(null);
    }
  };

  const actions = [
    {
      name: 'Summarize this doc',
      prompt: 'Summarize the document. Provide 5 bullet points, then 3 key facts with citations.',
    },
    {
      name: 'Extract action items',
      prompt: 'Extract actionable tasks. Output a checklist with owners if present, and due dates if present. Cite evidence.',
    },
    {
      name: 'Create a checklist',
      prompt: 'Create a step-by-step checklist to execute what this document describes. Cite the relevant lines.',
    },
    {
      name: 'Draft an email',
      prompt: 'Draft a concise professional email based on this document\'s intent. Ask 1 clarification question at the end if needed. Cite supporting snippets.',
    },
  ];

  return (
    <div style={{ marginTop: 16, marginBottom: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Quick Actions</div>
      {previewDocId && (
        <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8 }}>
          Using previewed doc
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {actions.map((action) => {
          const isActive = loading === action.name;
          return (
            <button
              key={action.name}
              onClick={() => handleAction(action.name, action.prompt)}
              disabled={loading !== null}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: '1px solid #ddd',
                background: isActive ? '#f3f4f6' : '#fff',
                color: isActive ? '#9ca3af' : '#1976d2',
                cursor: loading !== null ? 'not-allowed' : 'pointer',
                opacity: loading !== null && !isActive ? 0.6 : 1,
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {isActive ? '⏳ ' : ''}
              {action.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
