'use client';

import { useState, type FormEvent } from 'react';
import { useData } from '@/lib/DataProvider';
import { fmtPct, pnlSign, signClass } from '@/lib/format';
import { useLivePrices } from '@/lib/PriceProvider';
import { Panel } from './Panel';
import { PriceCell } from './PriceCell';
import { Sparkline } from './Sparkline';

export function Watchlist() {
  const { watchlist, watchlistLoaded, selected, select, addTicker, removeTicker } = useData();
  const store = useLivePrices();
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const err = await addTicker(input);
    setBusy(false);
    setError(err);
    if (!err) setInput('');
  }

  async function onRemove(ticker: string) {
    const err = await removeTicker(ticker);
    setError(err);
  }

  return (
    <Panel
      title="Watchlist"
      className="min-h-[280px] xl:h-full"
      bodyClassName="flex min-h-0 flex-col"
      actions={<span className="text-[11px] text-muted">Session % vs. first price seen</span>}
    >
      <div className="grid grid-cols-[minmax(0,1fr)_72px_60px_76px_18px] items-center gap-x-2 border-b border-line px-3 py-1.5 text-[11px] text-muted">
        <span>Ticker</span>
        <span className="text-right">Price</span>
        <span className="text-right">Session %</span>
        <span>Trend</span>
        <span />
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto" data-testid="watchlist">
        {watchlist.map((item) => {
          const t = item.ticker;
          const price = store.prices[t]?.price ?? item.price;
          const pct = store.sessionPct(t);
          const isSelected = t === selected;
          return (
            <li
              key={t}
              data-testid={`watchlist-row-${t}`}
              data-selected={isSelected}
              onClick={() => select(t)}
              className={`group grid cursor-pointer grid-cols-[minmax(0,1fr)_72px_60px_76px_18px] items-center gap-x-2 border-b border-line/60 px-3 py-1.5 transition-colors hover:bg-panel-2 ${
                isSelected ? 'bg-panel-2 shadow-[inset_2px_0_0_var(--color-accent)]' : ''
              }`}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  select(t);
                }}
                className="truncate text-left text-[13px] font-semibold tracking-wide"
                aria-pressed={isSelected}
              >
                {t}
              </button>
              <PriceCell ticker={t} price={price} className="text-right text-[13px]" />
              <span
                data-testid={`watchlist-session-pct-${t}`}
                className={`num text-right text-[12px] ${signClass(pnlSign(pct))}`}
              >
                {fmtPct(pct)}
              </span>
              <Sparkline ticker={t} points={store.points(t)} />
              <button
                type="button"
                data-testid={`watchlist-remove-${t}`}
                aria-label={`Remove ${t} from watchlist`}
                onClick={(e) => {
                  e.stopPropagation();
                  void onRemove(t);
                }}
                className="grid h-[18px] w-[18px] place-items-center rounded-[2px] text-[14px] leading-none text-muted opacity-60 hover:bg-line hover:text-down hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-100"
              >
                ×
              </button>
            </li>
          );
        })}
        {watchlistLoaded && watchlist.length === 0 && (
          <li className="px-3 py-6 text-center text-[12px] text-muted">Nothing watched yet. Add a ticker below.</li>
        )}
        {!watchlistLoaded && <li className="px-3 py-6 text-center text-[12px] text-muted">Loading watchlist…</li>}
      </ul>

      <form onSubmit={onAdd} className="shrink-0 border-t border-line p-2.5">
        <div className="flex gap-2">
          <input
            data-testid="watchlist-add-input"
            value={input}
            onChange={(e) => {
              setInput(e.target.value.toUpperCase());
              if (error) setError(null);
            }}
            placeholder="Add ticker, e.g. PYPL"
            aria-label="Ticker to add"
            maxLength={12}
            autoCapitalize="characters"
            spellCheck={false}
            className="num min-w-0 flex-1 rounded-[3px] border border-line-2 bg-bg px-2 py-1.5 text-[12px] uppercase placeholder:normal-case placeholder:text-muted focus:border-blue"
          />
          <button
            type="submit"
            data-testid="watchlist-add-button"
            disabled={busy}
            className="rounded-[3px] bg-purple px-3 py-1.5 text-[12px] font-medium text-white hover:bg-purple-hi disabled:opacity-60"
          >
            Add
          </button>
        </div>
        {error && (
          <p data-testid="watchlist-add-error" role="alert" className="mt-1.5 text-[12px] text-down">
            {error}
          </p>
        )}
      </form>
    </Panel>
  );
}
