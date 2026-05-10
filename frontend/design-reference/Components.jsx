// Shared primitives — Panel, Eyebrow, Chip, buttons, status text.
// Tiny on purpose — composition over abstraction.

const { useState } = React;

function Panel({ children, soft = false, className = '', style = {}, hover = false }) {
  const cls = 'panel' + (soft ? ' panel-soft' : '') + (className ? ' ' + className : '');
  return (
    <div
      className={cls}
      style={{
        transition: 'transform 150ms var(--ease-out), border-color 150ms var(--ease-out), box-shadow 150ms var(--ease-out)',
        ...style,
      }}
      onMouseEnter={hover ? (e) => {
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.borderColor = 'var(--accent-2)';
      } : undefined}
      onMouseLeave={hover ? (e) => {
        e.currentTarget.style.transform = '';
        e.currentTarget.style.borderColor = '';
      } : undefined}
    >
      {children}
    </div>
  );
}

function Eyebrow({ children, style = {} }) {
  return (
    <p
      className="eyebrow"
      style={{ margin: 0, marginBottom: '0.5rem', ...style }}
    >{children}</p>
  );
}

function SectionTitle({ children, size = '1.5rem', style = {} }) {
  return (
    <h2 className="section-title" style={{ margin: 0, fontSize: size, fontWeight: 700, ...style }}>
      {children}
    </h2>
  );
}

function Chip({ children, style = {} }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        fontFamily: 'var(--font-body)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        color: 'var(--muted)',
        border: '1px solid var(--border)',
        background: 'var(--surface-soft)',
        padding: '4px 8px',
        borderRadius: '6px',
        ...style,
      }}
    >{children}</span>
  );
}

function ButtonAccent({ children, onClick, type = 'button', size = 'sm' }) {
  const pad = size === 'lg' ? '10px 18px' : '8px 14px';
  const fs  = size === 'lg' ? '13px'      : '12px';
  const [pressed, setPressed] = useState(false);
  const [hover, setHover]     = useState(false);
  return (
    <button
      type={type}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPressed(false); }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      style={{
        border: '1px solid var(--accent)',
        background: 'linear-gradient(130deg, var(--accent), color-mix(in oklab, var(--accent), var(--accent-2) 35%))',
        color: '#091017',
        fontWeight: 700,
        padding: pad,
        borderRadius: '8px',
        fontFamily: 'inherit',
        fontSize: fs,
        cursor: 'pointer',
        transform: pressed ? 'translateY(0)' : (hover ? 'translateY(-1px)' : 'none'),
        transition: 'transform 150ms var(--ease-out)',
        boxShadow: hover ? '0 10px 24px rgba(var(--glow), 0.20)' : 'none',
      }}
    >{children}</button>
  );
}

function ButtonGhost({ children, onClick, active = false }) {
  const [hover, setHover] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        border: '1px solid ' + (active || hover ? 'var(--accent)' : 'var(--border)'),
        background: 'var(--surface-soft)',
        color: 'var(--text)',
        fontFamily: 'inherit',
        fontSize: '12px',
        padding: '8px 14px',
        borderRadius: '8px',
        cursor: 'pointer',
        transition: 'all 150ms var(--ease-out)',
        transform: hover ? 'translateY(-1px)' : 'none',
        boxShadow: hover ? '0 10px 24px rgba(var(--glow), 0.20)' : 'none',
      }}
    >{children}</button>
  );
}

function NavLink({ href, label, active, onClick }) {
  return (
    <a
      href={href}
      onClick={(e) => { e.preventDefault(); onClick && onClick(href); }}
      className="nav-link"
      aria-current={active ? 'page' : undefined}
      style={{
        fontFamily: 'var(--font-body)',
        fontSize: '14px',
        textDecoration: 'none',
      }}
    >{label}</a>
  );
}

function StatusDot({ status }) {
  const color =
    status === 'completed' ? 'var(--success)' :
    status === 'running'   ? 'var(--accent-2)' :
    status === 'failed'    ? 'var(--danger)'  :
    status === 'stopped'   ? 'var(--warn)'    :
    'var(--muted)';
  return <span style={{ width: 10, height: 10, borderRadius: 999, background: color, flexShrink: 0 }} />;
}

function StatusText({ status }) {
  const cls =
    status === 'completed' ? 'status-ok' :
    status === 'running'   ? 'status-running' :
    status === 'failed'    ? 'status-danger'  :
    status === 'stopped'   ? 'status-warn'    : '';
  return <span className={cls} style={{ fontWeight: 600, fontSize: '12px' }}>{status}</span>;
}

// Mono code chip — for env vars, model names, single tokens.
function Code({ children, style = {} }) {
  return (
    <code style={{
      fontFamily: 'var(--font-mono)',
      fontSize: '11px',
      color: 'var(--accent-2)',
      background: 'var(--surface-soft)',
      border: '1px solid var(--border)',
      padding: '1px 6px',
      borderRadius: '4px',
      ...style,
    }}>{children}</code>
  );
}

Object.assign(window, {
  Panel, Eyebrow, SectionTitle, Chip, ButtonAccent, ButtonGhost,
  NavLink, StatusDot, StatusText, Code,
});
