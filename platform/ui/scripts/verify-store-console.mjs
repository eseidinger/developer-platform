// Disposable fixture only. Sensitive input travels over stdin; no screenshots/traces.
import { chromium } from '@playwright/test'
let input = ''
for await (const part of process.stdin) input += part
const config = JSON.parse(input)
let stage = 'browser-start'
const browser = await chromium.launch({ headless: true })
try {
  const context = await browser.newContext()
  const page = await context.newPage()
  stage = 'console-login'
  await page.goto(config.base + '/login')
  await page.getByRole('button', { name: /Platform sign-in/ }).click()
  stage = 'identity-login'
  await page.locator('#username').fill(config.username)
  await page.locator('#password').fill(config.password)
  await page.locator('#kc-login').click()
  stage = 'sso-return'
  await page.waitForURL(url => url.pathname.endsWith('/browser/'), { timeout: 30000 })
  stage = 'csrf-bootstrap'
  const utils = await context.request.get(config.base + '/browser/js/utils.js')
  const script = await utils.text()
  const token = script.match(/pgAdmin\['csrf_token'\]\s*=\s*'([^']+)'/)
  if (!token) throw Error()
  const headers = { 'X-pgA-CSRFToken': token[1], Referer: config.base + '/browser/' }
  const call = async (method, path, data) => {
    const response = await context.request.fetch(config.base + path, { method, headers, data })
    return { status: response.status(), body: await response.json() }
  }
  stage = 'scoped-server-registration'
  const c = config.connection
  const created = await call('POST', '/browser/server/obj/1/', { name: 'Expiring fixture', db: c.PGDATABASE,
    host: c.PGHOST, port: Number(c.PGPORT), username: c.PGUSER, role: '', service: '',
    connection_params: { sslmode: 'disable' }, connect_now: false })
  const sid = created.body.node?._id
  if (!sid) throw Error()
  stage = 'scoped-server-connect'
  const path = `/browser/server/connect/1/${sid}`
  const connected = await call('POST', path, { password: c.PGPASSWORD, save_password: true })
  if (connected.body.data?.connected !== true || connected.body.data?.is_password_saved !== false) throw Error()
  stage = 'scoped-query'
  const stats = await call('GET', `/browser/server/stats/1/${sid}`)
  if (stats.status !== 200 || stats.body.success === 0) throw Error()
  stage = 'query-tool-initialize'
  const transaction = Date.now()
  const initialized = await call('POST', `/sqleditor/initialize/sqleditor/${transaction}/1/${sid}/0`,
    { dbname: c.PGDATABASE, password: c.PGPASSWORD })
  if (initialized.status !== 200 || initialized.body.success !== 1) throw Error()
  const query = async sql => {
    const started = await call('POST', `/sqleditor/query_tool/start/${transaction}`,
      { sql, explain_plan: null })
    if (started.status !== 200 || started.body.success !== 1) throw Error()
    for (let attempt = 0; attempt < 30; attempt++) {
      const polled = await call('GET', `/sqleditor/poll/${transaction}`)
      if (polled.body.data?.status === 'Success') return polled.body.data
      if (polled.body.data?.status !== 'Busy') throw Error()
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    throw Error()
  }
  stage = 'query-tool-read'
  if (!JSON.stringify((await query('SELECT 1 AS fixture_value')).result).includes('1')) throw Error()
  stage = 'query-tool-read-only-denial'
  const deniedWrite = await call('POST', `/sqleditor/query_tool/start/${transaction}`,
    { sql: 'CREATE TABLE public.phase7_forbidden(id integer)', explain_plan: null })
  if (deniedWrite.status !== 200 || deniedWrite.body.success !== 1) throw Error()
  let ddlDenied = false
  for (let attempt = 0; attempt < 30; attempt++) {
    const polled = await call('GET', `/sqleditor/poll/${transaction}`)
    if (polled.body.data?.status === 'Busy') {
      await new Promise(resolve => setTimeout(resolve, 100))
      continue
    }
    ddlDenied = polled.status >= 400 || polled.body.success === 0
    break
  }
  if (!ddlDenied) throw Error()
  stage = 'active-query-start'
  const held = await call('POST', `/sqleditor/query_tool/start/${transaction}`,
    { sql: 'SELECT pg_sleep(30)', explain_plan: null })
  if (held.status !== 200 || held.body.success !== 1) throw Error()
  const busy = await call('GET', `/sqleditor/poll/${transaction}`)
  if (busy.body.data?.status !== 'Busy') throw Error()
  stage = 'lease-expiry'
  await context.request.post(config.expireUrl)
  stage = 'active-query-terminated'
  let terminated = false
  for (let attempt = 0; attempt < 100; attempt++) {
    const polled = await call('GET', `/sqleditor/poll/${transaction}`)
    if (polled.body.data?.status === 'Success') throw Error()
    if (polled.status >= 400 || polled.body.success === 0 ||
        (polled.body.data?.status && polled.body.data.status !== 'Busy')) {
      terminated = true
      break
    }
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  if (!terminated) throw Error()
  stage = 'expired-reconnect-denial'
  await call('DELETE', path)
  const expired = await call('POST', path, { password: c.PGPASSWORD })
  if (expired.body.data?.connected === true || (expired.status === 200 && expired.body.success === 1)) throw Error()
  stage = 'different-human-isolation'
  const other = await browser.newContext()
  const otherPage = await other.newPage()
  await otherPage.goto(config.base + '/login')
  await otherPage.getByRole('button', { name: /Platform sign-in/ }).click()
  await otherPage.locator('#username').fill(config.otherUsername)
  await otherPage.locator('#password').fill(config.otherPassword)
  await otherPage.locator('#kc-login').click()
  await otherPage.waitForURL(url => url.pathname.endsWith('/browser/'), { timeout: 30000 })
  const foreign = await other.request.get(config.base + `/browser/server/obj/1/${sid}`)
  const foreignBody = await foreign.json()
  if ((!([400, 403, 404, 410].includes(foreign.status())) && foreignBody.success !== 0)
      || JSON.stringify(foreignBody).includes(c.PGUSER)) throw Error()
  await other.close()
  stage = 'anonymous-denial'
  const anonymous = await browser.newContext()
  const denied = await anonymous.request.get(config.base + `/browser/server/obj/1/${sid}`, { maxRedirects: 0 })
  if (![302, 401, 403].includes(denied.status())) throw Error()
  await anonymous.close()
  console.log('PASS console: real Keycloak SSO; scoped pgAdmin Query Tool read and read-only DDL denial; password saving denied; active query terminated and expired reconnect denied; other-human/anonymous isolation')
} catch {
  console.log(stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
