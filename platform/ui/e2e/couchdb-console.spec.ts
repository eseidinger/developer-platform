import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const assets = resolve(
  import.meta.dirname,
  '../../app/src/app/stores/console_assets/couchdb',
)
const database = 'resource_fixture'

async function openConsole(page: Page, mode: 'read-only' | 'read-write') {
  let document = { _id: 'first', _rev: '1-fixture', value: 1 }
  const writes: unknown[] = []

  await page.route('**/__platform/couchdb/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/config')) {
      return route.fulfill({ json: { database, mode } })
    }
    const file = path.endsWith('/app.js')
      ? 'app.js'
      : path.endsWith('/style.css')
        ? 'style.css'
        : 'index.html'
    const contentType = file.endsWith('.js')
      ? 'text/javascript'
      : file.endsWith('.css')
        ? 'text/css'
        : 'text/html'
    return route.fulfill({ path: resolve(assets, file), contentType })
  })
  await page.route(`**/${database}/**`, (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/_all_docs')) {
      return route.fulfill({ json: { rows: [{ id: document._id }] } })
    }
    if (path.endsWith('/_find')) {
      return route.fulfill({ json: { docs: [document] } })
    }
    if (path.endsWith('/_index')) {
      writes.push(request.postDataJSON())
      return route.fulfill({ json: { result: 'created', name: 'by_type' } })
    }
    if (request.method() === 'PUT') {
      const submitted = request.postDataJSON() as {
        _id: string
        value: number
      }
      writes.push(submitted)
      document = { ...submitted, _rev: '2-fixture' }
      return route.fulfill({ json: { ok: true, rev: '2-fixture' } })
    }
    return route.fulfill({ json: document })
  })

  await page.goto('/__platform/couchdb/')
  await expect(page.getByRole('button', { name: 'first' })).toBeVisible()
  return writes
}

test('CouchDB reader can browse and query without editing controls', async ({
  page,
}) => {
  await openConsole(page, 'read-only')
  await page.getByRole('button', { name: 'first' }).click()
  await expect(page.locator('#document-json')).toHaveValue(/"value": 1/)
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Delete' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Create index' })).toBeHidden()
  await page.getByRole('button', { name: 'Find up to 50 documents' }).click()
  await expect(page.getByRole('status')).toContainText('Found 1 documents')
})

test('CouchDB writer saves documents and creates a named index', async ({
  page,
}) => {
  const writes = await openConsole(page, 'read-write')
  await page.getByRole('button', { name: 'first' }).click()
  await expect(page.locator('#document-json')).toHaveValue(/"value": 1/)
  await page
    .locator('#document-json')
    .fill(JSON.stringify({ _id: 'first', _rev: '1-fixture', value: 2 }))
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('status')).toContainText('Saved first')
  await page.getByRole('button', { name: 'Create index' }).click()
  await expect(page.getByRole('status')).toContainText('Index by_type created')
  expect(writes).toEqual([
    { _id: 'first', _rev: '1-fixture', value: 2 },
    { index: { fields: ['type'] }, name: 'by_type', type: 'json' },
  ])
})
