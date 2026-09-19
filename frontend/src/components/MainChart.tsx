'use client';

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useData } from '@/lib/DataProvider';
import { fmtClock, fmtPct, fmtPrice, pnlSign, signClass } from '@/lib/format';
import { useLivePrices } from '@/lib/PriceProvider';
import { ChartTip } from './ChartTip';
import { Panel } from './Panel';
import { PriceCell } from './PriceCell';

const BLUE = '#209dd7';

export function MainChart() {
  const { selected } = useData();
  const store = useLivePrices();
  const ticker = selected;
  const points = ticker ? store.points(ticker) : [];
  const price = ticker ? store.prices[ticker]?.price : undefined;
  const pct = ticker ? store.sessionPct(ticker) : null;
  const baseline = ticker ? store.baselines[ticker] : undefined;

  let hi: number | null = null;
  let lo: number | null = null;
  for (const p of points) {
    if (hi === null || p.price > hi) hi = p.price;
    if (lo === null || p.price < lo) lo = p.price;
  }

  return (
    <Panel
      title={ticker ? `${ticker} price` : 'Price chart'}
      className="min-h-[300px] xl:h-full"
      bodyClassName="flex min-h-0 flex-col"
      actions={<span className="text-[11px] text-muted">Click a ticker in the watchlist to switch</span>}
    >
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-6 gap-y-1 px-3 pt-2">
        <div className="flex items-baseline gap-2">
          <span className="text-[20px] font-semibold tracking-wide">{ticker ?? '—'}</span>
          <PriceCell
            ticker={ticker ?? ''}
            price={price}
            testId="main-chart-price"
            className="text-[20px] font-semibold"
          />
          <span className={`num text-[13px] ${signClass(pnlSign(pct))}`}>{fmtPct(pct)}</span>
        </div>
        <div className="num flex gap-4 text-[12px] text-muted">
          <span>
            High <span className="text-ink-2">{fmtPrice(hi)}</span>
          </span>
          <span>
            Low <span className="text-ink-2">{fmtPrice(lo)}</span>
          </span>
        </div>
      </div>

      <div
        data-testid="main-chart"
        data-ticker={ticker ?? ''}
        data-points={points.length}
        className="relative min-h-[200px] flex-1"
      >
        <div className="absolute inset-0 px-1 pb-1 pt-2">
          {points.length >= 2 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="mainFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={BLUE} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={BLUE} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#232d3b" strokeOpacity={0.6} vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={fmtClock}
                  tick={{ fill: '#7d8a9c', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#303d50' }}
                  minTickGap={56}
                />
                <YAxis
                  orientation="right"
                  domain={['auto', 'auto']}
                  tickFormatter={(v: number) => v.toFixed(2)}
                  tick={{ fill: '#7d8a9c', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={58}
                />
                {baseline !== undefined && (
                  <ReferenceLine y={baseline} stroke="#7d8a9c" strokeDasharray="4 4" ifOverflow="hidden" />
                )}
                <Tooltip
                  isAnimationActive={false}
                  cursor={{ stroke: '#5a6b82', strokeDasharray: '3 3' }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as { t: number; price: number };
                    return (
                      <ChartTip label={fmtClock(p.t)}>
                        <div className="num font-semibold">{fmtPrice(p.price)}</div>
                      </ChartTip>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke={BLUE}
                  strokeWidth={2}
                  fill="url(#mainFill)"
                  dot={false}
                  activeDot={{ r: 4, stroke: '#111823', strokeWidth: 2, fill: BLUE }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-[12px] text-muted">
              {ticker ? 'Waiting for price data…' : 'Select a ticker to see its chart.'}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
