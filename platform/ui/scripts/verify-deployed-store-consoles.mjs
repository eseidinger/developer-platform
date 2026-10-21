// Live Phase 7 helper. Input contains ephemeral personas and runner credentials;
// never print input, native credentials, URLs with assertions, traces or storage state.
import { chromium } from '@playwright/test'
import { deploymentOrigin, unitVector } from './live-config.mjs'
import { createHash, createHmac } from 'node:crypto'

const sha = (value) => createHash('sha256').update(value).digest('hex')
const mac = (key, value) => createHmac('sha256', key).update(value).digest()
const signedS3 = async (
  page,
  origin,
  credentials,
  method,
  path,
  payload = '',
) => {
  const url = new URL(path, origin)
  const stamp = new Date().toISOString().replace(/[:-]|\.\d{3}/g, '')
  const day = stamp.slice(0, 8)
  const scope = day + '/us-east-1/s3/aws4_request'
  const headers = {
    host: url.host,
    'x-amz-content-sha256': sha(payload),
    'x-amz-date': stamp,
    'x-amz-security-token': credentials.SessionToken,
  }
  const names = Object.keys(headers).sort()
  const query = [...url.searchParams]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([a, b]) => encodeURIComponent(a) + '=' + encodeURIComponent(b))
    .join('&')
  const canonical = [
    method,
    url.pathname,
    query,
    names.map((name) => name + ':' + headers[name] + '\n').join(''),
    names.join(';'),
    sha(payload),
  ].join('\n')
  const secret = mac(
    mac(mac(mac('AWS4' + credentials.SecretAccessKey, day), 'us-east-1'), 's3'),
    'aws4_request',
  )
  const signature = mac(
    secret,
    ['AWS4-HMAC-SHA256', stamp, scope, sha(canonical)].join('\n'),
  ).toString('hex')
  delete headers.host
  headers.Authorization = `AWS4-HMAC-SHA256 Credential=${credentials.AccessKeyId}/${scope}, SignedHeaders=${names.join(';')}, Signature=${signature}`
  return page.evaluate(
    async ({ url, method, headers, payload }) => {
      const response = await fetch(url, {
        method,
        headers,
        ...(payload ? { body: payload } : {}),
      })
      return { status: response.status, text: await response.text() }
    },
    { url: url.toString(), method, headers, payload },
  )
}

let input = ''
for await (const chunk of process.stdin) input += chunk
const config = JSON.parse(input)
const base = deploymentOrigin(config.base)
const browser = await chromium.launch({ headless: true })
let stage = 'start'

