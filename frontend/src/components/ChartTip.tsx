import type { ReactNode } from 'react';

/** Shared hover card for line charts: a quiet panel with a label and one or more value rows. */
export function ChartTip({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-[3px] border border-line-2 bg-bg/95 px-2.5 py-1.5 text-[12px] shadow-lg">
      <div className="mb-0.5 text-[11px] text-muted">{label}</div>
      {children}
    </div>
  );
}
