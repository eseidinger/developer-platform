import { expect, test } from '@playwright/test'

test('renders the portal foundation', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'Developer Platform portal' }),
  ).toBeVisible()
})
