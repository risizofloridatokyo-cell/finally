import type { Portfolio, PriceMap } from './types';

/**
 * Re-value a fetched portfolio against the live SSE prices so the header and
 * positions update every tick. Mirrors the backend rules (PLAN §6): a position
 * with no price stays `null` and is excluded from `total_value`.
 */
export function derivePortfolio(base: Portfolio | null, prices: PriceMap): Portfolio | null {
  if (!base) return null;
  let invested = 0;
  let unrealized = 0;
  const positions = base.positions.map((p) => {
    const live = prices[p.ticker]?.price ?? p.current_price;
    if (live == null) {
      return { ...p, current_price: null, market_value: null, unrealized_pnl: null, unrealized_pnl_pct: null };
    }
    const market_value = live * p.quantity;
    const unrealized_pnl = (live - p.avg_cost) * p.quantity;
    invested += market_value;
    unrealized += unrealized_pnl;
    return {
      ...p,
      current_price: live,
      market_value,
      unrealized_pnl,
      unrealized_pnl_pct: p.avg_cost > 0 ? (live / p.avg_cost - 1) * 100 : null,
    };
  });
  return {
    ...base,
    positions,
    total_value: base.cash_balance + invested,
    total_unrealized_pnl: unrealized,
  };
}
