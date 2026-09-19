'use client';

import { useEffect, useState } from 'react';
import { ApiError } from '@/lib/api';
import { useData } from '@/lib/DataProvider';
import { fmtPrice, fmtQty, fmtUsd } from '@/lib/format';
import { useLivePrices } from '@/lib/PriceProvider';

/** Parse a quantity field: a positive finite number, else null. */
export function parseQuantity(raw: string): number | null {
  const s = raw.trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function TradeBar() {
  const { selected, trade } = useData();
  const store = useLivePrices();
  const [ticker, setTicker] = useState('');
  const [qty, setQty] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [followed, setFollowed] = useState<string | null>(null);

  // Selecting a ticker elsewhere pre-fills the trade ticker (adjust state during render, not in an effect).
  if (selected !== followed) {
    setFollowed(selected);
    if (selected) setTicker(selected);
  }

  useEffect(() => {
    if (!ok) return;
    const t = setTimeout(() => setOk(null), 5000);
    return () => clearTimeout(t);
  }, [ok]);

  const symbol = ticker.trim().toUpperCase();
  const q = parseQuantity(qty);
  const price = store.prices[symbol]?.price;
  const estimate = q !== null && q > 0 && price !== undefined ? q * price : null;

  async function submit(side: 'buy' | 'sell') {
    setOk(null);
    if (!symbol) return setError('Enter a ticker symbol');
    if (q === null) return setError('Enter a quantity');
    setError(null);
    setBusy(true);
    try {
      const r = await trade({ ticker: symbol, quantity: q, side });
      setOk(`${side === 'buy' ? 'Bought' : 'Sold'} ${fmtQty(r.quantity)} ${r.ticker} at ${fmtPrice(r.price)}`);
      setQty('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Trade failed');
    } finally {
      setBusy(false);
    }
  }

  const field =
    'num rounded-[3px] border border-line-2 bg-bg px-2 py-1.5 text-[13px] placeholder:text-muted focus:border-blue';

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[3px] border border-line bg-panel px-3 py-2">
      <span className="text-[12px] font-medium text-ink-2">Trade</span>
      <input
        data-testid="trade-ticker"
        aria-label="Ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="Ticker"
        maxLength={12}
        spellCheck={false}
        autoCapitalize="characters"
        className={`${field} w-24 uppercase`}
      />
      <input
        data-testid="trade-quantity"
        aria-label="Quantity"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="Shares"
        inputMode="decimal"
        className={`${field} w-28`}
      />
      <button
        type="button"
        data-testid="trade-buy"
        disabled={busy}
        onClick={() => void submit('buy')}
        className="rounded-[3px] bg-purple px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-purple-hi disabled:opacity-60"
      >
        Buy
      </button>
      <button
        type="button"
        data-testid="trade-sell"
        disabled={busy}
        onClick={() => void submit('sell')}
        className="rounded-[3px] border border-purple bg-transparent px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-purple/30 disabled:opacity-60"
      >
        Sell
      </button>
      <span className="num text-[12px] text-muted">
        {estimate !== null ? `≈ ${fmtUsd(estimate)} at market` : price !== undefined ? `Market ${fmtPrice(price)}` : ''}
      </span>
      {error && (
        <span data-testid="trade-error" role="alert" className="text-[12px] text-down">
          {error}
        </span>
      )}
      {ok && (
        <span data-testid="trade-success" role="status" className="text-[12px] text-up">
          {ok}
        </span>
      )}
    </div>
  );
}
