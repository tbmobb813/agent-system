'use client'

import { useState, FormEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next') || '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (res.ok) {
        router.push(next)
        router.refresh()
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.error || 'Invalid credentials')
      }
    } catch {
      setError('Connection error — try again')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg)',
      fontFamily: 'var(--font-body)',
    }}>
      <div style={{
        width: '100%',
        maxWidth: '380px',
        padding: '2.5rem',
        background: 'var(--bg-elev)',
        border: '1px solid color-mix(in oklab, var(--accent), transparent 70%)',
        borderRadius: '12px',
        boxShadow: '0 0 40px color-mix(in oklab, var(--accent), transparent 88%)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.25rem',
            fontWeight: 700,
            color: 'var(--accent)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: '0.4rem',
          }}>
            AI Agent System
          </div>
          <div style={{ color: 'var(--text-muted, #8899aa)', fontSize: '0.85rem' }}>
            Sign in to continue
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #8899aa)', marginBottom: '0.35rem', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Username
            </label>
            <input
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.6rem 0.8rem',
                background: 'var(--surface)',
                border: '1px solid color-mix(in oklab, var(--accent), transparent 70%)',
                borderRadius: '6px',
                color: 'var(--text, #e2e8f0)',
                fontSize: '0.95rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted, #8899aa)', marginBottom: '0.35rem', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.6rem 0.8rem',
                background: 'var(--surface)',
                border: '1px solid color-mix(in oklab, var(--accent), transparent 70%)',
                borderRadius: '6px',
                color: 'var(--text, #e2e8f0)',
                fontSize: '0.95rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {error && (
            <div style={{
              padding: '0.5rem 0.8rem',
              background: 'color-mix(in oklab, var(--danger, #ff4d4f), transparent 80%)',
              border: '1px solid color-mix(in oklab, var(--danger, #ff4d4f), transparent 50%)',
              borderRadius: '6px',
              color: 'var(--danger, #ff4d4f)',
              fontSize: '0.85rem',
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: '0.5rem',
              padding: '0.65rem',
              background: loading
                ? 'color-mix(in oklab, var(--accent), transparent 60%)'
                : 'var(--accent)',
              color: '#000',
              border: 'none',
              borderRadius: '6px',
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.85rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'opacity 0.15s',
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}
