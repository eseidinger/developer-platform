// Read disposable identities and expected resource IDs from private stdin.
// This check reads an existing AI run; it never starts another billable run.
import assert from 'node:assert/strict'
import { chromium, expect } from '@playwright/test'
import { deploymentOrigin } from './live-config.mjs'

let input = ''
for await (const chunk of process.stdin) input += chunk
const config = JSON.parse(input)
const base = deploymentOrigin(config.base)
let stage = 'browser-start'
const browser = await chromium.launch({ headless: true })

try {
  const context = await browser.newContext()
  const page = await context.newPage()
  stage = 'human-sign-in'
  await page.goto(base + '/')
  await page.getByRole('button', { name: 'Sign in with OIDC' }).click()
  await page.locator('#username').fill(config.owner.username)
  await page.locator('#password').fill(config.owner.password)
  await page.locator('#kc-login').click()
  await page.waitForURL((url) => url.origin === base)
  await expect(page.getByText(/Signed in/)).toBeVisible()
  console.log('PASS deployed portal human sign-in')

  stage = 'project-workspace'
  await page.getByRole('link', { name: config.project, exact: true }).click()
  await expect(
    page.getByRole('heading', { name: config.project, exact: true }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'AI assistance', exact: true }).click()

  stage = 'ai-persisted-history'
  await expect(page.getByRole('heading', { name: 'Run history' })).toBeVisible()
  await page.getByRole('link', { name: new RegExp(config.aiRunId) }).click()
  const selected = page.getByRole('region', { name: 'Selected run' })
  await expect(
    selected.getByRole('heading', { name: /completed/ }),
  ).toBeVisible()
  await expect(
    selected.getByRole('heading', { name: 'Evidence sources' }),
  ).toBeVisible()
  await expect(selected.locator('[id^="evidence-"]').first()).toBeVisible()
  console.log('PASS deployed portal AI history, result and evidence')

  stage = 'named-store-catalog'
  // Portal tokens stay in memory, so use its links rather than a full reload.
  await page.getByRole('link', { name: `Back to ${config.project}` }).click()
  await page.getByRole('link', { name: 'Data stores', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: `${config.project} data stores` }),
  ).toBeVisible()
  for (const provider of config.providers) {
    assert.match(provider, /^(postgresql|s3|qdrant|opensearch|neo4j)$/)
    await expect(
      page.getByRole('heading', {
        name: `functional-${provider} · ${provider}`,
      }),
    ).toBeVisible()
  }
  console.log('PASS deployed portal catalog for all requested store providers')
} catch {
  // Browser exception messages can contain form values or credential responses.
  console.log('FAIL deployed portal stage=' + stage)
  process.exitCode = 1
} finally {
  await browser.close()
}
