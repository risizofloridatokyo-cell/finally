import { test, expect } from '../lib/fixtures';
import type { APIRequestContext } from '@playwright/test';
import type { App } from '../lib/app';
import { getPortfolio } from '../lib/api';
import { parseMoney, signOf } from '../lib/format';

// Cash cannot be reset between tests, so every assertion is relative or checked against the API's own figures.

const cashMatchesApi = (app: App, request: APIRequestContext) =>
  expect
    .poll(async () => Math.abs(parseMoney(await app.cash.innerText()) - (await getPortfolio(request)).cash), {
      message: 'header cash equals GET /api/portfolio cash',
    })
    .toBeLessThan(0.005);

test.describe('buy and sell', () => {
  test('buy: cash decreases by qty x fill price, position appears', async ({ app, request }) => {
    await app.open();
    const cashBefore = (await getPortfolio(request)).cash;

    await app.placeTrade('buy', 'AAPL', 10);

    await expect(app.positionRow('AAPL')).toBeVisible();
    await expect(app.positionQty('AAPL')).toContainText('10');

    const pf = await getPortfolio(request);
    const pos = pf.positions.find((p) => p.ticker === 'AAPL')!;
    expect(pos.quantity).toBe(10);
    expect(pf.cash).toBeCloseTo(cashBefore - 10 * pos.avg_cost, 2);
    expect(pf.cash).toBeLessThan(cashBefore);
    await cashMatchesApi(app, request);
    // total value = cash + market value of holdings, so it should sit close to what we started with
    expect(parseMoney(await app.totalValue.innerText())).toBeGreaterThan(cashBefore * 0.9);
  });

  test('buying again averages the cost (weighted average)', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'MSFT', 4);
    await expect(app.positionQty('MSFT')).toContainText('4');
    const first = (await getPortfolio(request)).positions.find((p) => p.ticker === 'MSFT')!;

    await app.placeTrade('buy', 'MSFT', 6);
    await expect(app.positionQty('MSFT')).toContainText('10');
    const second = (await getPortfolio(request)).positions.find((p) => p.ticker === 'MSFT')!;

    expect(second.quantity).toBe(10);
    // avg_cost is a weighted mean of the two fills; prices barely move between them, so bound it loosely
    const lo = Math.min(first.avg_cost, second.avg_cost) * 0.9;
    const hi = Math.max(first.avg_cost, second.avg_cost) * 1.1;
    expect(second.avg_cost).toBeGreaterThan(lo);
    expect(second.avg_cost).toBeLessThan(hi);
    // one row per ticker
    await expect(app.page.locator('[data-testid="position-row-MSFT"]')).toHaveCount(1);
  });

  test('partial sell: cash increases, quantity drops, row stays', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'NVDA', 10);
    await expect(app.positionQty('NVDA')).toContainText('10');
    const before = await getPortfolio(request);

    await app.placeTrade('sell', 'NVDA', 4);

    await expect(app.positionQty('NVDA')).toContainText('6');
    await expect(app.positionRow('NVDA')).toBeVisible();
    const after = await getPortfolio(request);
    expect(after.cash).toBeGreaterThan(before.cash);
    const pos = after.positions.find((p) => p.ticker === 'NVDA')!;
    expect(pos.quantity).toBe(6);
    // avg cost unchanged on sells
    expect(pos.avg_cost).toBeCloseTo(before.positions.find((p) => p.ticker === 'NVDA')!.avg_cost, 6);
    await cashMatchesApi(app, request);
  });

  test('selling the whole position removes the row and updates realized P&L', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'GOOGL', 5);
    await expect(app.positionRow('GOOGL')).toBeVisible();
    const realizedBefore = (await getPortfolio(request)).realizedPnl;

    await app.placeTrade('sell', 'GOOGL', 5);

    await expect(app.positionRow('GOOGL')).toHaveCount(0);
    const pf = await getPortfolio(request);
    expect(pf.positions.find((p) => p.ticker === 'GOOGL')).toBeUndefined();

    // realized P&L: header shows the API's cumulative figure (may legitimately equal the old one if the price didn't move)
    await expect
      .poll(async () => Math.abs(parseMoney(await app.realizedPnl.innerText()) - pf.realizedPnl))
      .toBeLessThan(0.005);
    expect(Number.isFinite(pf.realizedPnl - realizedBefore)).toBe(true);
    await cashMatchesApi(app, request);
  });

  test('fractional quantities are supported', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'JPM', '0.5');
    await expect(app.positionQty('JPM')).toContainText('0.5');
    expect((await getPortfolio(request)).positions.find((p) => p.ticker === 'JPM')!.quantity).toBeCloseTo(0.5, 6);
  });

  test('positions table shows price and P&L (not the "—" placeholder) once warmed', async ({ app }) => {
    await app.open();
    await app.placeTrade('buy', 'AMZN', 3);
    await expect(app.positionRow('AMZN')).toBeVisible();
    await expect(app.positionRow('AMZN')).not.toContainText('—');
    await expect(app.positionPnl('AMZN')).toHaveText(/\d/);
  });
});

