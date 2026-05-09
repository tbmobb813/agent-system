// Shared primitives — Panel, Eyebrow, Chip, buttons, status text.
// Tiny on purpose — composition over abstraction.

function Panel({ children, soft = false, className = '', hover = false }) {
  const cls = [
    'panel',
    'dr-panel',
    soft ? 'panel-soft' : '',
    hover ? 'dr-panel-hover' : '',
    className,
  ].filter(Boolean).join(' ');

  return <div className={cls}>{children}</div>;
}

function Eyebrow({ children, className = '' }) {
  return <p className={['eyebrow', 'dr-eyebrow', className].filter(Boolean).join(' ')}>{children}</p>;
}

function SectionTitle({ children, size = '1.5rem', className = '' }) {
  const sizeClass = size === '32px' ? 'dr-title-32' : size === '22px' ? 'dr-title-22' : size === '16px' ? 'dr-title-16' : '';
  return <h2 className={['section-title', 'dr-section-title', sizeClass, className].filter(Boolean).join(' ')}>{children}</h2>;
}

function Chip({ children, className = '' }) {
  return <span className={['dr-chip', className].filter(Boolean).join(' ')}>{children}</span>;
}

function ButtonAccent({ children, onClick, type = 'button', size = 'sm' }) {
  return (
    <button
      type={type}
      onClick={onClick}
      className={['dr-btn-accent', size === 'lg' ? 'dr-btn-accent-lg' : ''].filter(Boolean).join(' ')}
    >
      {children}
    </button>
  );
}

function ButtonGhost({ children, onClick, active = false }) {
  return (
    <button type="button" onClick={onClick} className={['dr-btn-ghost', active ? 'is-active' : ''].filter(Boolean).join(' ')}>
      {children}
    </button>
  );
}

function NavLink({ href, label, active, onClick }) {
  return (
    <a
      href={href}
      onClick={(e) => { e.preventDefault(); onClick && onClick(href); }}
      className="nav-link dr-nav-link"
      aria-current={active ? 'page' : undefined}
    >
      {label}
    </a>
  );
}

function StatusDot({ status }) {
  const tone =
    status === 'completed' ? 'ok' :
    status === 'running' ? 'running' :
    status === 'failed' ? 'danger' :
    status === 'stopped' ? 'warn' :
    'muted';
  return <span className={`dr-status-dot dr-status-dot-${tone}`} />;
}

function StatusText({ status }) {
  const cls =
    status === 'completed' ? 'status-ok' :
    status === 'running' ? 'status-running' :
    status === 'failed' ? 'status-danger' :
    status === 'stopped' ? 'status-warn' :
    '';
  return <span className={['dr-status-text', cls].filter(Boolean).join(' ')}>{status}</span>;
}

// Mono code chip — for env vars, model names, single tokens.
function Code({ children, className = '' }) {
  return <code className={['dr-code', className].filter(Boolean).join(' ')}>{children}</code>;
}

Object.assign(window, {
  Panel, Eyebrow, SectionTitle, Chip, ButtonAccent, ButtonGhost,
  NavLink, StatusDot, StatusText, Code,
});
