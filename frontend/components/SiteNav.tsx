'use client'

import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect, useRef } from 'react'
import ThemeSwitcher from '@/components/ThemeSwitcher'

const navLinks = [
  { href: '/', label: 'Dashboard' },
  { href: '/agent', label: 'Agent' },
  { href: '/history', label: 'History' },
  { href: '/projects', label: 'Projects' },
  { href: '/analytics', label: 'Analytics' },
  { href: '/costs', label: 'Costs' },
  { href: '/schedules', label: 'Schedules' },
  { href: '/memory', label: 'Memory' },
  { href: '/documents', label: 'Documents' },
  { href: '/settings', label: 'Settings' },
  { href: '/commands', label: 'Commands' },
] as const

function linkIsActive(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

export default function SiteNav() {
  const pathname = usePathname()
  const [menuOpen, setMenuOpen] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const hamburgerRef = useRef<HTMLButtonElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!menuOpen) return
    function handleClick(e: MouseEvent) {
      if (
        drawerRef.current && !drawerRef.current.contains(e.target as Node) &&
        hamburgerRef.current && !hamburgerRef.current.contains(e.target as Node)
      ) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuOpen])

  // Close on route change
  useEffect(() => { setMenuOpen(false) }, [pathname])

  return (
    <>
      <header className="dr-shell-header" aria-label="Primary">
        <Link href="/" className="dr-shell-brand-link" aria-label="AI Agent dashboard home">
          <Image src="/glyph.svg" width={32} height={32} alt="" aria-hidden="true" priority />
          <span className="brand-title dr-shell-brand-title">AI AGENT</span>
        </Link>

        {/* Desktop nav — hidden on mobile */}
        <nav className="dr-shell-nav">
          {navLinks.map(link => {
            const active = linkIsActive(pathname, link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                className="nav-link dr-nav-link"
                aria-current={active ? 'page' : undefined}
              >
                {link.label}
              </Link>
            )
          })}
        </nav>

        <div className="dr-shell-actions">
          <ThemeSwitcher />
          <button type="button" className="dr-shell-profile-btn" title="Operator">OP</button>
          {/* Hamburger — visible on mobile only */}
          <button
            ref={hamburgerRef}
            type="button"
            className="dr-shell-hamburger"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(v => !v)}
          >
            {menuOpen ? (
              // X icon
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="2" y1="2" x2="16" y2="16" />
                <line x1="16" y1="2" x2="2" y2="16" />
              </svg>
            ) : (
              // Hamburger icon
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="2" y1="4" x2="16" y2="4" />
                <line x1="2" y1="9" x2="16" y2="9" />
                <line x1="2" y1="14" x2="16" y2="14" />
              </svg>
            )}
          </button>
        </div>
      </header>

      {/* Mobile drawer — renders below header, above page content */}
      {menuOpen && (
        <div ref={drawerRef} className="dr-mobile-nav" role="navigation" aria-label="Mobile navigation">
          {navLinks.map(link => {
            const active = linkIsActive(pathname, link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`dr-mobile-nav-link${active ? ' is-active' : ''}`}
                aria-current={active ? 'page' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
