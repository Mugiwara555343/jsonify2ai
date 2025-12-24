import { useState } from 'react';
import { fetchStatus } from './api';

type Status = {
  ok: boolean;
  counts: { chunks: number; images: number; total?: number };
  llm?: { provider?: string; model?: string; reachable?: boolean; synth_total?: number };
};

type LLMOnboardingPanelProps = {
  status: Status | null;
  onStatusRefresh: () => Promise<void>;
};

export default function LLMOnboardingPanel({
  status,
  onStatusRefresh,
}: LLMOnboardingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [testing, setTesting] = useState(false);

  const llm = status?.llm;
  const provider = llm?.provider || 'none';
  const model = llm?.model || '';
  const reachable = llm?.reachable === true;

  const handleTestOllama = async () => {
    setTesting(true);
    try {
      await onStatusRefresh();
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{
      marginTop: 16,
      marginBottom: 16,
      border: '1px solid #e5e7eb',
      borderRadius: 8,
      background: '#fafafa',
    }}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          width: '100%',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          fontSize: 14,
          fontWeight: 600,
          color: '#374151',
        }}
      >
        <span>Optional: Enable Local LLM (Ollama)</span>
        <span style={{ fontSize: 18 }}>{isExpanded ? '−' : '+'}</span>
      </button>

      {isExpanded && (
        <div style={{ padding: '0 16px 16px 16px' }}>
          {/* Current Status */}
          <div style={{
            padding: 12,
            background: '#fff',
            borderRadius: 6,
            marginBottom: 16,
            border: '1px solid #e5e7eb',
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Current Status</div>
            <div style={{ fontSize: 12, lineHeight: 1.6 }}>
              <div>Provider: <code style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: 3 }}>{provider}</code></div>
              {model && <div>Model: <code style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: 3 }}>{model}</code></div>}
              <div>Reachable: <code style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: 3 }}>{reachable ? 'Yes' : 'No'}</code></div>
            </div>
            <button
              onClick={handleTestOllama}
              disabled={testing}
              style={{
                marginTop: 8,
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid #ddd',
                background: '#fff',
                color: '#1976d2',
                cursor: testing ? 'not-allowed' : 'pointer',
                fontSize: 12,
                opacity: testing ? 0.6 : 1,
              }}
            >
              {testing ? 'Testing...' : 'Test Ollama'}
            </button>
          </div>

          {/* Setup Instructions */}
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Setup Instructions</div>
          <div style={{ fontSize: 12, lineHeight: 1.8, color: '#374151' }}>
            <div style={{ marginBottom: 12 }}>
              <strong>1. Install Ollama</strong>
              <div style={{ marginTop: 4, paddingLeft: 8 }}>
                Download from <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" style={{ color: '#1976d2' }}>ollama.com</a> and install on your system.
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <strong>2. Pull a model</strong>
              <div style={{ marginTop: 4, paddingLeft: 8 }}>
                <code style={{
                  display: 'block',
                  background: '#f5f5f5',
                  padding: '8px 12px',
                  borderRadius: 4,
                  fontFamily: 'monospace',
                  fontSize: 11,
                  marginTop: 4,
                }}>
                  ollama pull qwen2.5:3b-instruct-q4_K_M
                </code>
                <div style={{ marginTop: 4, fontSize: 11, opacity: 0.7 }}>
                  Or use any other model: <code>ollama pull llama2</code>, <code>ollama pull mistral</code>, etc.
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <strong>3. Set environment variables</strong>
              <div style={{ marginTop: 4, paddingLeft: 8 }}>
                <div style={{ marginBottom: 8 }}>
                  <strong>Windows (PowerShell):</strong>
                  <code style={{
                    display: 'block',
                    background: '#f5f5f5',
                    padding: '8px 12px',
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    fontSize: 11,
                    marginTop: 4,
                  }}>
                    $env:LLM_PROVIDER="ollama"<br />
                    $env:OLLAMA_HOST="http://host.docker.internal:11434"<br />
                    $env:OLLAMA_MODEL="qwen2.5:3b-instruct-q4_K_M"
                  </code>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <strong>macOS / Linux:</strong>
                  <code style={{
                    display: 'block',
                    background: '#f5f5f5',
                    padding: '8px 12px',
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    fontSize: 11,
                    marginTop: 4,
                  }}>
                    export LLM_PROVIDER=ollama<br />
                    export OLLAMA_HOST=http://host.docker.internal:11434<br />
                    export OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
                  </code>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <strong>Or add to <code>.env</code> file:</strong>
                  <code style={{
                    display: 'block',
                    background: '#f5f5f5',
                    padding: '8px 12px',
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    fontSize: 11,
                    marginTop: 4,
                  }}>
                    LLM_PROVIDER=ollama<br />
                    OLLAMA_HOST=http://host.docker.internal:11434<br />
                    OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
                  </code>
                </div>
                <div style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
                  After setting variables, restart containers: <code>docker compose restart worker</code>
                </div>
              </div>
            </div>

            <div style={{
              marginTop: 16,
              padding: 10,
              background: '#e0f2fe',
              borderRadius: 6,
              fontSize: 11,
              color: '#0369a1',
            }}>
              <strong>Note:</strong> The app works without an LLM. You'll still get semantic search results and exports. LLM synthesis is optional and only enhances the "Ask" feature with generated answers.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
