import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'

export const metadata: Metadata = {
  title: 'AI Agent System',
  description: 'Personal AI co-worker dashboard',
}

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
      <body className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="border-b border-gray-800 bg-gray-900">
          <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-6">
            <span className="font-bold text-indigo-400 mr-2">AI Agent</span>
            {navLinks.map(link => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-gray-400 hover:text-gray-100 transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}
