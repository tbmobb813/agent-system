import type { NextConfig } from 'next'

/** Proxy target for /api/backend/* (server-side). Use service hostname in Docker, localhost locally. */
function backendRewriteBase(): string {
  const raw = (process.env.BACKEND_URL || 'http://127.0.0.1:8000').trim().replace(/\/$/, '')
  return raw || 'http://127.0.0.1:8000'
}

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    const base = backendRewriteBase()
    return [
      {
        source: '/api/backend/:path*',
        destination: `${base}/:path*`,
      },
    ]
  },
}

export default nextConfig
