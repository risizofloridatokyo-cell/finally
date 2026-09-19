'use client';

import { useMemo } from 'react';
import { useData } from './DataProvider';
import { useLivePrices } from './PriceProvider';
import { derivePortfolio } from './portfolio';
import type { Portfolio } from './types';

/** The fetched portfolio re-valued against the latest SSE prices; re-renders on every tick. */
export function useLivePortfolio(): Portfolio | null {
  const { portfolio } = useData();
  const store = useLivePrices();
  const prices = store.prices;
  return useMemo(() => derivePortfolio(portfolio, prices), [portfolio, prices]);
}
