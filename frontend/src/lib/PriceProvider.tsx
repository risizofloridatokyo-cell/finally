'use client';

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import { API_BASE } from './api';
import { PriceStore } from './priceStore';
import type { PriceUpdate } from './types';

const PriceContext = createContext<PriceStore | null>(null);

type SourceFactory = (url: string) => EventSource;
const defaultFactory: SourceFactory = (url) => new EventSource(url);

/** After a hard close (HTTP error), retry with a fresh EventSource. Network blips are retried by the browser itself. */
const RECONNECT_DELAY_MS = 3000;

/**
 * Owns the ONE shared EventSource for the whole app and feeds the PriceStore.
 * `store` / `createSource` are injectable for tests.
 */
export function PriceProvider({
  children,
  store: injected,
  createSource = defaultFactory,
}: {
  children: ReactNode;
  store?: PriceStore;
  createSource?: SourceFactory;
}) {
  const [store] = useState(() => injected ?? new PriceStore());

  useEffect(() => {
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const source = createSource(`${API_BASE}/api/stream/prices`);
      es = source;
      source.onopen = () => store.onSourceEvent('open', source.readyState);
      source.onmessage = (e: MessageEvent<string>) => {
        try {
          store.ingest(JSON.parse(e.data) as Record<string, PriceUpdate>);
        } catch {
          // ignore malformed frames; keepalive comments never reach onmessage
        }
      };
      source.onerror = () => {
        store.onSourceEvent('error', source.readyState);
        if (source.readyState === 2 /* CLOSED */ && !disposed) {
          source.close();
          timer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      es?.close();
    };
  }, [store, createSource]);

  return <PriceContext.Provider value={store}>{children}</PriceContext.Provider>;
}

export function usePriceStore(): PriceStore {
  const store = useContext(PriceContext);
  if (!store) throw new Error('usePriceStore must be used inside <PriceProvider>');
  return store;
}

/** Subscribe to every store update (re-renders on each tick) and return the store for reading. */
export function useLivePrices(): PriceStore {
  const store = usePriceStore();
  useSyncExternalStore(store.subscribe, store.getVersion, store.getVersion);
  return store;
}
