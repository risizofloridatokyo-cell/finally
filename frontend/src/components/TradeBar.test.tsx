import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { PriceStore } from '@/lib/priceStore';
import { makeData, makeUpdate, renderWithData } from '@/test/helpers';
import { parseQuantity, TradeBar } from './TradeBar';

const watchlist = [{ ticker: 'AAPL', added_at: '', price: null }];

describe('parseQuantity', () => {
  it('accepts numbers and rejects blanks and junk', () => {
    expect(parseQuantity('5')).toBe(5);
    expect(parseQuantity(' 0.25 ')).toBe(0.25);
    expect(parseQuantity('')).toBeNull();
    expect(parseQuantity('abc')).toBeNull();
    expect(parseQuantity('Infinity')).toBeNull();
  });
});

describe('TradeBar', () => {
  it('pre-fills the ticker from the selection and submits a buy with no confirmation', async () => {
    const trade = vi.fn(async () => ({ ticker: 'AAPL', side: 'buy' as const, quantity: 5, price: 190.5, status: 'executed' }));
    renderWithData(<TradeBar />, makeData({ watchlist, selected: 'AAPL', trade }));
    expect(screen.getByTestId('trade-ticker')).toHaveValue('AAPL');
    await userEvent.type(screen.getByTestId('trade-quantity'), '5');
    await userEvent.click(screen.getByTestId('trade-buy'));
    expect(trade).toHaveBeenCalledWith({ ticker: 'AAPL', quantity: 5, side: 'buy' });
    expect(await screen.findByTestId('trade-success')).toHaveTextContent('Bought 5 AAPL at 190.50');
    expect(screen.getByTestId('trade-quantity')).toHaveValue('');
  });

  it('submits a sell', async () => {
    const trade = vi.fn(async () => ({ ticker: 'AAPL', side: 'sell' as const, quantity: 2, price: 100, status: 'executed' }));
    renderWithData(<TradeBar />, makeData({ watchlist, selected: 'AAPL', trade }));
    await userEvent.type(screen.getByTestId('trade-quantity'), '2');
    await userEvent.click(screen.getByTestId('trade-sell'));
    expect(trade).toHaveBeenCalledWith({ ticker: 'AAPL', quantity: 2, side: 'sell' });
  });

  it('shows the server detail inline on a rejected trade', async () => {
    const trade = vi.fn(async () => {
      throw new ApiError(409, 'Insufficient cash');
    });
    renderWithData(<TradeBar />, makeData({ watchlist, selected: 'AAPL', trade }));
    await userEvent.type(screen.getByTestId('trade-quantity'), '1000000');
    await userEvent.click(screen.getByTestId('trade-buy'));
    expect(await screen.findByTestId('trade-error')).toHaveTextContent('Insufficient cash');
  });

  it('asks for a quantity before calling the server', async () => {
    const trade = vi.fn();
    renderWithData(<TradeBar />, makeData({ watchlist, selected: 'AAPL', trade }));
    await userEvent.click(screen.getByTestId('trade-buy'));
    expect(screen.getByTestId('trade-error')).toHaveTextContent('Enter a quantity');
    expect(trade).not.toHaveBeenCalled();
  });

  it('shows an estimated cost from the live price', async () => {
    const store = new PriceStore();
    renderWithData(<TradeBar />, makeData({ watchlist, selected: 'AAPL' }), store);
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 100, 1) }));
    await userEvent.type(screen.getByTestId('trade-quantity'), '3');
    expect(screen.getByText(/≈ \$300\.00/)).toBeInTheDocument();
  });
});
