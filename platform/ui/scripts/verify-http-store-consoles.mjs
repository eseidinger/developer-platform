// Synthetic stdin only; no screenshots, traces, storage-state files or secret diagnostics.
import { chromium } from '@playwright/test'
let input = ''
for await (const part of process.stdin) input += part
const config = JSON.parse(input)
let stage = 'browser-start'
const browser = await chromium.launch({ headless: true })
try {
  for (const [name, provider] of Object.entries(config.providers)) {
    if (name !== 'qdrant') throw Error()
    const context = await browser.newContext({ ignoreHTTPSErrors: true, proxy: { server: config.proxy } })
    await context.route('https://platform.fixture.test/**', route => route.fulfill({ contentType: 'text/html', body: '<html><body>Fixture portal</body></html>' }))
    const page = await context.newPage()
    stage = name + '-anonymous'
    await page.goto(provider.origin + '/')
    if (!(await page.textContent('body')).includes('Open an active console lease')) throw Error()
    stage = name + '-portal-launch'
    await page.goto('https://platform.fixture.test/')
    provider.launch = (await (await context.request.post(config.gateway + '/launch/' + provider.port)).json()).launch
    await page.evaluate(({ origin, launch }) => {
      const form = document.createElement('form'); form.method = 'POST'; form.action = origin + '/__platform/start'
      const value = document.createElement('input'); value.name = 'launch'; value.value = launch; form.append(value)
      document.body.append(form); form.submit()
    }, provider)
    await page.waitForURL('**/dashboard/**')
    stage = name + '-native-login'
    await page.locator('input[type="password"]').fill(provider.connection.QDRANT_API_KEY)
    await page.getByRole('button', { name: 'Apply', exact: true }).click()
    await page.getByText(provider.connection.QDRANT_COLLECTION, { exact: true }).first().waitFor({ timeout: 10000 })
    const checked = await page.evaluate(async connection => {
      const response = await fetch('/collections', { headers: { 'api-key': connection.QDRANT_API_KEY } })
      const result = await response.json()
      return response.status === 200 && result.result.collections.length === 1 && result.result.collections[0].name === connection.QDRANT_COLLECTION
    }, provider.connection)
    if (!checked) throw Error()
    console.log('PASS official Qdrant console native JWT login and scoped collection listing')
    stage = name + '-active-console-revocation'
    await context.request.post(config.gateway + '/expire/' + provider.port)
    const expired = await page.evaluate(async connection => (await fetch('/collections', { headers: { 'api-key': connection.QDRANT_API_KEY } })).status, provider.connection)
    if (expired !== 401) throw Error()
    await page.reload()
    if (!(await page.textContent('body')).includes('Open an active console lease')) throw Error()
    console.log('PASS already-open Qdrant console revocation, cookie/storage cleanup and expired reload denial')
    await context.close()
  }
} catch {
  console.log(stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
