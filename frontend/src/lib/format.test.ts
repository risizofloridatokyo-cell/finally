import { describe, expect, it } from 'vitest';
import { axisFormatter, EMPTY, fmtPct, fmtPrice, fmtQty, fmtSignedUsd, fmtUsd, pnlSign, valueDomain } from './format';

describe('format', () => {
  it('formats currency with sign handling', () => {
    expect(fmtUsd(10000)).toBe('$10,000.00');
    expect(fmtUsd(-5)).toBe('-$5.00');
    expect(fmtUsd(-0.001)).toBe('$0.00');
    expect(fmtSignedUsd(12.345)).toBe('+$12.35');
    expect(fmtSignedUsd(-3)).toBe('-$3.00');
    expect(fmtSignedUsd(0)).toBe('$0.00');
  });

  it('renders an em dash for missing values', () => {
    expect(fmtUsd(null)).toBe(EMPTY);
    expect(fmtPrice(undefined)).toBe(EMPTY);
    expect(fmtPct(null)).toBe(EMPTY);
    expect(fmtQty(NaN)).toBe(EMPTY);
  });

  it('formats percentages and quantities', () => {
    expect(fmtPct(1.234)).toBe('+1.23%');
    expect(fmtPct(-0.4)).toBe('-0.40%');
    expect(fmtPct(0.001)).toBe('0.00%');
    expect(fmtQty(10)).toBe('10');
    expect(fmtQty(0.12345678)).toBe('0.1235');
  });

  it('classifies pnl sign', () => {
    expect(pnlSign(1)).toBe('pos');
    expect(pnlSign(-1)).toBe('neg');
    expect(pnlSign(0.001)).toBe('zero');
    expect(pnlSign(null)).toBe('zero');
  });
});

describe('chart axis helpers', () => {
  it('pads a flat range so tiny moves do not look like a cliff', () => {
    const [lo, hi] = valueDomain([9999.93, 10000]);
    expect(lo).toBeLessThan(9999.93);
    expect(hi - lo).toBeGreaterThan(1);
  });

  it('shows cents only for narrow ranges', () => {
    expect(axisFormatter(5)(10000.5)).toBe('$10,000.50');
    expect(axisFormatter(500)(10000.5)).toBe('$10,001');
  });
});
