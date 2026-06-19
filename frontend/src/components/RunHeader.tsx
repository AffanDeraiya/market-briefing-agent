// Run header — sticky bar with ticker, meta pill, actions, status pill.
import { useState } from 'react';
import { useRunStore } from '../store/runStore';
import type { RunStatus } from '../store/runStore';
import type { MarketBrief } from '../lib/types';
import { mdExport } from '../lib/format';

interface Props {
  ticker: string;
  exchange?: string;
  period: string;
  status: RunStatus;
  brief: MarketBrief | null;
  latencyS?: number;
  onStop?: () => void;
  onBack?: () => void;
}

function StatusPill({
  status,
  latencyS,
  verifying,
  onStop,
}: {
  status: RunStatus;
  latencyS?: number;
  verifying?: boolean;
  onStop?: () => void;
}) {
  if (status === 'streaming') {
    return (
      <span className="pill running">
        <span className="dot" aria-hidden="true" />
        {verifying ? 'Verifying…' : 'Researching…'}
        {onStop && (
          <button
            onClick={onStop}
            style={{
              marginLeft: 8,
              fontSize: 11,
              color: 'var(--accent)',
              fontFamily: 'JetBrains Mono',
              cursor: 'pointer',
              border: 'none',
              background: 'none',
              padding: 0,
            }}
            aria-label="Stop run"
          >
            ■ Stop
          </button>
        )}
      </span>
    );
  }
  if (status === 'success') {
    return (
      <span className="pill">
        <span className="dot" aria-hidden="true" />
        Done in {latencyS ?? '—'}s
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span
        className="pill"
        style={{
          color: 'var(--neg)',
          borderColor: 'rgba(160,32,32,.25)',
          background: 'rgba(160,32,32,.07)',
        }}
      >
        <span
          className="dot"
          style={{ background: 'var(--neg)' }}
          aria-hidden="true"
        />
        Failed
      </span>
    );
  }
  if (status === 'stopped') {
    return (
      <span
        className="pill"
        style={{
          color: 'var(--ts)',
          borderColor: 'var(--bd)',
          background: 'var(--raised)',
        }}
      >
        <span
          className="dot"
          style={{ background: 'var(--ts)' }}
          aria-hidden="true"
        />
        Stopped
      </span>
    );
  }
  if (status === 'rate_limited') {
    return (
      <span
        className="pill"
        style={{
          color: 'var(--anom)',
          borderColor: 'rgba(138,90,0,.25)',
          background: 'rgba(138,90,0,.07)',
        }}
      >
        <span
          className="dot"
          style={{ background: 'var(--anom)' }}
          aria-hidden="true"
        />
        Rate limited
      </span>
    );
  }
  if (status === 'server_waking') {
    return (
      <span
        className="pill running"
        style={{
          color: 'var(--ts)',
          borderColor: 'var(--bd)',
          background: 'var(--raised)',
        }}
      >
        <span
          className="dot"
          style={{ background: 'var(--ts)' }}
          aria-hidden="true"
        />
        Waking…
      </span>
    );
  }
  return null;
}

export function RunHeader({
  ticker,
  exchange,
  period,
  status,
  brief,
  latencyS,
  onStop,
  onBack,
}: Props) {
  const stopRun = useRunStore((s) => s.stopRun);
  const verifying = useRunStore((s) => s.verifying);
  const [copied, setCopied] = useState(false);

  const handleCopyMd = async () => {
    if (!brief) return;
    try {
      await navigator.clipboard.writeText(mdExport(brief));
    } catch {
      // fallback: create textarea
      const el = document.createElement('textarea');
      el.value = mdExport(brief);
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleExport = () => {
    if (!brief) return;
    const md = mdExport(brief);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // e.g. "AAPL-3mo-brief.md"
    a.download = `${brief.ticker}-${brief.period}-brief.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="runhead" role="banner">
      {onBack && (
        <button
          onClick={onBack}
          title="Back to home"
          aria-label="Back to home"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 30,
            height: 30,
            borderRadius: '50%',
            border: '1px solid var(--bd)',
            background: 'var(--raised)',
            color: 'var(--ts)',
            cursor: 'pointer',
            flexShrink: 0,
            transition: 'border-color 0.15s, color 0.15s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor =
              'var(--accent)';
            (e.currentTarget as HTMLButtonElement).style.color =
              'var(--accent)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.borderColor =
              'var(--bd)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--ts)';
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M9 2L4 7L9 12"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
      <span className="tkr mono">{ticker}</span>
      {exchange && (
        <span className="meta mono">
          {exchange} · {period}
        </span>
      )}
      {!exchange && <span className="meta mono">{period}</span>}
      <div className="spacer" />
      <div className="actions">
        <button
          onClick={handleCopyMd}
          title="Copy the brief as Markdown"
          disabled={!brief}
        >
          {copied ? '✓ Copied' : '⧉ Copy MD'}
        </button>
        <button
          onClick={handleExport}
          title="Download the brief as a .md file"
          disabled={!brief}
        >
          ↓ Export
        </button>
      </div>
      <StatusPill
        status={status}
        latencyS={latencyS}
        verifying={verifying}
        onStop={onStop ?? (() => stopRun())}
      />
    </div>
  );
}
