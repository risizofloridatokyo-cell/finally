'use client';

import { DataProvider } from '@/lib/DataProvider';
import { PriceProvider } from '@/lib/PriceProvider';
import { ChatPanel } from './ChatPanel';
import { Header } from './Header';
import { Heatmap } from './Heatmap';
import { MainChart } from './MainChart';
import { PnlChart } from './PnlChart';
import { PositionsTable } from './PositionsTable';
import { TradeBar } from './TradeBar';
import { Watchlist } from './Watchlist';

/**
 * Desktop (xl): fixed-viewport terminal, three columns — watchlist | charts + portfolio | chat.
 * Below xl the columns stack and the page scrolls.
 */
export function Dashboard() {
  return (
    <PriceProvider>
      <DataProvider>
        <div className="flex min-h-screen flex-col xl:h-screen xl:overflow-hidden">
          <Header />
          <main className="grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 md:grid-cols-[340px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_auto]">
            <div className="min-h-0 md:row-span-1 xl:h-full">
              <Watchlist />
            </div>

            <div className="grid min-h-0 min-w-0 grid-rows-[auto] gap-2 xl:h-full xl:grid-rows-[minmax(0,1.25fr)_minmax(0,1fr)_auto_minmax(0,0.8fr)]">
              <MainChart />
              <div className="grid min-h-0 grid-cols-1 gap-2 lg:grid-cols-2">
                <Heatmap />
                <PnlChart />
              </div>
              <TradeBar />
              <PositionsTable />
            </div>

            <div className="min-h-0 md:col-span-2 xl:col-span-1 xl:h-full">
              <ChatPanel />
            </div>
          </main>
        </div>
      </DataProvider>
    </PriceProvider>
  );
}
