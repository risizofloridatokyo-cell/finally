import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { vi } from 'vitest';
import { DataContext, type DataContextValue } from '@/lib/DataProvider';
import { PriceProvider } from '@/lib/PriceProvider';
import { PriceStore } from '@/lib/priceStore';
import type { Portfolio, PriceUpdate, WatchItem } from '@/lib/types';

export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
  error(readyState: 0 | 2) {
    this.readyState = readyState;
    this.onerror?.();
  }
}

export const makeUpdate = (ticker: string, price: number, timestamp: number, previous = price): PriceUpdate => ({
  ticker,
  price,
  previous_price: previous,
  timestamp,
  change: price - previous,
  change_percent: previous ? ((price - previous) / previous) * 100 : 0,
  direction: price > previous ? 'up' : price < previous ? 'down' : 'flat',
});

export const emptyPortfolio: Portfolio = {
  cash_balance: 10000,
  realized_pnl: 0,
  total_value: 10000,
  total_unrealized_pnl: 0,
  positions: [],
};

export function makeData(overrides: Partial<DataContextValue> = {}): DataContextValue {
  const watchlist: WatchItem[] = overrides.watchlist ?? [];
  return {
    watchlist,
    watchlistLoaded: true,
    portfolio: emptyPortfolio,
    portfolioHistory: [],
    selected: watchlist[0]?.ticker ?? null,
    select: vi.fn(),
    addTicker: vi.fn(async () => null),
    removeTicker: vi.fn(async () => null),
    trade: vi.fn(),
    refreshAll: vi.fn(async () => {}),
    ...overrides,
  };
}

/** Render inside a PriceProvider (given store, fake EventSource) and a stubbed DataContext. */
export function renderWithData(ui: ReactElement, data: DataContextValue, store = new PriceStore()) {
  const createSource = (() => new FakeEventSource('/x') as unknown as EventSource) as (url: string) => EventSource;
  const result = render(
    <PriceProvider store={store} createSource={createSource}>
      <DataContext.Provider value={data}>{ui}</DataContext.Provider>
    </PriceProvider>,
  );
  return { store, ...result };
}
