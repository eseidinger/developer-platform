import { expect, test } from '@playwright/test'
import { aiFixture, digest, proposalId, runId } from './ai-fixture.ts'

test('reviews sourced evidence, creates a proposal, approves its hash and explicitly executes once', async ({
  page,
}) => {
  const fixture = await aiFixture(page)
  await page.goto(`/projects/demo/ai?run=${runId}`)
  await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
  await expect(
    page.getByText('<script>untrusted()</script> Startup failed.'),
  ).toBeVisible()
  await expect(page.locator('script:not([type="module"])')).toHaveCount(0)
  expect(fixture.mutations).toHaveLength(0)
  await page.getByRole('link', { name: 'E1', exact: true }).first().click()
  await expect(page.locator(`[id="evidence-${runId}-E1"]`)).toBeFocused()
  await page.getByRole('button', { name: 'Create rollback proposal' }).click()
  await expect(page.getByText('Review rollback', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Review execution' }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Review approval' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText(`Diff SHA-256: ${digest}`)).toBeVisible()
  await expect(
    dialog.getByRole('button', { name: 'Approve diff' }),
  ).toBeDisabled()
  await dialog.getByLabel('Type demo to confirm').fill('demo')
  await dialog.getByRole('button', { name: 'Approve diff' }).click()
  await expect(dialog).toHaveCount(0)
  expect(fixture.mutations.map((m) => m.path.split('/').at(-1))).toEqual([
    'proposals',
    'approval',
  ])
  await page.getByRole('button', { name: 'Review execution' }).click()
  await dialog.getByLabel('Type demo to confirm').fill('demo')
  await dialog.getByRole('button', { name: 'Execute rollback' }).click()
  await expect(
    page.getByText('Runtime readiness: ready.', { exact: false }),
  ).toBeVisible()
  await expect(
    page.getByText('Metrics unavailable or not enabled.', { exact: false }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Review execution' }),
  ).toBeDisabled()
  const approvals = fixture.mutations.filter(
    (m) => m.path.endsWith('/approval') || m.path.endsWith('/execute'),
  )
  expect(approvals.map((m) => m.body)).toEqual([
    { diff_sha256: digest },
    { diff_sha256: digest },
  ])
  expect(
    fixture.mutations.filter((m) => m.path.endsWith('/execute')),
  ).toHaveLength(1)
  await page.reload()
  await expect(page.getByText('Recovery observation')).toBeVisible()
  expect(fixture.mutations).toHaveLength(3)
  const storage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  )
  expect(storage).not.toContain('startup diagnosis')
  expect(storage).not.toContain(digest)
})

test('creates a run only on an explicit action and recovers its detail after reload', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { manage: false })
  await page.goto('/projects/demo/ai')
  await expect(
    page.getByRole('button', { name: 'Explain application', exact: true }),
  ).toBeEnabled()
  expect(fixture.mutations).toHaveLength(0)
  await page
    .getByRole('button', { name: 'Explain application', exact: true })
    .click()
  await expect(page).toHaveURL(new RegExp(`run=${runId}`))
  await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
  expect(fixture.mutations[0]?.body).toEqual({ kind: 'explain_application' })
  await expect(
    page.getByRole('button', { name: 'Create rollback proposal' }),
  ).toBeDisabled()
  await page.reload()
  await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
  expect(fixture.mutations).toHaveLength(1)
})

test('uncertain POST is not retried; durable history must be refreshed before another action', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { uncertain: true })
  await page.goto('/projects/demo/ai')
  await page
    .getByRole('button', { name: 'Investigate incident', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText('outcome is unknown')
  await expect(
    page.getByRole('button', { name: 'Investigate incident', exact: true }),
  ).toBeDisabled()
  expect(fixture.wasCreated()).toBeTruthy()
  await page.getByRole('button', { name: 'Refresh AI' }).click()
  await expect(
    page.getByRole('button', { name: 'Investigate incident', exact: true }),
  ).toBeEnabled()
  await page.getByRole('link', { name: new RegExp(runId) }).click()
  await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
  expect(fixture.mutations).toHaveLength(1)
})

