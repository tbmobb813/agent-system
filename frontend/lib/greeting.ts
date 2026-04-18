/**
 * Time-of-day greeting using the user's IANA timezone (from settings).
 */

/** Current hour (0–23) in an IANA time zone; falls back to the browser's local hour if invalid. */
export function hourInTimeZone(date: Date, timeZone: string): number {
  const tz = (timeZone || 'UTC').trim() || 'UTC'
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      hour: 'numeric',
      hourCycle: 'h23',
    }).formatToParts(date)
    const h = parts.find(p => p.type === 'hour')?.value
    if (h === undefined) return date.getHours()
    const n = Number.parseInt(h, 10)
    return Number.isFinite(n) ? n : date.getHours()
  } catch {
    return date.getHours()
  }
}

export function timeGreetingForHour(hour: number): string {
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  if (hour >= 17 && hour < 22) return 'Good evening'
  return 'Good night'
}

/** e.g. "Good evening, Jason" or "Good afternoon" if no display name. */
export function dashboardWelcomeLine(
  displayName: string | null | undefined,
  timeZone: string,
  at: Date = new Date(),
): string {
  const hour = hourInTimeZone(at, timeZone)
  const greet = timeGreetingForHour(hour)
  const name = (displayName ?? '').trim()
  return name ? `${greet}, ${name}` : greet
}
