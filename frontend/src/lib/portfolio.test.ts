import { describe, expect, it } from 'vitest';
import { makeUpdate } from '@/test/helpers';
import { normalizePortfolio } from './api';
import { derivePortfolio } from './portfolio';
import type { Portfolio } from './types';

const pos = (ticker: string, quantity: number, avg_cost: number, current_price: number | null = null) => ({
  ticker,
  quantity,
  avg_cost,
  current_price,
  market_value: null,
  unrealized_pnl: null,
  unrealized_pnl_pct: null,
});

const base: Portfolio = {
  cash_balance: 5000,
  realized_pnl: 12.5,
  total_value: 0,
  total_unrealized_pnl: 0,
  positions: [pos('AAPL', 10, 100), pos('ZZZ', 2, 50)],
};

describe('derivePortfolio', () => {
  it('values positions against live prices and sums total value', () => {
    const p = derivePortfolio(base, { AAPL: makeUpdate('AAPL', 110, 1), ZZZ: makeUpdate('ZZZ', 40, 1) })!;
    const aapl = p.positions[0];
    expect(aapl.market_value).toBe(1100);
    expect(aapl.unrealized_pnl).toBe(100);
    expect(aapl.unrealized_pnl_pct).toBeCloseTo(10);
    expect(p.positions[1].unrealized_pnl).toBe(-20);
    expect(p.total_value).toBe(5000 + 1100 + 80);
    expect(p.total_unrealized_pnl).toBe(80);
    expect(p.realized_pnl).toBe(12.5);
  });

  it('reports null price/P&L and excludes the position from total when no price is warmed', () => {
    const p = derivePortfolio(base, { AAPL: makeUpdate('AAPL', 110, 1) })!;
    const zzz = p.positions[1];
    expect(zzz.current_price).toBeNull();
    expect(zzz.unrealized_pnl).toBeNull();
    expect(zzz.unrealized_pnl_pct).toBeNull();
    expect(p.total_value).toBe(5000 + 1100);
  });

  it('returns null with no base portfolio', () => {
    expect(derivePortfolio(null, {})).toBeNull();
  });

  it('falls back to the server price when the stream has not delivered one', () => {
    const withPrice: Portfolio = { ...base, positions: [pos('AAPL', 10, 100, 120)] };
    expect(derivePortfolio(withPrice, {})!.positions[0].market_value).toBe(1200);
  });
});

describe('normalizePortfolio', () => {
  it('passes the documented shape through and keeps nulls', () => {
    const p = normalizePortfolio({
      cash_balance: 100,
      realized_pnl: 1,
      total_value: 100,
      total_unrealized_pnl: 0,
      positions: [
        {
          ticker: 'AAPL',
          quantity: 1,
          avg_cost: 10,
          current_price: null,
          market_value: null,
          unrealized_pnl: null,
          unrealized_pnl_pct: null,
        },
      ],
    });
    expect(p.positions[0].current_price).toBeNull();
    expect(p.positions[0].unrealized_pnl).toBeNull();
    expect(p.cash_balance).toBe(100);
  });
});
