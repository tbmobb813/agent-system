import type { ReactNode } from 'react'
import Image from 'next/image'

type PageHeaderProps = {
  eyebrow?: string
  title: string
  description?: ReactNode
  /** Extra classes on the root `<header>` (spacing overrides, etc.). */
  className?: string
}

/**
 * Compact page title block for inner routes. Dashboard keeps its own hero + nav cards;
 * secondary pages use this so we do not repeat a full “marketing” panel above real content.
 */
export default function PageHeader({ eyebrow, title, description, className = '' }: PageHeaderProps) {
  return (
    <header className={`space-y-2 mb-6 md:mb-8 ${className}`.trim()}>
      <div className="page-header-brand text-xs uppercase tracking-[0.22em] text-muted">
        <Image
          src="/brand/glyph.svg"
          alt=""
          width={12}
          height={12}
          className="page-header-glyph"
        />
        <span>AI Agent</span>
        {eyebrow ? <span className="page-header-eyebrow">{eyebrow}</span> : null}
      </div>
      <h1 className="section-title text-2xl md:text-3xl font-bold">{title}</h1>
      {description ? (
        <div className="text-muted text-sm max-w-2xl leading-relaxed">{description}</div>
      ) : null}
    </header>
  )
}
