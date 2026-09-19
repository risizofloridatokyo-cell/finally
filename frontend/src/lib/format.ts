const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Shown wherever a value is not available (e.g. a price that has not warmed yet). */
export const EMPTY = '—';

export function isNum(n: number | null | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n);
}

/** `$1,234.50`, `-$5.00`; `—` for null. */
export function fmtUsd(n: number | null | undefined): string {
  if (!isNum(n)) return EMPTY;
  const v = Math.abs(n) < 0.005 ? 0 : n; // avoid "-$0.00"
  return v < 0 ? `-${usd.format(-v)}` : usd.format(v);
}

/** Like fmtUsd but with an explicit `+` on gains. */
export function fmtSignedUsd(n: number | null | undefined): string {
  if (!isNum(n)) return EMPTY;
  const s = fmtUsd(n);
  return n >= 0.005 ? `+${s}` : s;
}

/** Plain price with 2 decimals and no currency symbol; `—` for null. */
export function fmtPrice(n: number | null | undefined): string {
  if (!isNum(n)) return EMPTY;
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** `+1.23%` / `-0.40%` / `0.00%`; `—` for null. */
export function fmtPct(n: number | null | undefined): string {
  if (!isNum(n)) return EMPTY;
  const v = Math.abs(n) < 0.005 ? 0 : n;
  const s = `${Math.abs(v).toFixed(2)}%`;
  return v > 0 ? `+${s}` : v < 0 ? `-${s}` : s;
}

/** Share quantities: up to 4 decimals, trailing zeros trimmed. */
export function fmtQty(n: number | null | undefined): string {
  if (!isNum(n)) return EMPTY;
  return n.toLocaleString('en-US', { maximumFractionDigits: 4 });
}

export type Sign = 'pos' | 'neg' | 'zero';

export function pnlSign(n: number | null | undefined): Sign {
  if (!isNum(n) || Math.abs(n) < 0.005) return 'zero';
  return n > 0 ? 'pos' : 'neg';
}

/** Tailwind text color class for a P&L-ish number. */
export function signClass(sign: Sign): string {
  return sign === 'pos' ? 'text-up' : sign === 'neg' ? 'text-down' : 'text-ink-2';
}

export function fmtClock(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', { hour12: false });
}

/** Pad a y-domain so a near-flat series does not stretch a few cents into a cliff. */
export function valueDomain([min, max]: readonly [number, number]): [number, number] {
  const mid = (min + max) / 2;
  const pad = Math.max((max - min) * 0.15, Math.abs(mid) * 0.0005, 0.5);
  return [min - pad, max + pad];
}

/** Whole dollars for wide ranges; cents once the visible range is small enough to need them. */
export function axisFormatter(range: number): (v: number) => string {
  const digits = range < 20 ? 2 : 0;
  return (v) => '$' + v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
