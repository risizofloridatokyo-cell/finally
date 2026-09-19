export const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8000';

/**
 * The fresh-start spec asserts the seeded $10,000.00 balance. That only holds on a brand-new DB, so it is on by default
 * (docker-compose always starts a fresh DB). Set FRESH_DB=0 when re-running against a DB that already saw trades.
 */
export const EXPECT_FRESH_DB = (process.env.FRESH_DB ?? '1') !== '0';

export const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'] as const;
