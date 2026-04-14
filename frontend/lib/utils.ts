export function formatCost(usd: number): string {
  if (usd < 0.0001) return '<$0.01'
  return `$${usd.toFixed(4)}`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${(seconds / 60).toFixed(1)}m`
}

export function percentColor(percent: number): string {
  if (percent < 50) return 'text-green-400'
  if (percent < 80) return 'text-yellow-400'
  return 'text-red-400'
}
