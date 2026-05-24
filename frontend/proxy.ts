import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const SESSION_COOKIE = 'agent-session'
const SESSION_MESSAGE = 'authenticated'

// Cache the computed HMAC token — it only changes when SESSION_SECRET changes,
// which requires a process restart anyway.
let _cachedToken: string | null = null
let _cachedSecret: string | null = null

async function computeToken(secret: string): Promise<string> {
  if (_cachedToken !== null && _cachedSecret === secret) return _cachedToken
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  )
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(SESSION_MESSAGE))
  _cachedToken = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('')
  _cachedSecret = secret
  return _cachedToken
}

export async function proxy(request: NextRequest) {
  const requireAuth = (process.env.FRONTEND_REQUIRE_PROXY_AUTH || '').toLowerCase() === 'true'
  const isBackendProxy = request.nextUrl.pathname.startsWith('/api/backend')

  if (requireAuth) {
    const secret = (process.env.SESSION_SECRET || '').trim()
    if (!secret) {
      return new NextResponse('SESSION_SECRET is not set', { status: 500 })
    }
    const expected = await computeToken(secret)
    const cookie = request.cookies.get(SESSION_COOKIE)?.value ?? ''
    if (cookie !== expected) {
      if (isBackendProxy) {
        return new NextResponse('Unauthorized', { status: 401 })
      }
      const loginUrl = new URL('/login', request.url)
      loginUrl.searchParams.set('next', request.nextUrl.pathname)
      return NextResponse.redirect(loginUrl)
    }
  }

  // Only add the backend Authorization header for /api/backend/* requests
  if (!isBackendProxy) return NextResponse.next()

  const apiKey = process.env.BACKEND_API_KEY || process.env.API_KEY
  if (!apiKey) {
    console.warn('[proxy] BACKEND_API_KEY is not set — forwarding request without Authorization header')
    return NextResponse.next()
  }

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('Authorization', `Bearer ${apiKey}`)

  return NextResponse.next({
    request: { headers: requestHeaders },
  })
}

export const config = {
  // Protect all pages and the backend proxy.
  // Exclude: login page, auth API routes, and static assets.
  matcher: [
    '/api/backend/:path*',
    '/((?!login|api/auth|_next/static|_next/image|favicon|logo|glyph|manifest|icons|assets).*)',
  ],
}
