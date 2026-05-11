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
    <div className="app-shell" style={{
      maxWidth: '1200px',
      margin: '0 auto',
      padding: '24px clamp(20px, 4vw, 36px) 60px',
      display: 'flex',
      flexDirection: 'column',
      gap: '32px',
      minHeight: '100vh',
    }}>
      <header style={{
        display: 'flex',
        alignItems: 'center',
        gap: '24px',
        flexWrap: 'wrap',
        paddingBottom: '20px',
        borderBottom: '1px solid var(--border)',
      }}>
        <a
          href="/"
          onClick={(e) => { e.preventDefault(); onNavigate('/'); }}
          style={{ display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none' }}
        >
          <img src="../../assets/glyph.svg" width="32" height="32" alt="" />
          <span className="brand-title" style={{ fontSize: '18px' }}>AI AGENT</span>
        </a>

        <nav style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', flex: 1 }}>
          {navLinks.map(link => (
            <NavLink key={link.href}
              href={link.href}
              label={link.label}
              active={route === link.href}
              onClick={onNavigate}
            />
          ))}
        </nav>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select
            value={theme}
            onChange={(e) => onTheme(e.target.value)}
            style={{
              height: '34px',
              background: 'var(--bg-elev)',
              color: 'var(--text)',
              fontFamily: 'inherit',
              fontSize: '12px',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '0 10px',
              cursor: 'pointer',
            }}
          >
            {themes.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>

          <button
            onClick={() => setProfileOpen(o => !o)}
            style={{
              width: '34px', height: '34px',
              borderRadius: '999px',
              border: '1px solid var(--accent)',
              background: 'color-mix(in oklab, var(--accent), transparent 80%)',
              color: 'var(--text)',
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '12px',
              letterSpacing: '0.04em',
              cursor: 'pointer',
            }}
            title="Operator"
          >OP</button>
        </div>
      </header>

      {children}

      <footer style={{
        marginTop: 'auto',
        paddingTop: '24px',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontFamily: 'var(--font-body)',
        fontSize: '11px',
        color: 'var(--muted)',
        flexWrap: 'wrap',
        gap: '12px',
      }}>
        <span>localhost:3000 · backend connected at :8000</span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--success)' }} />
          all systems online
        </span>
      </footer>
    </div>
  );
}

Object.assign(window, { AppShell });
