import type { Metadata } from 'next'
import Link from 'next/link'
import { Orbitron, Space_Grotesk } from 'next/font/google'
import ThemeSwitcher from '@/components/ThemeSwitcher'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Agent System',
  description: 'Personal AI co-worker dashboard',
}

const displayFont = Orbitron({
  subsets: ['latin'],
  variable: '--font-display',
  weight: ['500', '700'],
})

const bodyFont = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '700'],
})

const navLinks = [
  { href: '/', label: 'Dashboard' },
  { href: '/agent', label: 'Agent' },
  { href: '/history', label: 'History' },
  { href: '/costs', label: 'Costs' },
  { href: '/settings', label: 'Settings' },
  { href: '/documents', label: 'Documents' },
  { href: '/commands', label: 'Commands' },
]

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${bodyFont.variable} min-h-screen font-[var(--font-body)]`}>
        <nav className="app-shell sticky top-0 z-40">
          <div className="mx-auto max-w-6xl px-4 py-3 flex flex-wrap items-center gap-4">
            <span className="brand-title text-sm md:text-base mr-2">AI Agent</span>
            {navLinks.map(link => (
              <Link
                key={link.href}
                href={link.href}
                className="nav-link text-sm"
              >
                {link.label}
              </Link>
            ))}
            <div className="ml-auto">
              <ThemeSwitcher />
            </div>
          </div>
        </nav>
        <main className="app-main mx-auto max-w-6xl px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}
