import { NextRequest, NextResponse } from 'next/server'

const SESSION_COOKIE = 'agent-session'
const SESSION_MESSAGE = 'authenticated'

async function computeToken(secret: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  )
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(SESSION_MESSAGE))
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('')
}

export async function POST(request: NextRequest) {
  const { username, password } = await request.json()

  const validUser = (process.env.FRONTEND_BASIC_AUTH_USER || '').trim()
  const validPass = (process.env.FRONTEND_BASIC_AUTH_PASSWORD || '').trim()
  const secret = (process.env.SESSION_SECRET || '').trim()

  if (!validUser || !validPass || !secret) {
    return NextResponse.json({ error: 'Auth not configured' }, { status: 500 })
  }

  if (username !== validUser || password !== validPass) {
    return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 })
  }

  const token = await computeToken(secret)
  const res = NextResponse.json({ ok: true })
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 30, // 30 days
  })
  return res
}
