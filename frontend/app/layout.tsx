import type { Metadata } from 'next'
import Image from 'next/image'
import { Orbitron, Space_Grotesk } from 'next/font/google'
import SiteNav from '@/components/SiteNav'
import './globals.css'
import './kit-styles.css'

export const metadata: Metadata = {
  title: 'AI Agent System',
  description: 'Personal AI co-worker dashboard',
  manifest: '/manifest.json',
  icons: {
    icon: '/glyph.svg',
    apple: '/logo-mark.svg',
  },
  appleWebApp: {
    capable: true,
    title: 'AI Agent',
    statusBarStyle: 'default',
  },
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
    <html lang="en" data-theme="neon-command" data-density="comfortable" data-motion="cinematic">
      <body className={`${displayFont.variable} ${bodyFont.variable} min-h-screen font-[var(--font-body)]`}>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <div className="dr-shell-layout">
          <SiteNav />
          <main id="main-content" className="app-main" tabIndex={-1}>
            {children}
          </main>
          <footer className="dr-shell-footer">
            <span>localhost:3000 · backend connected at :8000</span>
            <span className="dr-shell-health">
              <Image
                src="/logo-mark.svg"
                width={16}
                height={16}
                alt=""
                aria-hidden="true"
                className="dr-shell-logo-mark"
              />
              <span className="dr-shell-health-dot" />
              all systems online
            </span>
          </footer>
        </div>
      </body>
    </html>
  )
}
