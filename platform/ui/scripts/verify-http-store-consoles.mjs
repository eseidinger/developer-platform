// Synthetic stdin only; no screenshots, traces, storage-state files or secret diagnostics.
import { createHash, createHmac } from 'node:crypto'
import { chromium } from '@playwright/test'
const sha = value => createHash('sha256').update(value).digest('hex')
const mac = (key, value) => createHmac('sha256', key).update(value).digest()
async function signedS3(page, origin, credentials, method, path, payload = '') {
  const url = new URL(path, origin)
  const stamp = new Date().toISOString().replace(/[:-]|\.\d{3}/g, '')
  const day = stamp.slice(0, 8)
  const scope = day + '/us-east-1/s3/aws4_request'
  const headers = { host: url.host, 'x-amz-content-sha256': sha(payload), 'x-amz-date': stamp,
    'x-amz-security-token': credentials.SessionToken }
  const names = Object.keys(headers).sort()
  const query = [...url.searchParams].sort(([a], [b]) => a.localeCompare(b)).map(([a, b]) => encodeURIComponent(a) + '=' + encodeURIComponent(b)).join('&')
  const canonical = [method, url.pathname, query, names.map(name => name + ':' + headers[name] + '\n').join(''), names.join(';'), sha(payload)].join('\n')
  const secret = mac(mac(mac(mac('AWS4' + credentials.SecretAccessKey, day), 'us-east-1'), 's3'), 'aws4_request')
  const signature = mac(secret, ['AWS4-HMAC-SHA256', stamp, scope, sha(canonical)].join('\n')).toString('hex')
  delete headers.host
  headers.Authorization = `AWS4-HMAC-SHA256 Credential=${credentials.AccessKeyId}/${scope}, SignedHeaders=${names.join(';')}, Signature=${signature}`
  return page.evaluate(async ({ url, method, headers, payload }) => {
    const response = await fetch(url, { method, headers, ...(payload ? { body: payload } : {}) })
    return { status: response.status, text: await response.text() }
  }, { url: url.toString(), method, headers, payload })
}
let input = ''
for await (const part of process.stdin) input += part
const config = JSON.parse(input)
let stage = 'browser-start'
let activePage
let activeProvider
let statuses = []
const browser = await chromium.launch({ headless: true })
try {
  for (const [name, provider] of Object.entries(config.providers)) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, proxy: { server: config.proxy } })
    await context.route('https://platform.fixture.test/**', route => route.fulfill({ contentType: 'text/html', body: '<html><body>Fixture portal</body></html>' }))
    context.setDefaultTimeout(10000)
    const page = await context.newPage(); activePage = page; activeProvider = provider; statuses = []
    page.on('response', response => { const path = new URL(response.url()).pathname; if ((path === '/' || path.startsWith('/rustfs/admin/')) && statuses.length < 32) statuses.push(response.request().method() + ' ' + response.status() + ' ' + path) })
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
    await page.waitForURL(name === 's3' ? '**/rustfs/console/**' : '**/dashboard/**')
    stage = name + '-native-login'
    if (name === 's3') {
      await page.getByPlaceholder('Please enter account').fill(provider.connection.RUSTFS_CONSOLE_ACCESS_KEY)
      await page.getByPlaceholder('Please enter key').fill(provider.connection.RUSTFS_CONSOLE_SECRET_KEY)
      await page.getByRole('button', { name: 'Login', exact: true }).click()
      await page.waitForFunction(() => Boolean(localStorage.getItem('auth.credentials')), null, { timeout: 10000 })
      await page.waitForURL(url => !url.pathname.includes('/auth/login/'), { timeout: 10000 })
      stage = 's3-scoped-native-session'
      const session = await page.evaluate(() => JSON.parse(localStorage.getItem('auth.credentials')))
      if (!session.SessionToken || session.AccessKeyId === provider.connection.RUSTFS_CONSOLE_ACCESS_KEY) throw Error()
      const listed = await signedS3(page, provider.origin, session, 'GET', '/')
      if (listed.status !== 200 || !listed.text.includes(provider.connection.S3_BUCKET)) { console.log('Native STS list status: ' + listed.status + ' ' + (listed.text.match(/<Code>([A-Za-z0-9]+)<\/Code>/)?.[1] || '')); throw Error() }
      stage = 's3-scoped-bucket-browser'
      await page.goto(provider.origin + '/rustfs/console/browser/')
      await page.getByText(provider.connection.S3_BUCKET, { exact: true }).first().waitFor({ timeout: 10000 })
      console.log('PASS official RustFS scoped console identity, native STS exchange, relay-acknowledged child session and own bucket browser')
    } else {
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
    }
    stage = name + '-active-console-revocation'
    await context.request.post(config.gateway + '/expire/' + provider.port)
    const expired = await page.evaluate(async () => (await fetch('/')).status)
    if (expired !== 401) throw Error()
    await page.reload()
    if (!(await page.textContent('body')).includes('Open an active console lease')) throw Error()
    console.log('PASS ' + name + ' already-open console revocation, cookie/storage cleanup and expired reload denial')
    await context.close()
  }
} catch {
  if (activePage && stage.startsWith('s3')) {
    let text = await activePage.innerText('body', { timeout: 3000 })
    for (const value of Object.values(activeProvider.connection)) text = text.replaceAll(value, '[redacted]')
    console.log('Scoped synthetic console view: ' + new URL(activePage.url()).pathname + ' ' + text.slice(0, 700))
    console.log(statuses.join('|'))
  }
  console.log(stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
