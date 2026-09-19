import { test, expect } from '@playwright/test';
import { DEFAULT_TICKERS } from '../lib/env';
import { getPortfolio, getWatchlist, waitForPrices } from '../lib/api';

// Contract checks straight against the HTTP surface (PLAN §8). Cheap, and they make it obvious whether a UI failure
// is a frontend or a backend problem.

test.describe('API smoke', () => {
  test('health is ok', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ status: 'ok' });
  });

  test('watchlist seeds the default ten with prices once warmed', async ({ request }) => {
    await waitForPrices(request);
    const wl = await getWatchlist(request);
    expect(wl.map((e) => e.ticker).sort()).toEqual([...DEFAULT_TICKERS].sort());
    for (const e of wl) {
      expect(typeof e.price).toBe('number');
      expect(e.added_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    }
  });

  test('portfolio body has the documented shape', async ({ request }) => {
    const res = await request.get('/api/portfolio');
    expect(res.status()).toBe(200);
    const b = await res.json();
    expect(b).toEqual(
      expect.objectContaining({
        positions: expect.any(Array),
        total_value: expect.any(Number),
        realized_pnl: expect.any(Number),
        total_unrealized_pnl: expect.any(Number),
      }),
    );
    expect(typeof (b.cash_balance ?? b.cash)).toBe('number');
  });

  test('history: oldest-first points, bounded, 404 for untracked ticker', async ({ request }) => {
    await waitForPrices(request);
    const res = await request.get('/api/history?ticker=AAPL&limit=5');
    expect(res.status()).toBe(200);
    const b = await res.json();
    expect(b.ticker).toBe('AAPL');
    expect(b.points.length).toBeGreaterThan(0);
    expect(b.points.length).toBeLessThanOrEqual(5);
    const ts = b.points.map((p: { timestamp: number }) => p.timestamp);
    expect([...ts].sort((a, c) => a - c)).toEqual(ts);

    const full = await (await request.get('/api/history?ticker=AAPL')).json();
    expect(full.points.length).toBeLessThanOrEqual(300);

    expect((await request.get('/api/history?ticker=ZZZZZ')).status()).toBe(404);
  });

  test('watchlist rejects malformed tickers with 400', async ({ request }) => {
    for (const bad of ['', '123', 'TOOLONG', 'AA-PL', 'A B']) {
      const res = await request.post('/api/watchlist', { data: { ticker: bad } });
      expect([400, 422], `ticker ${JSON.stringify(bad)}`).toContain(res.status());
    }
    const res = await request.post('/api/watchlist', { data: { ticker: '123' } });
    expect(res.status()).toBe(400);
    expect(await res.json()).toEqual({ detail: 'Invalid ticker symbol' });
  });

  test('re-adding an existing ticker is idempotent (200)', async ({ request }) => {
    const res = await request.post('/api/watchlist', { data: { ticker: 'aapl ' } });
    expect(res.status()).toBe(200);
  });

  test('trade validation: bad quantity, bad side, untracked ticker, insufficient cash/shares', async ({ request }) => {
    await waitForPrices(request);
    const before = await getPortfolio(request);
    const post = (data: object) => request.post('/api/portfolio/trade', { data });

    for (const quantity of [0, -1, 1e10]) {
      const r = await post({ ticker: 'AAPL', side: 'buy', quantity });
      expect([400, 422], `quantity ${quantity}`).toContain(r.status());
    }
    expect([400, 422]).toContain((await post({ ticker: 'AAPL', side: 'hold', quantity: 1 })).status());
    expect([400, 404]).toContain((await post({ ticker: 'ZZZZZ', side: 'buy', quantity: 1 })).status());

    const tooBig = await post({ ticker: 'AAPL', side: 'buy', quantity: 1_000_000 });
    expect([400, 409]).toContain(tooBig.status());
    expect(typeof (await tooBig.json()).detail).toBe('string');

    if (!before.positions.some((p) => p.ticker === 'AAPL')) {
      const noShares = await post({ ticker: 'AAPL', side: 'sell', quantity: 1 });
      expect([400, 409]).toContain(noShares.status());
    }

    // nothing above may have touched the portfolio
    const after = await getPortfolio(request);
    expect(after.cash).toBe(before.cash);
    expect(after.positions.map((p) => [p.ticker, p.quantity])).toEqual(before.positions.map((p) => [p.ticker, p.quantity]));
  });

  test('price stream: SSE content type, retry directive, immediate full snapshot', async () => {
    // APIRequestContext buffers the whole body, so read the stream with fetch + abort instead.
    const base = process.env.BASE_URL ?? 'http://localhost:8000';
    const ctrl = new AbortController();
    const res = await fetch(`${base}/api/stream/prices`, { signal: ctrl.signal });
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    const reader = res.body!.getReader();
    const dec = new TextDecoder();
    let buf = '';
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline && !/^data:/m.test(buf)) {
      buf += dec.decode((await reader.read()).value ?? new Uint8Array());
    }
    ctrl.abort();
    expect(buf).toContain('retry: 1000');
    const dataLine = buf.split('\n').find((l) => l.startsWith('data:'))!;
    const payload = JSON.parse(dataLine.slice(5));
    const keys = Object.keys(payload);
    expect(keys.length).toBeGreaterThanOrEqual(DEFAULT_TICKERS.length);
    expect(payload.AAPL).toEqual(
      expect.objectContaining({
        ticker: 'AAPL',
        price: expect.any(Number),
        previous_price: expect.any(Number),
        direction: expect.stringMatching(/^(up|down|flat)$/),
      }),
    );
  });
});
