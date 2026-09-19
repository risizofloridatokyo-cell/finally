'use client';

import { useMemo } from 'react';
import { ResponsiveContainer, Tooltip, Treemap } from 'recharts';
import { fmtPct, fmtPrice, fmtSignedUsd, fmtUsd } from '@/lib/format';
import { heatColor, heatData, heatSign, type HeatDatum } from '@/lib/heat';
import { useLivePortfolio } from '@/lib/useLivePortfolio';
import { ChartTip } from './ChartTip';
import { Panel } from './Panel';

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  name?: string;
  pnl?: number;
  pnlPct?: number | null;
  weight?: number;
}

/** One treemap rectangle: fill = P&L color, area = portfolio weight. Exported for tests. */
export function HeatCell({ x = 0, y = 0, width = 0, height = 0, depth, name, pnl = 0, pnlPct = null, weight = 0 }: CellProps) {
  if (depth === 0 || !name) return <g />;
  const fits = width > 46 && height > 30;
  return (
    <g data-testid={`heatmap-cell-${name}`} data-pnl-sign={heatSign(pnl)}>
      <rect
        x={x}
        y={y}
        width={Math.max(width, 0)}
        height={Math.max(height, 0)}
        fill={heatColor(pnlPct)}
        stroke="#111823"
        strokeWidth={2}
        rx={2}
      />
      {fits && (
        <>
          <text x={x + 8} y={y + 18} fill="#e6edf3" fontSize={13} fontWeight={700} style={{ letterSpacing: '0.02em' }}>
            {name}
          </text>
          <text x={x + 8} y={y + 33} fill="#e6edf3" fillOpacity={0.85} fontSize={12} style={{ fontFamily: 'var(--font-mono)' }}>
            {fmtPct(pnlPct)}
          </text>
          {height > 62 && width > 70 && (
            <text x={x + 8} y={y + 48} fill="#e6edf3" fillOpacity={0.6} fontSize={11}>
              {weight.toFixed(0)}% of holdings
            </text>
          )}
        </>
      )}
    </g>
  );
}

/** Positions sized by weight, colored by unrealized P&L (green = profit, red = loss). */
export function Heatmap() {
  const portfolio = useLivePortfolio();
  const data = useMemo(() => heatData(portfolio?.positions ?? []), [portfolio]);

  return (
    <Panel
      title="Portfolio heatmap"
      className="min-h-[220px] xl:h-full"
      bodyClassName="flex min-h-0 flex-col"
      actions={<span className="text-[11px] text-muted">Size = weight, color = unrealized P&amp;L</span>}
    >
      <div data-testid="heatmap" data-cells={data.length} className="relative min-h-[170px] flex-1">
        <div className="absolute inset-0 p-1.5">
          {data.length === 0 ? (
            <div className="grid h-full place-items-center px-6 text-center text-[12px] text-muted">
              No positions yet. Buy a share and it appears here.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={data as unknown as HeatDatum[]}
                dataKey="size"
                nameKey="name"
                aspectRatio={1.4}
                isAnimationActive={false}
                content={<HeatCell />}
              >
                <Tooltip
                  isAnimationActive={false}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload as HeatDatum;
                    return (
                      <ChartTip label={d.name}>
                        <div className="num space-y-0.5">
                          <div>Value {fmtUsd(d.size)}</div>
                          <div>
                            P&amp;L {fmtSignedUsd(d.pnl)} ({fmtPct(d.pnlPct)})
                          </div>
                          <div className="text-muted">Weight {fmtPrice(d.weight)}%</div>
                        </div>
                      </ChartTip>
                    );
                  }}
                />
              </Treemap>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </Panel>
  );
}
