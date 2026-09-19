import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import type { ChatResponse } from '@/lib/types';
import { makeData, renderWithData } from '@/test/helpers';
import { ChatPanel } from './ChatPanel';

// A plain function (not vi.fn) drives the mocked API: vitest's spy wrapper reports rejected
// results as unhandled rejections, and rejecting is exactly what the 503 test needs.
const calls: string[] = [];
let impl: (message: string) => Promise<ChatResponse> = async () => ({ message: '', actions: null });
const reply = (r: ChatResponse) => {
  impl = async () => r;
};

vi.mock('@/lib/api', async (orig) => {
  const actual = await orig<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      chat: (m: string) => {
        calls.push(m);
        return impl(m);
      },
    },
  };
});

async function send(text: string) {
  await userEvent.type(screen.getByTestId('chat-input'), text);
  await userEvent.click(screen.getByTestId('chat-send'));
}

describe('ChatPanel', () => {
  beforeEach(() => {
    calls.length = 0;
  });

  it('shows a loading indicator while waiting, then the assistant reply', async () => {
    let resolve!: (r: ChatResponse) => void;
    impl = () => new Promise((r) => (resolve = r));
    renderWithData(<ChatPanel />, makeData());

    await send('hello');
    expect(screen.getByTestId('chat-message-user')).toHaveTextContent('hello');
    expect(screen.getByTestId('chat-loading')).toBeInTheDocument();
    expect(screen.getByTestId('chat-send')).toBeDisabled();

    resolve({ message: 'Mock: hi there', actions: null });
    expect(await screen.findByTestId('chat-message-assistant')).toHaveTextContent('Mock: hi there');
    expect(screen.queryByTestId('chat-loading')).not.toBeInTheDocument();
    expect(calls).toEqual(['hello']);
  });

  it('renders executed trades and watchlist changes inline and refreshes data', async () => {
    reply({
      message: 'Mock: bought AAPL',
      actions: {
        trades: [{ ticker: 'AAPL', side: 'buy', quantity: 5, price: 190.12, status: 'executed' }],
        watchlist_changes: [{ ticker: 'PYPL', action: 'add', status: 'executed' }],
      },
    });
    const data = makeData();
    renderWithData(<ChatPanel />, data);
    await send('buy some apple');

    expect(await screen.findByTestId('chat-action-trade-executed')).toHaveTextContent('Bought 5 AAPL @ $190.12');
    expect(screen.getByTestId('chat-action-watchlist')).toHaveTextContent('Added PYPL to watchlist');
    await waitFor(() => expect(data.refreshAll).toHaveBeenCalled());
  });

  it('renders a rejected trade and its error inline without an HTTP error', async () => {
    reply({
      message: 'Mock: oversized buy',
      actions: {
        trades: [{ ticker: 'AAPL', side: 'buy', quantity: 1000000, price: null, status: 'rejected' }],
        errors: ['Insufficient cash for AAPL buy'],
      },
    });
    const data = makeData();
    renderWithData(<ChatPanel />, data);
    await send('oversized');

    expect(await screen.findByTestId('chat-action-trade-rejected')).toHaveTextContent('Rejected: buy 1,000,000 AAPL');
    expect(screen.getByTestId('chat-action-error')).toHaveTextContent('Insufficient cash for AAPL buy');
    expect(screen.queryByTestId('chat-action-trade-executed')).not.toBeInTheDocument();
    expect(data.refreshAll).not.toHaveBeenCalled();
  });

  it('shows the 503 detail text as an error and keeps the user message', async () => {
    impl = async () => {
      throw new ApiError(503, 'The assistant is unavailable right now — please try again.');
    };
    renderWithData(<ChatPanel />, makeData());
    await send('anything');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent('The assistant is unavailable right now');
    expect(screen.getAllByTestId('chat-message-user')).toHaveLength(1);
    expect(screen.queryByTestId('chat-message-assistant')).not.toBeInTheDocument();
  });

  it('sends on Enter and ignores blank input', async () => {
    reply({ message: 'ok', actions: null });
    renderWithData(<ChatPanel />, makeData());
    await userEvent.type(screen.getByTestId('chat-input'), '   {Enter}');
    expect(calls).toHaveLength(0);
    await userEvent.type(screen.getByTestId('chat-input'), 'ping{Enter}');
    await screen.findByTestId('chat-message-assistant');
    expect(calls).toHaveLength(1);
  });

  it('collapses and expands', async () => {
    renderWithData(<ChatPanel />, makeData());
    expect(screen.getByTestId('chat-input')).toBeVisible();
    await userEvent.click(screen.getByTestId('chat-toggle'));
    expect(screen.getByTestId('chat-panel')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.getByTestId('chat-input')).not.toBeVisible();
    await userEvent.click(screen.getByTestId('chat-toggle'));
    expect(screen.getByTestId('chat-input')).toBeVisible();
  });
});
