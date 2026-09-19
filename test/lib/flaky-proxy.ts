import http from 'node:http';
import type { AddressInfo } from 'node:net';

export type StreamMode = 'normal' | 'quiet' | 'error500';

const STREAM_PATH = '/api/stream/prices';

interface LiveStream {
  upstream: http.ClientRequest;
  res: http.ServerResponse;
}

/**
 * Tiny reverse proxy in front of the app, used to break the SSE connection realistically (browser-level offline
 * emulation does not cut an already-established EventSource).
 *
 *  - drop():    kill live stream sockets and refuse new ones at the socket level -> EventSource `error`, readyState CONNECTING.
 *  - restore(): accept stream connections again -> EventSource auto-reconnects.
 *  - mode 'quiet':    forward only SSE comments / `retry:` (keepalive), swallow `data:` events (quiet-but-alive stream).
 *  - mode 'error500': answer stream requests with HTTP 500 -> per the EventSource spec this closes it for good (CLOSED).
 * Everything other than the stream is proxied untouched.
 */
export class FlakyProxy {
  mode: StreamMode = 'normal';
  private blocked = false;
  private live = new Set<LiveStream>();

  private constructor(private server: http.Server, private target: URL) {}

  static async start(targetBaseUrl: string): Promise<FlakyProxy> {
    const target = new URL(targetBaseUrl);
    let proxy!: FlakyProxy;
    const server = http.createServer((req, res) => proxy.handle(req, res));
    proxy = new FlakyProxy(server, target);
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    return proxy;
  }

  get url(): string {
    return `http://127.0.0.1:${(this.server.address() as AddressInfo).port}`;
  }

  drop(): void {
    this.blocked = true;
    this.killLive();
  }

  restore(): void {
    this.blocked = false;
    this.mode = 'normal';
  }

  killLive(): void {
    for (const s of this.live) {
      s.upstream.destroy();
      s.res.socket?.destroy();
    }
    this.live.clear();
  }

  async close(): Promise<void> {
    this.killLive();
    this.server.closeAllConnections();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }

  private handle(req: http.IncomingMessage, res: http.ServerResponse): void {
    const isStream = (req.url ?? '').startsWith(STREAM_PATH);

    if (isStream && this.blocked) {
      req.socket.destroy();
      return;
    }
    if (isStream && this.mode === 'error500') {
      res.writeHead(500, { 'content-type': 'text/plain' }).end('proxy: forced 500');
      return;
    }

    const upstream = http.request(
      {
        host: this.target.hostname,
        port: this.target.port || 80,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: this.target.host, 'accept-encoding': 'identity' },
        agent: false,
      },
      (upRes) => {
        res.writeHead(upRes.statusCode ?? 502, upRes.headers);
        res.flushHeaders();
        if (!isStream) {
          upRes.pipe(res);
          return;
        }
        const live: LiveStream = { upstream, res };
        this.live.add(live);
        res.on('close', () => this.live.delete(live));
        let pending = '';
        upRes.setEncoding('utf8');
        upRes.on('data', (chunk: string) => {
          if (this.mode !== 'quiet') {
            res.write(chunk);
            return;
          }
          pending += chunk;
          const blocks = pending.split('\n\n');
          pending = blocks.pop() ?? '';
          for (const block of blocks) {
            if (!/^data:/m.test(block)) res.write(block + '\n\n');
          }
        });
        upRes.on('end', () => res.end());
      },
    );
    upstream.on('error', () => res.destroy());
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
  }
}
