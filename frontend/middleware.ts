import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const apiKey = process.env.API_KEY
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
