'use client'

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
    <nav className="app-shell sticky top-0 z-40" aria-label="Primary">
      <div className="mx-auto max-w-6xl px-4 py-3 flex flex-wrap items-center gap-4">
        <span className="brand-title text-sm md:text-base mr-2">AI Agent</span>
        {navLinks.map(link => {
          const active = linkIsActive(pathname, link.href)
          return (
            <Link
              key={link.href}
              href={link.href}
              className="nav-link text-sm"
              aria-current={active ? 'page' : undefined}
            >
              {link.label}
            </Link>
          )
        })}
        <div className="ml-auto">
          <ThemeSwitcher />
        </div>
      </div>
    </nav>
  )
}
