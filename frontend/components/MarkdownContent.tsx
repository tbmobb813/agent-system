// Isolated so AgentExecutor can dynamic-import it with ssr:false,
// keeping react-markdown and react-syntax-highlighter out of the SSR bundle.
import { useState, type PropsWithChildren } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism'

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative group mb-2 rounded-lg overflow-hidden border border-[color:var(--border)]">
      <div className="flex items-center justify-between bg-[color:var(--surface-soft)] px-3 py-1.5 border-b border-[color:var(--border)]">
        <span className="text-xs text-muted font-mono">{language || 'code'}</span>
        <button
          type="button"
          onClick={copy}
          className="text-xs text-muted hover:text-[color:var(--text)] transition-colors"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: '0.75rem',
          background: '#1e1e1e',
        }}
        showLineNumbers={code.split('\n').length > 5}
        wrapLongLines={false}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

const mdComponents = {
  p: ({ children }: PropsWithChildren) => (
    <p className="mb-2 last:mb-0 leading-relaxed text-[color:var(--text)]">{children}</p>
  ),
  h1: ({ children }: PropsWithChildren) => (
    <h1 className="text-lg font-bold mt-4 mb-2 text-[color:var(--text)]">{children}</h1>
  ),
  h2: ({ children }: PropsWithChildren) => (
    <h2 className="text-base font-bold mt-3 mb-1 text-[color:var(--text)]">{children}</h2>
  ),
  h3: ({ children }: PropsWithChildren) => (
    <h3 className="text-sm font-semibold mt-2 mb-1 text-[color:var(--text)]">{children}</h3>
  ),
  ul: ({ children }: PropsWithChildren) => (
    <ul className="list-disc list-outside space-y-0.5 mb-2 pl-6 marker:text-[color:var(--muted)] text-[color:var(--text)]">{children}</ul>
  ),
  ol: ({ children }: PropsWithChildren) => (
    <ol className="list-decimal list-outside space-y-0.5 mb-2 pl-6 marker:text-[color:var(--muted)] text-[color:var(--text)]">{children}</ol>
  ),
  li: ({ children }: PropsWithChildren) => (
    <li>{children}</li>
  ),
  code({ inline, className, children }: PropsWithChildren<{ inline?: boolean; className?: string }>) {
    const match = /language-(\w+)/.exec(className || '')
    const code = String(children).replace(/\n$/, '')
    if (!inline && (match || code.includes('\n'))) {
      return <CodeBlock language={match?.[1] ?? ''} code={code} />
    }
    return (
      <code className="bg-[color:var(--surface-soft)] text-[color:var(--accent-2)] px-1 py-0.5 rounded text-xs font-mono border border-[color:var(--border)]">
        {children}
      </code>
    )
  },
  pre({ children }: PropsWithChildren) {
    return <>{children}</>
  },
  blockquote: ({ children }: PropsWithChildren) => (
    <blockquote className="border-l-2 border-[color:var(--accent-2)] pl-3 text-muted italic mb-2">{children}</blockquote>
  ),
  a: ({ href, children }: PropsWithChildren<{ href?: string }>) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[color:var(--accent-2)] underline hover:opacity-90"
    >
      {children}
    </a>
  ),
  table: ({ children }: PropsWithChildren) => (
    <div className="overflow-x-auto mb-2">
      <table className="text-xs border-collapse w-full">{children}</table>
    </div>
  ),
  th: ({ children }: PropsWithChildren) => (
    <th className="border border-[color:var(--border)] px-2 py-1 text-left text-[color:var(--text)] bg-[color:var(--surface-soft)]">{children}</th>
  ),
  td: ({ children }: PropsWithChildren) => (
    <td className="border border-[color:var(--border)] px-2 py-1 text-muted">{children}</td>
  ),
}

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-body text-[color:var(--text)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
