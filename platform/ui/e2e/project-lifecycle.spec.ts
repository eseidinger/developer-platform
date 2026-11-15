import { expect, test } from '@playwright/test'
import { projectFixture } from './project-fixture.ts'

test('project creation returns keyboard focus to its trigger at a narrow width', async ({
  page,
}) => {
  await projectFixture(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/e2e/project-harness.html')

  const trigger = page.getByRole('button', { name: 'New project' })
  await trigger.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Project name')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(trigger).toBeFocused()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false)
})

test('creates, deploys, rolls back, and retires a project through the portal', async ({
  page,
}) => {
  const fixture = await projectFixture(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/e2e/project-harness.html')
  await page.getByRole('button', { name: 'New project' }).click()
  await page.getByLabel('Project name').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Create project' })
    .click()
  await expect(page.getByRole('link', { name: 'demo' })).toBeVisible()
  if (process.env.PLAN042_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.PLAN042_SCREENSHOT_DIR}/projects-1440.png`,
      fullPage: true,
    })
  }
  await page.getByRole('link', { name: 'demo' }).click()
  await expect(
    page.getByText(
      'This project is empty. Deploy an application to create its first revision.',
    ),
  ).toBeVisible()
  if (process.env.PLAN042_SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.PLAN042_SCREENSHOT_DIR}/workspace-1440.png`,
      fullPage: true,
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({
      path: `${process.env.PLAN042_SCREENSHOT_DIR}/workspace-390.png`,
      fullPage: true,
    })
    await page.setViewportSize({ width: 1440, height: 900 })
  }

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
  await expect(page.getByRole('dialog')).toContainText('Namespace project-demo')
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Retire project' })
    .click()
  await expect(page.getByRole('link', { name: 'demo' })).toHaveCount(0)
  await page.getByRole('checkbox', { name: 'Show retired projects' }).check()
  await expect(page.getByRole('link', { name: 'demo' })).toBeVisible()
  await expect(page.getByText('retired', { exact: true })).toBeVisible()
  expect(fixture.isRetired()).toBe(true)
  expect(fixture.unexpected).toEqual([])
  expect(
    fixture.mutations.map(({ method, path }) => `${method} ${path}`),
  ).toEqual([
    'POST /v1/projects',
    'PUT /v1/projects/demo/application',
    'PUT /v1/projects/demo/application',
    'POST /v1/projects/demo/rollback',
    'POST /v1/projects/demo/retire',
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
  ).toEqual(['POST /v1/projects'])
})

test('restores a retired project and allows confirmed complete purge', async ({
  page,
}) => {
  const fixture = await projectFixture(page, { retired: true })
  await page.goto('/e2e/project-harness.html')
  await page.getByRole('checkbox', { name: 'Show retired projects' }).check()
  await page.getByRole('link', { name: 'demo' }).click()
  await page.getByRole('button', { name: 'Restore project' }).click()
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Restore project' })
    .click()
  await expect(
    page.getByRole('button', { name: 'Retire project' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Retire project' }).click()
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Retire project' })
    .click()
  await page.getByRole('checkbox', { name: 'Show retired projects' }).check()
  await page.getByRole('link', { name: 'demo' }).click()
  await page.getByRole('button', { name: 'Permanently purge' }).click()
  await expect(page.getByRole('dialog')).toContainText('backups')
  await expect(
    page.getByRole('dialog').getByRole('button', { name: 'Permanently purge' }),
  ).toBeDisabled()
  await page.getByLabel('Type demo to confirm').fill('demo')
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Permanently purge' })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Projects', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'demo' })).toHaveCount(0)
  expect(fixture.unexpected).toEqual([])
  expect(fixture.mutations.map(({ path }) => path)).toEqual([
    '/v1/operator/projects/demo/restore',
    '/v1/projects/demo/retire',
    '/v1/operator/projects/demo/purge',
  ])
})
