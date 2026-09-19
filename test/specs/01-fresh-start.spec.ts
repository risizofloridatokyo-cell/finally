import { test, expect } from '../lib/fixtures';
import { DEFAULT_TICKERS, EXPECT_FRESH_DB } from '../lib/env';
import { parseMoney } from '../lib/format';

// PLAN §12: "Fresh start: default watchlist appears, $10k balance shown, prices are streaming".
// Runs first (file order) so the $10,000.00 assertion sees an untouched DB; see FRESH_DB in lib/env.ts.

test.describe('fresh start', () => {
  test('default watchlist of ten tickers is shown', async ({ app }) => {
    await app.open();
    for (const t of DEFAULT_TICKERS) {
      await expect(app.row(t), `row ${t}`).toBeVisible();
    }
  });

  test('shows $10,000.00 virtual cash and no positions', async ({ app }) => {
    await app.open();
    if (EXPECT_FRESH_DB) {
      await expect(app.cash).toContainText('$10,000.00');
      await expect(app.totalValue).toContainText('$10,000.00');
    } else {
      await expect.poll(async () => parseMoney(await app.cash.innerText())).toBeGreaterThan(0);
    }
    await expect(app.realizedPnl).toBeVisible();
    await expect(app.positionsTable).toBeVisible();
    await expect(app.page.locator('[data-testid^="position-row-"]')).toHaveCount(0);
  });

  test('connection dot is green once the stream is open', async ({ app }) => {
    await app.open();
    await expect(app.dot).toHaveAttribute('data-status', 'connected');
  });

  test('prices are populated and streaming (they change over time)', async ({ app }) => {
    await app.open();
    const read = async () =>
      Promise.all(DEFAULT_TICKERS.map(async (t) => (await app.price(t).innerText()).trim()));

    await expect
      .poll(async () => (await read()).every((p) => p !== '—' && p !== '' && Number.isFinite(parseMoney(p))), {
        message: 'all ten prices painted',
      })
      .toBe(true);

    const first = await read();
    await expect
      .poll(async () => (await read()).some((p, i) => p !== first[i]), {
        message: 'at least one price ticks within 15s',
        timeout: 15_000,
      })
      .toBe(true);
  });

  test('a price change flashes green or red on the price cell', async ({ app }) => {
    await app.open();
    // Watch class mutations on all price cells; a flash-up / flash-down class must appear on a tick.
    const flashed = await app.page.evaluate(
      (tickers) =>
        new Promise<boolean>((resolve) => {
          const seen = () => tickers.some((t) => {
            const el = document.querySelector(`[data-testid="watchlist-price-${t}"]`);
            return !!el && (el.classList.contains('flash-up') || el.classList.contains('flash-down'));
          });
          const timer = setInterval(() => { if (seen()) { clearInterval(timer); resolve(true); } }, 25);
          setTimeout(() => { clearInterval(timer); resolve(false); }, 10_000);
        }),
      [...DEFAULT_TICKERS],
    );
    expect(flashed).toBe(true);
  });
});
