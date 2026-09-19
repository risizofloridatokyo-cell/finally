'use client';

import { useEffect, useState } from 'react';

export const FLASH_MS = 500;
/** Class stays on slightly longer than the CSS fade so the fade always completes. */
const FLASH_CLASS_MS = FLASH_MS + 100;

interface Flash {
  dir: 'up' | 'down';
  seq: number;
}

/**
 * Returns `{ className, phase }` for a price cell: `flash-up` / `flash-down`
 * for ~500ms after each change. `phase` (0/1) alternates on every change so
 * the CSS animation restarts even for back-to-back ticks in the same direction.
 */
export function useFlash(price: number | null | undefined): { className: string; phase: 0 | 1 } {
  const [prevPrice, setPrevPrice] = useState(price);
  const [flash, setFlash] = useState<Flash | null>(null);
  const [seq, setSeq] = useState(0);

  // Adjust state while rendering when the price prop changes (React-recommended over an effect).
  if (price !== prevPrice) {
    setPrevPrice(price);
    if (typeof price === 'number' && typeof prevPrice === 'number') {
      setFlash({ dir: price > prevPrice ? 'up' : 'down', seq: seq + 1 });
      setSeq(seq + 1);
    } else {
      setFlash(null);
    }
  }

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), FLASH_CLASS_MS);
    return () => clearTimeout(t);
  }, [flash]);

  return {
    className: flash ? (flash.dir === 'up' ? 'flash-up' : 'flash-down') : '',
    phase: ((flash?.seq ?? seq) % 2) as 0 | 1,
  };
}
