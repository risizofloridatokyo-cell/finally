import { APIRequestContext, expect } from '@playwright/test';
import { DEFAULT_TICKERS } from './env';

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_percent?: number | null;
}

export interface Portfolio {
  cash: number;
  realizedPnl: number;
  totalValue: number;
  positions: Position[];
}

export interface WatchlistEntry {
  ticker: string;
  added_at: string;
  price: number | null;
}

/** GET /api/portfolio, normalised (PLAN §8 does not pin the exact cash field name, so tolerate a couple of spellings). */
export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.get('/api/portfolio');
  expect(res.status(), 'GET /api/portfolio').toBe(200);
  const b = await res.json();
  return {
    cash: b.cash_balance ?? b.cash,
    realizedPnl: b.realized_pnl ?? 0,
    totalValue: b.total_value,
    positions: b.positions ?? [],
  };
}

export async function getWatchlist(request: APIRequestContext): Promise<WatchlistEntry[]> {
  const res = await request.get('/api/watchlist');
  expect(res.status(), 'GET /api/watchlist').toBe(200);
  const b = await res.json();
  return Array.isArray(b) ? b : (b.watchlist ?? b.tickers ?? b.items ?? []);
}

export async function waitForPrices(
  request: APIRequestContext,
  tickers: readonly string[] = DEFAULT_TICKERS,
  timeout = 30_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const wl = await getWatchlist(request);
        return tickers.filter((t) => !wl.some((e) => e.ticker === t && e.price != null));
      },
      { message: 'watchlist prices warmed', timeout },
    )
    .toEqual([]);
}

/** Wait until the server-side ring buffer holds at least `minPoints` points for `ticker`. */
export async function waitForHistory(
  request: APIRequestContext,
  ticker: string,
  minPoints: number,
  timeout = 60_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const res = await request.get(`/api/history?ticker=${ticker}`);
        if (res.status() !== 200) return -1;
        return ((await res.json()).points as unknown[]).length;
      },
      { message: `history buffer for ${ticker}`, timeout },
    )
    .toBeGreaterThanOrEqual(minPoints);
}

export async function trade(
  request: APIRequestContext,
  ticker: string,
  side: 'buy' | 'sell',
  quantity: number,
) {
  const res = await request.post('/api/portfolio/trade', { data: { ticker, side, quantity } });
  expect(res.status(), `${side} ${quantity} ${ticker}: ${await res.text()}`).toBe(200);
  return res.json();
}

/**
 * There is no reset endpoint, so bring the mutable state back to a known shape through the public API:
 * sell every position, then make the watchlist exactly the default ten. Cash / realized P&L cannot be reset,
 * so specs assert on deltas or on values read back from the API, never on absolute cash (except the fresh-start spec).
 */
export async function resetState(request: APIRequestContext): Promise<void> {
  const defaults = new Set<string>(DEFAULT_TICKERS);

  // 1. Make sure every default is watched (a prior test may have removed one), so its price is warming.
  const have = new Set((await getWatchlist(request)).map((e) => e.ticker));
  for (const t of DEFAULT_TICKERS) {
    if (!have.has(t)) {
      const res = await request.post('/api/watchlist', { data: { ticker: t } });
      expect(res.ok(), `POST /api/watchlist ${t}`).toBeTruthy();
    }
  }

  // 2. Sell every position once its price is available.
  await expect
    .poll(async () => (await getPortfolio(request)).positions.filter((p) => p.current_price == null).length, {
      message: 'held positions priced',
      timeout: 30_000,
    })
    .toBe(0);
  for (const p of (await getPortfolio(request)).positions) {
    await trade(request, p.ticker, 'sell', p.quantity);
  }

  // 3. Drop non-default tickers (positions are gone, so the feed for them is released too).
  for (const e of await getWatchlist(request)) {
    if (!defaults.has(e.ticker)) {
      const res = await request.delete(`/api/watchlist/${e.ticker}`);
      expect(res.ok(), `DELETE /api/watchlist/${e.ticker}`).toBeTruthy();
    }
  }
  await waitForPrices(request);
}
