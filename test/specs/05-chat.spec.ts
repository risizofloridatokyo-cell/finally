import { test, expect } from '../lib/fixtures';
import { getPortfolio, getWatchlist, trade } from '../lib/api';

// Runs against LLM_MOCK=true. Trigger table: planning/TEAM_CONTRACTS.md
//   oversized -> buy 1,000,000 AAPL (rejected) | buy -> buy 5 AAPL | sell -> sell 1 AAPL
//   add -> add PYPL | remove -> remove PYPL | anything else -> plain "Mock:" reply

test.describe('AI chat (mock)', () => {
  test('a plain message gets a "Mock:" reply and no action confirmations', async ({ app }) => {
    await app.open();
    await app.sendChat('hello there');

    await expect(app.userMessages.last()).toContainText('hello there');
    await expect(app.assistantMessages.last()).toContainText('Mock:');
    await expect(app.chatLoading).toBeHidden();
    await expect(app.tid('chat-action-trade-executed')).toHaveCount(0);
    await expect(app.tid('chat-action-trade-rejected')).toHaveCount(0);
    await expect(app.tid('chat-action-watchlist')).toHaveCount(0);
    await expect(app.tid('chat-action-error')).toHaveCount(0);
  });

  test('"buy some AAPL": reply, inline executed-trade confirmation, position and cash update', async ({ app, request }) => {
    await app.open();
    const cashBefore = (await getPortfolio(request)).cash;

    await app.sendChat('buy some AAPL');

    await expect(app.assistantMessages.last()).toContainText('Mock:');
    const executed = app.tid('chat-action-trade-executed');
    await expect(executed).toBeVisible();
    await expect(executed).toContainText('AAPL');
    await expect(executed).toContainText('5');

    await expect(app.positionRow('AAPL')).toBeVisible();
    await expect(app.positionQty('AAPL')).toContainText('5');
    expect((await getPortfolio(request)).cash).toBeLessThan(cashBefore);
  });

  test('"sell" sells one AAPL from an existing position', async ({ app, request }) => {
    await trade(request, 'AAPL', 'buy', 3);
    await app.open();
    await expect(app.positionQty('AAPL')).toContainText('3');

    await app.sendChat('please sell AAPL');

    await expect(app.tid('chat-action-trade-executed')).toBeVisible();
    await expect(app.positionQty('AAPL')).toContainText('2');
  });

  test('"oversized": buy is rejected, inline error shown, portfolio untouched', async ({ app, request }) => {
    await app.open();
    const before = await getPortfolio(request);

    await app.sendChat('make an oversized buy');

    await expect(app.assistantMessages.last()).toContainText('Mock:'); // not an HTTP error: message is still shown
    await expect(app.tid('chat-action-trade-rejected')).toBeVisible();
    await expect(app.tid('chat-action-error')).toBeVisible();
    await expect(app.tid('chat-action-trade-executed')).toHaveCount(0);
    await expect(app.positionRow('AAPL')).toHaveCount(0);
    expect((await getPortfolio(request)).cash).toBe(before.cash);
  });

  test('"add" adds PYPL to the watchlist, "remove" takes it away again', async ({ app, request }) => {
    await app.open();

    await app.sendChat('add a new ticker');
    await expect(app.tid('chat-action-watchlist')).toBeVisible();
    await expect(app.tid('chat-action-watchlist')).toContainText('PYPL');
    await expect(app.row('PYPL')).toBeVisible();
    expect((await getWatchlist(request)).map((e) => e.ticker)).toContain('PYPL');

    await app.sendChat('remove it again');
    await expect(app.tid('chat-action-watchlist')).toHaveCount(2);
    await expect(app.row('PYPL')).toHaveCount(0);
    expect((await getWatchlist(request)).map((e) => e.ticker)).not.toContain('PYPL');
  });

  test('conversation accumulates: user and assistant messages alternate', async ({ app }) => {
    await app.open();
    await app.sendChat('hello');
    await expect(app.assistantMessages).toHaveCount(1);
    await app.sendChat('hello again');
    await expect(app.assistantMessages).toHaveCount(2);
    await expect(app.userMessages).toHaveCount(2);
  });

  test('a loading indicator shows while the request is in flight', async ({ app }) => {
    await app.page.route('**/api/chat', async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.continue();
    });
    await app.open();
    await app.sendChat('hello slowly');

    await expect(app.chatLoading).toBeVisible();
    await expect(app.assistantMessages.last()).toContainText('Mock:');
    await expect(app.chatLoading).toBeHidden();
  });

  test('an upstream 503 does not wedge the panel', async ({ app }) => {
    await app.page.route('**/api/chat', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'The assistant is unavailable right now — please try again.' }),
      }),
    );
    await app.open();
    await app.sendChat('hello');

    await expect(app.chatLoading).toBeHidden();
    await expect(app.chatInput).toBeEnabled();
    await expect(app.tid('chat-action-trade-executed')).toHaveCount(0);

    // and it recovers once the backend does
    await app.page.unroute('**/api/chat');
    await app.sendChat('hello again');
    await expect(app.assistantMessages.last()).toContainText('Mock:');
  });

  test('chat can be collapsed and re-opened', async ({ app }) => {
    await app.open();
    await app.openChat();
    const toggle = app.tid('chat-toggle');

    await toggle.click(); // collapses to a rail: the panel stays, the conversation UI is hidden
    await expect(app.chatPanel).toHaveAttribute('data-collapsed', 'true');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(app.chatInput).toBeHidden();

    await toggle.click();
    await expect(app.chatPanel).toHaveAttribute('data-collapsed', 'false');
    await expect(app.chatInput).toBeVisible();

    // collapsed state does not lose the ability to chat: collapse, then sending re-opens it
    await toggle.click();
    await app.sendChat('hello after collapse');
    await expect(app.assistantMessages.last()).toContainText('Mock:');
  });
});
