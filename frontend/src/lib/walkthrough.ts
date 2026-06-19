// Guided "verifier walkthrough" — the visible part of the reason → verify →
// revised choreography.
//
// On a fresh live run, after the revised brief arrives, the verifier's edits are
// walked through ONE AT A TIME so the human eye can follow them: scroll to the
// changed claim, highlight it, then either backspace a refined (removed) line
// character-by-character or pulse a recalibrated confidence chip, pause, next.
// A Skip cancels the walk and jumps to the final brief. Recents / offline /
// prefers-reduced-motion never walk — they render the final brief directly.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MarketBrief } from './types';
import { stripInlineCites } from './format';

export type ItemState = 'idle' | 'pending' | 'active' | 'done';

export interface Walkthrough {
  /** True while the guided walk is in progress (gates the banner + Skip button). */
  active: boolean;
  /** Bullet sections should render the COMPOSED brief while true (so removed
   *  lines are still present to backspace). */
  displayComposed: boolean;
  /** Per-claim state for the section components to render against. */
  itemState: (target: string) => ItemState;
  /** Visible character count for the active refined (removed) line. */
  backspaceChars: number;
  /** Cancel the walk and jump straight to the final revised brief. */
  skip: () => void;
}

/** Map a verifier claim target to its on-page section anchor + display label. */
export function describeTarget(target: string): {
  sectionId: string;
  label: string;
  rank: number;
  index: number;
} {
  // Ranks follow on-page (DOM) order so the walk scrolls monotonically down:
  // anomaly (02) → news (03) → bull/bear (04) → risks (05) → signal (07).
  if (target === 'signal')
    return { sectionId: 'sec-signal', label: 'Signal', rank: 5, index: 0 };
  if (target.startsWith('anomaly:'))
    return { sectionId: 'sec-anomaly', label: 'Anomaly', rank: 0, index: 0 };
  const [section, idxStr] = target.split(':');
  const index = Number(idxStr ?? 0);
  const labelMap: Record<string, string> = {
    news_highlights: 'News',
    bull_case: 'Bull',
    bear_case: 'Bear',
    risks: 'Risk',
  };
  const sectionIdMap: Record<string, string> = {
    news_highlights: 'sec-news',
    bull_case: 'sec-bullbear',
    bear_case: 'sec-bullbear',
    risks: 'sec-risks',
  };
  const rankMap: Record<string, number> = {
    news_highlights: 1,
    bull_case: 2,
    bear_case: 3,
    risks: 4,
  };
  return {
    sectionId: sectionIdMap[section] ?? 'sec-news',
    label: labelMap[section] ?? section,
    rank: rankMap[section] ?? 9,
    index,
  };
}

interface Step {
  target: string;
  kind: 'refined' | 'recalibrated';
  sectionId: string;
  fullText: string;
  rank: number;
  index: number;
}

function composedBulletText(composed: MarketBrief, target: string): string {
  const [section, idxStr] = target.split(':');
  const idx = Number(idxStr ?? -1);
  const lists: Record<string, { text: string }[]> = {
    news_highlights: composed.news_highlights,
    bull_case: composed.bull_case,
    bear_case: composed.bear_case,
    risks: composed.risks,
  };
  const list = lists[section];
  if (!list || idx < 0 || idx >= list.length) return '';
  return stripInlineCites(list[idx].text);
}

function buildSteps(composed: MarketBrief, revised: MarketBrief): Step[] {
  const verdicts = revised.verification?.verdicts ?? [];
  const steps: Step[] = verdicts
    .filter((v) => v.action !== 'kept')
    .map((v) => {
      const d = describeTarget(v.target);
      const kind: Step['kind'] =
        v.action === 'dropped' ? 'refined' : 'recalibrated';
      return {
        target: v.target,
        kind,
        sectionId: d.sectionId,
        fullText:
          kind === 'refined' ? composedBulletText(composed, v.target) : '',
        rank: d.rank,
        index: d.index,
      };
    });
  steps.sort((a, b) => a.rank - b.rank || a.index - b.index);
  return steps;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

function maxScroll(): number {
  return Math.max(
    0,
    document.documentElement.scrollHeight - window.innerHeight,
  );
}

// Top-anchor the active section ~28% down the viewport, clamped so the viewport
// bottom never passes the content bottom (which would show blank below the
// sticky header).
function scrollToSection(id: string): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const el = document.getElementById(id);
  if (!el) return;
  const top =
    window.scrollY + el.getBoundingClientRect().top - window.innerHeight * 0.28;
  window.scrollTo({
    top: Math.max(0, Math.min(top, maxScroll())),
    behavior: 'smooth',
  });
}

