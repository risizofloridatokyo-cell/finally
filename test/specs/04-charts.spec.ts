import { test, expect } from '../lib/fixtures';
import { DEFAULT_TICKERS } from '../lib/env';
import { waitForHistory } from '../lib/api';
import { parsePct } from '../lib/format';

test.describe('session change %', () => {
  test('reads ~0 at page load, then moves as prices tick', async ({ app }) => {
    test.slow();
    await app.open();

    const read = async () => Promise.all(DEFAULT_TICKERS.map(async (t) => parsePct(await app.sessionPct(t).innerText())));
    await expect.poll(async () => (await read()).every(Number.isFinite), { message: 'all session % painted' }).toBe(true);

    // Baseline is the first tick this page saw, so right after load it is tiny (allow a few 2-5% "event" jumps).
    const initial = await read();
    const nearZero = initial.filter((v) => Math.abs(v) < 1).length;
    expect(nearZero, `initial session %: ${initial.join(', ')}`).toBeGreaterThanOrEqual(8);

    // ...and it moves.
    await expect
      .poll(async () => (await read()).some((v, i) => v !== initial[i]), { timeout: 40_000, message: 'a session % changes' })
      .toBe(true);
  });

  test('is a raw price move: baseline resets on reload', async ({ app }) => {
    await app.open();
    await expect(app.sessionPct('AAPL')).toHaveText(/\d/);
    await app.page.reload();
    await expect(app.sessionPct('AAPL')).toHaveText(/\d/);
    expect(Math.abs(parsePct(await app.sessionPct('AAPL').innerText()))).toBeLessThan(5);
  });
});

test.describe('history backfill (GET /api/history) and live charts', () => {
  test('sparklines are populated right after load, then keep growing', async ({ app, request }) => {
    test.slow();
    await waitForHistory(request, 'AAPL', 30); // let the server buffer fill (~15s at 500ms ticks)
    await app.open();

    for (const t of ['AAPL', 'MSFT', 'NVDA']) {
      await expect
        .poll(() => app.attrNumber(app.sparkline(t), 'data-points'), { message: `sparkline ${t}`, timeout: 3_000 })
        .toBeGreaterThan(20); // more than SSE alone could deliver in 3s => proves the backfill
    }

    const n = await app.attrNumber(app.sparkline('AAPL'), 'data-points');
    if (n < 300) {
      await expect
        .poll(() => app.attrNumber(app.sparkline('AAPL'), 'data-points'), { timeout: 10_000 })
        .toBeGreaterThan(n);
    }
  });

  test('detail chart is populated immediately when a ticker is selected', async ({ app, request }) => {
    test.slow();
    await waitForHistory(request, 'MSFT', 30);
    await app.open();

    await app.row('MSFT').click();
    await expect(app.mainChart).toHaveAttribute('data-ticker', 'MSFT');
    await expect
      .poll(() => app.attrNumber(app.mainChart, 'data-points'), { timeout: 3_000 })
      .toBeGreaterThan(20);
  });

  test('clicking another ticker swaps the detail chart and it keeps extending live', async ({ app, request }) => {
    test.slow();
    await waitForHistory(request, 'NVDA', 30);
    await app.open();

    await app.row('AAPL').click();
    await expect(app.mainChart).toHaveAttribute('data-ticker', 'AAPL');
    await app.row('NVDA').click();
    await expect(app.mainChart).toHaveAttribute('data-ticker', 'NVDA');
    await expect.poll(() => app.attrNumber(app.mainChart, 'data-points')).toBeGreaterThan(20);

    const n = await app.attrNumber(app.mainChart, 'data-points');
    if (n < 300) {
      await expect.poll(() => app.attrNumber(app.mainChart, 'data-points'), { timeout: 10_000 }).toBeGreaterThan(n);
    }
  });

  test('a freshly added ticker has a chart that fills from live data', async ({ app }) => {
    test.slow();
    await app.open();
    await app.addTicker('AMD');
    await expect(app.price('AMD')).toHaveText(/\d/);
    await app.row('AMD').click();
    await expect(app.mainChart).toHaveAttribute('data-ticker', 'AMD');
    await expect.poll(() => app.attrNumber(app.mainChart, 'data-points'), { timeout: 15_000 }).toBeGreaterThan(2);
  });
});
