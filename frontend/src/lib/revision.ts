// Drives the live "reason → verify → revised brief" transition.
//
// On a live run the agent emits the COMPOSED brief, audits it, then emits the
// REVISED brief. This hook holds the composed brief on screen for one animation
// frame so dropped claims can fade/collapse out, then swaps to the revised brief
// and pulses any downgraded/neutralized claims. Honors prefers-reduced-motion
// (skips straight to the final state).

import { useEffect, useState } from 'react';
import type { MarketBrief } from './types';

/** Targets currently animating, keyed by the verifier's claim-target convention
 *  ("bull_case:0", "anomaly:2026-06-09", "signal", …). */
export interface RevisionView {
  /** Dropped claims fading + collapsing out (rendered from the composed brief). */
  leaving: ReadonlySet<string>;
  /** Downgraded / neutralized claims to pulse (rendered from the revised brief). */
  changed: ReadonlySet<string>;
}

const EMPTY: ReadonlySet<string> = new Set<string>();

export const NO_REVISION: RevisionView = { leaving: EMPTY, changed: EMPTY };

/** Append ' leaving' / ' pulse-change' to a className when *target* is animating. */
export function revClass(
  rev: RevisionView | undefined,
  target: string,
): string {
  if (!rev) return '';
  if (rev.leaving.has(target)) return ' leaving';
  if (rev.changed.has(target)) return ' pulse-change';
  return '';
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

type Phase = 'idle' | 'leaving' | 'pulsing';

const LEAVE_MS = 360;
const PULSE_MS = 750;

/**
 * Returns the brief to render plus the set of targets currently animating.
 *
 * - `composedBrief` is the pre-verification brief; `brief` is the latest (revised
 *   once verification finishes). They are the same object until a revision lands.
 * - When a distinct revised brief with `verification` arrives, play the animation
 *   exactly once for that brief object.
 */
export function useBriefRevision(
  composedBrief: MarketBrief | null,
  brief: MarketBrief | null,
): { displayBrief: MarketBrief | null; revision: RevisionView } {
  const [phase, setPhase] = useState<Phase>('idle');
  const [seenBrief, setSeenBrief] = useState<MarketBrief | null>(null);

  const isRevised =
    !!brief &&
    !!composedBrief &&
    brief !== composedBrief &&
    !!brief.verification;

  // Detect a freshly-arrived revised brief during render (the React-sanctioned
  // "adjust state when a prop changes" pattern) so the leaving phase renders the
  // composed brief on the very same commit — no flash of the revised brief.
  if (brief !== seenBrief) {
    setSeenBrief(brief);
    if (isRevised && brief) {
      const verdicts = brief.verification?.verdicts ?? [];
      const hasDrops = verdicts.some((v) => v.action === 'dropped');
      const hasChanges = verdicts.some((v) => v.action !== 'kept');
      if (prefersReducedMotion() || !hasChanges) {
        setPhase('idle');
      } else {
        setPhase(hasDrops ? 'leaving' : 'pulsing');
      }
    }
  }

  // Advance the animation phase on timers (async setState is fine in effects).
  useEffect(() => {
    if (phase === 'leaving') {
      const t = setTimeout(() => setPhase('pulsing'), LEAVE_MS);
      return () => clearTimeout(t);
    }
    if (phase === 'pulsing') {
      const t = setTimeout(() => setPhase('idle'), PULSE_MS);
      return () => clearTimeout(t);
    }
  }, [phase]);

  const verdicts = brief?.verification?.verdicts ?? [];
  const dropped = new Set(
    verdicts.filter((v) => v.action === 'dropped').map((v) => v.target),
  );
  const changed = new Set(
    verdicts
      .filter(
        (v) =>
          v.action === 'confidence_downgraded' || v.action === 'neutralized',
      )
      .map((v) => v.target),
  );

  const displayBrief = phase === 'leaving' ? composedBrief : brief;
  const revision: RevisionView = {
    leaving: phase === 'leaving' ? dropped : EMPTY,
    changed: phase === 'pulsing' ? changed : EMPTY,
  };
  return { displayBrief, revision };
}