for (const scenario of [
  { runKind: 'explain_application' },
  { runState: 'abstained' },
  { runBase: null },
  { stale: true },
]) {
  test(`prevents unsupported proposal ${JSON.stringify(scenario)}`, async ({
    page,
  }) => {
    const fixture = await aiFixture(page, scenario)
    await page.goto(`/projects/demo/ai?run=${runId}`)
    await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Create rollback proposal' }),
    ).toBeDisabled()
    expect(fixture.mutations).toHaveLength(0)
  })
}
for (const scenario of [
  { expired: true, proposalState: 'approved' },
  { stale: true, proposalState: 'approved' },
  { proposalState: 'executed' },
]) {
  test(`disables unavailable execution ${JSON.stringify(scenario)}`, async ({
    page,
  }) => {
    const fixture = await aiFixture(page, scenario)
    await page.goto(`/projects/demo/ai?proposal=${proposalId}`)
    await expect(
      page.getByText('Review rollback', { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Review execution' }),
    ).toBeDisabled()
    expect(fixture.mutations).toHaveLength(0)
  })
}

test('keeps policy editing for platform admins with explicit project confirmation', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { admin: true })
  await page.goto('/projects/demo/ai')
  await page.getByRole('button', { name: 'Change classification' }).click()
  await page.getByRole('combobox').selectOption('restricted')
  await expect(
    page.getByRole('button', { name: 'Save classification' }),
  ).toBeDisabled()
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page.getByRole('button', { name: 'Save classification' }).click()
  await expect(
    page.getByText('Classification: restricted.', { exact: false }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Explain application', exact: true }),
  ).toBeDisabled()
  expect(fixture.mutations[0]?.body).toEqual({ classification: 'restricted' })
})

test('automation can read history but cannot start runs, manage proposals or edit policy', async ({
  page,
}) => {
  const fixture = await aiFixture(page, {
    human: false,
    admin: true,
    proposalState: 'approved',
  })
  await page.goto(`/projects/demo/ai?proposal=${proposalId}`)
  await expect(
    page.getByRole('button', { name: 'Explain application', exact: true }),
  ).toBeDisabled()
  await expect(
    page.getByRole('button', { name: 'Change classification' }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('button', { name: 'Review execution' }),
  ).toBeDisabled()
  expect(fixture.mutations).toHaveLength(0)
})

test('project navigation clears selected evidence and paginates project history', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { pagination: true })
  await page.goto(`/projects/demo/ai?run=${runId}`)
  await expect(page.getByText('A bounded startup diagnosis.')).toBeVisible()
  await page.getByRole('button', { name: 'Older runs' }).click()
  await expect(page.getByText('No runs on this page.')).toBeVisible()
  await page.getByRole('button', { name: 'Latest runs' }).click()
  await expect(
    page.getByRole('link', { name: new RegExp(runId) }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Switch project' }).click()
  await expect(
    page.getByText('other: bounded assistance', { exact: false }),
  ).toBeVisible()
  await expect(page.getByText('A bounded startup diagnosis.')).toHaveCount(0)
  await expect(page.getByText('No runs on this page.')).toBeVisible()
  expect(fixture.mutations).toHaveLength(0)
})

test('API permission changes block subsequent writes until refreshed', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { denied: true })
  await page.goto('/projects/demo/ai')
  await page
    .getByRole('button', { name: 'Explain application', exact: true })
    .click()
  await expect(page.getByRole('alert')).toHaveText('Permission changed')
  await expect(
    page.getByRole('button', { name: 'Explain application', exact: true }),
  ).toBeDisabled()
  expect(fixture.mutations).toHaveLength(1)
})

test('policy dialog supports keyboard cancellation and returns focus at a narrow width', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { admin: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/projects/demo/ai')
  const trigger = page.getByRole('button', { name: 'Change classification' })
  await trigger.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(trigger).toBeFocused()
  expect(fixture.mutations).toHaveLength(0)
})

test('running history is resumed with GETs and blocks another model request', async ({
  page,
}) => {
  const fixture = await aiFixture(page, { running: true })
  await page.goto(`/projects/demo/ai?run=${runId}`)
  await expect(
    page.getByRole('heading', { name: 'Investigate incident · running' }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Investigate incident', exact: true }),
  ).toBeDisabled()
  await page.reload()
  await expect(
    page.getByRole('heading', { name: 'Investigate incident · running' }),
  ).toBeVisible()
  expect(fixture.mutations).toHaveLength(0)
})
