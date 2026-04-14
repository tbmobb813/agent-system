// Isolated so AgentExecutor can dynamic-import it with ssr:false,
// keeping react-markdown (ESM-only) out of the SSR bundle entirely.
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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
    <ul className="list-disc list-inside space-y-0.5 mb-2 ml-2">{children}</ul>
  ),
  ol: ({ children }: React.PropsWithChildren) => (
    <ol className="list-decimal list-inside space-y-0.5 mb-2 ml-2">{children}</ol>
  ),
  li: ({ children }: React.PropsWithChildren) => (
    <li className="text-gray-100">{children}</li>
  ),
  code: ({ inline, children }: React.PropsWithChildren<{ inline?: boolean }>) =>
    inline ? (
      <code className="bg-gray-800 text-indigo-300 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
    ) : (
      <code>{children}</code>
    ),
  pre: ({ children }: React.PropsWithChildren) => (
    <pre className="bg-gray-800 rounded-lg p-3 overflow-x-auto text-xs font-mono text-gray-300 mb-2">{children}</pre>
  ),
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
