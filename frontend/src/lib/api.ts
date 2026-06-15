// API helpers — validate ticker endpoint.

const BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

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