const login = async (person) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  let token
  page.on('request', (request) => {
    const value = request.headers().authorization
    if (value?.startsWith('Bearer ')) token = value.slice(7)
  })
  await page.goto(base + '/')
  await page.getByRole('button', { name: 'Sign in with OIDC' }).click()
  await page.locator('#username').fill(person.username)
  await page.locator('#password').fill(person.password)
  await page.locator('#kc-login').click()
  await page.waitForURL((url) => url.origin === new URL(base).origin, {
    timeout: 30000,
  })
  await page.getByText(/Signed in/).waitFor({ timeout: 30000 })
  await page.goto(base + '/store-access')
  await page.waitForTimeout(1200)
  if (!token) throw Error('No portal token')
  return { context, page, token }
}
const api = async (person, method, path, data) => {
  const response = await person.context.request.fetch(base + path, {
    method,
    headers: { Authorization: 'Bearer ' + person.token },
    ...(data ? { data } : {}),
  })
  return { status: response.status(), body: await response.json() }
}
const lease = async (person, grant) => {
  const issued = await api(
    person,
    'POST',
    `/v1/store-access/${grant}/credentials`,
  )
  if (issued.status !== 202) throw Error('Lease issue ' + issued.status)
  const id = issued.body.credential_id
  for (let attempt = 0; attempt < 60; attempt++) {
    const result = await api(
      person,
      'GET',
      `/v1/store-access/credentials/${id}`,
    )
    if (result.status === 200) return result.body
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw Error('Lease did not become active')
}
const launch = async (person, credential) => {
  const response = await api(
    person,
    'POST',
    `/v1/store-access/credentials/${credential.credential_id}/console`,
  )
  if (response.status !== 200) throw Error('Console launch ' + response.status)
  const { url, launch } = response.body
  const origin = new URL(url).origin
  await person.page.goto(base + '/')
  await person.page.evaluate(
    ({ url, launch }) => {
      const form = document.createElement('form')
      form.method = 'POST'
      form.action = url
      const input = document.createElement('input')
      input.name = 'launch'
      input.value = launch
      form.append(input)
      document.body.append(form)
      form.submit()
    },
    { url, launch },
  )
  await person.page.waitForURL(
    (target) =>
      target.origin === origin &&
      (target.pathname.startsWith('/rustfs/console/') ||
        target.pathname.startsWith('/dashboard/') ||
        target.pathname.startsWith('/browser/') ||
        target.pathname.includes('/app/login')),
    { timeout: 30000 },
  )
  return origin
}
const native = async (provider, mode, person, credential, origin) => {
  const page = person.page
  const c = credential.connection
  if (provider === 's3') {
    stage += '-login-form'
    await page
      .getByPlaceholder('Please enter account')
      .fill(c.RUSTFS_CONSOLE_ACCESS_KEY)
    stage += '-secret-field'
    await page
      .getByPlaceholder('Please enter key')
      .fill(c.RUSTFS_CONSOLE_SECRET_KEY)
    await page.getByRole('button', { name: 'Login', exact: true }).click()
    stage += '-sts-session'
    await page.waitForFunction(() =>
      Boolean(localStorage.getItem('auth.credentials')),
    )
    stage += '-bucket-list'
    await page.goto(origin + '/rustfs/console/browser/')
    await page.getByText(c.S3_BUCKET, { exact: true }).first().waitFor()
    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem('auth.credentials')),
    )
    if (
      !session.SessionToken ||
      session.AccessKeyId === c.RUSTFS_CONSOLE_ACCESS_KEY
    )
      throw Error('No scoped STS session')
    if (mode === 'read-only') {
      const denied = await signedS3(
        page,
        origin,
        session,
        'PUT',
        '/' + c.S3_BUCKET + '/read-only-denial.txt',
        'denied',
      )
      if (denied.status !== 403)
        throw Error('RustFS reader write was not denied: ' + denied.status)
    }
    if (mode === 'read-write') {
      await page.goto(
        origin +
          '/rustfs/console/browser/?bucket=' +
          encodeURIComponent(c.S3_BUCKET),
      )
      await page
        .getByRole('button', { name: /Upload File/ })
        .first()
        .click()
      const uploaded = page.waitForResponse(
        (response) =>
          response.request().method() === 'PUT' &&
          new URL(response.url()).pathname.endsWith('/phase7-browser.txt'),
        { timeout: 20000 },
      )
      await page.locator('input[name="upload-files"]').setInputFiles({
        name: 'phase7-browser.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('phase 7 deployed browser'),
      })
      await page.getByRole('button', { name: 'Start Upload' }).click()
      if ((await uploaded).status() !== 200) throw Error('RustFS upload failed')
      await page.goto(
        origin +
          '/rustfs/console/browser/?bucket=' +
          encodeURIComponent(c.S3_BUCKET),
      )
      await page
        .getByText('phase7-browser.txt', { exact: true })
        .first()
        .waitFor()
      await page
        .getByRole('button', { name: 'Actions: phase7-browser.txt' })
        .click()
      await page.getByRole('menuitem', { name: 'Delete', exact: true }).click()
      const deleted = page.waitForResponse(
        (response) =>
          response.request().method() === 'DELETE' &&
          new URL(response.url()).pathname.endsWith('/phase7-browser.txt'),
        { timeout: 20000 },
      )
      await page.getByRole('button', { name: 'Confirm', exact: true }).click()
      if ((await deleted).status() !== 204) throw Error('RustFS delete failed')
    }
  } else if (provider === 'qdrant') {
    const probe = await person.context.request.get(origin + '/collections', {
      headers: { 'api-key': c.QDRANT_API_KEY },
    })
    if (probe.status() !== 200)
      throw Error('Qdrant API key rejected at gateway: ' + probe.status())
    await page.locator('input[type="password"]').fill(c.QDRANT_API_KEY)
    await page.getByRole('button', { name: 'Apply', exact: true }).click()
    await page.getByText(c.QDRANT_COLLECTION, { exact: true }).first().waitFor()
    const collection = await person.context.request.get(
      origin + '/collections/' + c.QDRANT_COLLECTION,
      { headers: { 'api-key': c.QDRANT_API_KEY } },
    )
    if (collection.status() !== 200)
      throw Error('Collection configuration unavailable')
    const vector = unitVector(
      (await collection.json()).result.config.params.vectors.size,
    )
    const status = await page.evaluate(
      async ({ c, mode, vector }) => {
        const headers = {
          'api-key': c.QDRANT_API_KEY,
          'Content-Type': 'application/json',
        }
        const list = await fetch('/collections', { headers })
        const names = (await list.json()).result?.collections?.map(
          (x) => x.name,
        )
        const write = await fetch(
          '/collections/' + c.QDRANT_COLLECTION + '/points?wait=true',
          {
            method: 'PUT',
            headers,
            body: JSON.stringify({ points: [{ id: 7, vector }] }),
          },
        )
        const drop = await fetch('/collections/' + c.QDRANT_COLLECTION, {
          method: 'DELETE',
          headers,
        })
        return {
          list: list.status,
          names,
          write: write.status,
          drop: drop.status,
        }
      },
      { c, mode, vector },
    )
    if (
      status.list !== 200 ||
      status.names?.join() !== c.QDRANT_COLLECTION ||
      status.write !== (mode === 'read-write' ? 200 : 403) ||
      status.drop !== 403
    )
      throw Error('Qdrant scope ' + JSON.stringify(status))
  } else if (provider === 'opensearch') {
    await page.locator('input').first().fill(c.OPENSEARCH_USERNAME)
    await page.locator('input[type="password"]').fill(c.OPENSEARCH_PASSWORD)
    await page
      .getByRole('button', { name: 'basicauth_login_button', exact: true })
      .click()
    await page.waitForURL((url) => !url.pathname.includes('/app/login'), {
      timeout: 30000,
    })
    const status = await page.evaluate(
      async ({ c, mode }) => {
        const call = async (method, path, body) =>
          fetch(
            '/api/console/proxy?path=' +
              encodeURIComponent(path) +
              '&method=' +
              method,
            {
              method: 'POST',
              headers: {
                'osd-xsrf': 'true',
                'Content-Type': 'application/json',
              },
              ...(body ? { body: JSON.stringify(body) } : {}),
            },
          )
        const read = await call('GET', c.OPENSEARCH_INDEX + '/_search')
        const write = await call(
          'PUT',
          c.OPENSEARCH_INDEX + '/_doc/phase7-browser',
          { title: 'phase 7 browser' },
        )
        const drop = await call('DELETE', c.OPENSEARCH_INDEX)
        return { read: read.status, write: write.status, drop: drop.status }
      },
      { c, mode },
    )
    if (
      status.read !== 200 ||
      (mode === 'read-write'
        ? ![200, 201].includes(status.write)
        : status.write !== 403) ||
      status.drop !== 403
    )
      throw Error('OpenSearch scope ' + JSON.stringify(status))
  } else {
    await page.getByRole('button', { name: 'Connect', exact: true }).waitFor()
    const inputs = page.locator('input[type="text"]')
    await inputs.nth(1).fill(new URL(origin).host + ':443')
    await inputs.nth(2).fill(c.NEO4J_USERNAME)
    await page.locator('input[type="password"]').fill(c.NEO4J_PASSWORD)
    await page.getByRole('button', { name: 'Connect', exact: true }).click()
    await page.waitForFunction(
      () =>
        /connection status:\s*connected/.test(
          document.body.innerText.toLowerCase(),
        ),
      null,
      { timeout: 30000 },
    )
    const status = await page.evaluate(
      async ({ c, mode }) => {
        const auth = 'Basic ' + btoa(c.NEO4J_USERNAME + ':' + c.NEO4J_PASSWORD)
        const call = (statement) =>
          fetch('/db/neo4j/query/v2', {
            method: 'POST',
            headers: {
              Authorization: auth,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ statement }),
          })
        const read = await call('RETURN 1')
        const write = await call('CREATE (:Phase7Browser {value:7}) RETURN 7')
        return { read: read.status, write: write.status }
      },
      { c, mode },
    )
    if (
      ![200, 202].includes(status.read) ||
      (mode === 'read-write'
        ? ![200, 202].includes(status.write)
        : status.write !== 403)
    )
      throw Error('Neo4j scope ' + JSON.stringify(status))
  }
}
const revoke = async (person, provider, grant) => {
  const runner = config.runner
  const auth = await person.context.request.post(runner.token_endpoint, {
    form: {
      grant_type: 'client_credentials',
      client_id: runner.client_id,
      client_secret: runner.client_secret,
    },
  })
  if (auth.status() !== 200) throw Error('Runner token exchange failed')
  const token = (await auth.json()).access_token
  const headers = { Authorization: 'Bearer ' + token }
  const resourceId = config.resources[provider].id
  const listed = await person.context.request.get(
    base + `/v1/resources/${resourceId}/grants`,
    { headers },
  )
  const row = (await listed.json()).grants.find(
    (value) => value.grant_id === grant,
  )
  if (!row || row.state !== 'active')
    throw Error('Grant missing before revocation')
  const ended = await person.context.request.post(
    base + `/v1/resource-grants/${grant}/revocation`,
    {
      headers,
      data: { version: row.version },
    },
  )
  if (ended.status() !== 202)
    throw Error('Grant revocation failed ' + ended.status())
  const denied = await person.page.evaluate(
    async () => (await fetch('/')).status,
  )
  if (denied !== 401)
    throw Error('Existing console retained access after revocation: ' + denied)
  await person.page.reload()
  if (
    !(await person.page.locator('body').innerText()).includes(
      'Open an active console lease',
    )
  )
    throw Error('Revoked console did not clear on reload')
  console.log('PASS deployed ' + provider + ' active console revocation')
}

