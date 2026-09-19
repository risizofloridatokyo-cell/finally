import { expect, Locator, Page } from '@playwright/test';
import { parseMoney } from './format';

/** Page object keyed strictly on the data-testid contract in planning/TEAM_CONTRACTS.md. */
export class App {
  constructor(readonly page: Page) {}

  tid(id: string): Locator {
    return this.page.getByTestId(id);
  }

  // header
  get dot() { return this.tid('connection-dot'); }
  get totalValue() { return this.tid('header-total-value'); }
  get cash() { return this.tid('header-cash'); }
  get realizedPnl() { return this.tid('header-realized-pnl'); }

  // watchlist
  row(t: string) { return this.tid(`watchlist-row-${t}`); }
  price(t: string) { return this.tid(`watchlist-price-${t}`); }
  sessionPct(t: string) { return this.tid(`watchlist-session-pct-${t}`); }
  sparkline(t: string) { return this.tid(`sparkline-${t}`); }
  removeButton(t: string) { return this.tid(`watchlist-remove-${t}`); }
  get addInput() { return this.tid('watchlist-add-input'); }
  get addButton() { return this.tid('watchlist-add-button'); }
  get addError() { return this.tid('watchlist-add-error'); }

  // charts
  get mainChart() { return this.tid('main-chart'); }
  get pnlChart() { return this.tid('pnl-chart'); }
  get heatmap() { return this.tid('heatmap'); }
  heatmapCell(t: string) { return this.tid(`heatmap-cell-${t}`); }

  // trade bar
  get tradeTicker() { return this.tid('trade-ticker'); }
  get tradeQty() { return this.tid('trade-quantity'); }
  get tradeError() { return this.tid('trade-error'); }

  // positions
  get positionsTable() { return this.tid('positions-table'); }
  positionRow(t: string) { return this.tid(`position-row-${t}`); }
  positionQty(t: string) { return this.tid(`position-qty-${t}`); }
  positionPnl(t: string) { return this.tid(`position-pnl-${t}`); }

  // chat
  get chatPanel() { return this.tid('chat-panel'); }
  get chatInput() { return this.tid('chat-input'); }
  get chatLoading() { return this.tid('chat-loading'); }
  get userMessages() { return this.tid('chat-message-user'); }
  get assistantMessages() { return this.tid('chat-message-assistant'); }

  /** Load the app and wait until the SSE connection is up. `url` lets the resilience spec go through its proxy. */
  async open(url = '/'): Promise<void> {
    await this.page.goto(url);
    await expect(this.dot).toHaveAttribute('data-status', 'connected');
  }

  async placeTrade(side: 'buy' | 'sell', ticker: string, quantity: number | string): Promise<void> {
    await this.tradeTicker.fill(ticker);
    await this.tradeQty.fill(String(quantity));
    await this.tid(`trade-${side}`).click();
  }

  async addTicker(ticker: string): Promise<void> {
    await this.addInput.fill(ticker);
    await this.addButton.click();
  }

  async openChat(): Promise<void> {
    // Collapsing shrinks the panel to a rail (data-collapsed="true"); the panel itself stays visible.
    await expect(this.chatPanel).toBeVisible();
    if ((await this.chatPanel.getAttribute('data-collapsed')) === 'true') await this.tid('chat-toggle').click();
    await expect(this.chatInput).toBeVisible();
  }

  async sendChat(message: string): Promise<void> {
    await this.openChat();
    await this.chatInput.fill(message);
    await this.tid('chat-send').click();
  }

  async attrNumber(locator: Locator, attr: string): Promise<number> {
    return Number((await locator.getAttribute(attr)) ?? NaN);
  }

  async cashValue(): Promise<number> {
    return parseMoney(await this.cash.innerText());
  }
}
