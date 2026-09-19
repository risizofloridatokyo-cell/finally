import { pnlSign, type Sign } from './format';

/** P&L % at which a heatmap cell reaches full color saturation. */
export const HEAT_SATURATION_PCT = 5;

const NEUTRAL: [number, number, number] = [36, 48, 68]; // #243044
const GAIN: [number, number, number] = [30, 140, 62];
const LOSS: [number, number, number] = [190, 48, 44];

/**
 * Diverging fill for a position: neutral slate at 0%, ramping to green (profit)
 * or red (loss), saturating at ±HEAT_SATURATION_PCT.
 */
export function heatColor(pnlPct: number | null | undefined): string {
  if (pnlPct == null || !Number.isFinite(pnlPct)) return `rgb(${NEUTRAL.join(',')})`;
  const t = Math.min(Math.abs(pnlPct) / HEAT_SATURATION_PCT, 1);
  const target = pnlPct >= 0 ? GAIN : LOSS;
  const c = NEUTRAL.map((n, i) => Math.round(n + (target[i] - n) * t));
  return `rgb(${c.join(',')})`;
}

export function heatSign(pnl: number | null | undefined): Sign {
  return pnlSign(pnl);
}

export interface HeatDatum {
  name: string;
  size: number;
  pnl: number;
  pnlPct: number | null;
  weight: number;
  [key: string]: string | number | null;
}

/** Treemap data: positions with a valued price, sized by market value (portfolio weight). */
export function heatData(
  positions: { ticker: string; market_value: number | null; unrealized_pnl: number | null; unrealized_pnl_pct: number | null }[],
): HeatDatum[] {
  const valued = positions.filter((p) => p.market_value != null && p.market_value > 0);
  const total = valued.reduce((s, p) => s + (p.market_value as number), 0);
  return valued.map((p) => ({
    name: p.ticker,
    size: p.market_value as number,
    pnl: p.unrealized_pnl ?? 0,
    pnlPct: p.unrealized_pnl_pct,
    weight: total > 0 ? ((p.market_value as number) / total) * 100 : 0,
  }));
}