try {
  for (const provider of ['s3', 'qdrant', 'opensearch', 'neo4j'].filter(
    (value) => !process.env.P7_ONLY || process.env.P7_ONLY === value,
  )) {
    for (const role of ['writer', 'reader'].filter(
      (value) => !process.env.P7_ROLE || process.env.P7_ROLE === value,
    )) {
      stage = provider + '-' + role + '-portal-login'
      const user = config.users.people.find((person) => person.role === role)
      const person = await login(user)
      const grant = config.grants[provider][role]
      stage = provider + '-' + role + '-lease'
      const credential = await lease(person, grant)
      stage = provider + '-' + role + '-console-launch'
      const origin = await launch(person, credential)
      stage = provider + '-' + role + '-native'
      await native(
        provider,
        provider === 'neo4j' || role === 'writer' ? 'read-write' : 'read-only',
        person,
        credential,
        origin,
      )
      console.log(
        'PASS deployed ' +
          provider +
          ' ' +
          role +
          ' portal, lease, native console and scoped operation',
      )
      if (config.runner && role === 'writer') {
        stage = provider + '-active-console-revocation'
        await revoke(person, provider, grant)
      }
      await person.context.close()
    }
  }
} catch (error) {
  const diagnostic = [
    'certificate',
    'ENOTFOUND',
    'ECONNREFUSED',
    'Timeout',
    'Lease issue',
    'Lease did not become active',
    'Console launch',
  ].find((value) => error.message?.includes(value))
  if (diagnostic) console.log('Diagnostic: ' + diagnostic)
  if (/^Console launch [0-9]{3}$/.test(error.message))
    console.log(error.message)
  console.error(
    'FAIL deployed console stage=' +
      stage +
      ' error=' +
      (error instanceof Error ? error.constructor.name : 'Failure'),
  )
  process.exitCode = 1
} finally {
  await browser.close()
}
