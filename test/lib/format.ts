/** Parse UI currency text such as "$10,000.00", "-$12.34", "+$5.00", "−$3.10" or "($3.10)". NaN for "—" / empty. */
export function parseMoney(text: string | null | undefined): number {
  if (!text) return NaN;
  const t = text.trim();
  const digits = t.replace(/[^0-9.]/g, '');
  if (!/\d/.test(digits)) return NaN;
  const n = parseFloat(digits);
  const negative = /^[-−–(]/.test(t) || /[-−–]\s*\$/.test(t);
  return negative ? -n : n;
}

/** Parse "+0.12%", "-1.5 %", "−0.3%". NaN for "—". */
export function parsePct(text: string | null | undefined): number {
  return parseMoney(text?.replace('%', ''));
}

export function signOf(n: number): 'pos' | 'neg' | 'zero' {
  if (n > 0) return 'pos';
  if (n < 0) return 'neg';
  return 'zero';
}
