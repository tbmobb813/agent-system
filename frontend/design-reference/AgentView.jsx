// AgentView — composer + streaming output. Click "Run" to replay the canned
// trace from data.js so the kit feels alive without a backend.

const { useState, useRef, useEffect } = React;

function AgentView({ onNavigate }) {
  const [query, setQuery] = useState('Search recent papers on speculative decoding and give me the three best');
  const [model, setModel] = useState('auto');
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(null); // {cost, model}
  const timerRef = useRef([]);
  const outRef = useRef(null);

  const stop = () => {
    timerRef.current.forEach(clearTimeout);
    timerRef.current = [];
    setRunning(false);
  };

  useEffect(() => stop, []);

  useEffect(() => {
    if (outRef.current) outRef.current.scrollTop = outRef.current.scrollHeight;
  }, [events]);

  const run = () => {
    if (!query.trim() || running) return;
    setEvents([]);
    setDone(null);
    setRunning(true);
    let acc = 0;
    window.AGENT_DATA.sampleStream.forEach((ev) => {
      acc += ev.delay;
      const t = setTimeout(() => {
        if (ev.kind === 'done') {
          setRunning(false);
          setDone({ cost: ev.cost, model: ev.model });
          return;
        }
        setEvents(prev => {
          if (ev.kind === 'text' && prev.length && prev[prev.length - 1].kind === 'text') {
            return prev.slice(0, -1).concat({ kind: 'text', text: prev[prev.length - 1].text + ev.text });
          }
          return prev.concat(ev);
        });
      }, acc);
      timerRef.current.push(t);
    });
  };

  const models = [
    { id: 'auto', label: 'Auto (cost router)' },
    { id: 'anthropic/claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
    { id: 'anthropic/claude-sonnet-4', label: 'Claude Sonnet 4' },
    { id: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { id: 'deepseek/deepseek-chat', label: 'DeepSeek Chat' },
    { id: 'meta-llama/llama-3.1-8b', label: 'Llama 3.1 8B' },
  ];

  const examples = [
    'Summarize the attached PDF and pull out owners.',
    'Compare GPT-4o and Sonnet 4 on regex generation.',
    'Search recent papers on speculative decoding and give me the three best.',
    'Watch this folder and upload new files to /documents.',
  ];

  return (
    <div className="dr-agent-container">
      <header>
        <Eyebrow>Agent</Eyebrow>
        <SectionTitle size="32px">Run a task</SectionTitle>
        <p className="dr-agent-summary">
          Output streams over SSE — you’ll see status updates, tool calls, and the
          model’s text token-by-token. Cost lands at the end.
        </p>
      </header>

      <Panel>
        <div className="dr-agent-form-stack">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run(); }}
            placeholder="Ask the agent anything…"
            rows={3}
            className="dr-agent-textarea"
          />
          <div className="dr-agent-controls-row">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="dr-agent-model-select"
              aria-label="Model"
              title="Model"
            >
              {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
            <span className="dr-agent-hint">Cmd/Ctrl + Enter to run</span>
            <span className="dr-agent-controls-actions">
              {running
                ? <ButtonGhost onClick={stop}>Stop</ButtonGhost>
                : <ButtonAccent onClick={run} size="lg">Run</ButtonAccent>}
            </span>
          </div>
          {!running && events.length === 0 && (
            <div className="dr-agent-example-row">
              {examples.map(ex => (
                <button key={ex} onClick={() => setQuery(ex)} className="dr-agent-example-chip">{ex}</button>
              ))}
            </div>
          )}
        </div>
      </Panel>

      {(running || events.length > 0) && (
        <Panel>
          <div className="dr-agent-stream-head">
            <Eyebrow className="dr-eyebrow-inline">{running ? 'Streaming…' : 'Run complete'}</Eyebrow>
            {running && <StreamingDots />}
            {!running && done && (
              <span className="dr-agent-stream-meta">
                <Code>{shortModel(done.model)}</Code>
                <span className="dr-agent-cost-line">cost: <span className="dr-agent-cost-value">{formatCost(done.cost)}</span></span>
              </span>
            )}
          </div>
          <div ref={outRef} className="dr-agent-stream-box">
            {events.map((ev, i) => <StreamLine key={i} ev={ev} />)}
            {running && <span className="dr-agent-cursor">▌</span>}
          </div>
        </Panel>
      )}
    </div>
  );
}

function StreamLine({ ev }) {
  if (ev.kind === 'status') {
    return <span className="dr-stream-status">• {ev.text}</span>;
  }
  if (ev.kind === 'tool_call') {
    return (
      <span className="dr-stream-inline-row dr-stream-inline-wrap">
        <Chip className="dr-chip-tool">TOOL</Chip>
        <Code>{ev.tool}</Code>
        <span className="dr-stream-mono-muted">"{ev.input}"</span>
      </span>
    );
  }
  if (ev.kind === 'tool_out') {
    return (
      <span className="dr-stream-inline-row">
        <span className="dr-stream-success">✓</span>
        <Code>{ev.tool}</Code>
        <span className="dr-stream-mono-muted">{ev.summary}</span>
      </span>
    );
  }
  if (ev.kind === 'text') {
    return <span className="dr-stream-text">{renderMarkdownish(ev.text)}</span>;
  }
  return null;
}

// Tiny **bold** renderer — enough for the canned stream.
function renderMarkdownish(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  return parts.map((p, i) => p.startsWith('**')
    ? <strong key={i} className="dr-stream-strong">{p.slice(2, -2)}</strong>
    : p
  );
}

function StreamingDots() {
  return (
    <span className="dr-streaming-dots" aria-hidden="true">
      {[0, 1, 2].map(i => (
        <span key={i} className="dr-streaming-dot" />
      ))}
    </span>
  );
}

Object.assign(window, { AgentView });
