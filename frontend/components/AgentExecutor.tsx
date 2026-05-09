'use client'

import { useMemo, useCallback } from 'react'
import type { StreamEvent } from '@/lib/hooks'
import {
  EventLine,
  TurnDoneFooter,
  visibleChatEvents,
  splitLeadingPhaseEvents,
  phaseSummaryPreview,
} from './AgentExecutorChat'
import {
  IconPlus,
  IconClock,
  IconPaperclip,
  IconSend,
  IconStop,
} from './Icons'
import {
  AgentActivityStrip,
  QuickActionsMenu,
} from './AgentExecutorUI'
import { useAgentExecutorState } from './useAgentExecutorState'
import {
  buildSuggestionRows,
  parseSlashSuggestContext,
  parseInputTrigger,
  REASONING_SUB_KEYS,
  type SuggestRow,
} from './AgentExecutorSuggestions'

export default function AgentExecutor() {
  const {
    query, setQuery, context, setContext, editLastOpen, setEditLastOpen, showThinkingLive,
    reasoningPhaseOpenByTurn, reasoningEffortForRequest, setReasoningEffortForRequest,
    dismissFeedbackNudge, feedbackDetailsRef, contextPanelRef, queryInputRef,
    toolNames, queryCursor, setQueryCursor, suggestDismissed, setSuggestDismissed, suggestHighlight, setSuggestHighlight,
    quickActionsOpen, setQuickActionsOpen, reasoningArgModal, setReasoningArgModal, helpModalOpen, setHelpModalOpen,
    modelsModalOpen, setModelsModalOpen, modelsModalState, opsModalOpen, setOpsModalOpen, opsPanel,
    quickActionsRef, quickActionsButtonRef,
    events, merged, isRunning, error, conversationId, run, stop, reset, newConversation,
    latestRunCost, lastUserMessage, openOpsPanel, loadModelsForModal, skipReasoningModalSig
  } = useAgentExecutorState()

  const suggestionRows = useMemo(
    () => buildSuggestionRows(query, queryCursor, suggestDismissed, toolNames),
    [query, queryCursor, suggestDismissed, toolNames],
  )

  const reasoningEffortLabel = useMemo(() => 
    reasoningEffortForRequest === undefined ? 'server default' : reasoningEffortForRequest === 'off' ? 'off' : reasoningEffortForRequest, 
  [reasoningEffortForRequest])

  const liveActivitySummary = useMemo(() => {
    // This could also be moved to useAgentExecutorState if preferred
    return '' // Simplified for now, or import deriveLiveActivitySummary
  }, [])

  const commitReasoningArg = useCallback((opt: string, range: { from: number; to: number }) => {
    skipReasoningModalSig.current = null
    setReasoningArgModal(null)
    if (range.from === -1) {
      setSuggestDismissed(true)
      if (opt === 'default' || opt === 'clear' || opt === 'env') setReasoningEffortForRequest(undefined)
      else if (opt === 'off' || opt === 'disable') setReasoningEffortForRequest('off')
      else if (opt !== 'help' && opt !== '?') setReasoningEffortForRequest(opt)
      queueMicrotask(() => queryInputRef.current?.focus())
      return
    }
    const insert = `/reasoning ${opt} `
    setQuery((q) => q.slice(0, range.from) + insert + q.slice(range.to))
    const pos = range.from + insert.length
    queueMicrotask(() => {
      const el = queryInputRef.current
      if (el) { el.focus(); el.setSelectionRange(pos, pos) }
    })
    setQueryCursor(pos)
    setSuggestDismissed(true)
  }, [setReasoningEffortForRequest, setQuery, setQueryCursor, setSuggestDismissed, setReasoningArgModal, skipReasoningModalSig, queryInputRef])

  const handleDownloadThread = useCallback(() => {
    // Implementation details...
  }, [])

  const tryOpenFeedbackPanel = useCallback(() => {
    // Implementation details...
    return false
  }, [])

  const applySuggestionPick = useCallback((row: SuggestRow, cursorPos: number) => {
    const slashSc = parseSlashSuggestContext(query, cursorPos)
    const atTrig = parseInputTrigger(query, cursorPos)
    const focusPos = (pos: number) => { 
      queueMicrotask(() => { 
        const el = queryInputRef.current
        if (el) { el.focus(); el.setSelectionRange(pos, pos) } 
      })
      setQueryCursor(pos)
      setSuggestDismissed(true) 
    }
    if (row.pick.type === 'replace' || row.pick.type === 'replace_then_reasoning_modal') {
      const start = slashSc ? slashSc.start : atTrig?.start
      if (start === undefined) return
      let repl = row.pick.text; if (repl.startsWith('/') && !/\s$/.test(repl)) repl += ' '
      const next = query.slice(0, start) + repl + query.slice(cursorPos)
      setQuery(next)
      const pos = start + repl.length
      focusPos(pos)
      if (row.pick.type === 'replace_then_reasoning_modal') { 
        skipReasoningModalSig.current = null
        setReasoningArgModal({ from: start, to: pos }) 
      }
      return
    }
    if (row.pick.type === 'action_feedback_panel') { tryOpenFeedbackPanel(); return }
    if (row.pick.type === 'action_clear') { reset(); return }
    if (row.pick.type === 'action_new_thread') { newConversation(); return }
    if (row.pick.type === 'action_stop') { void stop(); return }
  }, [query, reset, newConversation, stop, tryOpenFeedbackPanel, setQuery, setQueryCursor, setSuggestDismissed, setReasoningArgModal, skipReasoningModalSig, queryInputRef])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget; const cursor = el.selectionStart ?? query.length; setQueryCursor(cursor)
    const rows = suggestionRows
    if (rows.length > 0 && !isRunning) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSuggestHighlight((h) => (h + 1) % rows.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSuggestHighlight((h) => (h - 1 + rows.length) % rows.length); return }
      if (e.key === 'Tab') { e.preventDefault(); applySuggestionPick(rows[suggestHighlight % rows.length], cursor); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault(); const raw = el.value.trim(); if (!raw || isRunning) return
      run(raw, context.trim() || undefined, conversationId, reasoningEffortForRequest); setQuery('')
    }
  }

  const turnItems = useMemo(() => {
    type TurnItem = { kind: 'turn'; id: number; user?: StreamEvent; events: StreamEvent[] }
    type DividerItem = { kind: 'divider'; event: StreamEvent }
    const items: Array<TurnItem | DividerItem> = []
    let current: TurnItem | null = null
    let nextId = 1
    const flush = () => { if (current && (current.user || current.events.length > 0)) items.push(current); current = null }
    for (const ev of merged) {
      if (ev.type === 'turn_divider') { flush(); items.push({ kind: 'divider', event: ev }); continue }
      if (ev.type === 'user_message') { flush(); current = { kind: 'turn', id: nextId++, user: ev, events: [] }; continue }
      if (!current) current = { kind: 'turn', id: nextId++, events: [] }
      current.events.push(ev)
    }
    flush()
    return items
  }, [merged])

  return (
    <div className="flex flex-col h-full gap-2 min-h-0">
      <div className="flex-1 min-h-0 flex flex-col">
        {merged.length > 0 ? (
          <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-elev)] overflow-hidden font-mono text-sm">
            <div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 relative">
              <div className="space-y-2">
                {turnItems.map((item, i) => {
                  if (item.kind === 'divider') return <EventLine key={`divider-${i}`} event={item.event} />
                  const chatEvents = visibleChatEvents(item.events)
                  const { phase, rest } = splitLeadingPhaseEvents(chatEvents)
                  const turnHasDone = item.events.some(ev => ev.type === 'done')
                  const phaseDetailsOpen = (showThinkingLive && !turnHasDone) || reasoningPhaseOpenByTurn[item.id] === true
                  return (
                    <div key={`turn-${item.id}`} className="space-y-2">
                      {item.user && <EventLine event={item.user} />}
                      {showThinkingLive && phase.length > 0 && (
                        <div className="flex justify-start">
                          <details className="max-w-[min(92%,42rem)] w-full rounded-2xl rounded-bl-md border border-[color:var(--border)] bg-[color:var(--surface-soft)] px-3 py-2 text-sm" open={phaseDetailsOpen}>
                            <summary className="text-muted text-sm cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-start gap-2">
                              <span className="shrink-0 opacity-70">▸</span><span className="truncate min-w-0">{phaseSummaryPreview(phase)}</span>
                            </summary>
                            <div className="mt-2 max-h-48 space-y-1 overflow-y-auto border-t border-[color:var(--border)]/50 pt-2">
                              {phase.map((ev, idx) => <EventLine key={`turn-${item.id}-phase-${idx}`} event={ev} />)}
                            </div>
                          </details>
                        </div>
                      )}
                      {(showThinkingLive && phase.length > 0 ? rest : chatEvents).filter(ev => ev.type !== 'done').map((ev, idx) => <EventLine key={`turn-${item.id}-event-${idx}`} event={ev} />)}
                      {turnHasDone && (
                        <TurnDoneFooter
                          turnId={item.id}
                          events={item.events}
                          isRunning={isRunning}
                          dismissFeedbackNudge={dismissFeedbackNudge}
                          registerFeedbackRef={(el) => {
                            feedbackDetailsRef.current = el
                          }}
                          showThreadDownload={true}
                          threadExportEmpty={false}
                          onDownloadThread={handleDownloadThread}
                          omitDoneCost={false}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            <AgentActivityStrip reasoningEffortLabel={reasoningEffortLabel} liveActivitySummary={liveActivitySummary} isRunning={isRunning} streamEvents={events} latestRunCost={latestRunCost} className="shrink-0" />
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex items-center justify-center text-muted text-sm text-center px-6">Start chatting to see responses here.</div>
        )}
      </div>

      <div className="shrink-0 space-y-3 sticky bottom-0 z-20 bg-[color:var(--bg)]/95 backdrop-blur-sm pt-2 border-t border-[color:var(--border)]">
        <form onSubmit={(e) => e.preventDefault()} className="space-y-2">
          {error ? (
            <p className="text-sm text-[color:var(--danger)]" role="alert">{error}</p>
          ) : null}
          <div className="relative rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-elev)] focus-within:border-[color:var(--accent)] transition-colors">
            <textarea data-testid="agent-message-input" ref={queryInputRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={handleKeyDown} placeholder="Ask anything…" rows={3} disabled={isRunning} className="relative z-10 w-full bg-transparent rounded-t-xl px-4 pt-3 pb-2 text-sm focus:outline-none resize-none disabled:opacity-50" />
            <div className="flex items-center gap-1 px-2 pb-2 pt-1 border-t border-[color:var(--border)]/50">
              <div className="relative" ref={quickActionsRef}>
                <button type="button" ref={quickActionsButtonRef} onClick={() => setQuickActionsOpen(!quickActionsOpen)} className="btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm"><IconPlus /> Actions</button>
                {quickActionsOpen && <QuickActionsMenu isRunning={isRunning} hasMessages={merged.length > 0} hasLastMessage={!!lastUserMessage} reasoningEffortLabel={reasoningEffortLabel} threadExportEmpty={false} onNewConversation={() => { newConversation(); setQuickActionsOpen(false) }} onStop={() => { void stop(); setQuickActionsOpen(false) }} onClear={() => { reset(); setQuickActionsOpen(false) }} onOpenOps={(p) => { openOpsPanel(p); setQuickActionsOpen(false) }} onOpenModels={() => { setModelsModalOpen(true); loadModelsForModal(); setQuickActionsOpen(false) }} onOpenHelp={() => { setHelpModalOpen(true); setQuickActionsOpen(false) }} onOpenReasoningPicker={() => { setSuggestDismissed(true); setReasoningArgModal({ from: -1, to: -1 }); setQuickActionsOpen(false) }} onCopyThread={() => { setQuickActionsOpen(false) }} onDownloadThread={() => { handleDownloadThread(); setQuickActionsOpen(false) }} onFeedback={() => { tryOpenFeedbackPanel(); setQuickActionsOpen(false) }} onEditResend={() => { setEditLastOpen(!editLastOpen); setQuickActionsOpen(false) }} />}
              </div>
              <button type="button" aria-label="Toggle context panel" title="Toggle context panel" onClick={() => { if (contextPanelRef.current) contextPanelRef.current.open = !contextPanelRef.current.open }} className="btn-ghost p-1.5 rounded-lg"><IconPaperclip /></button>
              <div className="flex-1" />
              <button type="button" onClick={() => setReasoningArgModal({ from: -1, to: -1 })} className="btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-muted font-mono"><IconClock /> {reasoningEffortLabel}</button>
              {isRunning ? <button type="button" aria-label="Stop" onClick={() => void stop()} className="btn-ghost text-[color:var(--danger)]"><IconStop /> Stop</button> : <button type="submit" data-testid="agent-send-button" aria-label="Send" onClick={() => { run(query, context || undefined, conversationId, reasoningEffortForRequest); setQuery('') }} className="btn-accent px-3 py-1.5 rounded-lg text-sm"><IconSend /></button>}
            </div>
          </div>
          <details ref={contextPanelRef} className="group rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-soft)]/40 px-3 py-2">
            <summary className="text-xs text-muted cursor-pointer">Optional context</summary>
            <textarea value={context} onChange={e => setContext(e.target.value)} rows={2} className="mt-2 w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none resize-none" />
          </details>
        </form>
      </div>

      {helpModalOpen && <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"><div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full"><h3>Help</h3><button onClick={() => setHelpModalOpen(false)}>Close</button></div></div>}
      {modelsModalOpen && <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"><div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full"><h3>Models</h3><pre className="text-xs">{JSON.stringify(modelsModalState, null, 2)}</pre><button onClick={() => setModelsModalOpen(false)}>Close</button></div></div>}
      {opsModalOpen && <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"><div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-3xl w-full"><h3>Ops: {opsPanel}</h3><button onClick={() => setOpsModalOpen(false)}>Close</button></div></div>}
      {reasoningArgModal && <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"><div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full"><h3>Reasoning</h3><div className="grid grid-cols-2 gap-2">{REASONING_SUB_KEYS.map(opt => <button key={opt} onClick={() => commitReasoningArg(opt, reasoningArgModal)} className="p-2 border rounded">{opt}</button>)}</div><button onClick={() => setReasoningArgModal(null)}>Cancel</button></div></div>}
    </div>
  )
}
