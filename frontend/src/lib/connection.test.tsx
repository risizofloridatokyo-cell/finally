import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConnectionDot } from '@/components/ConnectionDot';
import { FakeEventSource, makeUpdate } from '@/test/helpers';
import { deriveStatus } from './connection';
import { PriceProvider, useLivePrices } from './PriceProvider';

describe('deriveStatus', () => {
  it('is connected once open with readyState OPEN', () => {
    expect(deriveStatus('open', 1)).toBe('connected');
  });
  it('is reconnecting on error while CONNECTING', () => {
    expect(deriveStatus('error', 0)).toBe('reconnecting');
  });
  it('is disconnected on error when CLOSED', () => {
    expect(deriveStatus('error', 2)).toBe('disconnected');
  });
});

function Probe() {
  const store = useLivePrices();
  return (
    <div>
      <ConnectionDot status={store.status} />
      <span data-testid="aapl">{store.prices.AAPL?.price ?? 'none'}</span>
    </div>
  );
}

describe('PriceProvider (shared EventSource)', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource;

  it('opens exactly one EventSource and walks yellow -> green -> yellow -> green -> red', () => {
    render(
      <PriceProvider createSource={factory}>
        <Probe />
      </PriceProvider>,
    );
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe('/api/stream/prices');
    const dot = () => screen.getByTestId('connection-dot');
    expect(dot()).toHaveAttribute('data-status', 'reconnecting');

    const es = FakeEventSource.instances[0];
    act(() => es.open());
    expect(dot()).toHaveAttribute('data-status', 'connected');

    act(() => es.error(0));
    expect(dot()).toHaveAttribute('data-status', 'reconnecting');

    act(() => es.open());
    expect(dot()).toHaveAttribute('data-status', 'connected');

    act(() => es.error(2));
    expect(dot()).toHaveAttribute('data-status', 'disconnected');
  });

  it('retries with a new EventSource after a hard close', () => {
    render(
      <PriceProvider createSource={factory}>
        <Probe />
      </PriceProvider>,
    );
    act(() => FakeEventSource.instances[0].error(2));
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it('feeds SSE messages into the store and closes on unmount', () => {
    const { unmount } = render(
      <PriceProvider createSource={factory}>
        <Probe />
      </PriceProvider>,
    );
    const es = FakeEventSource.instances[0];
    act(() => es.message({ AAPL: makeUpdate('AAPL', 190.5, 1) }));
    expect(screen.getByTestId('aapl')).toHaveTextContent('190.5');
    unmount();
    expect(es.closed).toBe(true);
  });
});
