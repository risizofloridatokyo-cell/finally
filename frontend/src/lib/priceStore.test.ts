import { describe, expect, it, vi } from 'vitest';
import { makeUpdate } from '@/test/helpers';
import { MAX_POINTS, PriceStore, sessionChangePct } from './priceStore';

describe('PriceStore', () => {
  it('uses the first observed price as the session baseline and computes Session %', () => {
    const s = new PriceStore();
    s.ingest({ AAPL: makeUpdate('AAPL', 100, 1) });
    expect(s.sessionPct('AAPL')).toBe(0);
    s.ingest({ AAPL: makeUpdate('AAPL', 102, 2, 100) });
    expect(s.baselines.AAPL).toBe(100);
    expect(s.sessionPct('AAPL')).toBeCloseTo(2);
    s.ingest({ AAPL: makeUpdate('AAPL', 95, 3, 102) });
    expect(s.sessionPct('AAPL')).toBeCloseTo(-5);
  });

  it('returns null Session % before any tick', () => {
    expect(new PriceStore().sessionPct('AAPL')).toBeNull();
    expect(sessionChangePct(undefined, 10)).toBeNull();
    expect(sessionChangePct(0, 10)).toBeNull();
  });

  it('appends one point per new timestamp and ignores repeated ones', () => {
    const s = new PriceStore();
    s.ingest({ AAPL: makeUpdate('AAPL', 100, 1) });
    s.ingest({ AAPL: makeUpdate('AAPL', 100, 1) });
    s.ingest({ AAPL: makeUpdate('AAPL', 101, 2, 100) });
    expect(s.points('AAPL').map((p) => p.price)).toEqual([100, 101]);
  });

  it('notifies subscribers once per changed event, not for identical payloads', () => {
    const s = new PriceStore();
    const fn = vi.fn();
    s.subscribe(fn);
    s.ingest({ AAPL: makeUpdate('AAPL', 100, 1), MSFT: makeUpdate('MSFT', 300, 1) });
    expect(fn).toHaveBeenCalledTimes(1);
    s.ingest({ AAPL: makeUpdate('AAPL', 100, 1), MSFT: makeUpdate('MSFT', 300, 1) });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('bounds each series to MAX_POINTS, dropping the oldest', () => {
    const s = new PriceStore();
    for (let i = 0; i < MAX_POINTS + 25; i++) s.ingest({ AAPL: makeUpdate('AAPL', 100 + i, i + 1) });
    const pts = s.points('AAPL');
    expect(pts).toHaveLength(MAX_POINTS);
    expect(pts[0].t).toBe(26);
    expect(pts[pts.length - 1].price).toBe(100 + MAX_POINTS + 24);
  });

  it('backfills history in front of live points without duplicating overlap', () => {
    const s = new PriceStore();
    s.ingest({ AAPL: makeUpdate('AAPL', 105, 10) });
    s.mergeHistory('AAPL', [
      { t: 7, price: 101 },
      { t: 8, price: 102 },
      { t: 10, price: 105 }, // overlaps the first live point
    ]);
    expect(s.points('AAPL')).toEqual([
      { t: 7, price: 101 },
      { t: 8, price: 102 },
      { t: 10, price: 105 },
    ]);
  });

  it('claims history once per ticker until released', () => {
    const s = new PriceStore();
    expect(s.claimHistory('AAPL')).toBe(true);
    expect(s.claimHistory('AAPL')).toBe(false);
    s.releaseHistory('AAPL');
    expect(s.claimHistory('AAPL')).toBe(true);
  });

  it('skips malformed entries', () => {
    const s = new PriceStore();
    s.ingest({ BAD: { ...makeUpdate('BAD', 1, 1), price: NaN } });
    expect(s.prices.BAD).toBeUndefined();
  });
});
