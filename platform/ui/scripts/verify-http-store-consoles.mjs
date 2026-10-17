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
    const page = await context.newPage();
    const liveSockets = new Set();
    page.on('websocket', socket => { liveSockets.add(socket); socket.on('close', () => liveSockets.delete(socket)) });
    activePage = page; activeProvider = provider; statuses = []
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
    await page.waitForURL(url => provider.provider === 's3' ? url.pathname.startsWith('/rustfs/console/') :
      provider.provider === 'qdrant' ? url.pathname.startsWith('/dashboard/') : provider.provider === 'neo4j' ? url.pathname.startsWith('/browser/') : url.pathname.includes('/app/login'))
    stage = name + '-native-login'
    if (provider.provider === 's3') {
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
      // A forced policy refresh used to unmount/remount this page indefinitely.
      await page.reload()
      await page.getByText(provider.connection.S3_BUCKET, { exact: true }).first().waitFor()
      const own = '/' + provider.connection.S3_BUCKET
      const read = await signedS3(page, provider.origin, session, 'GET', own + '/fixture.txt')
      if (read.status !== 200 || read.text !== 'console fixture') throw Error()
      const write = await signedS3(page, provider.origin, session, 'PUT', own + '/written.txt', 'browser fixture')
      if (write.status !== (provider.mode === 'read-write' ? 200 : 403)) throw Error()
      const removed = await signedS3(page, provider.origin, session, 'DELETE', own + '/written.txt')
      if (removed.status !== (provider.mode === 'read-write' ? 204 : 403)) throw Error()
      const foreign = await signedS3(page, provider.origin, session, 'GET', '/' + provider.foreign + '/fixture.txt')
      const destroy = await signedS3(page, provider.origin, session, 'DELETE', own)
      if (foreign.status !== 403 || destroy.status !== 403) throw Error()
      console.log('PASS RustFS ' + provider.mode + ' official console login, STS binding, refresh, object permissions and foreign/admin denial')
    } else if (provider.provider === 'qdrant') {
      await page.locator('input[type="password"]').fill(provider.connection.QDRANT_API_KEY)
      await page.getByRole('button', { name: 'Apply', exact: true }).click()
      await page.getByText(provider.connection.QDRANT_COLLECTION, { exact: true }).first().waitFor({ timeout: 10000 })
      const checked = await page.evaluate(async connection => {
        const response = await fetch('/collections', { headers: { 'api-key': connection.QDRANT_API_KEY } })
        const result = await response.json()
        return response.status === 200 && result.result.collections.length === 1 && result.result.collections[0].name === connection.QDRANT_COLLECTION
      }, provider.connection)
      if (!checked) throw Error()
      const denied = await page.evaluate(async ({ connection, foreign, mode }) => {
        const headers = { 'api-key': connection.QDRANT_API_KEY, 'Content-Type': 'application/json' }
        const write = await fetch('/collections/' + connection.QDRANT_COLLECTION + '/points?wait=true', {
          method: 'PUT', headers, body: JSON.stringify({ points: [{ id: 1, vector: [1, 0, 0] }] }) })
        const other = await fetch('/collections/' + foreign, { headers })
        const drop = await fetch('/collections/' + connection.QDRANT_COLLECTION, { method: 'DELETE', headers })
        return write.status === (mode === 'read-write' ? 200 : 403) && other.status === 403 && drop.status === 403
      }, provider)
      if (!denied) throw Error()
      console.log('PASS Qdrant ' + provider.mode + ' official console login, scoped collection, point permissions and foreign/admin denial')
    } else if (provider.provider === 'neo4j') {
      stage = name + '-browser-connect';
      await page.getByRole('button', { name: 'Connect', exact: true }).waitFor();
      const inputs = page.locator('input[type="text"]');
      await inputs.nth(1).fill(new URL(provider.origin).host + ':443');
      await inputs.nth(2).fill(provider.connection.NEO4J_USERNAME);
      await page.locator('input[type="password"]').fill(provider.connection.NEO4J_PASSWORD);
      await page.getByRole('button', {name:'Connect',exact:true}).click();
      await page.waitForFunction(() => /connection status:\s*connected/.test(document.body.innerText.toLowerCase()),null,{timeout:20000});
      if (!liveSockets.size) throw Error();
      const checked = await page.evaluate(async connection => {
        const response = await fetch('/db/neo4j/query/v2', {method:'POST',headers:{'Content-Type':'application/json',Authorization:'Basic '+btoa(connection.NEO4J_USERNAME+':'+connection.NEO4J_PASSWORD)},body:JSON.stringify({statement:'CREATE (:BrowserFixture {value:7}) RETURN 7'})});
        const value=await response.json();
        return response.status===202 || (response.status===200 && !value.errors?.length);
      },provider.connection);
      if (!checked) throw Error();
      const foreign = await page.evaluate(async peer => (await fetch('/db/neo4j/query/v2',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Basic '+btoa(peer.NEO4J_USERNAME+':'+peer.NEO4J_PASSWORD)},body:JSON.stringify({statement:'RETURN 1'})})).status,provider.peer);
      if (foreign!==401) throw Error();
      console.log('PASS Neo4j official Browser native WSS login, graph writes and foreign-lease denial');
    } else {
      stage = name + '-foreign-lease-login'
      const foreignLogin = await page.evaluate(async peer => (await fetch('/auth/login', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'osd-xsrf': 'true' },
        body: JSON.stringify({ username: peer.OPENSEARCH_USERNAME, password: peer.OPENSEARCH_PASSWORD }) })).status, provider.peer)
      if (foreignLogin !== 401) { console.log('Foreign native login status: ' + foreignLogin); throw Error() }
      stage = name + '-username-field'
      await page.locator('input').first().fill(provider.connection.OPENSEARCH_USERNAME)
      stage = name + '-password-field'
      await page.locator('input[type="password"]').fill(provider.connection.OPENSEARCH_PASSWORD)
      stage = name + '-login-submit'
      await page.getByRole('button', { name: 'basicauth_login_button', exact: true }).click()
      stage = name + '-authenticated-navigation'
      await page.waitForURL(url => !url.pathname.includes('/app/login'), { timeout: 20000 })
      stage = name + '-native-data-proxy'
      const result = await page.evaluate(async ({ connection, foreign, mode }) => {
        const request = async (method, path, value) => {
          const response = await fetch('/api/console/proxy?path=' + encodeURIComponent(path) + '&method=' + method, {
            method: 'POST', headers: { 'osd-xsrf': 'true', 'Content-Type': 'application/json' },
            ...(value ? { body: JSON.stringify(value) } : {}) })
          return { status: response.status, text: await response.text() }
        }
        const index = connection.OPENSEARCH_INDEX
        const read = await request('GET', index + '/_search')
        const write = await request('PUT', index + '/_doc/browser', { title: 'browser fixture' })
        const other = await request('GET', foreign + '/_search')
        const drop = await request('DELETE', index)
        return { read: read.status, hasFixture: read.text.includes('console fixture'), write: write.status,
          other: other.status, drop: drop.status, expectedWrite: mode === 'read-write' ? 201 : 403 }
      }, provider)
      if (result.read !== 200 || !result.hasFixture || result.write !== result.expectedWrite || result.other !== 403 || result.drop !== 403) {
        console.log('Synthetic Dashboards native status: ' + JSON.stringify(result)); throw Error()
      }
      stage = name + '-resource-saved-objects'
      const saved = await page.evaluate(async connection => {
        const headers = { 'osd-xsrf': 'true', 'Content-Type': 'application/json' }
        const prior = await fetch('/api/saved_objects/index-pattern/fixture', { headers })
        const created = await fetch('/api/saved_objects/index-pattern/fixture', { method: 'POST', headers,
          body: JSON.stringify({ attributes: { title: connection.OPENSEARCH_INDEX } }) })
        return { prior: prior.status, created: created.status }
      }, provider.connection)
      if (saved.prior !== (provider.retained_workspace ? 200 : 404) || saved.created !== (provider.retained_workspace ? 409 : 200)) { console.log('Synthetic saved-object status: ' + JSON.stringify(saved)); throw Error() }
      stage = name + '-discover-view'
      const configured = await page.evaluate(async () => (await fetch('/api/opensearch-dashboards/settings', {
        method: 'POST', headers: { 'osd-xsrf': 'true', 'Content-Type': 'application/json' },
        body: JSON.stringify({ changes: { defaultIndex: 'fixture' } }) })).status)
      if (configured !== 200) { console.log('Default data-view setting status: ' + configured); throw Error() }
      await page.goto(provider.origin + '/app/discover')
      await page.waitForFunction(() => document.body.textContent.includes('console fixture'), null, { timeout: 20000 })
      console.log('PASS OpenSearch Dashboards ' + provider.mode + ' native login, Discover documents, scoped data, foreign/admin denial and resource workspace isolation/retention')
    }
    stage = name + '-active-console-revocation'
    const end = name.includes('second-') ? 'revoke' : provider.mode === 'read-write' ? 'expire' : 'revoke'
    await context.request.post(config.gateway + '/' + end + '/' + provider.port)
    if (end === 'expire') await new Promise(resolve => setTimeout(resolve, 400))
    if (provider.provider === 'neo4j') {
      for(let attempt=0;attempt<20 && liveSockets.size;attempt++) await new Promise(resolve => setTimeout(resolve,100));
      if(liveSockets.size) throw Error();
    }
    const expired = await page.evaluate(async () => (await fetch('/')).status)
    if (expired !== 401) throw Error()
    await page.reload()
    if (!(await page.textContent('body')).includes('Open an active console lease')) throw Error()
    console.log('PASS ' + name + ' already-open console ' + end + ', cookie/storage cleanup and reload denial')
    await context.close()
  }
} catch {
  if (activePage && ['s3', 'opensearch', 'neo4j'].includes(activeProvider.provider)) {
    let text = await activePage.innerText('body', { timeout: 3000 })
    for (const value of Object.values(activeProvider.connection)) if (typeof value==='string' && value) text = text.replaceAll(value, '[redacted]')
    console.log('Scoped synthetic console view: ' + new URL(activePage.url()).pathname + ' ' + text.slice(0, 700))
    console.log(statuses.join('|'))
    if (activeProvider.provider === 'opensearch') {
      console.log('Login field metadata: ' + JSON.stringify(await activePage.locator('input').evaluateAll(elements =>
        elements.map(element => ({ type: element.type, name: element.name, placeholder: element.placeholder, filled: Boolean(element.value) })))))
      console.log('Login button metadata: ' + JSON.stringify(await activePage.locator('button').evaluateAll(elements =>
        elements.map(element => ({ text: element.textContent?.slice(0, 60), disabled: element.disabled })))))
    }
  }
  console.log(stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
