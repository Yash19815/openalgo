import { expect, type Page, test } from '@playwright/test'

const current = {
  strategy_version: '3.3.0', confidence_method: 'five-indicator-v2-pinned',
  atr_period: 20, atr_multiplier: 2, crossover_freshness: 2, selection: 'ATM',
  monthly_loss_limit: '2000', monthly_profit_target: null,
}

async function offlineWorkspace(page: Page, legacy: boolean) {
  let configuration = legacy ? { ...current, strategy_version: '3.2.0',
    confidence_method: 'five-indicator-v1', atr_period: 10, atr_multiplier: 3 } : { ...current }
  const writes: { path: string; body: unknown }[] = []
  const json = (body: unknown) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/*', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!['fetch', 'xhr'].includes(request.resourceType()) || /^\/(src|node_modules|@)/.test(path)) return route.fallback()
    if (request.method() !== 'GET') {
      writes.push({ path, body: request.postDataJSON() })
      if (request.method() === 'PUT' && path.endsWith('/configuration')) {
        configuration = request.postDataJSON().configuration
      }
    }
    if (path === '/auth/session-status') return route.fulfill(json({ status: 'success', logged_in: true,
      authenticated: true, broker: 'angel', username: 'offline-test', user: 'offline-test', active_sessions: 1 }))
    if (path === '/auth/csrf-token') return route.fulfill(json({ csrf_token: 'offline-fixture' }))
    if (path.endsWith('/configuration')) return route.fulfill(json({ status: 'success', data: { configuration, revision: 1 } }))
    if (path.endsWith('/status')) return route.fulfill(json({ status: 'success', data: {
      mode: 'PAPER_ONLY', state: 'PAUSED', revision: 1, ready: false, readiness: ['OFFLINE_FIXTURE'],
    } }))
    if (path.startsWith('/api/nifty-algo/')) return route.fulfill(json({ status: 'success', data: {} }))
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
  await page.routeWebSocket(/socket\.io/, socket => socket.close())
  await page.goto('/nifty-algo?view=configuration')
  await expect(page.getByLabel('SuperTrend length')).toBeVisible()
  return writes
}

test('edits and saves both SuperTrend inputs without starting a monitor or trade', async ({ page }) => {
  const writes = await offlineWorkspace(page, false)
  await expect(page.getByLabel('SuperTrend length')).toHaveValue('20')
  await expect(page.getByLabel('SuperTrend factor')).toHaveValue('2')
  await page.getByLabel('SuperTrend length').fill('21')
  await page.getByLabel('SuperTrend factor').fill('2.5')
  await page.getByRole('button', { name: 'Save configuration' }).click()
  await expect(page.getByText('Configuration saved.')).toBeVisible()
  expect(writes).toEqual([{ path: '/api/nifty-algo/configuration', body: {
    revision: 1, configuration: { ...current, atr_period: 21, atr_multiplier: 2.5 },
  } }])
})

test('legacy upgrade requires a review action and a separate save', async ({ page }) => {
  const writes = await offlineWorkspace(page, true)
  await expect(page.getByLabel('SuperTrend length')).toHaveValue('10')
  await page.getByRole('button', { name: 'Review approved 20/2 upgrade' }).click()
  await expect(page.getByLabel('SuperTrend length')).toHaveValue('20')
  await expect(page.getByLabel('SuperTrend factor')).toHaveValue('2')
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Save configuration' }).click()
  await expect(page.getByText('Configuration saved.')).toBeVisible()
  expect(writes).toEqual([{ path: '/api/nifty-algo/configuration', body: { revision: 1, configuration: current } }])
})
