import { test, expect } from '../lib/fixtures';
import { BASE_URL, DEFAULT_TICKERS } from '../lib/env';
import { FlakyProxy } from '../lib/flaky-proxy';
import type { App } from '../lib/app';

// The page is loaded through a small reverse proxy (lib/flaky-proxy.ts) so the test can cut, refuse, and mute the
// SSE stream at the socket level. Browser "offline" emulation does not sever an already-open EventSource.

test.describe('SSE resilience', () => {
  let proxy: FlakyProxy;

  test.beforeEach(async () => {
    proxy = await FlakyProxy.start(BASE_URL);
  });

  test.afterEach(async () => {
    await proxy.close();
  });

  const readPrices = (app: App) =>
    Promise.all(DEFAULT_TICKERS.map(async (t) => (await app.price(t).innerText()).trim()));

  test('through the proxy the app behaves normally (control)', async ({ app }) => {
    await app.open(proxy.url);
    await expect(app.dot).toHaveAttribute('data-status', 'connected');
    await expect(app.price('AAPL')).toHaveText(/\d/);
  });

  test('dropped stream: dot goes yellow (reconnecting), then green again once the server is reachable', async ({ app }) => {
    test.slow();
    await app.open(proxy.url);

    proxy.drop();
    await expect(app.dot).toHaveAttribute('data-status', 'reconnecting', { timeout: 10_000 });

    // stays yellow (not red) while retries keep failing at the network level
    await app.page.waitForTimeout(3_000);
    await expect(app.dot).toHaveAttribute('data-status', 'reconnecting');

    proxy.restore();
    await expect(app.dot).toHaveAttribute('data-status', 'connected', { timeout: 20_000 });
  });

  test('prices resume ticking after a reconnect', async ({ app }) => {
    test.slow();
    await app.open(proxy.url);
    await expect.poll(async () => (await readPrices(app)).every((p) => /\d/.test(p))).toBe(true);

    proxy.drop();
    await expect(app.dot).toHaveAttribute('data-status', 'reconnecting', { timeout: 10_000 });
    proxy.restore();
    await expect(app.dot).toHaveAttribute('data-status', 'connected', { timeout: 20_000 });

    const after = await readPrices(app);
    await expect
      .poll(async () => (await readPrices(app)).some((p, i) => p !== after[i]), { timeout: 20_000 })
      .toBe(true);
  });

  test('a quiet-but-alive stream (only keepalive comments) stays green', async ({ app }) => {
    test.slow();
    await app.open(proxy.url);
    await expect(app.price('AAPL')).toHaveText(/\d/);

    // Swallow all price events but let comments through; force a reconnect so the quiet mode applies to the new
    // connection. The server's ~15s keepalive must keep the UI from declaring the stream dead.
    proxy.mode = 'quiet';
    proxy.killLive();
    await expect(app.dot).toHaveAttribute('data-status', 'connected', { timeout: 10_000 });

    const deadline = Date.now() + 22_000; // > one keepalive interval (~15s)
    while (Date.now() < deadline) {
      await expect(app.dot).toHaveAttribute('data-status', 'connected', { timeout: 1_000 });
      await app.page.waitForTimeout(500);
    }
  });

  test('a hard HTTP failure of the stream shows the red (disconnected) state', async ({ app }) => {
    await app.open(proxy.url);
    proxy.mode = 'error500';
    proxy.killLive();
    // Non-200 on reconnect => EventSource goes CLOSED (per spec) => red. (A yellow flash on the way is fine.)
    await expect(app.dot).toHaveAttribute('data-status', 'disconnected', { timeout: 15_000 });
  });
});
