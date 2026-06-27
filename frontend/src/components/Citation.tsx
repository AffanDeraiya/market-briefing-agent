// Citation chip with hover popover — keyboard and touch accessible.
import { useState, useRef, useCallback, useEffect } from 'react';
import type { Citation as CitationType } from '../lib/types';
import { useHasHover } from '../lib/useHasHover';

interface Props {
  id: string;
  citations: CitationType[];
}

export function CitationChip({ id, citations }: Props) {
  const hasHover = useHasHover();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  // Toggle on tap (touch devices only).
  const handleClick = useCallback(() => {
    if (!hasHover) setIsOpen((prev) => !prev);
  }, [hasHover]);

  // Keyboard: Enter / Space trigger the toggle on any device.
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault(); // prevent page scroll on Space
      setIsOpen((prev) => !prev);
    }
    if (e.key === 'Escape') setIsOpen(false);
  }, []);

  // On touch: close when tapping outside the chip or pressing Escape.
  useEffect(() => {
    if (hasHover || !isOpen) return;

    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [hasHover, isOpen]);

  const c = citations.find((x) => x.id === id);

  // Unknown citation: render a plain non-interactive chip.
  if (!c) return <span className="cite">[{id}]</span>;

  const domain = c.url ? c.url.replace(/^https?:\/\//, '').split('/')[0] : null;

  return (
    <span
      ref={ref}
      className={`cite${isOpen ? ' is-open' : ''}`}
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      [{id}]
      <span className="cpop">
        <div className="ck">
          {c.kind} · {id}
        </div>
        <div className="ct">{c.title}</div>
        {domain && <div className="cu">{domain}</div>}
      </span>
    </span>
  );
}

interface InlineCitesProps {
  ids: string[];
  citations: CitationType[];
}

export function InlineCites({ ids, citations }: InlineCitesProps) {
  if (!ids.length) return null;
  return (
    <>
      {' '}
      {ids.map((id) => (
        <CitationChip key={id} id={id} citations={citations} />
      ))}{' '}
    </>
  );
}
