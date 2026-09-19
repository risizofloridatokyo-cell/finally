import type { ConnectionStatus } from './types';

/** EventSource.readyState values (avoids the global so this also runs under SSR/jsdom). */
export const READY_CONNECTING = 0;
export const READY_OPEN = 1;
export const READY_CLOSED = 2;

/**
 * Three-state connection dot derived from EventSource (PLAN §10):
 *  - green  once `onopen` fired and readyState === OPEN
 *  - yellow on `onerror` while readyState === CONNECTING (browser is auto-reconnecting)
 *  - red    when readyState === CLOSED
 */
export function deriveStatus(event: 'open' | 'error', readyState: number): ConnectionStatus {
  if (event === 'open') return readyState === READY_OPEN ? 'connected' : 'reconnecting';
  return readyState === READY_CLOSED ? 'disconnected' : 'reconnecting';
}
