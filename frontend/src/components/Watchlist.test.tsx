import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PriceStore } from '@/lib/priceStore';
import { makeData, makeUpdate, renderWithData } from '@/test/helpers';
import { Watchlist } from './Watchlist';

const list = [
  { ticker: 'AAPL', added_at: '2026-01-01T00:00:00+00:00', price: null },
  { ticker: 'MSFT', added_at: '2026-01-01T00:00:00+00:00', price: null },
];

function setup(overrides = {}) {
  const store = new PriceStore();
  const data = makeData({ watchlist: list, ...overrides });
  const utils = renderWithData(<Watchlist />, data, store);
  return { data, ...utils };
}

describe('Watchlist', () => {
  it('renders a row per ticker with a dash for a price that has not warmed', () => {
    const { store } = setup();
    expect(screen.getByTestId('watchlist-row-AAPL')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-row-MSFT')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('—');
    expect(screen.getByTestId('watchlist-session-pct-AAPL')).toHaveTextContent('—');
    expect(store.prices.AAPL).toBeUndefined();
  });

  it('shows live price, Session % vs. first tick, and sparkline point count', () => {
    const { store } = setup();
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 100, 1) }));
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('100.00');
    expect(screen.getByTestId('watchlist-session-pct-AAPL')).toHaveTextContent('0.00%');

    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 101, 2, 100) }));
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 102, 3, 101) }));
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveTextContent('102.00');
    expect(screen.getByTestId('watchlist-session-pct-AAPL')).toHaveTextContent('+2.00%');
    expect(screen.getByTestId('sparkline-AAPL')).toHaveAttribute('data-points', '3');
  });

  it('flashes the price cell on a tick', () => {
    const { store } = setup();
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 100, 1) }));
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 100.25, 2, 100) }));
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveClass('flash-up');
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 99.9, 3, 100.25) }));
    expect(screen.getByTestId('watchlist-price-AAPL')).toHaveClass('flash-down');
  });

  it('selects a ticker when its row is clicked', async () => {
    const { data } = setup();
    await userEvent.click(screen.getByTestId('watchlist-row-MSFT'));
    expect(data.select).toHaveBeenCalledWith('MSFT');
  });

  it('adds an upper-cased ticker and clears the input', async () => {
    const { data } = setup();
    const input = screen.getByTestId('watchlist-add-input');
    await userEvent.type(input, 'pypl');
    await userEvent.click(screen.getByTestId('watchlist-add-button'));
    expect(data.addTicker).toHaveBeenCalledWith('PYPL');
    await waitFor(() => expect(input).toHaveValue(''));
    expect(screen.queryByTestId('watchlist-add-error')).not.toBeInTheDocument();
  });

  it('shows the server error inline when adding fails', async () => {
    setup({ addTicker: vi.fn(async () => 'Invalid ticker symbol') });
    await userEvent.type(screen.getByTestId('watchlist-add-input'), 'TOOLONG1');
    await userEvent.click(screen.getByTestId('watchlist-add-button'));
    expect(await screen.findByTestId('watchlist-add-error')).toHaveTextContent('Invalid ticker symbol');
  });

  it('removes a ticker without selecting it', async () => {
    const { data } = setup();
    await userEvent.click(screen.getByTestId('watchlist-remove-MSFT'));
    expect(data.removeTicker).toHaveBeenCalledWith('MSFT');
    expect(data.select).not.toHaveBeenCalled();
  });

  it('marks the selected row', () => {
    setup({ selected: 'MSFT' });
    expect(screen.getByTestId('watchlist-row-MSFT')).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId('watchlist-row-AAPL')).toHaveAttribute('data-selected', 'false');
  });
});
