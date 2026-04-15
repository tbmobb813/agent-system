/**
 * Streaming proxy for the FastAPI backend.
 *
 * Next.js `rewrites()` buffers the full response before forwarding, which
 * breaks SSE streaming. This route handler pipes the upstream body directly
 * through to the client, preserving the Content-Type and stream semantics.
 */
import { type NextRequest } from 'next/server'

const BACKEND = process.env.BACKEND_URL?.trim() || 'http://localhost:8000'

// Headers that must not be forwarded to the upstream or back to the client
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
])

async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params
  const url = `${BACKEND}/${path.join('/')}${req.nextUrl.search}`

  const forwardHeaders = new Headers()
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      forwardHeaders.set(key, value)
    }
  })

  const hasBody = req.method !== 'GET' && req.method !== 'HEAD'

  const upstream = await fetch(url, {
    method: req.method,
    headers: forwardHeaders,
    body: hasBody ? req.body : undefined,
    // Required for streaming request bodies in Node.js fetch
    // @ts-expect-error - duplex not in TS types yet
    duplex: 'half',
  })

  const responseHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      responseHeaders.set(key, value)
    }
  })

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export const GET    = proxy
export const POST   = proxy
export const PUT    = proxy
export const PATCH  = proxy
export const DELETE = proxy
