// API helpers — validate ticker endpoint.

const BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export { BASE };

export interface ValidateResult {
  valid: boolean;
  name?: string;
  exchange?: string;
  error?: string;
}

export async function validateTicker(
  ticker: string,
  signal?: AbortSignal,
): Promise<ValidateResult> {
  const resp = await fetch(
    `${BASE}/api/validate/${encodeURIComponent(ticker)}`,
    { signal },
  );
  if (resp.status === 404) return { valid: false, error: 'Ticker not found' };
  if (!resp.ok) return { valid: false, error: `Server error (${resp.status})` };
  const data = (await resp.json()) as {
    valid: boolean;
    name?: string;
    exchange?: string;
  };
  return data;
}

export interface SymbolSuggestion {
  symbol: string;
  name: string;
  exchange: string;
}

export async function searchSymbols(
  q: string,
  signal?: AbortSignal,
): Promise<SymbolSuggestion[]> {
  const query = q.trim();
  if (!query) return [];
  try {
    const resp = await fetch(
      `${BASE}/api/search?q=${encodeURIComponent(query)}`,
      { signal },
    );
    if (!resp.ok) return [];
    const data = (await resp.json()) as { results?: SymbolSuggestion[] };
    return data.results ?? [];
  } catch {
    return [];
  }
}
