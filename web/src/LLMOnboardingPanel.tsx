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
    <div className="mt-4 mb-4 border border-gray-200 dark:border-gray-800 rounded-lg bg-gray-50 dark:bg-gray-900 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-transparent border-none cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      >
        <span>Optional: Enable Local LLM (Ollama)</span>
        <span className="text-lg">{isExpanded ? '−' : '+'}</span>
      </button>

      {isExpanded && (
        <div className="p-4 pt-0">
          {/* Current Status */}
          <div className="p-3 bg-white dark:bg-gray-800 rounded-md mb-4 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100">
            <div className="text-sm font-semibold mb-2">Current Status</div>
            <div className="text-xs leading-relaxed">
              <div>Provider: <code className="bg-gray-100 dark:bg-black px-1 py-0.5 rounded">{provider}</code></div>
              {model && <div>Model: <code className="bg-gray-100 dark:bg-black px-1 py-0.5 rounded">{model}</code></div>}
              <div>Reachable: <code className="bg-gray-100 dark:bg-black px-1 py-0.5 rounded">{reachable ? 'Yes' : 'No'}</code></div>
            </div>
            <button
              onClick={handleTestOllama}
              disabled={testing}
              className="mt-2 px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-300 text-xs cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {testing ? 'Testing...' : 'Test Ollama'}
            </button>
          </div>

          {/* Setup Instructions */}
          <div className="text-sm font-semibold mb-2 text-gray-900 dark:text-gray-100">Setup Instructions</div>
          <div className="text-xs leading-relaxed text-gray-700 dark:text-gray-300">
            <div className="mb-3">
              <strong>1. Install Ollama</strong>
              <div className="mt-1 pl-2">
                Download from <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">ollama.com</a> and install on your system.
              </div>
            </div>

            <div className="mb-3">
              <strong>2. Pull a model</strong>
              <div className="mt-1 pl-2">
                <code className="block bg-gray-100 dark:bg-black p-2 rounded font-mono text-xs mt-1 text-gray-800 dark:text-gray-200">
                  ollama pull qwen2.5:3b-instruct-q4_K_M
                </code>
                <div className="mt-1 text-xs opacity-70">
                  Or use any other model: <code>ollama pull llama2</code>, <code>ollama pull mistral</code>, etc.
                </div>
              </div>
            </div>

            <div className="mb-3">
              <strong>3. Set environment variables</strong>
              <div className="mt-1 pl-2">
                <div className="mb-2">
                  <strong>Windows (PowerShell):</strong>
                  <code className="block bg-gray-100 dark:bg-black p-2 rounded font-mono text-xs mt-1 text-gray-800 dark:text-gray-200">
                    $env:LLM_PROVIDER="ollama"<br />
                    $env:OLLAMA_HOST="http://host.docker.internal:11434"<br />
                    $env:OLLAMA_MODEL="qwen2.5:3b-instruct-q4_K_M"
                  </code>
                </div>
                <div className="mb-2">
                  <strong>macOS / Linux:</strong>
                  <code className="block bg-gray-100 dark:bg-black p-2 rounded font-mono text-xs mt-1 text-gray-800 dark:text-gray-200">
                    export LLM_PROVIDER=ollama<br />
                    export OLLAMA_HOST=http://host.docker.internal:11434<br />
                    export OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
                  </code>
                </div>
                <div className="mb-2">
                  <strong>Or add to <code>.env</code> file:</strong>
                  <code className="block bg-gray-100 dark:bg-black p-2 rounded font-mono text-xs mt-1 text-gray-800 dark:text-gray-200">
                    LLM_PROVIDER=ollama<br />
                    OLLAMA_HOST=http://host.docker.internal:11434<br />
                    OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
                  </code>
                </div>
                <div className="text-xs opacity-70 mt-1">
                  After setting variables, restart containers: <code>docker compose restart worker</code>
                </div>
              </div>
            </div>

            <div className="mt-4 p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-md text-xs text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-blue-800">
              <strong>Note:</strong> The app works without an LLM. You'll still get semantic search results and exports. LLM synthesis is optional and only enhances the "Ask" feature with generated answers.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
