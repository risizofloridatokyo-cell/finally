'use client';

import { fmtPrice } from '@/lib/format';
import { useFlash } from '@/lib/useFlash';

/** Price text that flashes green/red (CSS fade ~500ms) whenever the price changes. */
export function PriceCell({
  ticker,
  price,
  className = '',
  testId,
}: {
  ticker: string;
  price: number | null | undefined;
  className?: string;
  testId?: string;
}) {
  const { className: flash, phase } = useFlash(price);
  return (
    <span
      data-testid={testId ?? `watchlist-price-${ticker}`}
      data-flash-phase={flash ? phase : undefined}
      className={`num inline-block rounded-[2px] px-1 ${flash} ${className}`}
    >
      {fmtPrice(price)}
    </span>
  );
}
