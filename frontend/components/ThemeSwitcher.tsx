'use client'

import { useEffect, useState } from 'react'

const THEMES = [
  { value: 'neon-command', label: 'Neon Command' },
  { value: 'starforge', label: 'Starforge' },
  { value: 'retro-grid', label: 'Retro Grid' },
  { value: 'clean-tech', label: 'Clean Tech' },
] as const

const DEFAULT_THEME: (typeof THEMES)[number]['value'] = 'neon-command'

const STORAGE_THEME_KEY = 'agent-ui-theme'

function applyTheme(next: (typeof THEMES)[number]['value']) {
  document.documentElement.setAttribute('data-theme', next)
  document.documentElement.setAttribute('data-density', 'comfortable')
  document.documentElement.setAttribute('data-motion', 'cinematic')
  document.documentElement.style.colorScheme = next === 'clean-tech' ? 'light' : 'dark'

  if (document.body) {
    document.body.setAttribute('data-theme', next)
    document.body.setAttribute('data-density', 'comfortable')
    document.body.setAttribute('data-motion', 'cinematic')
  }
}

export default function ThemeSwitcher() {
  const [theme, setTheme] = useState<(typeof THEMES)[number]['value']>(DEFAULT_THEME)
  const isLight = theme === 'clean-tech'

  useEffect(() => {
    const savedTheme = window.localStorage.getItem(STORAGE_THEME_KEY)
    const initialTheme = THEMES.some(t => t.value === savedTheme) ? (savedTheme as (typeof THEMES)[number]['value']) : DEFAULT_THEME
    setTheme(initialTheme)
    applyTheme(initialTheme)
  }, [])

  const onThemeChange = (next: (typeof THEMES)[number]['value']) => {
    setTheme(next)
    applyTheme(next)
    window.localStorage.setItem(STORAGE_THEME_KEY, next)
  }

  const toggleMode = () => {
    onThemeChange(isLight ? 'neon-command' : 'clean-tech')
  }

  return (
    <div className="dr-shell-actions">
      <button
        type="button"
        onClick={toggleMode}
        className="dr-btn-ghost"
        title={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        {isLight ? 'Dark' : 'Light'}
      </button>
      <select
        aria-label="Theme"
        title="Theme"
        value={theme}
        onChange={e => onThemeChange(e.target.value as (typeof THEMES)[number]['value'])}
        className="dr-shell-theme-select"
      >
        {THEMES.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
