import type { Metadata } from 'next'
import { Orbitron, Space_Grotesk } from 'next/font/google'
import SiteNav from '@/components/SiteNav'
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${bodyFont.variable} min-h-screen font-[var(--font-body)]`}>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <SiteNav />
        <main id="main-content" className="app-main mx-auto max-w-6xl px-4 py-8" tabIndex={-1}>
          {children}
        </main>
      </body>
    </html>
  )
}
