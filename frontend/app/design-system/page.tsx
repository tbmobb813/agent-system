import Link from 'next/link'

const previewFiles = [
  'brand-atmosphere.html',
  'brand-mark.html',
  'color-clean-tech.html',
  'color-glow.html',
  'color-neon-command.html',
  'color-retro-grid.html',
  'color-starforge.html',
  'color-status.html',
  'color-surface.html',
  'comp-budget.html',
  'comp-buttons.html',
  'comp-chips.html',
  'comp-codeblock.html',
  'comp-input.html',
  'comp-nav.html',
  'comp-panel.html',
  'comp-statpills.html',
  'spacing-motion.html',
  'spacing-radius.html',
  'spacing-scale.html',
  'spacing-shadows.html',
  'type-body.html',
  'type-display.html',
  'type-eyebrow.html',
  'type-mono.html',
  'type-scale.html',
] as const

const sections = [
  { key: 'brand', title: 'Brand' },
  { key: 'color', title: 'Color' },
  { key: 'comp', title: 'Components' },
  { key: 'spacing', title: 'Spacing & Motion' },
  { key: 'type', title: 'Typography' },
] as const

function titleFromFile(file: string) {
  return file
    .replace('.html', '')
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function DesignSystemPage() {
  return (
    <div className="dr-history-stack">
      <section>
        <p className="eyebrow">Verification</p>
        <h1 className="section-title dr-dashboard-hero-title">ZIP Design System Specimens</h1>
        <p className="dr-history-summary">
          Every panel below is loaded from the original unzipped HTML in
          <code className="dr-code"> /zip-preview/*</code>, using
          <code className="dr-code"> /colors_and_type.css</code> and
          <code className="dr-code"> /assets/*</code> from the same source bundle.
        </p>
      </section>

      <section className="panel p-5">
        <div className="dr-history-controls">
          <Link href="/zip-preview/brand-atmosphere.html" target="_blank" rel="noreferrer" className="btn-ghost dr-btn-ghost">Open sample directly</Link>
          <Link href="/colors_and_type.css" target="_blank" rel="noreferrer" className="btn-ghost dr-btn-ghost">Open source tokens</Link>
          <Link href="/assets/logo-mark.svg" target="_blank" rel="noreferrer" className="btn-ghost dr-btn-ghost">Open logo mark</Link>
        </div>
      </section>

      {sections.map(section => {
        const files = previewFiles.filter(file => file.startsWith(`${section.key}-`))
        if (files.length === 0) return null
        return (
          <section key={section.key} className="dr-history-stack">
            <h2 className="section-title dr-title-22">{section.title}</h2>
            <div className="dr-dashboard-cards-grid">
              {files.map(file => (
                <article key={file} className="panel p-4 dr-panel">
                  <div className="dr-dashboard-section-head">
                    <h3 className="section-title dr-title-16">{titleFromFile(file)}</h3>
                    <Link href={`/zip-preview/${file}`} target="_blank" rel="noreferrer" className="dr-dashboard-link">open</Link>
                  </div>
                  <iframe
                    className="dr-specimen-frame"
                    src={`/zip-preview/${file}`}
                    title={titleFromFile(file)}
                    loading="lazy"
                  />
                </article>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
