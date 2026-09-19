'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { api, ApiError } from './api';
import { usePriceStore } from './PriceProvider';
import type { Portfolio, PortfolioPoint, TradeRequest, TradeResult, WatchItem } from './types';

const PORTFOLIO_POLL_MS = 10_000;
const HISTORY_POLL_MS = 30_000;

export interface DataContextValue {
  watchlist: WatchItem[];
  watchlistLoaded: boolean;
  /** Portfolio as last fetched from the server (re-valued against live prices by consumers). */
  portfolio: Portfolio | null;
  portfolioHistory: PortfolioPoint[];
  selected: string | null;
  select: (ticker: string) => void;
  /** Resolves to an error message, or null on success. */
  addTicker: (raw: string) => Promise<string | null>;
  removeTicker: (ticker: string) => Promise<string | null>;
  /** Throws ApiError with the server's `detail` on failure. */
  trade: (req: TradeRequest) => Promise<TradeResult>;
  /** Re-fetch everything that a trade / chat action may have changed. */
  refreshAll: () => Promise<void>;
}

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const store = usePriceStore();
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [watchlistLoaded, setWatchlistLoaded] = useState(false);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioHistory, setPortfolioHistory] = useState<PortfolioPoint[]>([]);
  const [selectedRaw, setSelected] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const loadWatchlist = useCallback(async () => {
    try {
      const list = await api.watchlist();
      if (!alive.current) return;
      setWatchlist(list);
      setWatchlistLoaded(true);
    } catch {
      // keep the previous list; the next poll/action retries
    }
  }, []);

  const loadPortfolio = useCallback(async () => {
    try {
      const p = await api.portfolio();
      if (alive.current) setPortfolio(p);
    } catch {
      /* transient */
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.portfolioHistory();
      if (alive.current) setPortfolioHistory(h);
    } catch {
      /* transient */
    }
  }, []);

  useEffect(() => {
    // Initial fetches: state is only set after the network calls resolve (external-system sync).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadWatchlist();
    void loadPortfolio();
    void loadHistory();
    const p = setInterval(() => void loadPortfolio(), PORTFOLIO_POLL_MS);
    const h = setInterval(() => void loadHistory(), HISTORY_POLL_MS);
    return () => {
      clearInterval(p);
      clearInterval(h);
    };
  }, [loadWatchlist, loadPortfolio, loadHistory]);

  // Backfill sparklines / detail charts from GET /api/history once per ticker.
  const tickersKey = watchlist.map((w) => w.ticker).join(',');
  useEffect(() => {
    for (const ticker of tickersKey ? tickersKey.split(',') : []) {
      if (!store.claimHistory(ticker)) continue;
      api
        .priceHistory(ticker)
        .then((pts) => store.mergeHistory(ticker, pts))
        .catch(() => store.releaseHistory(ticker));
    }
  }, [tickersKey, store]);

  const selected =
    selectedRaw && watchlist.some((w) => w.ticker === selectedRaw) ? selectedRaw : (watchlist[0]?.ticker ?? null);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadWatchlist(), loadPortfolio(), loadHistory()]);
  }, [loadWatchlist, loadPortfolio, loadHistory]);

  const addTicker = useCallback(
    async (raw: string) => {
      const ticker = raw.trim().toUpperCase();
      if (!ticker) return 'Enter a ticker symbol';
      try {
        await api.addTicker(ticker);
        await loadWatchlist();
        setSelected(ticker);
        return null;
      } catch (e) {
        return e instanceof ApiError ? e.message : 'Could not add ticker';
      }
    },
    [loadWatchlist],
  );

  const removeTicker = useCallback(
    async (ticker: string) => {
      try {
        await api.removeTicker(ticker);
        await loadWatchlist();
        return null;
      } catch (e) {
        return e instanceof ApiError ? e.message : 'Could not remove ticker';
      }
    },
    [loadWatchlist],
  );

  const trade = useCallback(
    async (req: TradeRequest) => {
      const result = await api.trade(req);
      await Promise.all([loadPortfolio(), loadHistory()]);
      return result;
    },
    [loadPortfolio, loadHistory],
  );

  const value = useMemo<DataContextValue>(
    () => ({
      watchlist,
      watchlistLoaded,
      portfolio,
      portfolioHistory,
      selected,
      select: setSelected,
      addTicker,
      removeTicker,
      trade,
      refreshAll,
    }),
    [watchlist, watchlistLoaded, portfolio, portfolioHistory, selected, addTicker, removeTicker, trade, refreshAll],
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): DataContextValue {
  const v = useContext(DataContext);
  if (!v) throw new Error('useData must be used inside <DataProvider>');
  return v;
}

export { DataContext };
