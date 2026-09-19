// Production build is a static export served by FastAPI (no rewrites, no server runtime).
// `next dev` proxies /api/* to the FastAPI backend so the app stays same-origin in development.
const isDev = process.env.NODE_ENV === 'development';
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(isDev ? {} : { output: 'export' }),
  trailingSlash: false,
  images: { unoptimized: true },
  compress: false,
  ...(isDev
    ? {
        async rewrites() {
          return [{ source: '/api/:path*', destination: `${apiTarget}/api/:path*` }];
        },
      }
    : {}),
};

export default nextConfig;
