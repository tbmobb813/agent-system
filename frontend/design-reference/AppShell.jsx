// AppShell — header chrome with brand, nav, and theme switcher.

const { useState } = React;

function AppShell({ route, onNavigate, theme, onTheme, children }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const navLinks = window.AGENT_DATA.navLinks;

  const themes = [
    { id: 'neon-command', label: 'Neon Command' },
    { id: 'starforge',    label: 'Starforge' },
    { id: 'retro-grid',   label: 'Retro Grid' },
    { id: 'clean-tech',   label: 'Clean Tech' },
  ];

  return (
    <div className="app-shell dr-shell-layout">
      <header className="dr-shell-header">
        <a
          href="/"
          onClick={(e) => { e.preventDefault(); onNavigate('/'); }}
          className="dr-shell-brand-link"
        >
          <img src="../../assets/glyph.svg" width="32" height="32" alt="" />
          <span className="brand-title dr-shell-brand-title">AI AGENT</span>
        </a>

        <nav className="dr-shell-nav">
          {navLinks.map(link => (
            <NavLink key={link.href}
              href={link.href}
              label={link.label}
              active={route === link.href}
              onClick={onNavigate}
            />
          ))}
        </nav>

        <div className="dr-shell-actions">
          <select
            value={theme}
            onChange={(e) => onTheme(e.target.value)}
            className="dr-shell-theme-select"
            aria-label="Theme"
            title="Theme"
          >
            {themes.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>

          <button
            onClick={() => setProfileOpen(o => !o)}
            className="dr-shell-profile-btn"
            title="Operator"
          >OP</button>
        </div>
      </header>

      {children}

      <footer className="dr-shell-footer">
        <span>localhost:3000 · backend connected at :8000</span>
        <span className="dr-shell-health">
          <span className="dr-shell-health-dot" />
          all systems online
        </span>
      </footer>
    </div>
  );
}

Object.assign(window, { AppShell });
