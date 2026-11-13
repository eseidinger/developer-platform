import { expect, test } from '@playwright/test'

async function mockPortalConfig(page: import('@playwright/test').Page) {
  await page.route('**/portal/config', async (route) => {
    await route.fulfill({
      json: {
        issuer: 'https://identity.example.com/realms/platform',
        client_id: 'platform-portal',
        redirect_uri: 'http://127.0.0.1:5173/',
      },
    })
  })
}

test('orients anonymous visitors toward sign-in', async ({ page }) => {
  await mockPortalConfig(page)

  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'Developer Platform portal' }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Sign in with OIDC' }),
  ).toBeVisible()
})

test('mobile navigation closes with Escape and returns focus', async ({
  page,
}) => {
  await mockPortalConfig(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')

  const menuButton = page.getByRole('button', { name: 'Open navigation' })
  await menuButton.focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: 'Workspace navigation' })
  await expect(
    drawer.getByRole('link', { name: 'Platform admin' }),
  ).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(menuButton).toBeFocused()

  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(page.locator('main')).toHaveCSS(
      'padding-left',
      width < 768 ? '0px' : '248px',
    )
    const horizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
    expect(horizontalOverflow).toBe(false)
    if (process.env.PLAN042_SCREENSHOT_DIR) {
      await page.screenshot({
        path: `${process.env.PLAN042_SCREENSHOT_DIR}/home-${width}.png`,
        fullPage: true,
        animations: 'disabled',
      })
    }
  }

  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(page.locator('main')).toHaveCSS('transition-duration', '0s')
})
