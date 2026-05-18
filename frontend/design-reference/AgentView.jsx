// AgentView — composer + streaming output. Click "Run" to replay the canned
// trace from data.js so the kit feels alive without a backend.

const { useState, useRef, useEffect } = React;

function AgentView({ onNavigate }) {
  const [query, setQuery]   = useState('Search recent papers on speculative decoding and give me the three best');
  const [model, setModel]   = useState('auto');
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [done, setDone]     = useState(null); // {cost, model}
  const timerRef = useRef([]);
  const outRef   = useRef(null);

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
          // Coalesce streaming text into one growing block
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
    { id: 'auto',                            label: 'Auto (cost router)' },
    { id: 'anthropic/claude-3.5-haiku',      label: 'Claude 3.5 Haiku' },
    { id: 'anthropic/claude-sonnet-4',       label: 'Claude Sonnet 4' },
    { id: 'google/gemini-2.5-flash',         label: 'Gemini 2.5 Flash' },
    { id: 'deepseek/deepseek-chat',          label: 'DeepSeek Chat' },
    { id: 'meta-llama/llama-3.1-8b',         label: 'Llama 3.1 8B' },
  ];

  const examples = [
    'Summarize the attached PDF and pull out owners.',
    'Compare GPT-4o and Sonnet 4 on regex generation.',
    'Search recent papers on speculative decoding and give me the three best.',
    'Watch this folder and upload new files to /documents.',
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

      <header>
        <Eyebrow>Agent</Eyebrow>
        <SectionTitle size="32px">Run a task</SectionTitle>
        <p style={{
          fontFamily: 'var(--font-body)', fontSize: '15px', color: 'var(--muted)',
          margin: '8px 0 0', maxWidth: '640px', lineHeight: 1.55,
        }}>
          Output streams over SSE — you’ll see status updates, tool calls, and the
          model’s text token-by-token. Cost lands at the end.
        </p>
      </header>

      <Panel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run(); }}
            placeholder="Ask the agent anything…"
            rows={3}
            style={{
              background: 'var(--bg-elev)',
              color: 'var(--text)',
              fontFamily: 'var(--font-body)',
              fontSize: '14px',
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '12px 14px',
              outline: 'none',
              resize: 'vertical',
              lineHeight: 1.5,
            }}
          />
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              style={{
                height: '38px',
                background: 'var(--bg-elev)',
                color: 'var(--text)',
                fontFamily: 'inherit',
                fontSize: '13px',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                padding: '0 12px',
                cursor: 'pointer',
              }}
            >
              {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
            <span style={{ fontFamily: 'var(--font-body)', fontSize: '11px', color: 'var(--muted)' }}>
              Cmd/Ctrl + Enter to run
            </span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: '10px' }}>
              {running
                ? <ButtonGhost onClick={stop}>Stop</ButtonGhost>
                : <ButtonAccent onClick={run} size="lg">Run</ButtonAccent>}
            </span>
          </div>
          {!running && events.length === 0 && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {examples.map(ex => (
                <button key={ex} onClick={() => setQuery(ex)} style={{
                  background: 'var(--surface-soft)',
                  border: '1px dashed var(--border)',
                  color: 'var(--muted)',
                  fontFamily: 'inherit',
                  fontSize: '12px',
                  padding: '6px 10px',
                  borderRadius: '999px',
                  cursor: 'pointer',
                }}>{ex}</button>
              ))}
            </div>
          )}
        </div>
      </Panel>

      {(running || events.length > 0) && (
        <Panel>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <Eyebrow style={{ marginBottom: 0 }}>{running ? 'Streaming…' : 'Run complete'}</Eyebrow>
            {running && <StreamingDots />}
            {!running && done && (
              <span style={{ display: 'inline-flex', gap: '12px', alignItems: 'center', fontFamily: 'var(--font-body)', fontSize: '12px' }}>
                <Code>{shortModel(done.model)}</Code>
                <span style={{ color: 'var(--muted)' }}>cost: <span style={{ color: 'var(--text)' }}>{formatCost(done.cost)}</span></span>
              </span>
            )}
          </div>
          <div ref={outRef} style={{
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            padding: '14px 16px',
            maxHeight: '320px',
            overflow: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            fontFamily: 'var(--font-body)',
            fontSize: '13px',
            lineHeight: 1.55,
          }}>
            {events.map((ev, i) => <StreamLine key={i} ev={ev} />)}
            {running && <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>▌</span>}
          </div>
        </Panel>
      )}
    </div>
  );
}

function StreamLine({ ev }) {
  if (ev.kind === 'status') {
    return <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.04em' }}>• {ev.text}</span>;
  }
  if (ev.kind === 'tool_call') {
    return (
      <span style={{ display: 'inline-flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <Chip style={{ color: 'var(--accent-2)' }}>TOOL</Chip>
        <Code>{ev.tool}</Code>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>"{ev.input}"</span>
      </span>
    );
  }
  if (ev.kind === 'tool_out') {
    return (
      <span style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
        <span style={{ color: 'var(--success)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>✓</span>
        <Code>{ev.tool}</Code>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>{ev.summary}</span>
      </span>
    );
  }
  if (ev.kind === 'text') {
    return <span style={{ color: 'var(--text)', whiteSpace: 'pre-wrap' }}>{renderMarkdownish(ev.text)}</span>;
  }
  return null;
}

// Tiny **bold** renderer — enough for the canned stream.
function renderMarkdownish(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  return parts.map((p, i) => p.startsWith('**')
    ? <strong key={i} style={{ color: 'var(--text)' }}>{p.slice(2, -2)}</strong>
    : p
  );
}

function StreamingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center', height: '14px' }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 4, height: 4, borderRadius: 999,
          background: 'var(--accent)',
          animation: `pulse 1.2s var(--ease-out) infinite`,
          animationDelay: `${i * 0.15}s`,
        }} />
      ))}
      <style>{`
        @keyframes pulse { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
      `}</style>
    </span>
  );
}

Object.assign(window, { AgentView });
