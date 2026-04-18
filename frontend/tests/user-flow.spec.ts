import { test, expect } from '@playwright/test'

test('full user flow: dashboard to agent execution', async ({ page }) => {
  await page.route('**/api/backend/health', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        timestamp: '2026-04-14T00:00:00Z',
        agent_ready: true,
        cost_tracking: true,
      }),
    })
  })

  await page.route('**/api/backend/status/costs', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        budget: 30,
        spent_month: 2.5,
        spent_today: 0.2,
        remaining: 27.5,
        percent_used: 8.3,
        status: 'ok',
        reset_date: '2026-05-01T00:00:00Z',
      }),
    })
  })

  await page.route('**/api/backend/history?limit=5&offset=0', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        tasks: [
          {
            id: 'task-1',
            query: 'Earlier task',
            cost: 0.01,
          },
        ],
        total: 1,
      }),
    })
  })

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
        metadata: {},
      }),
    })
  })

  const sseBody = [
    'data: {"type":"status","content":"initializing","task_id":"task-999"}',
    'data: {"type":"text_delta","content":"Flow completed."}',
    'data: {"type":"done","cost":0.002,"conversation_id":"conv-999"}',
    '',
  ].join('\n\n')

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

  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Good (morning|afternoon|evening|night)/)
  await page.getByRole('link', { name: /Run Agent/ }).first().click()

  await expect(page).toHaveURL(/\/agent$/)
  await page
    .getByPlaceholder('Message the agent (Enter to send, Shift+Enter for newline)')
    .fill('Run a full flow test')
  await page.getByRole('button', { name: 'Run Agent' }).click()

  await expect(page.getByText('Flow completed.')).toBeVisible()
  await expect(page.getByText('thread: conv-999…')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Copy response' })).toBeVisible()
})