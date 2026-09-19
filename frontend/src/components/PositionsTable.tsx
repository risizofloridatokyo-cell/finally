'use client';

import { useData } from '@/lib/DataProvider';
import { fmtPct, fmtPrice, fmtQty, fmtSignedUsd, fmtUsd, pnlSign, signClass } from '@/lib/format';
import { useLivePortfolio } from '@/lib/useLivePortfolio';
import { Panel } from './Panel';

const th = 'px-3 py-1.5 text-right text-[11px] font-normal text-muted first:text-left';
const td = 'num px-3 py-1.5 text-right first:text-left';

export function PositionsTable() {
  const portfolio = useLivePortfolio();
  const { select } = useData();
  const positions = portfolio?.positions ?? [];

  return (
    <Panel title="Positions" className="min-h-[160px] xl:h-full" bodyClassName="overflow-auto">
      <table data-testid="positions-table" className="w-full min-w-[560px] border-collapse">
        <thead className="sticky top-0 bg-panel">
          <tr className="border-b border-line">
            <th className={th}>Ticker</th>
            <th className={th}>Qty</th>
            <th className={th}>Avg cost</th>
            <th className={th}>Price</th>
            <th className={th}>Value</th>
            <th className={th}>Unrealized P&amp;L</th>
            <th className={th}>P&amp;L % vs cost</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const sign = pnlSign(p.unrealized_pnl);
            const tone = signClass(sign);
            return (
              <tr
                key={p.ticker}
                data-testid={`position-row-${p.ticker}`}
                onClick={() => select(p.ticker)}
                className="cursor-pointer border-b border-line/60 hover:bg-panel-2"
              >
                <td className={`${td} font-sans text-[13px] font-semibold tracking-wide`}>{p.ticker}</td>
                <td className={td} data-testid={`position-qty-${p.ticker}`}>
                  {fmtQty(p.quantity)}
                </td>
                <td className={td}>{fmtPrice(p.avg_cost)}</td>
                <td className={td} data-testid={`position-price-${p.ticker}`}>
                  {fmtPrice(p.current_price)}
                </td>
                <td className={td}>{fmtUsd(p.market_value)}</td>
                <td className={`${td} ${tone}`} data-testid={`position-pnl-${p.ticker}`}>
                  {fmtSignedUsd(p.unrealized_pnl)}
                </td>
                <td className={`${td} ${tone}`} data-testid={`position-pnl-pct-${p.ticker}`}>
                  {fmtPct(p.unrealized_pnl_pct)}
                </td>
              </tr>
            );
          })}
          {positions.length === 0 && (
            <tr>
              <td colSpan={7} className="px-3 py-6 text-center text-[12px] text-muted">
                No open positions. Use the trade bar to buy your first shares.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Panel>
  );
}