// Pull the viewport back up if a collapsed line left it parked past the content.
function clampScroll(): void {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const limit = maxScroll();
  if (window.scrollY > limit) window.scrollTo({ top: limit, behavior: 'auto' });
}

// Timing (ms)
const HIGHLIGHT_HOLD = 480;
const BACKSPACE_TOTAL = 700;
const BACKSPACE_TICK = 28;
const COLLAPSE_HOLD = 260;
const RECAL_HOLD = 880;
const BETWEEN = 320;

export function useVerifyWalkthrough(
  composedBrief: MarketBrief | null,
  brief: MarketBrief | null,
): Walkthrough {
  const [seenBrief, setSeenBrief] = useState<MarketBrief | null>(null);
  const [active, setActive] = useState(false);
  const [activeTarget, setActiveTarget] = useState<string | null>(null);
  const [doneTargets, setDoneTargets] = useState<string[]>([]);
  const [backspaceChars, setBackspaceChars] = useState(0);
  const [changedTargets, setChangedTargets] = useState<string[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [runTick, setRunTick] = useState(0);
  // Cancel flag for the running sequence. Only ever touched inside the effect's
  // timer callbacks and the skip handler — never read during render — so a ref
  // is safe here.
  const cancelRef = useRef(false);

  // Detect a freshly-arrived revised brief during render (React-sanctioned
  // "adjust state on prop change"); kick off or skip the walk accordingly.
  if (brief !== seenBrief) {
    setSeenBrief(brief);
    const fresh =
      !!composedBrief &&
      !!brief &&
      brief !== composedBrief &&
      !!brief.verification;
    if (fresh && !prefersReducedMotion()) {
      const built = buildSteps(composedBrief, brief);
      if (built.length > 0) {
        setSteps(built);
        setChangedTargets(built.map((s) => s.target));
        setActive(true);
        setActiveTarget(null);
        setDoneTargets([]);
        setBackspaceChars(0);
        setRunTick((t) => t + 1);
      } else {
        setActive(false);
      }
    } else {
      setActive(false);
    }
  }

  // Run the timed sequence. All setState happens inside timer callbacks (started
  // via setTimeout(run, 0)), never synchronously in the effect body.
  useEffect(() => {
    if (runTick === 0 || steps.length === 0) return;
    cancelRef.current = false;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const sleep = (ms: number) =>
      new Promise<void>((res) => {
        timers.push(setTimeout(res, ms));
      });

    const backspace = async (len: number) => {
      const ticks = Math.max(1, Math.ceil(BACKSPACE_TOTAL / BACKSPACE_TICK));
      const per = Math.max(1, Math.ceil(len / ticks));
      let n = len;
      setBackspaceChars(n);
      while (n > 0) {
        if (cancelRef.current) return;
        await sleep(BACKSPACE_TICK);
        n = Math.max(0, n - per);
        setBackspaceChars(n);
      }
    };

    const run = async () => {
      for (const step of steps) {
        if (cancelRef.current) return;
        setActiveTarget(step.target);
        // Seed the full length up front so the line shows intact (not collapsed)
        // during the highlight hold, then backspaces from full → 0.
        if (step.kind === 'refined') setBackspaceChars(step.fullText.length);
        scrollToSection(step.sectionId);
        await sleep(HIGHLIGHT_HOLD);
        if (cancelRef.current) return;
        if (step.kind === 'refined') {
          await backspace(step.fullText.length);
          if (cancelRef.current) return;
          await sleep(COLLAPSE_HOLD);
          // The line just collapsed — recompute so the viewport isn't left over
          // empty space below the now-shorter content.
          clampScroll();
        } else {
          await sleep(RECAL_HOLD);
        }
        if (cancelRef.current) return;
        setDoneTargets((d) => [...d, step.target]);
        setActiveTarget(null);
        await sleep(BETWEEN);
      }
      if (!cancelRef.current) {
        setActive(false);
        setActiveTarget(null);
        clampScroll();
      }
    };

    timers.push(setTimeout(run, 0));
    return () => {
      cancelRef.current = true;
      timers.forEach(clearTimeout);
    };
  }, [runTick, steps]);

  const skip = useCallback(() => {
    cancelRef.current = true;
    setActive(false);
    setActiveTarget(null);
  }, []);

  const doneSet = useMemo(() => new Set(doneTargets), [doneTargets]);
  const changedSet = useMemo(() => new Set(changedTargets), [changedTargets]);

  const itemState = useCallback(
    (target: string): ItemState => {
      if (!active) return 'idle';
      if (target === activeTarget) return 'active';
      if (doneSet.has(target)) return 'done';
      if (changedSet.has(target)) return 'pending';
      return 'idle';
    },
    [active, activeTarget, doneSet, changedSet],
  );

  return { active, displayComposed: active, itemState, backspaceChars, skip };
}
