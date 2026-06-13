// Persistent disclaimer footer.
import { DISCLAIMER } from '../lib/demoFixture';

export function DisclaimerFooter() {
  return (
    <div className="footer">
      <span className="mark">
        <span className="ud">
          <span className="u">▴</span>
          <span className="dn">▾</span>
        </span>
        Market Briefing Agent
      </span>
      <span>{DISCLAIMER}</span>
    </div>
  );
}
