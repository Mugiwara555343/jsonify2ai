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
  mode: 'search' | 'llm' | 'retrieve' | 'synthesize';
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
  activeDocId: string | null;
  askScope: 'doc' | 'all';
  answerMode: 'retrieve' | 'synthesize';
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
  activeDocId,
  askScope,
  answerMode,
}: QuickActionsProps) {
  const getTargetDocument = (): Document | null => {
    // If scope is "all", return null (no document targeting)
    if (askScope === 'all') {
      return null;
    }
    // If scope is "doc", only return doc if explicitly selected (no fallback)
    // Priority 1: previewDocId if available and document exists
    if (previewDocId) {
      const doc = documents.find((d) => d.document_id === previewDocId);
      if (doc) return doc;
    }
    // Priority 2: activeDocId if provided and document exists
    if (activeDocId) {
      const doc = documents.find((d) => d.document_id === activeDocId);
      if (doc) return doc;
    }
    // No fallback when scope is 'doc' - require explicit selection
    return null;
  };

  const handleAction = async (actionName: string, prompt: string) => {
    // If scope is "doc" and no target doc, show toast and return
    if (askScope === 'doc') {
      const targetDoc = getTargetDocument();
      if (!targetDoc) {
        showToast('Preview or upload a document first', true);
        return;
      }
    }

    // Clear any previous errors when starting a new action
    onActionError('', actionName); // This will clear the error state
    setLoading(actionName);
    try {
      // Determine documentId based on scope
      const documentId = askScope === 'doc' ? getTargetDocument()?.document_id : undefined;
      const result: AskResp = await askQuestion(prompt, 6, documentId, answerMode);
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

  const getScopeLabel = (): string => {
    if (askScope === 'all') {
      return 'Scope: Global';
    }
    const targetDoc = getTargetDocument();
    if (targetDoc) {
      const filename = targetDoc.paths[0] ? targetDoc.paths[0].split('/').pop() || targetDoc.paths[0] : 'Unknown';
      return `Scope: This doc (${filename})`;
    }
    return 'Scope: This doc (no active document)';
  };

  return (
    <div style={{ marginTop: 16, marginBottom: 16 }}>
      <div className="text-sm font-semibold mb-2 text-gray-900 dark:text-gray-100">Quick Actions</div>
      <div className="text-xs opacity-70 mb-2 text-gray-600 dark:text-gray-400">
        {getScopeLabel()}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {actions.map((action) => {
          const isActive = loading === action.name;
          return (
            <button
              key={action.name}
              onClick={() => handleAction(action.name, action.prompt)}
              disabled={loading !== null}
              className={`px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${isActive
                  ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-700 cursor-not-allowed'
                  : 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
                } ${loading !== null && !isActive ? 'opacity-60' : ''}`}
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
