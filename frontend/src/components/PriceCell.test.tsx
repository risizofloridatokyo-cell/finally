import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PriceCell } from './PriceCell';

describe('PriceCell flash', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const cell = () => screen.getByTestId('watchlist-price-AAPL');

  it('shows a dash for a null price and does not flash', () => {
    render(<PriceCell ticker="AAPL" price={null} />);
    expect(cell()).toHaveTextContent('—');
    expect(cell().className).not.toMatch(/flash/);
  });

  it('does not flash on first render', () => {
    render(<PriceCell ticker="AAPL" price={100} />);
    expect(cell().className).not.toMatch(/flash/);
  });

  it('flashes green on an uptick and clears after the fade', () => {
    const { rerender } = render(<PriceCell ticker="AAPL" price={100} />);
    rerender(<PriceCell ticker="AAPL" price={100.5} />);
    expect(cell()).toHaveClass('flash-up');
    expect(cell()).toHaveTextContent('100.50');
    act(() => {
      vi.advanceTimersByTime(700);
    });
    expect(cell().className).not.toMatch(/flash/);
  });

  it('flashes red on a downtick', () => {
    const { rerender } = render(<PriceCell ticker="AAPL" price={100} />);
    rerender(<PriceCell ticker="AAPL" price={99.5} />);
    expect(cell()).toHaveClass('flash-down');
  });

  it('alternates the animation phase so back-to-back ticks restart the fade', () => {
    const { rerender } = render(<PriceCell ticker="AAPL" price={100} />);
    rerender(<PriceCell ticker="AAPL" price={101} />);
    const first = cell().getAttribute('data-flash-phase');
    rerender(<PriceCell ticker="AAPL" price={102} />);
    const second = cell().getAttribute('data-flash-phase');
    expect(cell()).toHaveClass('flash-up');
    expect(first).not.toBeNull();
    expect(second).not.toBe(first);
  });

  it('does not flash when the price is unchanged', () => {
    const { rerender } = render(<PriceCell ticker="AAPL" price={100} />);
    rerender(<PriceCell ticker="AAPL" price={100} />);
    expect(cell().className).not.toMatch(/flash/);
  });
});
