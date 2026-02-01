type Status = {
  ok: boolean;
  counts: { chunks: number; images: number; total?: number };
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
};

type Hit = {
  id: string;
  score: number;
  text?: string;
  caption?: string;
  path?: string;
  idx?: number;
  kind?: string;
  document_id?: string;
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
  synth_skipped_reason?: string;
  top_score?: number;
  min_synth_score?: number;
};

type AssistantOutputProps = {
  result: AskResp | null;
  status: Status | null;
  loading: boolean;
  error: string | null;
  actionName?: string;
  showToast?: (msg: string, isError?: boolean) => void;
  scope?: 'doc' | 'all';
  activeDocFilename?: string;
  onUseDoc?: (documentId: string, llmReachable: boolean) => void;
  documents?: Array<{ document_id: string; paths: string[] }>;
};

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    // Success - caller can show toast
  }).catch(() => {
    // Fallback for older browsers
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
  });
}

function truncateId(id: string, maxLength = 12): string {
  if (id.length <= maxLength) return id;
  return id.substring(0, maxLength) + '...';
}

function truncatePath(path: string, maxLength = 50): string {
  if (path.length <= maxLength) return path;
  return '...' + path.substring(path.length - maxLength);
}

export default function AssistantOutput({
  result,
  status,
  loading,
  error,
  actionName,
  showToast,
  scope,
  activeDocFilename,
  onUseDoc,
  documents,
}: AssistantOutputProps) {
  // Empty state
  if (!loading && !error && !result) {
    return (
      <div className="mt-3 p-4 text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 rounded-lg border border-dashed border-gray-300 dark:border-gray-700">
        <div className="text-sm font-medium mb-1">Ready to help</div>
        <div className="text-xs opacity-80">
          Ask a question to get started.
        </div>
      </div>
    );
  }

  // Loading state
  if (loading) {
    const loadingText = status?.llm?.reachable === true
      ? 'Thinking…'
      : 'Searching your data…';
    return (
      <div style={{ marginTop: 12, padding: 12, color: '#666', fontSize: 14 }}>
        {loadingText}
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="mt-3 p-3 border border-red-200 dark:border-red-900 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
        {error}
      </div>
    );
  }

  // Result display
  if (!result) return null;

  const title = actionName || 'Assistant Output';
  const mainText = result.final?.trim() || result.answer?.trim() || '';
  const sources = result.sources || result.answers || [];
  const hasLLM = status?.llm?.provider === 'ollama' && status?.llm?.reachable === true;
  const showLowConfidence = result.synth_skipped_reason === "low_confidence";
  const showNoSources = result.synth_skipped_reason === "no_sources";
  const showRetrieveOnly = result.synth_skipped_reason === "retrieve_only";

  // Build markdown for copy
  const buildMarkdown = (): string => {
    let md = `# ${title}\n\n`;
    if (mainText) {
      md += `${mainText}\n\n`;
    }
    if (sources.length > 0) {
      md += `## Citations\n\n`;
      sources.forEach((source, i) => {
        const filename = source.path ? source.path.split('/').pop() || source.path : `Source ${i + 1}`;
        const snippet = source.text || source.caption || '';
        const docId = source.document_id ? truncateId(source.document_id) : null;
        md += `### ${filename}\n`;
        if (docId) {
          md += `Document ID: ${docId}\n`;
        }
        if (source.score !== undefined) {
          md += `Score: ${source.score.toFixed(2)}\n`;
        }
        if (snippet) {
          md += `\n${snippet}\n\n`;
        }
      });
    }
    return md;
  };

  const handleCopy = () => {
    const markdown = buildMarkdown();
    copyToClipboard(markdown);
    if (showToast) {
      showToast('Output copied to clipboard');
    }
  };

  return (
    <div className="mt-3 p-3 border border-gray-200 dark:border-gray-800 rounded-xl bg-white dark:bg-black transition-colors">
      {/* Title and Model Badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 16 }}>{title}</div>
        {hasLLM && (
          <span style={{
            fontSize: 11,
            padding: '2px 6px',
            borderRadius: 999,
            background: '#eef2ff',
            color: '#3730a3',
          }}>
            local (ollama)
          </span>
        )}
        {!hasLLM && sources.length > 0 && !showNoSources && (
          <span style={{
            fontSize: 11,
            padding: '2px 6px',
            borderRadius: 999,
            background: '#f3f4f6',
            color: '#6b7280',
          }}>
            Top matches below
          </span>
        )}
        {showLowConfidence && (
          <span style={{
            fontSize: 11,
            padding: '2px 6px',
            borderRadius: 999,
            background: '#fef3c7',
            color: '#92400e',
          }}>
            Low confidence — showing top matches only
          </span>
        )}
        {showNoSources && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200">
            No matching sources found
          </span>
        )}
        {(mainText || sources.length > 0) && (
          <button
            onClick={handleCopy}
            className="ml-auto px-3 py-1 rounded-md border text-xs bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            Copy output
          </button>
        )}
      </div>
      {/* Score transparency for low confidence */}
      {showLowConfidence && result.top_score !== undefined && result.min_synth_score !== undefined && (
        <div style={{ fontSize: 11, color: '#92400e', marginTop: 4, marginBottom: 8 }}>
          Top score: {result.top_score.toFixed(2)} (threshold {result.min_synth_score.toFixed(2)})
        </div>
      )}
      {/* Scope Label */}
      {scope && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4, color: '#6b7280' }}>
            {scope === 'doc' && activeDocFilename
              ? `Using document: ${activeDocFilename}`
              : scope === 'doc'
                ? 'Using document: (no active document)'
                : 'Using all indexed documents'}
          </div>
          {scope === 'all' && (
            <div style={{ fontSize: 11, color: '#f59e0b', opacity: 0.8 }}>
              Global mode can mix unrelated files. Switch to 'This document' for precise answers.
            </div>
          )}
        </div>
      )}

      {/* Main Output */}
      {mainText && (
        <div className="mb-4 p-4 border rounded-lg shadow-sm bg-gray-50 dark:!bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100">
          <div className="whitespace-pre-wrap leading-relaxed text-sm">
            {mainText}
          </div>
        </div>
      )}

      {/* Top Matching Documents (Global scope only) */}
      {scope === 'all' && sources.length > 0 && (() => {
        // Group sources by document_id
        const grouped = new Map<string, { sources: typeof sources; bestScore: number; filename: string }>();
        sources.forEach((source) => {
          const docId = source.document_id || 'unknown';
          const filename = source.path ? source.path.split('/').pop() || source.path : 'Unknown';
          const score = source.score || 0;

          if (!grouped.has(docId)) {
            grouped.set(docId, { sources: [], bestScore: score, filename });
          }
          const group = grouped.get(docId)!;
          group.sources.push(source);
          if (score > group.bestScore) {
            group.bestScore = score;
          }
        });

        const groupedArray = Array.from(grouped.entries())
          .map(([docId, data]) => ({ docId, ...data }))
          .sort((a, b) => b.bestScore - a.bestScore)
          .slice(0, 5); // Top 5 documents

        if (groupedArray.length === 0) return null;

        return (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8, fontStyle: 'italic' }}>
              Select a document to unlock actions like summaries and checklists.
            </div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
              Top matching documents
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {groupedArray.map((group) => {
                const docExists = documents?.some(d => d.document_id === group.docId);
                const llmReachable = status?.llm?.reachable === true;
                return (
                  <div
                    key={group.docId}
                    className="p-3 border rounded-lg flex justify-between items-center flex-wrap gap-2 transition-colors bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 4 }}>
                        {group.filename}
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 11, color: '#6b7280' }}>
                          {group.sources.length} {group.sources.length === 1 ? 'source' : 'sources'}
                        </span>
                        <span style={{
                          fontSize: 11,
                          padding: '2px 6px',
                          borderRadius: 4,
                          background: '#f0f9ff',
                          color: '#0369a1',
                        }}>
                          best: {group.bestScore.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    {docExists && onUseDoc && (
                      <button
                        onClick={() => {
                          onUseDoc(group.docId, llmReachable);
                          if (showToast) {
                            showToast('Switched to document mode');
                          }
                        }}
                        style={{
                          padding: '6px 12px',
                          borderRadius: 6,
                          border: '1px solid #1976d2',
                          background: '#1976d2',
                          color: '#fff',
                          cursor: 'pointer',
                          fontSize: 12,
                          fontWeight: 500,
                        }}
                      >
                        Use this doc
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* Citations */}
      {sources.length > 0 && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12 }}>Sources</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {sources.map((source, i) => {
              const filename = source.path ? source.path.split('/').pop() || source.path : (source.id || `Source ${i + 1}`);
              const docId = source.document_id ? truncateId(source.document_id) : null;
              const snippet = source.text || source.caption || '';
              const score = source.score !== undefined ? source.score : null;
              const path = source.path ? truncatePath(source.path) : null;

              return (
                <div
                  key={i}
                  className="p-3 border rounded-lg transition-colors bg-white dark:!bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="font-medium text-[13px] text-gray-900 dark:text-gray-100">{filename}</span>
                    {path && (
                      <span className="text-[11px] opacity-70 font-mono text-gray-600 dark:text-gray-400">
                        {path}
                      </span>
                    )}
                    {docId && (
                      <code className="text-[11px] font-mono bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-700 dark:text-gray-300">
                        {docId}
                      </code>
                    )}
                    {score !== null && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                        score: {score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  {snippet && (
                    <div className="text-sm leading-relaxed font-mono whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800 p-2 rounded text-gray-700 dark:text-gray-300">
                      {snippet}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* No sources fallback */}
      {sources.length === 0 && (
        <div className="text-gray-500 dark:text-gray-400 text-sm p-3 bg-gray-50 dark:bg-gray-900 rounded-md italic">
          No matching snippets yet. Try a different query or upload more files.
        </div>
      )}
    </div>
  );
}
