// Mock data for the kit — shaped to match the Next.js types.

const recentTasks = [
  { id: 't_4f9a', query: 'Summarize the Q3 OKRs from this PDF and extract owner names',                status: 'completed', cost: 0.0042, created_at: minutesAgo(5),    model: 'anthropic/claude-3.5-haiku' },
  { id: 't_4f99', query: 'Compare GPT-4o and Sonnet 4 on regex generation \u2014 same prompt twice',          status: 'running',   cost: 0,        created_at: minutesAgo(0),    model: 'anthropic/claude-sonnet-4' },
  { id: 't_4f98', query: 'Write a Python script that watches a folder and uploads new PDFs to /documents', status: 'completed', cost: 0.0029, created_at: minutesAgo(34),   model: 'deepseek/deepseek-chat' },
  { id: 't_4f97', query: 'Search recent papers on speculative decoding and give me the three best',     status: 'completed', cost: 0.0118, created_at: hoursAgo(2),     model: 'google/gemini-2.5-flash' },
  { id: 't_4f96', query: 'Refactor the cost router to log the chosen tier as an SSE event',             status: 'failed',    cost: 0.0061, created_at: hoursAgo(5),     model: 'anthropic/claude-3.5-haiku' },
  { id: 't_4f95', query: 'Draft a Telegram welcome message in the project\u2019s voice',                       status: 'completed', cost: 0.0008, created_at: hoursAgo(9),     model: 'meta-llama/llama-3.1-8b' },
  { id: 't_4f94', query: 'Stop the current run \u2014 it\u2019s in a search loop',                                status: 'stopped',   cost: 0.0017, created_at: daysAgo(1),      model: 'anthropic/claude-3.5-haiku' },
];

const modelBreakdown = {
  'anthropic/claude-3.5-haiku': { cost: 1.84, calls: 142 },
  'deepseek/deepseek-chat':     { cost: 0.41, calls: 89  },
  'google/gemini-2.5-flash':    { cost: 0.78, calls: 31  },
  'anthropic/claude-sonnet-4':  { cost: 1.12, calls:  9  },
  'meta-llama/llama-3.1-8b':    { cost: 0.08, calls: 47  },
};

const budget = {
  budget: 30.0,
  spent_month: 4.23,
  spent_today: 0.47,
  remaining: 25.77,
  percent_used: 14.1,
  status: 'ok',
  reset_date: new Date(Date.now() + 18 * 24 * 60 * 60 * 1000).toISOString(),
};

const navCards = [
  { href: '/agent',     title: 'Run Agent',     description: 'Execute tasks with real-time streaming output.',                          icon: 'CORE', primary: true  },
  { href: '/history',   title: 'History',       description: 'Browse runs, export results, and leave feedback the agent learns from.',  icon: 'LOGS' },
  { href: '/costs',     title: 'Budget',        description: 'Track spending and enforce your monthly cap.',                            icon: 'COST' },
  { href: '/analytics', title: 'Analytics',     description: 'Review trends, model performance, and tool usage.',                       icon: 'DATA' },
  { href: '/documents', title: 'Documents',     description: 'Upload files for the agent to search and use.',                           icon: 'DOCS' },
  { href: '/settings',  title: 'Settings',      description: 'Configure models, tools, and preferences.',                               icon: 'CONF' },
  { href: '/commands',  title: 'Commands',      description: 'CLI shortcuts, Telegram commands, API routes.',                           icon: 'CMD'  },
];

const navLinks = [
  { href: '/',          label: 'Dashboard' },
  { href: '/agent',     label: 'Agent'     },
  { href: '/history',   label: 'History'   },
  { href: '/analytics', label: 'Analytics' },
  { href: '/costs',     label: 'Costs'     },
  { href: '/documents', label: 'Documents' },
  { href: '/settings',  label: 'Settings'  },
  { href: '/commands',  label: 'Commands'  },
];

// Pre-baked streaming sequence the AgentView replays.
const sampleStream = [
  { kind: 'status',    text: 'planning…',                                          delay: 320 },
  { kind: 'tool_call', tool: 'web_search', input: 'speculative decoding 2026',     delay: 700 },
  { kind: 'tool_out',  tool: 'web_search', summary: '12 results',                  delay: 850 },
  { kind: 'status',    text: 'reading top 3 papers…',                              delay: 600 },
  { kind: 'text',      text: 'Three recent papers stand out:\n\n',                 delay: 420 },
  { kind: 'text',      text: '1. **EAGLE-3** \u2014 keeps the tree-attention idea but ',     delay: 240 },
  { kind: 'text',      text: 'drops the draft model in favor of an MLP head ',     delay: 220 },
  { kind: 'text',      text: 'trained on the target\u2019s logits.\n\n',                  delay: 200 },
  { kind: 'text',      text: '2. **Medusa-2** \u2014 multi-head decoder; ',                 delay: 220 },
  { kind: 'text',      text: '~2.4\u00d7 throughput on Llama-3 70B.\n\n',                   delay: 180 },
  { kind: 'text',      text: '3. **Lookahead Decoding** \u2014 no draft model, no fine-tune. ', delay: 220 },
  { kind: 'text',      text: 'Gains depend on the workload.\n\n',                  delay: 200 },
  { kind: 'text',      text: 'Want me to pull the actual numbers from each?',     delay: 220 },
  { kind: 'done',      cost: 0.0118, model: 'google/gemini-2.5-flash',             delay: 0 },
];

// ---- helpers ---------------------------------------------------

function minutesAgo(m) { return new Date(Date.now() - m * 60 * 1000).toISOString(); }
function hoursAgo(h)   { return new Date(Date.now() - h * 60 * 60 * 1000).toISOString(); }
function daysAgo(d)    { return new Date(Date.now() - d * 24 * 60 * 60 * 1000).toISOString(); }

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatCost(n) {
  if (n === 0) return '$0';
  if (n < 0.01) return '$' + n.toFixed(4);
  if (n < 1)    return '$' + n.toFixed(3);
  return '$' + n.toFixed(2);
}

function shortModel(m) { return m.includes('/') ? m.split('/')[1] : m; }

Object.assign(window, {
  AGENT_DATA: { recentTasks, modelBreakdown, budget, navCards, navLinks, sampleStream },
  timeAgo, formatCost, shortModel,
});
