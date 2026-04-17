'use client'

import { useEffect, useState } from 'react'

const THEMES = [
  { value: 'neon-command', label: 'Neon Command' },
  { value: 'starforge', label: 'Starforge' },
  { value: 'retro-grid', label: 'Retro Grid' },
  { value: 'clean-tech', label: 'Clean Tech' },
] as const

const STORAGE_KEY = 'agent-ui-theme'

export default function ThemeSwitcher() {
  const [theme, setTheme] = useState<(typeof THEMES)[number]['value']>('neon-command')

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    const initial = THEMES.some(t => t.value === saved) ? (saved as (typeof THEMES)[number]['value']) : 'neon-command'
    setTheme(initial)
    document.documentElement.setAttribute('data-theme', initial)
  }, [])

  const onThemeChange = (next: (typeof THEMES)[number]['value']) => {
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    window.localStorage.setItem(STORAGE_KEY, next)
  }

  return (
    <label className="flex items-center gap-2 text-xs text-[color:var(--muted)]">
      <span className="uppercase tracking-[0.18em]">Theme</span>
      <select
        aria-label="Select theme"
        value={theme}
        onChange={e => onThemeChange(e.target.value as (typeof THEMES)[number]['value'])}
        className="h-9 rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-3 text-sm text-[color:var(--text)] outline-none transition-colors focus:border-[color:var(--accent)]"
      >
        {THEMES.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}