test.describe('trade validation shows inline errors and changes nothing', () => {
  test('selling a ticker you do not hold', async ({ app, request }) => {
    await app.open();
    const before = await getPortfolio(request);
    await app.placeTrade('sell', 'META', 1);
    await expect(app.tradeError).toBeVisible();
    expect((await getPortfolio(request)).cash).toBe(before.cash);
    await expect(app.positionRow('META')).toHaveCount(0);
  });

  test('buying more than the cash balance', async ({ app, request }) => {
    await app.open();
    const before = await getPortfolio(request);
    await app.placeTrade('buy', 'AAPL', 1_000_000);
    await expect(app.tradeError).toBeVisible();
    expect((await getPortfolio(request)).cash).toBe(before.cash);
    await expect(app.positionRow('AAPL')).toHaveCount(0);
  });

  test('zero / negative quantity and an untracked ticker', async ({ app, request }) => {
    await app.open();
    const before = await getPortfolio(request);
    for (const [ticker, qty] of [['AAPL', '0'], ['AAPL', '-3'], ['ZZZZZ', '1']] as const) {
      await app.placeTrade('buy', ticker, qty);
      await expect(app.tradeError, `${ticker} x ${qty}`).toBeVisible();
    }
    expect((await getPortfolio(request)).cash).toBe(before.cash);
  });
});

test.describe('portfolio visualisation', () => {
  test('heatmap cell per position with a P&L colour sign that matches the position P&L', async ({ app }) => {
    await app.open();
    await app.placeTrade('buy', 'AAPL', 10);
    await app.placeTrade('buy', 'TSLA', 5);

    await expect(app.heatmap).toBeVisible();
    for (const t of ['AAPL', 'TSLA']) {
      await expect(app.heatmapCell(t)).toBeVisible();
      await expect(app.heatmapCell(t)).toHaveAttribute('data-pnl-sign', /^(pos|neg|zero)$/);
    }
    // Prices tick between the two reads, so poll until DOM snapshots agree.
    await expect
      .poll(async () => {
        const text = (await app.positionPnl('AAPL').innerText()).trim();
        const cell = await app.heatmapCell('AAPL').getAttribute('data-pnl-sign');
        return cell === signOf(parseMoney(text));
      }, { timeout: 15_000 })
      .toBe(true);
  });

  test('a closed position leaves the heatmap', async ({ app }) => {
    await app.open();
    await app.placeTrade('buy', 'V', 2);
    await expect(app.heatmapCell('V')).toBeVisible();
    await app.placeTrade('sell', 'V', 2);
    await expect(app.heatmapCell('V')).toHaveCount(0);
  });

  test('P&L chart has data points, and each trade records a portfolio snapshot', async ({ app, request }) => {
    const count = async () => {
      const body = await (await request.get('/api/portfolio/history')).json();
      const rows = Array.isArray(body) ? body : (body.history ?? body.snapshots ?? body.points ?? []);
      return rows.length as number;
    };

    await app.open();
    await app.placeTrade('buy', 'AAPL', 1);
    await expect(app.pnlChart).toBeVisible();
    await expect.poll(() => app.attrNumber(app.pnlChart, 'data-points')).toBeGreaterThan(0);

    const before = await count();
    await app.placeTrade('buy', 'AAPL', 1);
    await expect(app.positionQty('AAPL')).toContainText('2');
    await expect.poll(count).toBeGreaterThan(before);
  });

  test('header total value tracks cash + holdings live', async ({ app, request }) => {
    await app.open();
    await app.placeTrade('buy', 'NVDA', 3);
    await expect(app.positionRow('NVDA')).toBeVisible();
    await expect
      .poll(async () => {
        const api = await getPortfolio(request);
        return Math.abs(parseMoney(await app.totalValue.innerText()) - api.totalValue);
      }, { timeout: 15_000 })
      .toBeLessThan(Math.max(5, (await getPortfolio(request)).totalValue * 0.002));
  });
});
