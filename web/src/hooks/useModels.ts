import { useState, useEffect } from 'react';
import { apiRequest } from '../api';

export interface Model {
    name: string;
    modified_at: string;
    size: number;
    digest: string;
    details: {
        format: string;
        family: string;
        families: string[] | null;
        parameter_size: string;
        quantization_level: string;
    };
}

interface ModelsResponse {
    models: Model[];
}

export function useModels() {
    const [models, setModels] = useState<Model[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchModels = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await apiRequest('/api/models', { method: 'GET' }, true);
            if (!response.ok) {
                throw new Error(`Failed to fetch models: ${response.status}`);
            }
            const data: ModelsResponse = await response.json();
            setModels(data.models || []);
        } catch (err: any) {
            console.error('Error fetching models:', err);
            setError(err.message || String(err));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchModels();
    }, []);

    return { models, loading, error, refresh: fetchModels };
}
