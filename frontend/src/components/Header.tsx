'use client';

import { fmtSignedUsd, fmtUsd, pnlSign, signClass } from '@/lib/format';
import { useLivePortfolio } from '@/lib/useLivePortfolio';
import { useLivePrices } from '@/lib/PriceProvider';
import { ConnectionDot } from './ConnectionDot';

function Stat({ label, value, testId, className = '' }: { label: string; value: string; testId: string; className?: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[11px] text-muted">{label}</span>
      <span data-testid={testId} className={`num text-[15px] font-semibold ${className}`}>
        {value}
      </span>
    </div>
  );
}

export function Header() {
  const portfolio = useLivePortfolio();
  const store = useLivePrices();

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-panel px-4">
      <div className="flex items-center gap-2.5">
        <span aria-hidden className="grid h-6 w-6 place-items-center rounded-[3px] bg-accent text-[13px] font-black text-bg">
          F
        </span>
        <span className="text-[15px] font-semibold tracking-tight">FinAlly</span>
      </div>

      <div className="flex flex-1 items-center gap-7 overflow-x-auto">
        <Stat label="Total value" testId="header-total-value" value={fmtUsd(portfolio?.total_value)} className="text-ink" />
        <Stat label="Cash" testId="header-cash" value={fmtUsd(portfolio?.cash_balance)} />
        <Stat
          label="Realized P&L"
          testId="header-realized-pnl"
          value={fmtSignedUsd(portfolio?.realized_pnl)}
          className={signClass(pnlSign(portfolio?.realized_pnl))}
        />
        <Stat
          label="Unrealized P&L"
          testId="header-unrealized-pnl"
          value={fmtSignedUsd(portfolio?.total_unrealized_pnl)}
          className={signClass(pnlSign(portfolio?.total_unrealized_pnl))}
        />
      </div>

      <ConnectionDot status={store.status} />
    </header>
  );
}
