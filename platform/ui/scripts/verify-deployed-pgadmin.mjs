// Live acceptance helper. Read ephemeral test identities and tokens from stdin;
// print only fixed stage names and results, never credentials or browser traces.
import { chromium } from '@playwright/test'

let input = ''
for await (const part of process.stdin) input += part
const config = JSON.parse(input)
let stage = 'browser-start'
let lastPath = ''
let activePage
const browser = await chromium.launch({ headless: true })
const base = config.base.replace(/\/$/, '')
const requestJson = async (context, path, token, method = 'GET', data) => {
  const response = await context.request.fetch(base + path, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    ...(data === undefined ? {} : { data }),
  })
  return { status: response.status(), body: await response.json() }
}
const loginPortal = async (context, person) => {
  const page = await context.newPage()
  activePage = page
  let token
  page.on('request', request => {
    const value = request.headers().authorization
    if (value?.startsWith('Bearer ')) token = value.slice(7)
  })
  stage = 'portal-load'
  await page.goto(base + '/')
  stage = 'portal-signin-button'
  await page.getByRole('button', { name: 'Sign in with OIDC' }).click()
  stage = 'identity-login-form'
  await page.locator('#username').fill(person.username)
  await page.locator('#password').fill(person.password)
  stage = 'identity-submit'
  await page.locator('#kc-login').click()
  stage = 'portal-return'
  await page.waitForURL(url => url.origin === new URL(base).origin, { timeout: 30000 })
  stage = 'portal-auth-complete'
  await page.getByText(/Signed in/).waitFor({ timeout: 30000 })
  stage = 'portal-bearer-capture'
  await page.goto(base + '/store-access')
  await page.waitForTimeout(1500)
  if (!token) throw Error()
  return { page, token }
}
try {
  const context = await browser.newContext()
  stage = 'portal-interactive-login'
  const owner = await loginPortal(context, config.owner)
  stage = 'human-credential-issue'
  const issued = await requestJson(context, `/v1/store-access/${config.grantId}/credentials`, owner.token, 'POST')
  if (issued.status !== 202 || !issued.body.credential_id) throw Error()
  const credentialId = issued.body.credential_id
  let lease
  for (let i = 0; i < 30; i++) {
    const result = await requestJson(context, `/v1/store-access/credentials/${credentialId}`, owner.token)
    if (result.status === 200) { lease = result.body; break }
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
  if (!lease?.connection?.PGPASSWORD) throw Error()
  stage = 'pgadmin-sso'
  const page = await context.newPage()
  activePage = page
  const consoleBase = base + '/store-console/postgresql'
  stage = 'pgadmin-login-page'
  await page.goto(consoleBase + '/login')
  lastPath = new URL(page.url()).pathname
  stage = 'pgadmin-signin-button'
  await page.getByRole('button', { name: /Platform sign-in/ }).click()
  lastPath = new URL(page.url()).pathname
  stage = 'pgadmin-sso-return'
  await page.waitForURL(url => url.pathname.endsWith('/browser/'), { timeout: 30000 })
  stage = 'pgadmin-csrf'
  const utils = await context.request.get(consoleBase + '/browser/js/utils.js')
  const script = await utils.text()
  const match = script.match(/pgAdmin\['csrf_token'\]\s*=\s*'([^']+)'/)
  if (!match) throw Error()
  const headers = { 'X-pgA-CSRFToken': match[1], Referer: consoleBase + '/browser/' }
  const call = async (method, path, data) => {
    const response = await context.request.fetch(consoleBase + path, { method, headers, data })
    return { status: response.status(), body: await response.json() }
  }
  stage = 'pgadmin-scoped-register'
  const c = lease.connection
  const created = await call('POST', '/browser/server/obj/1/', {
    name: 'Phase 7 deployed acceptance', db: c.PGDATABASE,
    host: 'store-access', port: Number(c.PGPORT), username: c.PGUSER,
    role: '', service: '', connection_params: { sslmode: 'disable' }, connect_now: false,
  })
  const sid = created.body.node?._id
  if (!sid) throw Error()
  const connectionPath = `/browser/server/connect/1/${sid}`
  stage = 'pgadmin-scoped-connect'
  const connected = await call('POST', connectionPath, { password: c.PGPASSWORD, save_password: true })
  if (connected.body.data?.connected !== true || connected.body.data?.is_password_saved !== false) throw Error()
  stage = 'pgadmin-scoped-query'
  const stats = await call('GET', `/browser/server/stats/1/${sid}`)
  if (stats.status !== 200 || stats.body.success === 0) throw Error()
  stage = 'pgadmin-query-tool-initialize'
  const transaction = Date.now()
  const initialized = await call('POST', `/sqleditor/initialize/sqleditor/${transaction}/1/${sid}/0`,
    { dbname: c.PGDATABASE, password: c.PGPASSWORD })
  if (initialized.status !== 200 || initialized.body.success !== 1) throw Error()
  const query = async sql => {
    const started = await call('POST', `/sqleditor/query_tool/start/${transaction}`,
      { sql, explain_plan: null })
    if (started.status !== 200 || started.body.success !== 1) throw Error()
    for (let attempt = 0; attempt < 50; attempt++) {
      const polled = await call('GET', `/sqleditor/poll/${transaction}`)
      if (polled.body.data?.status === 'Success') return polled.body.data
      if (polled.body.data?.status !== 'Busy') throw Error()
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    throw Error()
  }
  if (config.mode === 'read-write') {
    stage = 'pgadmin-query-tool-write'
    const marker = config.marker
    if (!/^phase7_[a-z0-9_]{1,50}$/.test(marker)) throw Error()
    await query(`CREATE TABLE public.${marker}(value text PRIMARY KEY)`)
    await query(`INSERT INTO public.${marker} VALUES ('query-tool-write')`)
    if (!JSON.stringify((await query(`SELECT value FROM public.${marker}`)).result).includes('query-tool-write')) throw Error()
    await query(`DROP TABLE public.${marker}`)
  } else {
    stage = 'pgadmin-query-tool-read'
    if (!JSON.stringify((await query('SELECT 1 AS fixture_value')).result).includes('1')) throw Error()
    stage = 'pgadmin-query-tool-read-only-denial'
    const attempted = await call('POST', `/sqleditor/query_tool/start/${transaction}`,
      { sql: 'CREATE TABLE public.phase7_forbidden(id integer)', explain_plan: null })
    if (attempted.status !== 200 || attempted.body.success !== 1) throw Error()
    let deniedWrite = false
    for (let attempt = 0; attempt < 50; attempt++) {
      const polled = await call('GET', `/sqleditor/poll/${transaction}`)
      if (polled.body.data?.status === 'Busy') {
        await new Promise(resolve => setTimeout(resolve, 100))
        continue
      }
      deniedWrite = polled.status >= 400 || polled.body.success === 0
      break
    }
    if (!deniedWrite) throw Error()
  }
  if (config.other) {
    stage = 'other-human-isolation'
    const otherContext = await browser.newContext()
    await loginPortal(otherContext, config.other)
    const foreign = await otherContext.request.get(consoleBase + `/browser/server/obj/1/${sid}`)
    const foreignBody = await foreign.json()
    if ((!([400, 403, 404, 410].includes(foreign.status())) && foreignBody.success !== 0)
        || JSON.stringify(foreignBody).includes(c.PGUSER)) throw Error()
    await otherContext.close()
  }
  stage = 'anonymous-denial'
  const anonymous = await browser.newContext()
  const denied = await anonymous.request.get(consoleBase + `/browser/server/obj/1/${sid}`, { maxRedirects: 0 })
  if (![302, 401, 403].includes(denied.status())) throw Error()
  await anonymous.close()
  stage = 'grant-revocation'
  const grant = await requestJson(context, `/v1/resources/${config.resourceId}/grants`, config.runnerToken)
  const row = grant.body.grants?.find(item => item.grant_id === config.grantId)
  if (!row) throw Error()
  const revoked = await requestJson(context, `/v1/resource-grants/${config.grantId}/revocation`,
    config.runnerToken, 'POST', { version: row.version })
  if (revoked.status !== 202) throw Error()
  await new Promise(resolve => setTimeout(resolve, 1200))
  stage = 'revoked-reconnect-denial'
  await call('DELETE', connectionPath)
  const reconnect = await call('POST', connectionPath, { password: c.PGPASSWORD })
  if (reconnect.body.data?.connected === true || (reconnect.status === 200 && reconnect.body.success === 1)) throw Error()
  console.log('PASS deployed pgAdmin: interactive portal and console SSO; scoped Query Tool ' +
    (config.mode === 'read-write' ? 'DDL/write/read' : 'read and read-only DDL denial') +
    '; password save denied; anonymous isolation; revoked reconnect denied' +
    (config.other ? '; other-human isolation' : ''))
} catch {
  if (activePage) lastPath = new URL(activePage.url()).pathname
  console.log('FAIL deployed pgAdmin stage=' + stage + (lastPath ? ' path=' + lastPath : ''))
  process.exitCode = 1
} finally {
  await browser.close()
}
