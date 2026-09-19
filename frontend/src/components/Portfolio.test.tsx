import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { heatColor, heatData } from '@/lib/heat';
import { PriceStore } from '@/lib/priceStore';
import type { Portfolio, Position } from '@/lib/types';
import { makeData, makeUpdate, renderWithData } from '@/test/helpers';
import { Header } from './Header';
import { HeatCell } from './Heatmap';
import { PositionsTable } from './PositionsTable';

const pos = (ticker: string, quantity: number, avg_cost: number): Position => ({
  ticker,
  quantity,
  avg_cost,
  current_price: null,
  market_value: null,
  unrealized_pnl: null,
  unrealized_pnl_pct: null,
});

const portfolio: Portfolio = {
  cash_balance: 8000,
  realized_pnl: 25,
  total_value: 8000,
  total_unrealized_pnl: 0,
  positions: [pos('AAPL', 10, 100), pos('MSFT', 5, 300)],
};

describe('PositionsTable', () => {
  it('shows dashes for price and P&L while a price is not warmed', () => {
    renderWithData(<PositionsTable />, makeData({ portfolio }));
    expect(screen.getByTestId('position-row-AAPL')).toBeInTheDocument();
    expect(screen.getByTestId('position-qty-AAPL')).toHaveTextContent('10');
    expect(screen.getByTestId('position-price-AAPL')).toHaveTextContent('—');
    expect(screen.getByTestId('position-pnl-AAPL')).toHaveTextContent('—');
    expect(screen.getByTestId('position-pnl-pct-AAPL')).toHaveTextContent('—');
  });

  it('computes unrealized P&L ($ and % vs. avg cost) from live prices', () => {
    const { store } = renderWithData(<PositionsTable />, makeData({ portfolio }));
    act(() =>
      store.ingest({ AAPL: makeUpdate('AAPL', 110, 1), MSFT: makeUpdate('MSFT', 270, 1) }),
    );
    expect(screen.getByTestId('position-pnl-AAPL')).toHaveTextContent('+$100.00');
    expect(screen.getByTestId('position-pnl-pct-AAPL')).toHaveTextContent('+10.00%');
    expect(screen.getByTestId('position-pnl-MSFT')).toHaveTextContent('-$150.00');
    expect(screen.getByTestId('position-pnl-pct-MSFT')).toHaveTextContent('-10.00%');
  });

  it('shows an empty state with no positions', () => {
    renderWithData(<PositionsTable />, makeData());
    expect(screen.getByTestId('positions-table')).toHaveTextContent('No open positions');
  });
});

describe('Header', () => {
  it('shows cash, realized P&L, and total value that moves with live prices', () => {
    const { store } = renderWithData(<Header />, makeData({ portfolio }));
    expect(screen.getByTestId('header-cash')).toHaveTextContent('$8,000.00');
    expect(screen.getByTestId('header-realized-pnl')).toHaveTextContent('+$25.00');
    // No price warmed: positions excluded from the total.
    expect(screen.getByTestId('header-total-value')).toHaveTextContent('$8,000.00');
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 110, 1) }));
    expect(screen.getByTestId('header-total-value')).toHaveTextContent('$9,100.00');
    act(() => store.ingest({ AAPL: makeUpdate('AAPL', 120, 2, 110), MSFT: makeUpdate('MSFT', 300, 2) }));
    expect(screen.getByTestId('header-total-value')).toHaveTextContent('$10,700.00');
  });

  it('reflects the connection status on the dot', () => {
    const store = new PriceStore();
    renderWithData(<Header />, makeData(), store);
    expect(screen.getByTestId('connection-dot')).toHaveAttribute('data-status', 'reconnecting');
    act(() => store.onSourceEvent('open', 1));
    expect(screen.getByTestId('connection-dot')).toHaveAttribute('data-status', 'connected');
    act(() => store.onSourceEvent('error', 2));
    expect(screen.getByTestId('connection-dot')).toHaveAttribute('data-status', 'disconnected');
  });
});

describe('heatmap', () => {
  it('sizes by market value and drops positions without a price', () => {
    const data = heatData([
      { ticker: 'AAPL', market_value: 750, unrealized_pnl: 50, unrealized_pnl_pct: 7 },
      { ticker: 'MSFT', market_value: 250, unrealized_pnl: -10, unrealized_pnl_pct: -4 },
      { ticker: 'ZZZ', market_value: null, unrealized_pnl: null, unrealized_pnl_pct: null },
    ]);
    expect(data.map((d) => d.name)).toEqual(['AAPL', 'MSFT']);
    expect(data[0].weight).toBeCloseTo(75);
    expect(data[1].weight).toBeCloseTo(25);
  });

  it('colors green for profit, red for loss, neutral at zero', () => {
    const channels = (c: string) => c.match(/\d+/g)!.map(Number);
    const [gr, gg] = channels(heatColor(5));
    const [lr, lg] = channels(heatColor(-5));
    const [nr, ng] = channels(heatColor(0));
    expect(gg).toBeGreaterThan(gr); // green dominant
    expect(lr).toBeGreaterThan(lg); // red dominant
    expect(nr).toBeLessThan(80);
    expect(ng).toBeLessThan(80);
    expect(heatColor(50)).toBe(heatColor(5)); // saturates
  });

  it.each([
    [12, 'pos'],
    [-12, 'neg'],
    [0, 'zero'],
  ])('cell with pnl %s is marked %s', (pnl, sign) => {
    render(
      <svg>
        <HeatCell x={0} y={0} width={120} height={80} depth={1} name="AAPL" pnl={pnl} pnlPct={pnl / 10} weight={50} />
      </svg>,
    );
    const cell = screen.getByTestId('heatmap-cell-AAPL');
    expect(cell).toHaveAttribute('data-pnl-sign', sign);
    expect(cell).toHaveTextContent('AAPL');
  });
});
