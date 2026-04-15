import { test, expect } from '@playwright/test'

test('agent full flow: submit query, receive stream, and show completion controls', async ({ page }) => {
  const sseBody = [
    'data: {"type":"status","content":"initializing","task_id":"task-123"}',
    'data: {"type":"text_delta","content":"Hello from mocked agent."}',
    'data: {"type":"done","cost":0.0012,"conversation_id":"conv-123"}',
    '',
  ].join('\n')

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
    .getByPlaceholder('What do you want the agent to do? (Ctrl+Enter to run)')
    .fill('Write a short greeting')

  await page.getByRole('button', { name: 'Run Agent' }).click()

  await expect(page.getByText('Hello from mocked agent.')).toBeVisible()
  await expect(page.getByText('Done')).toBeVisible()
  await expect(page.getByText('$0.0012')).toBeVisible()
  await expect(page.getByText('thread: conv-123…')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Copy response' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download .txt' })).toBeVisible()

  await page.getByRole('button', { name: 'Clear' }).click()
  await expect(page.getByText('Hello from mocked agent.')).toHaveCount(0)
})

test('agent flow shows an error when stream request fails', async ({ page }) => {
  await page.route('**/api/backend/agent/stream', async route => {
    await route.abort()
  })

  await page.goto('/agent')

  await page
    .getByPlaceholder('What do you want the agent to do? (Ctrl+Enter to run)')
    .fill('Trigger stream error')

  await page.getByRole('button', { name: 'Run Agent' }).click()

  await expect(page.getByText(/failed to fetch|networkerror|load failed/i)).toBeVisible()
})