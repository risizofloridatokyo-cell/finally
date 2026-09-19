import type { ConnectionStatus } from '@/lib/types';

const LABEL: Record<ConnectionStatus, string> = {
  connected: 'Live',
  reconnecting: 'Reconnecting',
  disconnected: 'Offline',
};

const COLOR: Record<ConnectionStatus, string> = {
  connected: 'bg-up',
  reconnecting: 'bg-accent dot-pulse',
  disconnected: 'bg-down',
};

/** Green = connected, yellow = reconnecting, red = disconnected (PLAN §10). Label repeats the state for non-color cues. */
export function ConnectionDot({ status }: { status: ConnectionStatus }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-ink-2" title={`Price stream: ${LABEL[status]}`}>
      <span
        data-testid="connection-dot"
        data-status={status}
        role="status"
        aria-label={`Price stream ${LABEL[status]}`}
        className={`inline-block h-2.5 w-2.5 rounded-full ${COLOR[status]}`}
      />
      <span className="hidden sm:inline">{LABEL[status]}</span>
    </div>
  );
}
