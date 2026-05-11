'use client'

import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import ThemeSwitcher from '@/components/ThemeSwitcher'

const navLinks = [
  { href: '/', label: 'Dashboard' },
  { href: '/agent', label: 'Agent' },
  { href: '/history', label: 'History' },
  { href: '/analytics', label: 'Analytics' },
  { href: '/costs', label: 'Costs' },
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

  return (
    <header className="dr-shell-header" aria-label="Primary">
      <Link href="/" className="dr-shell-brand-link" aria-label="AI Agent dashboard home">
        <Image src="/glyph.svg" width={32} height={32} alt="" aria-hidden="true" priority />
        <span className="brand-title dr-shell-brand-title">AI AGENT</span>
      </Link>

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
      </div>
    </header>
  )
}
