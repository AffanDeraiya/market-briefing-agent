// One brief bullet that participates in the verifier walkthrough: normally it
// renders text + citation pills; when the walk is backspacing this line it shows
// the shrinking text + a caret, then collapses out; once done it unmounts.
import type { Bullet, Citation } from '../lib/types';
import type { Walkthrough } from '../lib/walkthrough';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';

interface Props {
  bullet: Bullet;
  citations: Citation[];
  target: string;
  walk?: Walkthrough;
}

export function WalkBullet({ bullet, citations, target, walk }: Props) {
  const state = walk ? walk.itemState(target) : 'idle';
  if (state === 'done') return null;

  const text = stripInlineCites(bullet.text);

  if (state === 'active' && walk) {
    const shown = text.slice(0, walk.backspaceChars);
    const collapsing = walk.backspaceChars === 0;
    return (
      <li className={`wk-active${collapsing ? ' wk-collapsing' : ''}`}>
        <span>
          {shown}
          <span className="wk-cursor" aria-hidden="true">
            ▏
          </span>
        </span>
      </li>
    );
  }

  return (
    <li>
      <span>
        {text}
        <InlineCites ids={bullet.citations} citations={citations} />
      </span>
    </li>
  );
}
