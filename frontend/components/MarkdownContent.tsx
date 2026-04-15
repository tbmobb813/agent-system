// Isolated so AgentExecutor can dynamic-import it with ssr:false,
// keeping react-markdown and react-syntax-highlighter out of the SSR bundle.
import { useState } from 'react'
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
    <div className="relative group mb-2">
      <div className="flex items-center justify-between bg-gray-800 rounded-t-lg px-3 py-1.5 border-b border-gray-700">
        <span className="text-xs text-gray-400 font-mono">{language || 'code'}</span>
        <button
          onClick={copy}
          className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          borderRadius: '0 0 0.5rem 0.5rem',
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
  p: ({ children }: React.PropsWithChildren) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),
  h1: ({ children }: React.PropsWithChildren) => (
    <h1 className="text-lg font-bold mt-4 mb-2 text-white">{children}</h1>
  ),
  h2: ({ children }: React.PropsWithChildren) => (
    <h2 className="text-base font-bold mt-3 mb-1 text-white">{children}</h2>
  ),
  h3: ({ children }: React.PropsWithChildren) => (
    <h3 className="text-sm font-semibold mt-2 mb-1 text-gray-200">{children}</h3>
  ),
  ul: ({ children }: React.PropsWithChildren) => (
    <ul className="list-disc list-outside space-y-0.5 mb-2 pl-6 marker:text-gray-400">{children}</ul>
  ),
  ol: ({ children }: React.PropsWithChildren) => (
    <ol className="list-decimal list-outside space-y-0.5 mb-2 pl-6 marker:text-gray-400">{children}</ol>
  ),
  li: ({ children }: React.PropsWithChildren) => (
    <li className="text-gray-100">{children}</li>
  ),
  code({ inline, className, children }: React.PropsWithChildren<{ inline?: boolean; className?: string }>) {
    const match = /language-(\w+)/.exec(className || '')
    const code = String(children).replace(/\n$/, '')
    if (!inline && (match || code.includes('\n'))) {
      return <CodeBlock language={match?.[1] ?? ''} code={code} />
    }
    return (
      <code className="bg-gray-800 text-indigo-300 px-1 py-0.5 rounded text-xs font-mono">
        {children}
      </code>
    )
  },
  pre({ children }: React.PropsWithChildren) {
    // react-markdown wraps <code> in <pre> — let CodeBlock handle the styling
    return <>{children}</>
  },
  blockquote: ({ children }: React.PropsWithChildren) => (
    <blockquote className="border-l-2 border-indigo-500 pl-3 text-gray-400 italic mb-2">{children}</blockquote>
  ),
  a: ({ href, children }: React.PropsWithChildren<{ href?: string }>) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-400 underline hover:text-indigo-300">{children}</a>
  ),
  table: ({ children }: React.PropsWithChildren) => (
    <div className="overflow-x-auto mb-2">
      <table className="text-xs border-collapse w-full">{children}</table>
    </div>
  ),
  th: ({ children }: React.PropsWithChildren) => (
    <th className="border border-gray-700 px-2 py-1 text-left text-gray-300 bg-gray-800">{children}</th>
  ),
  td: ({ children }: React.PropsWithChildren) => (
    <td className="border border-gray-700 px-2 py-1 text-gray-400">{children}</td>
  ),
}

export default function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
      {content}
    </ReactMarkdown>
  )
}
