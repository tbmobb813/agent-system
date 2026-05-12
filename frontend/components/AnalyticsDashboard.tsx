'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAnalyticsAbTests,
  getAnalyticsAlerts,
  getAnalyticsCostEfficiency,
  getAnalyticsDaily,
  getAnalyticsDecisions,
  getAnalyticsErrors,
  getAnalyticsModels,
  getAnalyticsOverview,
  getAnalyticsSkills,
  getAnalyticsTools,
} from '@/lib/api'
import { formatCost } from '@/lib/utils'

type Overview = {
  budget: number
  spent_month: number
  spent_today: number
  remaining: number
  daily_average: number
  projected_total: number
  percent_used: number
  days_elapsed: number
  days_in_month: number
  is_overspend_risk: boolean
}
type DailyPoint = { date: string; cost: number; calls: number }
type ModelMetric = { model: string; tasks: number; successful: number; success_rate: number; avg_execution_time: number; avg_cost: number; total_cost: number }
type ToolMetric = { tool_name: string; uses: number; unique_tasks: number; total_task_cost: number }
type AlertRow = { type: string; message: string; spent: number; budget: number; created_at: string | null; acknowledged: boolean }
type AlertsPayload = { risk_level: 'ok' | 'medium' | 'high'; projected_total: number; budget: number; delta: number; alerts: AlertRow[] }
type DecisionRow = { decision_point: string; chosen: string; times_chosen: number; avg_confidence: number; successes: number; failures: number }
type EfficiencyModel = { model: string; avg_cost_per_task: number; thumbs_up_rate: number; efficiency_score: number; sample_count: number }
type ErrorPattern = { error_type: string; recovery_strategy: string | null; model_used: string | null; occurrences: number; recovered: number }
type AbTestResult = { task: string; approach_a: Record<string, string>; approach_b: Record<string, string>; result_a: { cost?: number; time_ms?: number; success?: boolean }; result_b: { cost?: number; time_ms?: number; success?: boolean }; winner: string | null; win_reason: string | null; created_at: string | null }
type SkillRow = { task_type: string; skill_name: string; success_rate: number; proficiency_level: string; total_uses: number; required_tools: string[] }

function StatCard({ label, value, hint, hintDanger }: { label: string; value: string; hint?: string; hintDanger?: boolean }) {
  return (
    <div className="panel p-4">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      {hint ? <p className={`text-xs mt-2 ${hintDanger ? 'text-[color:var(--danger)]' : 'text-muted'}`}>{hint}</p> : null}
    </div>
  )
}

function shortModel(model: string) {
  return model.includes('/') ? model.split('/')[1] : model
}

