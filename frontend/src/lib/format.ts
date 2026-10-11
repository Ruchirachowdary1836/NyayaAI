export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, withTime
    ? { dateStyle: 'medium', timeStyle: 'short' }
    : { dateStyle: 'medium' });
}

export function formatScore(score: number | null | undefined, digits = 3): string {
  return typeof score === 'number' ? score.toFixed(digits) : '—';
}

export function formatMs(value: number | null | undefined): string {
  if (typeof value !== 'number') return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(value < 10 ? 1 : 0)} ms`;
}

export const ENGINE_LABELS = { bm25: 'BM25', dense: 'Dense', hybrid: 'Hybrid' } as const;
export const ENGINE_COLORS = { bm25: '#26385e', dense: '#6f927e', hybrid: '#ba8a3c' } as const;
export const ENGINE_DETAILS = {
  bm25: 'Lexical match for exact terms and provisions',
  dense: 'Semantic similarity from a sentence-embedding model',
  hybrid: 'Rank fusion of lexical and semantic evidence',
} as const;

export function judgmentMeta(metadata: Record<string, unknown>): string[] {
  return [metadata.court, metadata.judgment_date ? formatDate(String(metadata.judgment_date)) : null, metadata.case_number]
    .filter((value): value is string => typeof value === 'string' && value.length > 0);
}
