import { deriveStatus } from './connection';
import type { ConnectionStatus, Point, PriceMap, PriceUpdate } from './types';

/** Max points kept per ticker (backend ring buffer is ~300; live ticks extend it). */
export const MAX_POINTS = 600;

/**
 * Client-side price state fed by the single shared SSE connection:
 * latest price per ticker, the session baseline (first price observed per
 * ticker after page load), and a bounded series per ticker for charts.
 *
 * Exposed through `subscribe` / `getVersion` so React can read it with
 * `useSyncExternalStore`; every `ingest` bumps the version once.
 */
export class PriceStore {
  prices: PriceMap = {};
  baselines: Record<string, number> = {};
  series: Record<string, Point[]> = {};
  status: ConnectionStatus = 'reconnecting';

  private version = 0;
  private listeners = new Set<() => void>();
  private historyRequested = new Set<string>();

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  private emit(): void {
    this.version += 1;
    this.listeners.forEach((fn) => fn());
  }

  setStatus(status: ConnectionStatus): void {
    if (status === this.status) return;
    this.status = status;
    this.emit();
  }

  /** Map an EventSource lifecycle event onto the 3-state connection status. */
  onSourceEvent(event: 'open' | 'error', readyState: number): void {
    this.setStatus(deriveStatus(event, readyState));
  }

  /** Apply one SSE payload: an object keyed by ticker. */
  ingest(payload: Record<string, PriceUpdate>): void {
    let changed = false;
    for (const [ticker, u] of Object.entries(payload)) {
      if (!u || typeof u.price !== 'number' || !Number.isFinite(u.price)) continue;
      const prev = this.prices[ticker];
      this.prices[ticker] = u;
      if (this.baselines[ticker] === undefined) this.baselines[ticker] = u.price;
      const pts = this.series[ticker] ?? [];
      const last = pts[pts.length - 1];
      // The server sends every tracked ticker per event; unchanged ticks share a timestamp.
      if (!last || u.timestamp > last.t) {
        // Immutable update so chart consumers see a new array identity.
        const next = pts.length >= MAX_POINTS ? pts.slice(pts.length - MAX_POINTS + 1) : pts.slice();
        next.push({ t: u.timestamp, price: u.price });
        this.series[ticker] = next;
        changed = true;
      } else if (!prev || prev.price !== u.price) {
        changed = true;
      }
    }
    if (changed) {
      this.prices = { ...this.prices }; // new identity for memoised consumers
      this.emit();
    }
  }

  /**
   * Merge backfilled history (oldest-first) in front of whatever live points
   * already arrived, dropping overlap.
   */
  mergeHistory(ticker: string, history: Point[]): void {
    const existing = this.series[ticker] ?? [];
    const cutoff = existing.length ? existing[0].t : Infinity;
    const older = history.filter((p) => p.t < cutoff);
    if (!older.length) return;
    this.series[ticker] = [...older, ...existing].slice(-MAX_POINTS);
    this.emit();
  }

  /** True the first time it is asked for a ticker; lets callers fetch history once. */
  claimHistory(ticker: string): boolean {
    if (this.historyRequested.has(ticker)) return false;
    this.historyRequested.add(ticker);
    return true;
  }

  releaseHistory(ticker: string): void {
    this.historyRequested.delete(ticker);
  }

  /** Session % change vs. the first price observed this session; null until a baseline exists. */
  sessionPct(ticker: string): number | null {
    return sessionChangePct(this.baselines[ticker], this.prices[ticker]?.price);
  }

  points(ticker: string): Point[] {
    return this.series[ticker] ?? [];
  }
}

/** Pure helper used by tests and the store consumers. */
export function sessionChangePct(baseline: number | undefined, price: number | undefined | null): number | null {
  if (baseline === undefined || baseline === 0 || price === undefined || price === null) return null;
  return (price / baseline - 1) * 100;
}
