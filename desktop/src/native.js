/**
 * Native desktop helpers — called from the Next.js frontend via window.__native.*
 * Only available when running inside Tauri (window.__TAURI__ is defined).
 */

const isTauri = typeof window !== 'undefined' && '__TAURI__' in window

export async function sendNotification(title, body) {
  if (!isTauri) return
  const { isPermissionGranted, requestPermission, sendNotification } =
    await import('@tauri-apps/plugin-notification')

  let granted = await isPermissionGranted()
  if (!granted) {
    const perm = await requestPermission()
    granted = perm === 'granted'
  }
  if (granted) sendNotification({ title, body })
}

export async function setAutostart(enabled) {
  if (!isTauri) return
  const { enable, disable } = await import('@tauri-apps/plugin-autostart')
  if (enabled) await enable()
  else await disable()
}

export async function isAutostartEnabled() {
  if (!isTauri) return false
  const { isEnabled } = await import('@tauri-apps/plugin-autostart')
  return isEnabled()
}
