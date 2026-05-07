'use client'

import { useEffect, useMemo, useState } from 'react'

const THEMES = [
  { value: 'neon-command', label: 'Neon Command' },
  { value: 'starforge', label: 'Starforge' },
  { value: 'retro-grid', label: 'Retro Grid' },
  { value: 'clean-tech', label: 'Clean Tech' },
] as const

const DENSITY = [
  { value: 'comfortable', label: 'Comfortable' },
  { value: 'compact', label: 'Compact' },
] as const

const MOTION = [
  { value: 'cinematic', label: 'Cinematic' },
  { value: 'minimal', label: 'Minimal' },
] as const

const PRESETS = [
  {
    value: 'streamer',
    label: 'Streamer',
    theme: 'retro-grid',
    density: 'comfortable',
    motion: 'cinematic',
    shortcut: '1',
  },
  {
    value: 'analyst',
    label: 'Analyst',
    theme: 'starforge',
    density: 'compact',
    motion: 'minimal',
    shortcut: '2',
  },
  {
    value: 'focus',
    label: 'Focus',
    theme: 'clean-tech',
    density: 'compact',
    motion: 'minimal',
    shortcut: '3',
  },
] as const

const DEFAULT_THEME: (typeof THEMES)[number]['value'] = 'neon-command'
const DEFAULT_DENSITY: (typeof DENSITY)[number]['value'] = 'comfortable'
const DEFAULT_MOTION: (typeof MOTION)[number]['value'] = 'cinematic'

const STORAGE_THEME_KEY = 'agent-ui-theme'
const STORAGE_DENSITY_KEY = 'agent-ui-density'
const STORAGE_MOTION_KEY = 'agent-ui-motion'

export default function ThemeSwitcher() {
  const [theme, setTheme] = useState<(typeof THEMES)[number]['value']>(DEFAULT_THEME)
  const [density, setDensity] = useState<(typeof DENSITY)[number]['value']>(DEFAULT_DENSITY)
  const [motion, setMotion] = useState<(typeof MOTION)[number]['value']>(DEFAULT_MOTION)

  useEffect(() => {
    const savedTheme = window.localStorage.getItem(STORAGE_THEME_KEY)
    const initialTheme = THEMES.some(t => t.value === savedTheme) ? (savedTheme as (typeof THEMES)[number]['value']) : DEFAULT_THEME
    setTheme(initialTheme)
    document.documentElement.setAttribute('data-theme', initialTheme)

    const savedDensity = window.localStorage.getItem(STORAGE_DENSITY_KEY)
    const initialDensity = DENSITY.some(t => t.value === savedDensity) ? (savedDensity as (typeof DENSITY)[number]['value']) : DEFAULT_DENSITY
    setDensity(initialDensity)
    document.documentElement.setAttribute('data-density', initialDensity)

    const savedMotion = window.localStorage.getItem(STORAGE_MOTION_KEY)
    const initialMotion = MOTION.some(t => t.value === savedMotion) ? (savedMotion as (typeof MOTION)[number]['value']) : DEFAULT_MOTION
    setMotion(initialMotion)
    document.documentElement.setAttribute('data-motion', initialMotion)
  }, [])

  const onThemeChange = (next: (typeof THEMES)[number]['value']) => {
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    window.localStorage.setItem(STORAGE_THEME_KEY, next)
  }

  const onDensityChange = (next: (typeof DENSITY)[number]['value']) => {
    setDensity(next)
    document.documentElement.setAttribute('data-density', next)
    window.localStorage.setItem(STORAGE_DENSITY_KEY, next)
  }

  const onMotionChange = (next: (typeof MOTION)[number]['value']) => {
    setMotion(next)
    document.documentElement.setAttribute('data-motion', next)
    window.localStorage.setItem(STORAGE_MOTION_KEY, next)
  }

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    onThemeChange(preset.theme)
    onDensityChange(preset.density)
    onMotionChange(preset.motion)
  }

  const resetDefaults = () => {
    onThemeChange(DEFAULT_THEME)
    onDensityChange(DEFAULT_DENSITY)
    onMotionChange(DEFAULT_MOTION)
  }

  const activePreset = PRESETS.find(
    preset => preset.theme === theme && preset.density === density && preset.motion === motion
  )?.value

  const activeProfileLabel = useMemo(() => {
    const preset = PRESETS.find(item => item.value === activePreset)
    if (preset) return preset.label
    return 'Custom'
  }, [activePreset])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey) return
      const target = event.target as HTMLElement | null
      if (target) {
        const tag = target.tagName.toLowerCase()
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) return
      }

      const preset = PRESETS.find(item => item.shortcut === event.key)
      if (!preset) return
      event.preventDefault()

      setTheme(preset.theme)
      setDensity(preset.density)
      setMotion(preset.motion)

      document.documentElement.setAttribute('data-theme', preset.theme)
      document.documentElement.setAttribute('data-density', preset.density)
      document.documentElement.setAttribute('data-motion', preset.motion)

      window.localStorage.setItem(STORAGE_THEME_KEY, preset.theme)
      window.localStorage.setItem(STORAGE_DENSITY_KEY, preset.density)
      window.localStorage.setItem(STORAGE_MOTION_KEY, preset.motion)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--muted)]">
      <span className="rounded-md border border-[color:var(--accent)]/50 bg-[color:var(--surface-soft)] px-2 py-1 text-[11px] text-[color:var(--text)]">
        Profile: {activeProfileLabel}
      </span>

      <label className="flex items-center gap-2">
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

      <label className="flex items-center gap-2">
        <span className="uppercase tracking-[0.18em]">Density</span>
        <select
          aria-label="Select density"
          value={density}
          onChange={e => onDensityChange(e.target.value as (typeof DENSITY)[number]['value'])}
          className="h-9 rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-3 text-sm text-[color:var(--text)] outline-none transition-colors focus:border-[color:var(--accent)]"
        >
          {DENSITY.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2">
        <span className="uppercase tracking-[0.18em]">Motion</span>
        <select
          aria-label="Select motion"
          value={motion}
          onChange={e => onMotionChange(e.target.value as (typeof MOTION)[number]['value'])}
          className="h-9 rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-3 text-sm text-[color:var(--text)] outline-none transition-colors focus:border-[color:var(--accent)]"
        >
          {MOTION.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <div className="flex items-center gap-2">
        <span className="uppercase tracking-[0.18em]">Presets</span>
        <div className="flex items-center gap-1.5">
          {PRESETS.map(preset => (
            <button
              key={preset.value}
              type="button"
              onClick={() => applyPreset(preset)}
              className={`rounded-md px-2 py-1 text-[11px] border transition-colors ${
                activePreset === preset.value
                  ? 'border-[color:var(--accent)] bg-[color:var(--surface-soft)] text-[color:var(--text)]'
                  : 'border-[color:var(--border)] text-[color:var(--muted)] hover:text-[color:var(--text)] hover:border-[color:var(--accent-2)]'
              }`}
              title={`${preset.label}: ${preset.theme}, ${preset.density}, ${preset.motion} (Alt+${preset.shortcut})`}
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            onClick={resetDefaults}
            className="rounded-md px-2 py-1 text-[11px] border border-[color:var(--border)] text-[color:var(--muted)] hover:text-[color:var(--text)] hover:border-[color:var(--accent-2)] transition-colors"
            title="Reset to default display profile"
          >
            Reset
          </button>
        </div>
      </div>

      <span className="text-[10px] text-[color:var(--muted)]/85">Shortcuts: Alt+1, Alt+2, Alt+3</span>
    </div>
  )
}
