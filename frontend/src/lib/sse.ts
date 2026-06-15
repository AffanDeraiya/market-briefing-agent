// SSE stream consumer — POST /api/brief, parse text/event-stream.
// Uses fetch + ReadableStream reader (EventSource can't POST).

import type { BriefEvent, Period } from './types';

const BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export interface BriefRequest {
  ticker: string;
  period: Period;
}

/** Typed error thrown by streamBrief for non-2xx HTTP responses. */
export class BriefStreamError extends Error {
  /** HTTP status code (undefined if the request never got a response — network/connect error). */
  readonly status?: number;
  /** Retry-After header value in seconds, if the server sent one (429 rate-limit). */
  readonly retryAfter?: number;

  constructor(message: string, status?: number, retryAfter?: number) {
    super(message);
    this.name = 'BriefStreamError';
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export async function streamBrief(
  req: BriefRequest,
  onEvent: (ev: BriefEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${BASE}/api/brief`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });

  if (!resp.ok) {
    let retryAfter: number | undefined;
    const ra = resp.headers.get('Retry-After');
    if (ra) {
      const parsed = parseInt(ra, 10);
      if (!isNaN(parsed)) retryAfter = parsed;
    }
    throw new BriefStreamError(`HTTP ${resp.status}`, resp.status, retryAfter);
  }

  const reader = resp.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buf = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buf += decoder.decode(value, { stream: true });

    // SSE framing: split on double newline.
    // sse-starlette ≥3.x defaults to \r\n line endings so the frame
    // boundary is \r\n\r\n, not \n\n.  Handle both to be safe.
    const parts = buf.split(/\r?\n\r?\n/);
    buf = parts.pop() ?? ''; // last incomplete chunk

    for (const part of parts) {
      const lines = part.split(/\r?\n/);
      let eventName = '';
      let dataLine = '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventName = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          // trimEnd() strips a trailing \r when the server sends CRLF lines
          dataLine = line.slice(6).trimEnd();
        }
      }

      if (eventName && dataLine) {
        try {
          const parsed = JSON.parse(dataLine) as unknown;
          onEvent({ event: eventName, data: parsed } as BriefEvent);
        } catch {
          // malformed frame — skip
        }
      }
    }
  }
}
