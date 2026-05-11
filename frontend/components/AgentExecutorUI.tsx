import { useMemo, type ReactNode } from 'react'
import { StreamEvent } from '@/lib/hooks'
import { formatCost } from '@/lib/utils'
import {
  IconClipboard,
  IconDownload,
  IconStar,
  IconPlus,
  IconEdit,
  IconTrash,
  IconStop,
  IconTool,
  IconZap,
  IconServer,
  IconHistory,
  IconStats,
  IconCpu,
  IconClock,
  IconHelp,
  IconPlug,
} from './Icons'

export type OpsPanel = 'tools' | 'skills' | 'mcp' | 'stats' | 'history' | 'connectors'

export function ContextMetricsCompact({ events }: { events: StreamEvent[] }) {
  const ctx = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].type === 'context') return events[i]
    }
    return null
  }, [events])
  if (!ctx || ctx.context_percent == null) return null
  const pct = ctx.context_percent
  const color = pct >= 90 ? 'bg-[color:var(--danger)]' : pct >= 70 ? 'bg-[color:var(--warn)]' : 'bg-[color:var(--accent-2)]'
  const label = pct >= 70 ? (pct >= 90 ? 'critical' : 'compacting soon') : 'ok'
  const clamped = Math.max(0, Math.min(pct, 100))
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted tabular-nums">
      <span className="uppercase tracking-wide text-muted shrink-0">Context</span>
      <div className="h-1.5 w-16 sm:w-24 shrink-0 rounded-full border border-[color:var(--border)] bg-[color:var(--bg)] overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${clamped}%` } as React.CSSProperties} />
      </div>
      <span className={pct >= 70 ? 'text-[color:var(--warn)]' : ''}>{pct.toFixed(0)}% — {label}</span>
      {ctx.context_tokens_used != null && <span className="text-muted/85">{ctx.context_tokens_used.toLocaleString()} / {ctx.context_tokens_max?.toLocaleString()} tok</span>}
    </div>
  )
}

export function AgentActivityStrip({ reasoningEffortLabel, liveActivitySummary, isRunning, streamEvents, latestRunCost, className = '' }: { reasoningEffortLabel: string; liveActivitySummary: string | null; isRunning: boolean; streamEvents: StreamEvent[]; latestRunCost: number | null; className?: string }) {
  return (
    <div className={`border-t border-[color:var(--border)] bg-[color:var(--bg-elev)]/95 backdrop-blur-sm px-3 sm:px-4 py-2 font-sans text-[11px] text-muted ${className}`.trim()} role="status" aria-live={isRunning ? 'polite' : undefined}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[color:var(--text)]/90"><span className="uppercase tracking-wide text-[10px] text-muted">Reasoning effort</span>{' · '}<span className="font-mono">{reasoningEffortLabel}</span></span>
        {latestRunCost != null && <span className="text-[color:var(--success)] shrink-0"><span className="uppercase tracking-wide text-[10px] text-muted">Last cost</span>{' · '}<span className="font-mono">{formatCost(latestRunCost)}</span></span>}
        {liveActivitySummary && <span className="min-w-0 flex-1 truncate" title={liveActivitySummary}><span className="uppercase tracking-wide text-[10px] text-muted">Activity</span>{' · '}<span className="text-[color:var(--text)]/85">{liveActivitySummary}</span></span>}
      </div>
      <ContextMetricsCompact events={streamEvents} />
    </div>
  )
}

export type QuickActionsMenuProps = {
  isRunning: boolean
  hasMessages: boolean
  hasLastMessage: boolean
  reasoningEffortLabel: string
  threadExportEmpty: boolean
  onNewConversation: () => void
  onStop: () => void
  onClear: () => void
  onOpenOps: (panel: OpsPanel) => void
  onOpenModels: () => void
  onOpenHelp: () => void
  onOpenReasoningPicker: () => void
  onCopyThread: () => void
  onDownloadThread: () => void
  onFeedback: () => void
  onEditResend: () => void
}

