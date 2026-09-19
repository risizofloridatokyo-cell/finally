import type {
  ChatResponse,
  Point,
  Portfolio,
  PortfolioPoint,
  Position,
  TradeRequest,
  TradeResult,
  WatchItem,
} from './types';

/** Same-origin by default. Only set NEXT_PUBLIC_API_BASE to point a dev build at another origin. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
  }
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: unknown };
      if (first && typeof first.msg === 'string') return first.msg;
    }
  }
  return fallback;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, 'Cannot reach the server');
  }
  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) throw new ApiError(res.status, detailOf(body, `Request failed (${res.status})`));
  return body as T;
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** Tolerant to small naming variations so a backend rename degrades gracefully. */
function normalizePosition(raw: Record<string, unknown>): Position {
  const quantity = num(raw.quantity ?? raw.qty) ?? 0;
  const current = num(raw.current_price ?? raw.price);
  const avg = num(raw.avg_cost) ?? 0;
  return {
    ticker: String(raw.ticker),
    quantity,
    avg_cost: avg,
    current_price: current,
    market_value: num(raw.market_value) ?? (current == null ? null : current * quantity),
    unrealized_pnl: num(raw.unrealized_pnl ?? raw.pnl) ?? (current == null ? null : (current - avg) * quantity),
    unrealized_pnl_pct:
      num(raw.unrealized_pnl_pct ?? raw.unrealized_pnl_percent ?? raw.pnl_percent) ??
      (current == null || avg === 0 ? null : (current / avg - 1) * 100),
  };
}

export function normalizePortfolio(raw: Record<string, unknown>): Portfolio {
  const positions = Array.isArray(raw.positions)
    ? (raw.positions as Record<string, unknown>[]).map(normalizePosition)
    : [];
  return {
    cash_balance: num(raw.cash_balance ?? raw.cash) ?? 0,
    realized_pnl: num(raw.realized_pnl) ?? 0,
    total_value: num(raw.total_value) ?? 0,
    total_unrealized_pnl: num(raw.total_unrealized_pnl) ?? 0,
    positions,
  };
}

export const api = {
  async watchlist(): Promise<WatchItem[]> {
    const raw = await request<WatchItem[] | { watchlist?: WatchItem[] }>('/api/watchlist');
    return Array.isArray(raw) ? raw : (raw.watchlist ?? []);
  },
  async addTicker(ticker: string): Promise<void> {
    await request('/api/watchlist', { method: 'POST', body: JSON.stringify({ ticker }) });
  },
  async removeTicker(ticker: string): Promise<void> {
    await request(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: 'DELETE' });
  },
  async portfolio(): Promise<Portfolio> {
    return normalizePortfolio(await request<Record<string, unknown>>('/api/portfolio'));
  },
  async portfolioHistory(): Promise<PortfolioPoint[]> {
    const raw = await request<PortfolioPoint[] | { snapshots?: PortfolioPoint[]; points?: PortfolioPoint[] }>(
      '/api/portfolio/history',
    );
    if (Array.isArray(raw)) return raw;
    return raw.snapshots ?? raw.points ?? [];
  },
  trade(req: TradeRequest): Promise<TradeResult> {
    return request<TradeResult>('/api/portfolio/trade', { method: 'POST', body: JSON.stringify(req) });
  },
  async priceHistory(ticker: string): Promise<Point[]> {
    const raw = await request<{ points: { price: number; timestamp: number }[] }>(
      `/api/history?ticker=${encodeURIComponent(ticker)}`,
    );
    return (raw.points ?? []).map((p) => ({ t: p.timestamp, price: p.price }));
  },
  chat(message: string): Promise<ChatResponse> {
    return request<ChatResponse>('/api/chat', { method: 'POST', body: JSON.stringify({ message }) });
  },
};
