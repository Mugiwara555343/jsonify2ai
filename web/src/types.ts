export type Document = {
    document_id: string;
    kinds: string[];
    paths: string[];
    counts: Record<string, number>;
};
