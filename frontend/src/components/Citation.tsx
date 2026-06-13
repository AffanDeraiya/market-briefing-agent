// Citation chip with hover popover.
import type { Citation as CitationType } from '../lib/types';

interface Props {
  id: string;
  citations: CitationType[];
}

export function CitationChip({ id, citations }: Props) {
  const c = citations.find((x) => x.id === id);
  if (!c) return <span className="cite">[{id}]</span>;

  const domain = c.url ? c.url.replace(/^https?:\/\//, '').split('/')[0] : null;

  return (
    <span className="cite">
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
