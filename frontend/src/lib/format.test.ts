import { currencySymbol, fmtCap, stripInlineCites } from './format';

describe('currencySymbol', () => {
  it('returns $ for USD', () => expect(currencySymbol('USD')).toBe('$'));
  it('returns ₹ for INR', () => expect(currencySymbol('INR')).toBe('₹'));
  it('returns € for EUR', () => expect(currencySymbol('EUR')).toBe('€'));
  it('returns £ for GBP', () => expect(currencySymbol('GBP')).toBe('£'));
  it('returns ¥ for JPY', () => expect(currencySymbol('JPY')).toBe('¥'));
  it('returns C$ for CAD', () => expect(currencySymbol('CAD')).toBe('C$'));
  it('returns A$ for AUD', () => expect(currencySymbol('AUD')).toBe('A$'));
  it('returns HK$ for HKD', () => expect(currencySymbol('HKD')).toBe('HK$'));
  it('returns ¥ for CNY', () => expect(currencySymbol('CNY')).toBe('¥'));
  it('returns $ for null', () => expect(currencySymbol(null)).toBe('$'));
  it('returns $ for undefined', () => expect(currencySymbol(undefined)).toBe('$'));
  it('returns code + space for unrecognised code', () =>
    expect(currencySymbol('BRL')).toBe('BRL '));
});

describe('fmtCap', () => {
  it('formats trillions', () =>
    expect(fmtCap(4_280_000_000_000)).toBe('$4.28T'));
  it('formats billions', () =>
    expect(fmtCap(38_000_000_000)).toBe('$38.0B'));
  it('formats millions', () =>
    expect(fmtCap(500_000_000)).toBe('$500.0M'));
  it('uses custom symbol', () =>
    expect(fmtCap(4_280_000_000_000, '₹')).toBe('₹4.28T'));
  it('returns N/A for null', () => expect(fmtCap(null)).toBe('N/A'));
  it('returns N/A for undefined', () => expect(fmtCap(undefined)).toBe('N/A'));
  it('returns N/A for NaN', () => expect(fmtCap(NaN)).toBe('N/A'));
});

describe('stripInlineCites', () => {
  it('strips a single trailing cite', () =>
    expect(stripInlineCites('Some text (c4)')).toBe('Some text'));
  it('strips multiple cites in one group', () =>
    expect(stripInlineCites('Some text (c4, c5)')).toBe('Some text'));
  it('strips cite with spaces', () =>
    expect(stripInlineCites('Some text ( c4 )')).toBe('Some text'));
  it('strips multiple separate cite groups', () =>
    expect(stripInlineCites('A (c1) and B (c2)')).toBe('A and B'));
  it('does not strip non-citation parens', () =>
    expect(stripInlineCites('Apple (AAPL) rose today')).toBe(
      'Apple (AAPL) rose today',
    ));
  it('returns empty string unchanged', () =>
    expect(stripInlineCites('')).toBe(''));
});
