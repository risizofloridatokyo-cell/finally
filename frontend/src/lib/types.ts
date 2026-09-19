export type Direction = 'up' | 'down' | 'flat';

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number; // unix seconds
  change: number;
  change_percent: number;
  direction: Direction;
}

export type PriceMap = Record<string, PriceUpdate>;

/** One plotted price sample; `t` is unix seconds. */
export interface Point {
  t: number;
  price: number;
}

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export interface WatchItem {
  ticker: string;
  added_at: string;
  price: number | null;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
}

export interface Portfolio {
  cash_balance: number;
  realized_pnl: number;
  total_value: number;
  total_unrealized_pnl: number;
  positions: Position[];
}

export interface PortfolioPoint {
  total_value: number;
  recorded_at: string;
}

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: 'buy' | 'sell';
}

export interface TradeResult {
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  status: string;
}

export interface ChatTradeAction {
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  price?: number | null;
  status: 'executed' | 'rejected';
}

export interface ChatWatchlistAction {
  ticker: string;
  action: 'add' | 'remove';
  status: 'executed' | 'rejected';
}

export interface ChatActions {
  trades?: ChatTradeAction[];
  watchlist_changes?: ChatWatchlistAction[];
  errors?: string[];
}

export interface ChatResponse {
  message: string;
  actions: ChatActions | null;
}
