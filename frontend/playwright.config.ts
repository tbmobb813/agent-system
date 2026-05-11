import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:3003',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'pnpm run dev -- --port 3003',
    url: 'http://127.0.0.1:3003',
    // Reusing a stray `next dev` on :3003 (e.g. another clone or wrong cwd) serves HTML that
    // references chunks this build never emitted → 404 on `app-pages-internals.js` and no hydration.
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_DEV_SERVER === '1',
    timeout: 120_000,
  },
})
