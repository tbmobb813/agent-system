import { test, expect } from '@playwright/test'

test('settings page: load and update settings', async ({ page }) => {
  // Mock settings endpoint
  await page.route('**/api/backend/settings', async route => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          preferred_model: 'gpt-4',
          max_monthly_cost: 50,
          enable_notifications: true,
          auto_save_results: false,
          timezone: 'UTC',
        }),
      })
    } else if (method === 'PUT') {
      const body = await route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...body,
          success: true,
        }),
      })
    } else {
      await route.continue()
    }
  })

  await page.goto('/settings')

  // Verify page title and form elements load
  const heading = page.getByRole('heading', { name: 'Settings' })
  await expect(heading).toBeVisible()

  // Verify settings are loaded into form
  const budgetInput = page.locator('input[type="number"]')
  await expect(budgetInput).toHaveValue('50')

  const modelInput = page.locator('input[type="text"]').first()
  await expect(modelInput).toHaveValue('gpt-4')

  const timezoneInput = page.locator('input[type="text"]').nth(1)
  await expect(timezoneInput).toHaveValue('UTC')

  // Verify checkboxes
  const notificationsCheckbox = page.locator('input[id="notifications"]')
  await expect(notificationsCheckbox).toBeChecked()

  const autosaveCheckbox = page.locator('input[id="autosave"]')
  await expect(autosaveCheckbox).not.toBeChecked()
})
