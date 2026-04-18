import { test, expect } from '@playwright/test'

const settingsBody = JSON.stringify({
  display_name: null,
  preferred_model: null,
  max_monthly_cost: 30,
  enable_notifications: true,
  auto_save_results: true,
  context_window_target_percent: 0.75,
  default_tools: null,
  timezone: 'UTC',
  agent_persona_enabled: true,
  agent_persona_path: 'data/persona',
  metadata: {},
})

test('dashboard renders primary navigation and cards', async ({ page }) => {
  await page.route('**/api/backend/settings', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: settingsBody })
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Good (morning|afternoon|evening|night)/)
  await expect(page.getByText(/Telemetry, budget, and execution history/)).toBeVisible()

  await expect(page.getByRole('navigation').getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible()
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Agent', exact: true })).toBeVisible()

  await expect(page.getByRole('link', { name: /Run Agent/ }).first()).toBeVisible()
})
