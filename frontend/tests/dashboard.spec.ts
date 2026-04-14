import { test, expect } from '@playwright/test'

test('dashboard renders primary navigation and cards', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByText('Your personal AI co-worker')).toBeVisible()

  await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Agent' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Run Agent Execute tasks with real-time streaming output.' })).toBeVisible()
})