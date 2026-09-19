'use client';

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { api, ApiError } from '@/lib/api';
import { useData } from '@/lib/DataProvider';
import { fmtPrice, fmtQty } from '@/lib/format';
import type { ChatActions } from '@/lib/types';

interface Msg {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  actions?: ChatActions | null;
}

const SUGGESTIONS = ['How is my portfolio doing?', 'Which position is my biggest risk?', 'Buy 5 shares of NVDA'];

const executedTrades = (a?: ChatActions | null) => (a?.trades ?? []).filter((t) => t.status === 'executed').length;
const executedWatch = (a?: ChatActions | null) =>
  (a?.watchlist_changes ?? []).filter((w) => w.status === 'executed').length;

/** Inline confirmations for what the assistant executed (or could not execute). Exported for tests. */
export function ActionList({ actions }: { actions?: ChatActions | null }) {
  if (!actions) return null;
  const { trades = [], watchlist_changes = [], errors = [] } = actions;
  if (!trades.length && !watchlist_changes.length && !errors.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {trades.map((t, i) =>
        t.status === 'executed' ? (
          <li
            key={`t${i}`}
            data-testid="chat-action-trade-executed"
            className="flex items-start gap-1.5 rounded-[3px] border border-up/30 bg-up/10 px-2 py-1 text-[12px] text-up"
          >
            <span aria-hidden>✓</span>
            <span className="num">
              {t.side === 'buy' ? 'Bought' : 'Sold'} {fmtQty(t.quantity)} {t.ticker}
              {t.price != null ? ` @ $${fmtPrice(t.price)}` : ''}
            </span>
          </li>
        ) : (
          <li
            key={`t${i}`}
            data-testid="chat-action-trade-rejected"
            className="flex items-start gap-1.5 rounded-[3px] border border-down/30 bg-down/10 px-2 py-1 text-[12px] text-down"
          >
            <span aria-hidden>✕</span>
            <span className="num">
              Rejected: {t.side} {fmtQty(t.quantity)} {t.ticker}
            </span>
          </li>
        ),
      )}
      {watchlist_changes.map((w, i) => (
        <li
          key={`w${i}`}
          data-testid="chat-action-watchlist"
          data-status={w.status}
          className={`flex items-start gap-1.5 rounded-[3px] border px-2 py-1 text-[12px] ${
            w.status === 'executed' ? 'border-blue/30 bg-blue/10 text-blue' : 'border-down/30 bg-down/10 text-down'
          }`}
        >
          <span aria-hidden>{w.status === 'executed' ? '✓' : '✕'}</span>
          <span>
            {w.status === 'executed'
              ? w.action === 'add'
                ? `Added ${w.ticker} to watchlist`
                : `Removed ${w.ticker} from watchlist`
              : `Could not ${w.action} ${w.ticker}`}
          </span>
        </li>
      ))}
      {errors.map((err, i) => (
        <li key={`e${i}`} data-testid="chat-action-error" className="px-0.5 text-[12px] text-down">
          {err}
        </li>
      ))}
    </ul>
  );
}

export function ChatPanel() {
  const { refreshAll } = useData();
  const [collapsed, setCollapsed] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, error, collapsed]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || loading) return;
    setInput('');
    setError(null);
    setMessages((m) => [...m, { id: nextId.current++, role: 'user', content }]);
    setLoading(true);
    try {
      const res = await api.chat(content);
      setMessages((m) => [...m, { id: nextId.current++, role: 'assistant', content: res.message, actions: res.actions }]);
      if (executedTrades(res.actions) || executedWatch(res.actions)) void refreshAll();
    } catch (e) {
      setError(e instanceof ApiError && e.message ? e.message : 'The assistant is unavailable right now — please try again.');
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  return (
    <aside
      data-testid="chat-panel"
      data-collapsed={collapsed}
      className={`flex min-h-0 flex-col rounded-[3px] border border-line bg-panel ${
        collapsed ? 'xl:w-11' : 'min-h-[420px] xl:w-[360px]'
      } xl:h-full`}
    >
      <header className={`flex h-8 shrink-0 items-center justify-between gap-2 px-3 ${collapsed ? '' : 'border-b border-line'}`}>
        {!collapsed && <h2 className="text-[12px] font-medium text-ink-2">AI assistant</h2>}
        {collapsed && <h2 className="text-[12px] font-medium text-ink-2 xl:hidden">AI assistant</h2>}
        <button
          type="button"
          data-testid="chat-toggle"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Open AI assistant' : 'Collapse AI assistant'}
          onClick={() => setCollapsed((c) => !c)}
          className="grid h-5 w-5 place-items-center rounded-[2px] text-[13px] leading-none text-ink-2 hover:bg-line hover:text-ink"
        >
          {collapsed ? '‹' : '›'}
        </button>
      </header>

      {collapsed && (
        <div
          aria-hidden
          className="hidden flex-1 items-center justify-center xl:flex"
          onClick={() => setCollapsed(false)}
        >
          <span className="rotate-180 text-[12px] font-medium tracking-wide text-muted [writing-mode:vertical-rl]">
            AI assistant
          </span>
        </div>
      )}

      <div hidden={collapsed} className="flex min-h-0 flex-1 flex-col">
        <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3" data-testid="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="space-y-3 pt-2 text-[12px] text-muted">
              <p>Ask about your portfolio, or tell me to trade and manage your watchlist.</p>
              <div className="flex flex-col items-start gap-1.5">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="rounded-[3px] border border-line-2 px-2 py-1 text-left text-ink-2 hover:border-blue hover:text-ink"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="flex justify-end">
                <div
                  data-testid="chat-message-user"
                  className="max-w-[88%] whitespace-pre-wrap rounded-[3px] bg-blue/15 px-2.5 py-1.5 text-[13px] leading-snug"
                >
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex">
                <div
                  data-testid="chat-message-assistant"
                  className="max-w-[94%] rounded-[3px] border border-line bg-panel-2 px-2.5 py-1.5 text-[13px] leading-snug"
                >
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  <ActionList actions={m.actions} />
                </div>
              </div>
            ),
          )}

          {loading && (
            <div data-testid="chat-loading" role="status" aria-label="Assistant is thinking" className="flex items-center gap-1 px-1 py-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-accent"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
              <span className="ml-1.5 text-[12px] text-muted">Thinking</span>
            </div>
          )}

          {error && (
            <div
              data-testid="chat-error"
              role="alert"
              className="rounded-[3px] border border-down/40 bg-down/10 px-2.5 py-1.5 text-[12px] text-down"
            >
              {error}
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-line p-2.5">
          <div className="flex items-end gap-2">
            <textarea
              data-testid="chat-input"
              aria-label="Message the AI assistant"
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask FinAlly…"
              className="min-w-0 flex-1 resize-none rounded-[3px] border border-line-2 bg-bg px-2 py-1.5 text-[13px] placeholder:text-muted focus:border-blue"
            />
            <button
              type="button"
              data-testid="chat-send"
              disabled={loading || !input.trim()}
              onClick={() => void send(input)}
              className="rounded-[3px] bg-purple px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-purple-hi disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
