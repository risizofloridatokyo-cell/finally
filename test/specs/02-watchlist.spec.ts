import { test, expect } from '../lib/fixtures';
import { getWatchlist } from '../lib/api';

test.describe('watchlist', () => {
  test('add a ticker: row appears, price warms up, survives a reload', async ({ app, request }) => {
    await app.open();
    await app.addTicker('pypl'); // lower case: the API layer upper-cases + trims

    await expect(app.row('PYPL')).toBeVisible();
    await expect(app.price('PYPL')).not.toHaveText('—');
    await expect(app.price('PYPL')).toHaveText(/\d/);
    expect((await getWatchlist(request)).map((e) => e.ticker)).toContain('PYPL');

    await app.page.reload();
    await expect(app.row('PYPL')).toBeVisible();
  });

  test('remove a ticker: row disappears, and stays gone after a reload', async ({ app, request }) => {
    await app.open();
    await expect(app.row('NFLX')).toBeVisible();
    await app.removeButton('NFLX').click();
    await expect(app.row('NFLX')).toHaveCount(0);
    expect((await getWatchlist(request)).map((e) => e.ticker)).not.toContain('NFLX');

    await app.page.reload();
    await expect(app.row('AAPL')).toBeVisible();
    await expect(app.row('NFLX')).toHaveCount(0);
  });

  test('added ticker gets a live price and can be traded', async ({ app }) => {
    await app.open();
    await app.addTicker('IBM');
    await expect(app.price('IBM')).toHaveText(/\d/);
    await app.placeTrade('buy', 'IBM', 1);
    await expect(app.positionRow('IBM')).toBeVisible();
  });

  test('invalid symbols are rejected with an inline error and add no row', async ({ app }) => {
    await app.open();
    const rowsBefore = await app.page.locator('[data-testid^="watchlist-row-"]').count();
    for (const bad of ['123', 'TOOLONGSYMBOL', 'AA-PL']) {
      await app.addTicker(bad);
      await expect(app.addError, `error for ${bad}`).toBeVisible();
    }
    await expect(app.page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(rowsBefore);
  });

  test('adding an already-watched ticker is harmless', async ({ app }) => {
    await app.open();
    await app.addTicker('AAPL');
    await expect(app.page.locator('[data-testid="watchlist-row-AAPL"]')).toHaveCount(1);
  });

  test('removing a held ticker keeps its position valued (feed retained)', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'TSLA', 2);
    await expect(app.positionRow('TSLA')).toBeVisible();

    await app.removeButton('TSLA').click();
    await expect(app.row('TSLA')).toHaveCount(0);

    // Position stays, and its price is still live (not "—")
    await expect(app.positionRow('TSLA')).toBeVisible();
    await expect(app.positionRow('TSLA')).not.toContainText('—');
    const pf = await (await request.get('/api/portfolio')).json();
    const p = pf.positions.find((x: { ticker: string }) => x.ticker === 'TSLA');
    expect(p.current_price).not.toBeNull();
  });
});
