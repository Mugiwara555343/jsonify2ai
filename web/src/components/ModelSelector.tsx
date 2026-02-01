import { Model } from '../hooks/useModels';

interface ModelSelectorProps {
    models: Model[];
    selectedModel: string | null;
    onSelect: (model: string) => void;
    loading?: boolean;
    disabled?: boolean;
}

export default function ModelSelector({
    models,
    selectedModel,
    onSelect,
    loading,
    disabled
}: ModelSelectorProps) {
    // if (models.length === 0 && !loading) return null; // Removed to show empty state

    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label className="text-xs opacity-70 dark:text-gray-400">Model:</label>
            <select
                value={selectedModel || ''}
                onChange={(e) => onSelect(e.target.value)}
                disabled={disabled || loading}
                className="px-2 py-1 rounded-md border text-xs bg-white text-gray-900 border-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                style={{
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    maxWidth: 200
                }}
            >
                <option value="" disabled>Select a model...</option>
                {models.length > 0 ? (
                    models.map((m) => (
                        <option key={m.name} value={m.name}>
                            {m.name}
                        </option>
                    ))
                ) : (
                    <option value="" disabled>No models found</option>
                )}
            </select>
            {loading && <span style={{ fontSize: 10, opacity: 0.5 }}>Loading...</span>}
        </div>
    );
}
