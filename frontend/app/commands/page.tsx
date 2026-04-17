'use client'

import { useState } from 'react'

type Section = {
  title: string
  rows: { cell1: string; cell2: string; code?: boolean }[]
}

const sections: Section[] = [
  {
    title: 'Terminal — One-Word CLI (from anywhere)',
    rows: [
      { cell1: 'agent', cell2: 'Start everything', code: true },
      { cell1: 'agent stop', cell2: 'Stop everything', code: true },
      { cell1: 'agent status', cell2: 'Check what\'s running', code: true },
      { cell1: 'agent logs', cell2: 'Tail backend logs', code: true },
      { cell1: 'agent logs frontend', cell2: 'Tail frontend logs', code: true },
      { cell1: 'agent logs telegram', cell2: 'Tail Telegram bot logs', code: true },
    ],
  },
  {
    title: 'Web UI Pages',
    rows: [
      { cell1: 'http://localhost:3003/agent', cell2: 'Run the agent', code: true },
      { cell1: 'http://localhost:3003/history', cell2: 'Task history', code: true },
      { cell1: 'http://localhost:3003/costs', cell2: 'Budget & costs', code: true },
      { cell1: 'http://localhost:3003/settings', cell2: 'Settings', code: true },
      { cell1: 'http://localhost:3003/commands', cell2: 'This page', code: true },
      { cell1: 'http://localhost:8000/docs', cell2: 'Backend API docs (interactive)', code: true },
    ],
  },
  {
    title: 'Telegram Bot',
    rows: [
      { cell1: '/start', cell2: 'Welcome message', code: true },
      { cell1: '/new', cell2: 'Start a fresh conversation', code: true },
      { cell1: '/ask <question>', cell2: 'Ask the agent anything', code: true },
      { cell1: '/code <task>', cell2: 'Generate or debug code', code: true },
      { cell1: '/analyze <text>', cell2: 'Summarize or analyze text', code: true },
      { cell1: '/status', cell2: 'Budget & usage', code: true },
      { cell1: '/history', cell2: 'Last 5 tasks', code: true },
      { cell1: '/help', cell2: 'Full command list', code: true },
      { cell1: 'Any message', cell2: 'Sent directly to agent (no command needed)', code: false },
    ],
  },
  {
    title: 'Model Routing',
    rows: [
      { cell1: 'Greetings / short messages', cell2: 'Llama 3.1 8B — free' },
      { cell1: '"what is...", "define..."', cell2: 'DeepSeek — $0.0001' },
      { cell1: '"write code...", "debug..."', cell2: 'DeepSeek — $0.0001' },
      { cell1: '"research...", "deep dive..."', cell2: 'Gemini 2.5 Flash — $0.001' },
      { cell1: '"analyze...", "compare..."', cell2: 'Claude Haiku — $0.001' },
      { cell1: '"best possible", "use sonnet"', cell2: 'Claude Sonnet 4 — $0.01' },
      { cell1: 'Any query using tools', cell2: 'Claude Haiku — $0.002' },
    ],
  },
  {
    title: 'Backend API (base: http://localhost:8000)',
    rows: [
      { cell1: 'GET /health', cell2: 'Health check (no auth)', code: true },
      { cell1: 'GET /status/costs', cell2: 'Budget and spending', code: true },
      { cell1: 'POST /agent/run', cell2: 'Run agent (sync)', code: true },
      { cell1: 'POST /agent/stream', cell2: 'Run agent (streaming SSE)', code: true },
      { cell1: 'GET /agent/tools', cell2: 'List available tools', code: true },
      { cell1: 'GET /agent/models', cell2: 'List models and routing', code: true },
      { cell1: 'GET /history', cell2: 'Paginated task history', code: true },
      { cell1: 'GET /settings', cell2: 'Get current settings', code: true },
      { cell1: 'POST /settings', cell2: 'Update settings', code: true },
      { cell1: 'GET /memory/search', cell2: 'Search memory', code: true },
      { cell1: 'GET /conversations', cell2: 'List conversations', code: true },
    ],
  },
  {
    title: 'Key Environment Variables (.env)',
    rows: [
      { cell1: 'OPENROUTER_API_KEY', cell2: 'OpenRouter API key (required)', code: true },
      { cell1: 'BACKEND_API_KEY', cell2: 'Master API key for web UI', code: true },
      { cell1: 'TELEGRAM_BOT_TOKEN', cell2: 'Telegram bot token', code: true },
      { cell1: 'TELEGRAM_CHAT_ID', cell2: 'Your chat ID for budget alerts', code: true },
      { cell1: 'OPENROUTER_BUDGET_MONTHLY', cell2: 'Monthly budget in USD (default: 30)', code: true },
      { cell1: 'SEARXNG_URL', cell2: 'SearXNG URL (default: http://localhost:8888)', code: true },
      { cell1: 'E2B_API_KEY', cell2: 'E2B sandbox key for code execution', code: true },
      { cell1: 'DATABASE_URL', cell2: 'PostgreSQL connection string', code: true },
    ],
  },
  {
    title: 'Docker / SearXNG',
    rows: [
      { cell1: 'docker start searxng', cell2: 'Start SearXNG', code: true },
      { cell1: 'docker stop searxng', cell2: 'Stop SearXNG', code: true },
      { cell1: 'docker ps', cell2: 'List running containers', code: true },
      { cell1: 'http://localhost:8888', cell2: 'SearXNG search UI', code: true },
    ],
  },
]

export default function CommandsPage() {
  const [filter, setFilter] = useState('')

  const filtered = filter.trim()
    ? sections.map(s => ({
        ...s,
        rows: s.rows.filter(
          r =>
            r.cell1.toLowerCase().includes(filter.toLowerCase()) ||
            r.cell2.toLowerCase().includes(filter.toLowerCase())
        ),
      })).filter(s => s.rows.length > 0)
    : sections

  return (
    <div className="space-y-6">
      <div className="panel panel-soft p-6 flex items-center justify-between gap-4 flex-wrap">
        <h1 className="section-title text-2xl font-bold">Commands & Reference</h1>
        <input
          type="text"
          placeholder="Filter..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-[color:var(--accent)] w-56"
        />
      </div>

      <div className="space-y-8">
        {filtered.map(section => (
          <div key={section.title}>
            <h2 className="text-sm font-semibold text-[color:var(--accent-2)] uppercase tracking-wider mb-3">
              {section.title}
            </h2>
            <div className="panel rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <tbody>
                  {section.rows.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-[color:var(--border)] last:border-0 hover:bg-[color:var(--surface-soft)] transition-colors"
                    >
                      <td className="px-4 py-3 w-1/2">
                        {row.code !== false ? (
                          <code className="text-[color:var(--accent-2)] bg-[color:var(--surface-soft)] border border-[color:var(--border)] px-1.5 py-0.5 rounded text-xs">
                            {row.cell1}
                          </code>
                        ) : (
                          <span>{row.cell1}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted">{row.cell2}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
