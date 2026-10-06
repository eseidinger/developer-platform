import { expect, test } from '@playwright/test'

test('renders the portal foundation', async ({ page }) => {
  await page.route('**/portal/config', async (route) => {
    await route.fulfill({
      json: {
        issuer: 'https://identity.example.com/realms/platform',
        client_id: 'platform-portal',
        redirect_uri: 'http://127.0.0.1:5173/',
      },
    })
  })

  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'Developer Platform portal' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in with OIDC' })).toBeVisible()
})
