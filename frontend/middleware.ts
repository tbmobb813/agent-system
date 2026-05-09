import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

function unauthorizedResponse() {
  return new NextResponse('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Agent System"' },
  })
}

function decodeBasicAuth(headerValue: string): { user: string; pass: string } | null {
  if (!headerValue.startsWith('Basic ')) return null
  const encoded = headerValue.slice(6).trim()
  if (!encoded) return null
  try {
    const decoded = atob(encoded)
    const sep = decoded.indexOf(':')
    if (sep < 0) return null
    return { user: decoded.slice(0, sep), pass: decoded.slice(sep + 1) }
  } catch {
    return null
  }
}

export function middleware(request: NextRequest) {
  const basicUser = (process.env.FRONTEND_BASIC_AUTH_USER || '').trim()
  const basicPass = (process.env.FRONTEND_BASIC_AUTH_PASSWORD || '').trim()
  const requireProxyAuth = (process.env.FRONTEND_REQUIRE_PROXY_AUTH || '').toLowerCase() === 'true'
  const basicAuthConfigured = basicUser.length > 0 && basicPass.length > 0

  if (requireProxyAuth || basicAuthConfigured) {
    if (!basicAuthConfigured) {
      return new NextResponse('Proxy auth is enabled but credentials are missing', { status: 500 })
    }
    const parsed = decodeBasicAuth(request.headers.get('authorization') || '')
    if (!parsed || parsed.user !== basicUser || parsed.pass !== basicPass) {
      return unauthorizedResponse()
    }
  }

  const apiKey = process.env.BACKEND_API_KEY || process.env.API_KEY
  if (!apiKey) return NextResponse.next()

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('Authorization', `Bearer ${apiKey}`)

  return NextResponse.next({
    request: { headers: requestHeaders },
  })
}

export const config = {
  matcher: '/api/backend/:path*',
}
