import { test, expect } from '@playwright/test'
import { agentMessageInput, expectTranscriptText, fillAgentMessage } from './test-helpers'

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
      body: JSON.stringify({ breakdown: {} }),
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

  const messageInput = agentMessageInput(page)
  await messageInput.click()
  await fillAgentMessage(page, 'Write a short greeting')

  const sendButton = page.getByRole('button', { name: 'Send' })
  await expect(sendButton).toBeEnabled()
  await sendButton.click()

  await expectTranscriptText(page, 'Hello from mocked agent.')
  await expectTranscriptText(page, /✓ Done/)
  await expectTranscriptText(page, /cost:\s*\$0\.0012/)

  const copyReply = page.getByRole('button', { name: 'Copy this reply' })
  await copyReply.scrollIntoViewIfNeeded()
  await expect(copyReply).toBeVisible()
  const downloadThread = page.getByRole('button', { name: 'Download full thread' })
  await downloadThread.scrollIntoViewIfNeeded()
  await expect(downloadThread).toBeVisible()

  await page.getByRole('button', { name: 'Actions' }).click()
  // Menu anchors above the launcher; strict viewport checks can flag it as “outside viewport”.
  await page.getByRole('button', { name: 'Clear thread' }).click({ force: true })
  await expect(page.getByRole('button', { name: 'Actions' })).toBeVisible()
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
      body: JSON.stringify({ breakdown: {} }),
    })
  })

  await page.route('**/api/backend/agent/stream', async route => {
    await route.abort()
  })

  await page.goto('/agent')

  const messageInput = agentMessageInput(page)
  await messageInput.click()
  await fillAgentMessage(page, 'Trigger stream error')

  const sendButton = page.getByRole('button', { name: 'Send' })
  await expect(sendButton).toBeEnabled()
  await sendButton.click()

  await expect(page.getByText(/failed to fetch|networkerror|load failed|stream request failed|unknown error/i).first()).toBeVisible()
})