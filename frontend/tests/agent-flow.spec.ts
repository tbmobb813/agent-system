import { test, expect } from '@playwright/test'

test('agent full flow: submit query, receive stream, and show completion controls', async ({ page }) => {
  await page.route('**/api/backend/settings', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
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
        agent_show_thinking_while_streaming: true,
        metadata: {},
      }),
    })
  })

  const sseBody = [
    'data: {"type":"status","content":"initializing","task_id":"task-123"}',
    'data: {"type":"text_delta","content":"Hello from mocked agent."}',
    'data: {"type":"done","cost":0.0012,"conversation_id":"conv-123","task_id":"task-123"}',
    '',
  ].join('\n\n')

  await page.route('**/api/backend/tools', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tools: [] }),
    })
  })

  await page.route('**/api/backend/status/costs/breakdown', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ by_provider: [], by_model: [], by_day: [] }),
    })
  })

  await page.route('**/api/backend/agent/stream', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sseBody,
      headers: {
        'cache-control': 'no-cache',
      },
    })
  })

  await page.goto('/agent')

  await page
    .getByPlaceholder(/Message —/)
    .fill('Write a short greeting')

  await page.getByPlaceholder(/Message —/).press('Enter')

  await expect(page.getByText('Hello from mocked agent.')).toBeVisible()
  await expect(page.getByText('Done')).toBeVisible()
  await expect(page.getByText('$0.0012')).toBeVisible()
  await expect(page.getByText('thread: conv-123…')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Copy this reply' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download full thread' })).toBeVisible()

  await page.getByRole('button', { name: 'Clear' }).click()
  await expect(page.getByText('Hello from mocked agent.')).toHaveCount(0)
})

test('agent flow shows an error when stream request fails', async ({ page }) => {
  await page.route('**/api/backend/settings', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
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
        agent_show_thinking_while_streaming: true,
        metadata: {},
      }),
    })
  })

  await page.route('**/api/backend/tools', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tools: [] }),
    })
  })

  await page.route('**/api/backend/status/costs/breakdown', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ by_provider: [], by_model: [], by_day: [] }),
    })
  })

  await page.route('**/api/backend/agent/stream', async route => {
    await route.abort()
  })

  await page.goto('/agent')

  await page
    .getByPlaceholder(/Message —/)
    .fill('Trigger stream error')

  await page.getByPlaceholder(/Message —/).press('Enter')

  await expect(page.getByText(/failed to fetch|networkerror|load failed/i)).toBeVisible()
})