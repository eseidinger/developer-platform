import { expect, test } from '@playwright/test'

const resourceId = '12345678-1234-4234-8234-123456789abc'

test('creates a PostgreSQL resource and confirms its retirement', async ({
  page,
}) => {
  let resource: Record<string, unknown> | null = null
  const mutations: string[] = []

  await page.route('**/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const method = request.method()
    const send = (data: unknown, status = 200) =>
      route.fulfill({ json: data, status })

    if (path === '/v1/projects/alpha/store-context' && method === 'GET') {
      return send({
        manage: true,
        platform_admin: false,
        providers: [
          { id: 'postgresql', enabled: true },
          { id: 's3', enabled: true },
        ],
      })
    }
    if (path === '/v1/projects/alpha/resources' && method === 'GET') {
      return send({ resources: resource ? [resource] : [] })
    }
    if (path === '/v1/projects/alpha/resources' && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      mutations.push(`${method} ${path}`)
      if (
        body.name !== 'measurements' ||
        body.provider !== 'postgresql' ||
        JSON.stringify(body.extensions) !==
          JSON.stringify([
            'vector',
            'age',
            'timescaledb',
            'postgis',
            'pgmq',
            'pg_duckdb',
          ])
      ) {
        return send({ detail: 'Unexpected resource request' }, 400)
      }
      resource = {
        resource_id: resourceId,
        owner_project: 'alpha',
        name: body.name,
        provider: body.provider,
        state: 'active',
        observed_state: 'active',
        version: 1,
        quota_bytes: body.quota_bytes,
        extensions: body.extensions,
        error_code: null,
      }
      return send(resource, 201)
    }
    if (
      path === `/v1/resources/${resourceId}/retirement` &&
      method === 'POST'
    ) {
      mutations.push(`${method} ${path}`)
      const body = request.postDataJSON() as { version?: number }
      if (body.version !== 1 || !resource) {
        return send({ detail: 'Invalid retirement version' }, 409)
      }
      resource = {
        ...resource,
        state: 'retired',
        observed_state: 'retired',
        version: 2,
      }
      return send(resource)
    }
    if (path === '/v1/projects/alpha/resource-bindings' && method === 'GET') {
      return send({ bindings: [] })
    }
    if (path === '/v1/store-access/me' && method === 'GET') {
      return send({ grants: [] })
    }
    if (path === `/v1/resources/${resourceId}/grants` && method === 'GET') {
      return send({ grants: [] })
    }
    return send(
      { detail: `Unexpected fixture request: ${method} ${path}` },
      404,
    )
  })

  await page.goto('/e2e/store-harness.html')
  await page.getByLabel('Resource name').fill('measurements')
  for (const name of [
    'pgvector (vector search)',
    'AGE (graph projections)',
    'TimescaleDB (time series)',
    'PostGIS (spatial)',
    'pgmq (queues)',
    'pg_duckdb (analytics)',
  ]) {
    await page.getByRole('checkbox', { name }).check()
  }
  await page.getByRole('button', { name: 'Create resource' }).click()
  await expect(
    page.getByRole('heading', { name: 'measurements · postgresql' }),
  ).toBeVisible()
  await expect(
    page.getByText(/Desired: active · observed: active/),
  ).toBeVisible()
  if (process.env.PLAN041_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.PLAN041_SCREENSHOT_DIR}/store-desktop.png`,
      fullPage: true,
    })
  }

  await page.getByRole('button', { name: 'Retire resource' }).click()
  const dialog = page.getByRole('dialog', { name: 'Retire resource' })
  await expect(dialog).toContainText(
    'measurements: revoke every human and application grant',
  )
  if (process.env.PLAN041_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.PLAN041_SCREENSHOT_DIR}/store-retirement-dialog.png`,
      animations: 'disabled',
    })
  }
  expect(mutations).toEqual(['POST /v1/projects/alpha/resources'])
  await dialog.getByRole('button', { name: 'Confirm' }).click()
  await expect(
    page.getByText(/Desired: retired · observed: retired/),
  ).toBeVisible()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.mantine-Modal-overlay')).toBeHidden()
  expect(mutations).toEqual([
    'POST /v1/projects/alpha/resources',
    `POST /v1/resources/${resourceId}/retirement`,
  ])

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(
    page.getByRole('heading', { name: 'alpha data stores' }),
  ).toBeVisible()
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(horizontalOverflow).toBe(false)
  if (process.env.PLAN041_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.PLAN041_SCREENSHOT_DIR}/store-mobile.png`,
      fullPage: true,
      animations: 'disabled',
    })
  }
})
