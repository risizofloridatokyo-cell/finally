import { test as base, expect } from '@playwright/test';
import { App } from './app';
import { resetState } from './api';

/** `app` fixture: page object, with portfolio/watchlist brought back to a known shape (via public API) before each test. */
export const test = base.extend<{ app: App }>({
  app: async ({ page, request }, use) => {
    await resetState(request);
    await use(new App(page));
  },
});

export { expect };
