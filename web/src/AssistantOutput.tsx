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
  mode: 'search' | 'llm';
  model?: string;
  answer?: string;
  final?: string;
  sources?: Hit[];
  answers?: Hit[];
  error?: string;
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
}: AssistantOutputProps) {
  // Empty state
  if (!loading && !error && !result) {
    return (
      <div style={{
        marginTop: 12,
        padding: 16,
        color: '#6b7280',
        fontSize: 13,
        textAlign: 'center',
        background: '#f9fafb',
        borderRadius: 8,
        border: '1px dashed #d1d5db',
      }}>
        <div style={{ marginBottom: 4, fontWeight: 500 }}>Ready to help</div>
        <div style={{ fontSize: 12, opacity: 0.8 }}>
          Try a Quick Action above or ask a question to get started.
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
      <div style={{
        marginTop: 12,
        padding: 12,
        border: '1px solid #fecaca',
        borderRadius: 8,
        background: '#fef2f2',
        color: '#dc2626',
        fontSize: 14,
      }}>
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
    <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 10 }}>
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
        {!hasLLM && sources.length > 0 && (
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
        {(mainText || sources.length > 0) && (
          <button
            onClick={handleCopy}
            style={{
              marginLeft: 'auto',
              padding: '4px 12px',
              borderRadius: 6,
              border: '1px solid #ddd',
              background: '#fff',
              color: '#1976d2',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Copy output
          </button>
        )}
      </div>
      {/* Scope Label */}
      {scope && (
        <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 16, color: '#6b7280' }}>
          {scope === 'doc' && activeDocFilename
            ? `Using document: ${activeDocFilename}`
            : scope === 'doc'
            ? 'Using document: (no active document)'
            : 'Using all indexed documents'}
        </div>
      )}

      {/* Main Output */}
      {mainText && (
        <div style={{
          marginBottom: 16,
          padding: 12,
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          background: '#fafafa',
        }}>
          <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: 14 }}>
            {mainText}
          </div>
        </div>
      )}

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
                  style={{
                    padding: 12,
                    border: '1px solid #e5e7eb',
                    borderRadius: 8,
                    background: '#fff',
                  }}
                >
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginBottom: 8,
                    flexWrap: 'wrap',
                  }}>
                    <span style={{ fontWeight: 500, fontSize: 13 }}>{filename}</span>
                    {path && (
                      <span style={{
                        fontSize: 11,
                        opacity: 0.7,
                        fontFamily: 'monospace',
                      }}>
                        {path}
                      </span>
                    )}
                    {docId && (
                      <code style={{
                        fontSize: 11,
                        fontFamily: 'monospace',
                        background: '#f5f5f5',
                        padding: '2px 6px',
                        borderRadius: 4,
                      }}>
                        {docId}
                      </code>
                    )}
                    {score !== null && (
                      <span style={{
                        fontSize: 11,
                        padding: '2px 6px',
                        borderRadius: 4,
                        background: '#f0f9ff',
                        color: '#0369a1',
                      }}>
                        score: {score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  {snippet && (
                    <div style={{
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: '#374151',
                      fontFamily: 'ui-monospace, monospace',
                      background: '#f9fafb',
                      padding: 8,
                      borderRadius: 4,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}>
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
        <div style={{
          color: '#666',
          fontSize: 14,
          padding: 12,
          background: '#f9fafb',
          borderRadius: 6,
        }}>
          No matching snippets yet. Try a different query or upload more files.
        </div>
      )}
    </div>
  );
}
