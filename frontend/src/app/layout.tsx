import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'FinAlly — AI Trading Workstation',
  description: 'Live simulated market data, a virtual portfolio and an AI trading copilot.',
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#0d1117' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg text-ink antialiased">{children}</body>
    </html>
  );
}