export default function AnalyticsDashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)

  const [overview, setOverview] = useState<Overview | null>(null)
  const [daily, setDaily] = useState<DailyPoint[]>([])
  const [models, setModels] = useState<ModelMetric[]>([])
  const [tools, setTools] = useState<ToolMetric[]>([])
  const [alerts, setAlerts] = useState<AlertsPayload | null>(null)

  const [decisions, setDecisions] = useState<DecisionRow[]>([])
  const [efficiency, setEfficiency] = useState<EfficiencyModel[]>([])
  const [errorPatterns, setErrorPatterns] = useState<ErrorPattern[]>([])
  const [abTests, setAbTests] = useState<AbTestResult[]>([])
  const [skills, setSkills] = useState<SkillRow[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [o, d, m, t, a, dec, eff, err, ab, sk] = await Promise.all([
        getAnalyticsOverview(),
        getAnalyticsDaily(7),
        getAnalyticsModels(30),
        getAnalyticsTools(30),
        getAnalyticsAlerts(30),
        getAnalyticsDecisions(30).catch(() => ({ decisions: [] })),
        getAnalyticsCostEfficiency().catch(() => ({ models: [] })),
        getAnalyticsErrors(30).catch(() => ({ patterns: [] })),
        getAnalyticsAbTests(10).catch(() => ({ tests: [] })),
        getAnalyticsSkills().catch(() => []),
      ])
      setOverview(o as Overview)
      setDaily((Array.isArray(d?.points) ? d.points : []) as DailyPoint[])
      setModels((Array.isArray(m?.metrics) ? m.metrics : []) as ModelMetric[])
      setTools((Array.isArray(t?.tools) ? t.tools : []) as ToolMetric[])
      setAlerts(a as AlertsPayload)
      setDecisions((Array.isArray(dec?.decisions) ? dec.decisions : []) as DecisionRow[])
      setEfficiency((Array.isArray(eff?.models) ? eff.models : []) as EfficiencyModel[])
      setErrorPatterns((Array.isArray(err?.patterns) ? err.patterns : []) as ErrorPattern[])
      setAbTests((Array.isArray(ab?.tests) ? ab.tests : []) as AbTestResult[])
      setSkills((Array.isArray(sk) ? sk : []) as SkillRow[])
      setLastRefreshed(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load analytics data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 300000)
    return () => clearInterval(interval)
  }, [load])

  const maxDaily = useMemo(() => {
    if (!daily.length) return 0
    return Math.max(...daily.map(p => p.cost))
  }, [daily])

  if (loading) return <p className="text-muted">Loading analytics...</p>
  if (error) return (
    <div className="flex items-center gap-3">
      <p className="text-[color:var(--danger)]">Error: {error}</p>
      <button onClick={load} className="btn-ghost px-3 py-1.5 text-sm rounded-lg">Retry</button>
    </div>
  )
  if (!overview) return <p className="text-muted">No analytics data yet.</p>

  const riskColor =
    !alerts ? 'text-muted' :
    alerts.risk_level === 'high' ? 'text-[color:var(--danger)]' :
    alerts.risk_level === 'medium' ? 'text-[color:var(--warn)]' :
    'text-[color:var(--success)]'

  const decisionsByPoint = decisions.reduce<Record<string, DecisionRow[]>>((acc, d) => {
    ;(acc[d.decision_point] ??= []).push(d)
    return acc
  }, {})

  return (
    <div className="space-y-6">

      {/* Cost & Performance */}
      <div className="flex items-center justify-between">
        <h2 className="section-title text-xl font-semibold">Cost & Performance</h2>
        <div className="flex items-center gap-3">
          {lastRefreshed && (
            <span className="text-xs text-muted hidden sm:block">
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
          )}
          <button onClick={load} className="btn-ghost px-3 py-1.5 text-sm rounded-lg">Refresh</button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        <StatCard label="Spent Today" value={formatCost(overview.spent_today)} />
        <StatCard label="Spent This Month" value={formatCost(overview.spent_month)} hint={`${overview.percent_used.toFixed(1)}% of budget`} />
        <StatCard label="Remaining Budget" value={formatCost(overview.remaining)} />
        <StatCard label="Daily Average" value={formatCost(overview.daily_average)} hint={`${overview.days_elapsed}/${overview.days_in_month} days`} />
        <StatCard
          label="Projected Month End"
          value={formatCost(overview.projected_total)}
          hint={overview.is_overspend_risk ? '⚠ Overspend risk' : undefined}
          hintDanger={overview.is_overspend_risk}
        />
      </div>

      <div className="panel p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">7-Day Cost Trend</h3>
          <span className="text-xs text-muted">{formatCost(overview.spent_today)} today · auto-refreshes every 5 min</span>
        </div>
        {!daily.length ? <p className="text-sm text-muted">No daily trend data yet.</p> : (
          <div className="space-y-2">
            {daily.map(point => {
              const width = maxDaily > 0 ? (point.cost / maxDaily) * 100 : 0
              return (
                <div key={point.date} className="grid grid-cols-[96px_1fr_72px] items-center gap-3">
                  <span className="text-xs text-muted">{new Date(point.date).toLocaleDateString()}</span>
                  <progress className="budget-progress" max={100} value={width} />
                  <span className="text-xs text-right">{formatCost(point.cost)}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="panel p-5">
        <h3 className="text-sm font-semibold mb-3">Model Performance (30 Days)</h3>
        {!models.length ? <p className="text-sm text-muted">No model performance data yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted border-b border-[color:var(--border)]">
                  <th className="py-2 pr-3">Model</th><th className="py-2 pr-3">Tasks</th>
                  <th className="py-2 pr-3">Success</th><th className="py-2 pr-3">Avg Time</th>
                  <th className="py-2 pr-3">Avg Cost</th><th className="py-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {models.map(row => (
                  <tr key={row.model} className="border-b border-[color:var(--border)]/60">
                    <td className="py-2 pr-3 font-mono text-xs">{shortModel(row.model)}</td>
                    <td className="py-2 pr-3">{row.tasks}</td>
                    <td className="py-2 pr-3">{row.success_rate.toFixed(1)}%</td>
                    <td className="py-2 pr-3">{row.avg_execution_time.toFixed(2)}s</td>
                    <td className="py-2 pr-3">{formatCost(row.avg_cost)}</td>
                    <td className="py-2">{formatCost(row.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="panel p-5">
          <h3 className="text-sm font-semibold mb-3">Tool Usage (30 Days)</h3>
          {!tools.length ? <p className="text-sm text-muted">No tool call data yet.</p> : (
            <ul className="space-y-2">
              {tools.slice(0, 8).map(tool => (
                <li key={tool.tool_name} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-xs truncate pr-2">{tool.tool_name}</span>
                  <span className="text-muted">{tool.uses} uses • {formatCost(tool.total_task_cost)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel p-5">
          <h3 className="text-sm font-semibold mb-2">Budget Alerts</h3>
          <p className={`text-sm font-semibold mb-2 ${riskColor}`}>Risk: {alerts?.risk_level.toUpperCase() ?? 'UNKNOWN'}</p>
          <p className="text-xs text-muted mb-3">
            Projected {formatCost(alerts?.projected_total ?? overview.projected_total)} against budget {formatCost(alerts?.budget ?? overview.budget)}
          </p>
          {!alerts?.alerts?.length ? <p className="text-sm text-muted">No recorded alert events in the last 30 days.</p> : (
            <ul className="space-y-2 max-h-44 overflow-auto pr-1">
              {alerts.alerts.map((alert, index) => (
                <li key={`${alert.type}-${index}`} className="text-xs border border-[color:var(--border)] rounded-md px-2 py-1.5 bg-[color:var(--surface-soft)]">
                  <p className="font-medium">{alert.type}</p>
                  <p className="text-muted">{alert.message}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Learning Intelligence */}
      <div className="pt-2 space-y-4">
        <h2 className="section-title text-xl font-semibold">Learning Intelligence</h2>

        <div className="panel p-5">
          <h3 className="text-sm font-semibold mb-3">Agent Skills</h3>
          {!skills.length ? <p className="text-sm text-muted">No skills recorded yet — complete more tasks to populate.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-[color:var(--border)]">
                    <th className="py-2 pr-3">Skill</th><th className="py-2 pr-3">Level</th>
                    <th className="py-2 pr-3">Success</th><th className="py-2 pr-3">Uses</th>
                    <th className="py-2">Required Tools</th>
                  </tr>
                </thead>
                <tbody>
                  {skills.map(sk => {
                    const pct = Math.round((sk.success_rate ?? 0) * 100)
                    const lvlColor = sk.proficiency_level === 'expert' ? 'text-[color:var(--success)]' : sk.proficiency_level === 'advanced' ? 'text-[color:var(--accent)]' : 'text-muted'
                    return (
                      <tr key={sk.task_type} className="border-b border-[color:var(--border)]/60">
                        <td className="py-2 pr-3 font-medium">{sk.skill_name}</td>
                        <td className={`py-2 pr-3 text-xs font-semibold uppercase ${lvlColor}`}>{sk.proficiency_level}</td>
                        <td className="py-2 pr-3">
                          <div className="flex items-center gap-2">
                            <progress className="budget-progress w-16" max={100} value={pct} />
                            <span className="text-xs">{pct}%</span>
                          </div>
                        </td>
                        <td className="py-2 pr-3">{sk.total_uses}</td>
                        <td className="py-2 text-xs text-muted">{(sk.required_tools ?? []).join(', ') || '\u2014'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="panel p-5">
            <h3 className="text-sm font-semibold mb-3">Cost Efficiency (Quality / $)</h3>
            {!efficiency.length ? <p className="text-sm text-muted">No efficiency data yet — rate task outputs with thumbs up/down to populate.</p> : (
              <ul className="space-y-3">
                {efficiency.map((m, i) => {
                  const maxEff = efficiency[0].efficiency_score || 1
                  const barPct = Math.round((m.efficiency_score / maxEff) * 100)
                  return (
                    <li key={m.model}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-mono truncate pr-2">{shortModel(m.model)}</span>
                        <span className="text-muted">{m.efficiency_score.toFixed(1)} eff · {formatCost(m.avg_cost_per_task)}/task · {Math.round(m.thumbs_up_rate * 100)}% liked</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <progress className="budget-progress flex-1" max={100} value={barPct} />
                        <span className="text-xs text-muted">#{i + 1}</span>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="panel p-5">
            <h3 className="text-sm font-semibold mb-3">Decision Patterns (30 Days)</h3>
            {!decisions.length ? <p className="text-sm text-muted">No decision data yet.</p> : (
              <div className="space-y-4 max-h-72 overflow-auto pr-1">
                {Object.entries(decisionsByPoint).map(([point, rows]) => (
                  <div key={point}>
                    <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">{point.replace(/_/g, ' ')}</p>
                    <ul className="space-y-1">
                      {rows.map(row => {
                        const total = row.successes + row.failures
                        const sr = total > 0 ? Math.round((row.successes / total) * 100) : 0
                        return (
                          <li key={row.chosen} className="flex items-center justify-between text-xs">
                            <span className="font-mono truncate pr-2">{shortModel(row.chosen)}</span>
                            <span className="text-muted">{row.times_chosen}x · {sr}% success · {Math.round(row.avg_confidence * 100)}% conf</span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="panel p-5">
            <h3 className="text-sm font-semibold mb-3">Error Recovery (30 Days)</h3>
            {!errorPatterns.length ? <p className="text-sm text-muted">No error patterns recorded yet.</p> : (
              <ul className="space-y-2 max-h-60 overflow-auto pr-1">
                {errorPatterns.map((ep, i) => {
                  const recoverPct = ep.occurrences > 0 ? Math.round((ep.recovered / ep.occurrences) * 100) : 0
                  const recoverColor = recoverPct >= 80 ? 'text-[color:var(--success)]' : recoverPct >= 50 ? 'text-[color:var(--warn)]' : 'text-[color:var(--danger)]'
                  return (
                    <li key={i} className="text-xs border border-[color:var(--border)] rounded-md px-3 py-2 bg-[color:var(--surface-soft)]">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="font-medium">{ep.error_type}</span>
                        <span className={recoverColor}>{recoverPct}% recovered</span>
                      </div>
                      <p className="text-muted">
                        {ep.occurrences} occurrence{ep.occurrences !== 1 ? 's' : ''}
                        {ep.recovery_strategy ? ` · ${ep.recovery_strategy}` : ''}
                        {ep.model_used ? ` · ${shortModel(ep.model_used)}` : ''}
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="panel p-5">
            <h3 className="text-sm font-semibold mb-3">A/B Tests</h3>
            {!abTests.length ? <p className="text-sm text-muted">No A/B tests run yet. Trigger one via the API or settings.</p> : (
              <ul className="space-y-3 max-h-60 overflow-auto pr-1">
                {abTests.map((test, i) => {
                  const aModel = shortModel(test.approach_a.model ?? 'A')
                  const bModel = shortModel(test.approach_b.model ?? 'B')
                  const winnerLabel = test.winner === 'a' ? aModel : test.winner === 'b' ? bModel : 'Tie'
                  return (
                    <li key={i} className="text-xs border border-[color:var(--border)] rounded-md px-3 py-2 bg-[color:var(--surface-soft)]">
                      <p className="font-medium mb-1 truncate">{test.task}</p>
                      <div className="flex items-center gap-3 text-muted flex-wrap">
                        <span>{aModel}{test.result_a.cost != null ? ` $${test.result_a.cost.toFixed(4)}` : ''}</span>
                        <span className="text-[color:var(--border)]">vs</span>
                        <span>{bModel}{test.result_b.cost != null ? ` $${test.result_b.cost.toFixed(4)}` : ''}</span>
                        <span className="ml-auto font-semibold text-[color:var(--accent)]">Winner: {winnerLabel}</span>
                      </div>
                      {test.win_reason ? <p className="text-muted mt-0.5">{test.win_reason}</p> : null}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
