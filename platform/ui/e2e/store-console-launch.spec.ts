import { expect, test } from '@playwright/test'

test('console launch preserves the portal origin and isolates the new tab', async ({
  page,
  context,
}) => {
  const consoleUrl =
    'https://console-20000.apps.fixture.invalid/__platform/start'
  await page.route('**/e2e/console-launch-harness.html', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><title>Console launch fixture</title>',
    }),
  )
  await context.route(consoleUrl, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><title>Console fixture</title>',
    }),
  )
  await page.goto('/e2e/console-launch-harness.html')
  const portalOrigin = new URL(page.url()).origin
  const requestReady = context.waitForEvent(
    'request',
    (request) => request.url() === consoleUrl,
  )
  const popupReady = context.waitForEvent('page')
  await page.evaluate(async (url) => {
    const modulePath = '/src/features/stores/console-launch.ts'
    const { submitConsoleLaunch } = (await import(modulePath)) as {
      submitConsoleLaunch: (url: string, launch: string) => void
    }
    submitConsoleLaunch(url, 'fixture-launch-assertion')
  }, consoleUrl)
  const request = await requestReady
  expect(request.method()).toBe('POST')
  expect(request.headers().origin).toBe(portalOrigin)
  expect(request.headers()['content-type']).toBe(
    'application/x-www-form-urlencoded',
  )
  expect(request.postData()).toBe('launch=fixture-launch-assertion')
  const popup = await popupReady
  await popup.waitForLoadState()
  expect(await popup.evaluate(() => window.opener === null)).toBe(true)
  await expect(page.locator('input[name="launch"]')).toHaveCount(0)
  expect(popup.url()).not.toContain('fixture-launch-assertion')
})
