import { expect, test } from '@playwright/test'
import { projectFixture } from './project-fixture.ts'

test('creates, deploys, rolls back, and retires a project through the portal', async ({
  page,
}) => {
  const fixture = await projectFixture(page)
  await page.goto('/e2e/project-harness.html')
  await page.getByRole('button', { name: 'New project' }).click()
  await page.getByLabel('Project name').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Create project' })
    .click()
  await page.getByRole('link', { name: 'demo' }).click()
  await expect(
    page.getByText(
      'This project is empty. Deploy an application to create its first revision.',
    ),
  ).toBeVisible()

  for (const revision of [1, 2]) {
    await page.getByRole('button', { name: 'Deploy application' }).click()
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Deploy', exact: true })
      .click()
    await expect(
      page.getByText(`Current desired revision: ${revision}.`),
    ).toBeVisible()
  }
  await page.getByRole('button', { name: 'Roll back', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText(
    'Roll back to revision 1',
  )
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Roll back', exact: true })
    .click()
  await expect(page.getByText('Current desired revision: 3.')).toBeVisible()
  await expect(
    page.getByText('Revision 3: succeeded; readiness ready.'),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Retire project' }).click()
  await expect(page.getByRole('dialog')).toContainText('namespace project-demo')
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Retire project' })
    .click()
  await expect(page.getByRole('link', { name: 'demo' })).toBeVisible()
  await expect(page.getByText('retired', { exact: true })).toBeVisible()
  expect(fixture.isRetired()).toBe(true)
  expect(fixture.unexpected).toEqual([])
  expect(
    fixture.mutations.map(({ method, path }) => `${method} ${path}`),
  ).toEqual([
    'POST /projects',
    'PUT /projects/demo',
    'PUT /projects/demo',
    'POST /projects/demo/rollback',
    'POST /projects/demo/retire',
  ])
  expect(
    fixture.mutations.find(({ path }) => path.endsWith('/rollback'))?.ifMatch,
  ).toBe('2')
})

test('keeps a denied project creation visible as an error', async ({
  page,
}) => {
  const fixture = await projectFixture(page, { denyCreate: true })
  await page.goto('/e2e/project-harness.html')
  await page.getByRole('button', { name: 'New project' }).click()
  await page.getByLabel('Project name').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Create project' })
    .click()
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText(
    'Project creation denied',
  )
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(fixture.unexpected).toEqual([])
  expect(
    fixture.mutations.map(({ method, path }) => `${method} ${path}`),
  ).toEqual(['POST /projects'])
})
