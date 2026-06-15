// Tests for AgentLogStrip auto-collapse behaviour on success.

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AgentLogStrip } from './AgentLogStrip';
import type { LogStep, UsagePayload } from '../lib/types';

const USAGE: UsagePayload = {
  input_tokens: 10000,
  output_tokens: 2500,
  est_cost_usd: 0,
  tool_calls: 6,
  iterations: 4,
  latency_ms: 41000,
};

const LOG: LogStep[] = [
  {
    id: 'tc-1',
    type: 'tool_call',
    seq: 1,
    name: 'market_data',
    input: {},
    ok: true,
    ms: 312,
  },
  {
    id: 'tc-2',
    type: 'tool_call',
    seq: 2,
    name: 'news_search',
    input: {},
    ok: true,
    ms: 511,
  },
];

describe('AgentLogStrip', () => {
  it('shows full strip while streaming', () => {
    render(
      <AgentLogStrip
        log={LOG}
        usage={null}
        status="streaming"
        model="gemini"
      />,
    );
    // The steps container should be present
    expect(
      screen.getByRole('region', { name: /agent log/i }),
    ).toBeInTheDocument();
    // Tool names should be visible in the full strip (tool step + hover card both render it)
    expect(screen.getAllByText('market_data').length).toBeGreaterThan(0);
  });

  it('collapses to summary bar when status becomes success', () => {
    render(
      <AgentLogStrip log={LOG} usage={USAGE} status="success" model="gemini" />,
    );
    // Should show the collapsed summary (not the full step list)
    const region = screen.getByRole('region', { name: /agent log summary/i });
    expect(region).toBeInTheDocument();
    // The summary should mention tool calls count and latency
    expect(
      screen.getByRole('button', { name: /expand agent log/i }),
    ).toBeInTheDocument();
    // "expand" hint text should be visible
    expect(screen.getByText('expand')).toBeInTheDocument();
  });

  it('summary bar shows correct tool call count and latency', () => {
    render(
      <AgentLogStrip log={LOG} usage={USAGE} status="success" model="gemini" />,
    );
    // 2 tool_call steps in LOG
    const btn = screen.getByRole('button', { name: /expand agent log/i });
    expect(btn.textContent).toMatch(/2 tool calls/);
    // latency: 41000ms → 41s
    expect(btn.textContent).toMatch(/41s/);
  });

  it('clicking expand button shows the full strip', () => {
    render(
      <AgentLogStrip log={LOG} usage={USAGE} status="success" model="gemini" />,
    );
    const expandBtn = screen.getByRole('button', { name: /expand agent log/i });
    fireEvent.click(expandBtn);
    // After expanding, tool names should be visible and the aria label changes back
    expect(
      screen.getByRole('region', { name: /agent log$/i }),
    ).toBeInTheDocument();
    // tool name appears in both the step pill and the hover card
    expect(screen.getAllByText('market_data').length).toBeGreaterThan(0);
  });

  it('clicking collapse button in expanded view returns to summary', () => {
    render(
      <AgentLogStrip log={LOG} usage={USAGE} status="success" model="gemini" />,
    );
    // First expand
    fireEvent.click(screen.getByRole('button', { name: /expand agent log/i }));
    // Then collapse
    const collapseBtn = screen.getByRole('button', {
      name: /collapse agent log/i,
    });
    fireEvent.click(collapseBtn);
    // Back to summary
    expect(
      screen.getByRole('region', { name: /agent log summary/i }),
    ).toBeInTheDocument();
  });

  it('does not collapse when status is error (full strip stays visible)', () => {
    render(
      <AgentLogStrip log={LOG} usage={USAGE} status="error" model="gemini" />,
    );
    // Should NOT show the collapsed summary
    expect(
      screen.queryByRole('button', { name: /expand agent log/i }),
    ).toBeNull();
    // Full strip visible — aria-label is exactly "Agent log" (no "summary" suffix)
    expect(
      screen.getByRole('region', { name: 'Agent log' }),
    ).toBeInTheDocument();
  });
});