type QuickMenuItem = {
  id: string
  icon: ReactNode
  label: string
  disabled?: boolean
  danger?: boolean
  action: () => void
}

export function QuickActionsMenu({
  isRunning,
  hasMessages,
  hasLastMessage,
  reasoningEffortLabel,
  threadExportEmpty,
  onNewConversation,
  onStop,
  onClear,
  onOpenOps,
  onOpenModels,
  onOpenHelp,
  onOpenReasoningPicker,
  onCopyThread,
  onDownloadThread,
  onFeedback,
  onEditResend,
}: QuickActionsMenuProps) {
  const groups: { label: string; items: QuickMenuItem[] }[] = [
    {
      label: 'Conversation',
      items: [
        { id: 'new', icon: <IconPlus />, label: 'New conversation', disabled: isRunning, action: onNewConversation },
        { id: 'edit', icon: <IconEdit />, label: 'Edit & resend last', disabled: !hasLastMessage || isRunning, action: onEditResend },
        { id: 'clear', icon: <IconTrash />, label: 'Clear thread', disabled: !hasMessages || isRunning, action: onClear },
        { id: 'stop', icon: <IconStop />, label: 'Stop run', disabled: !isRunning, danger: true, action: onStop }
      ]
    },
    {
      label: 'Workspace',
      items: [
        { id: 'tools', icon: <IconTool />, label: 'Tools menu', action: () => onOpenOps('tools') },
        { id: 'skills', icon: <IconZap />, label: 'Skills analytics', action: () => onOpenOps('skills') },
        { id: 'mcp', icon: <IconServer />, label: 'MCP servers', action: () => onOpenOps('mcp') },
        { id: 'connectors', icon: <IconPlug />, label: 'Connectors', action: () => onOpenOps('connectors') },
        { id: 'history', icon: <IconHistory />, label: 'Task history', action: () => onOpenOps('history') },
        { id: 'stats', icon: <IconStats />, label: 'Stats & costs', action: () => onOpenOps('stats') }
      ]
    },
    {
      label: 'Models & Config',
      items: [
        { id: 'models', icon: <IconCpu />, label: 'Agent models', action: onOpenModels },
        { id: 'reasoning', icon: <IconClock />, label: `Reasoning: ${reasoningEffortLabel}`, action: onOpenReasoningPicker }
      ]
    },
    {
      label: 'Export & Feedback',
      items: [
        { id: 'copy', icon: <IconClipboard />, label: 'Copy thread', disabled: threadExportEmpty, action: onCopyThread },
        { id: 'download', icon: <IconDownload />, label: 'Download thread', disabled: threadExportEmpty, action: onDownloadThread },
        { id: 'feedback', icon: <IconStar />, label: 'Rate this reply', action: onFeedback },
        { id: 'help', icon: <IconHelp />, label: 'Help & shortcuts', action: onOpenHelp }
      ]
    }
  ]

  return (
    <div id="quick-actions-popover" className="absolute left-0 bottom-full z-[200] mb-2 w-72 rounded-xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl ring-1 ring-[color:var(--border)]/20 font-sans overflow-hidden">
      {groups.map((group, gi) => (
        <div key={group.label}>
          {gi > 0 && <div className="border-t border-[color:var(--border)]/60" />}
          <div className="px-3 pt-2 pb-0.5"><span className="text-[10px] uppercase tracking-widest text-muted font-semibold">{group.label}</span></div>
          {group.items.map((item) => (
            <button key={item.id} type="button" disabled={item.disabled ?? false} onClick={item.action} className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors disabled:opacity-40 disabled:pointer-events-none ${item.danger ? 'hover:bg-[color:var(--danger)]/10 text-[color:var(--danger)]' : 'hover:bg-[color:var(--surface-soft)] text-[color:var(--text)]'}`}>
              <span className="w-5 shrink-0 flex items-center justify-center">{item.icon}</span>
              <span className="flex-1 min-w-0">
                <span className="block">{item.label}</span>
              </span>
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}
