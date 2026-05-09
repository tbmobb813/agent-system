import { expect, type Page } from '@playwright/test'

/** Main agent chat composer — stable for E2E (do not key off placeholder copy). */
export function agentMessageInput(page: Page) {
  return page.getByTestId('agent-message-input')
}

export async function fillAgentMessage(page: Page, text: string) {
  const input = agentMessageInput(page)
  await expect(input).toBeEnabled()
  await input.click()
  await input.fill(text)
  await expect(input).toHaveValue(text)
}

/** Transcript lives in a scrollable panel; assert visibility after bringing the row into view. */
export async function expectTranscriptText(page: Page, text: string | RegExp) {
  const loc = page.getByText(text).first()
  await expect(loc).toBeVisible({ timeout: 20_000 })
}
