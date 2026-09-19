'use client';

import { memo } from 'react';
import { Line, LineChart, YAxis } from 'recharts';
import type { Point } from '@/lib/types';

const W = 76;
const H = 26;

/** Tiny fixed-size price line. Colored by direction over the plotted window; `data-points` = points plotted. */
function SparklineImpl({ ticker, points }: { ticker: string; points: Point[] }) {
  const up = points.length < 2 || points[points.length - 1].price >= points[0].price;
  const color = points.length < 2 ? '#7d8a9c' : up ? '#3fb950' : '#f85149';
  return (
    <div data-testid={`sparkline-${ticker}`} data-points={points.length} style={{ width: W, height: H }} aria-hidden>
      {points.length >= 2 && (
        <LineChart width={W} height={H} data={points} margin={{ top: 2, right: 1, bottom: 2, left: 1 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line type="monotone" dataKey="price" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      )}
    </div>
  );
}

export const Sparkline = memo(SparklineImpl);
