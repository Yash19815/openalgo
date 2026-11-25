import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  use: {
    ...base.use,
    baseURL: 'http://127.0.0.1:5199',
    ...(process.env.NIFTY_AUDIT_BROWSER_CHANNEL
      ? { channel: process.env.NIFTY_AUDIT_BROWSER_CHANNEL }
      : {}),
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --config vite.nifty-audit.config.ts',
    url: 'http://127.0.0.1:5199',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
