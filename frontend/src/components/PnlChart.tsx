'use client';

import { useMemo } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useData } from '@/lib/DataProvider';
import { axisFormatter, fmtUsd, valueDomain } from '@/lib/format';
import { useLivePrices } from '@/lib/PriceProvider';
import { useLivePortfolio } from '@/lib/useLivePortfolio';
import { ChartTip } from './ChartTip';
import { Panel } from './Panel';

const START_CASH = 10_000;

interface ValuePoint {
  t: number; // ms
  v: number;
}

const clock = (ms: number) =>
  new Date(ms).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

/** Total portfolio value over time: server snapshots plus a live tail point from the current valuation. */
export function PnlChart() {
  const { portfolioHistory } = useData();
  const portfolio = useLivePortfolio();
  const store = useLivePrices();

  const latestTick = Math.max(0, ...Object.values(store.prices).map((p) => p.timestamp)) * 1000;
  const total = portfolio?.total_value;

  const data = useMemo<ValuePoint[]>(() => {
    const pts = portfolioHistory
      .map((p) => ({ t: Date.parse(p.recorded_at), v: p.total_value }))
      .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v));
    const last = pts[pts.length - 1];
    if (total !== undefined && latestTick > 0 && (!last || latestTick > last.t)) pts.push({ t: latestTick, v: total });
    return pts;
  }, [portfolioHistory, total, latestTick]);

  const range = data.length ? Math.max(...data.map((d) => d.v)) - Math.min(...data.map((d) => d.v)) : 0;

  return (
    <Panel title="Portfolio value" className="min-h-[220px] xl:h-full" bodyClassName="flex min-h-0 flex-col">
      <div data-testid="pnl-chart" data-points={data.length} className="relative min-h-[170px] flex-1">
        <div className="absolute inset-0 px-1 pb-1 pt-2">
          {data.length >= 2 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#232d3b" strokeOpacity={0.6} vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={clock}
                  tick={{ fill: '#7d8a9c', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#303d50' }}
                  minTickGap={48}
                />
                <YAxis
                  orientation="right"
                  domain={valueDomain}
                  tickFormatter={axisFormatter(range)}
                  tick={{ fill: '#7d8a9c', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={64}
                />
                <ReferenceLine y={START_CASH} stroke="#7d8a9c" strokeDasharray="4 4" ifOverflow="hidden" />
                <Tooltip
                  isAnimationActive={false}
                  cursor={{ stroke: '#5a6b82', strokeDasharray: '3 3' }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as ValuePoint;
                    return (
                      <ChartTip label={new Date(p.t).toLocaleString('en-US', { hour12: false })}>
                        <div className="num font-semibold">{fmtUsd(p.v)}</div>
                      </ChartTip>
                    );
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke="#ecad0a"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: '#111823', strokeWidth: 2, fill: '#ecad0a' }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center px-6 text-center text-[12px] text-muted">
              Value history builds up as prices move and you trade.
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
