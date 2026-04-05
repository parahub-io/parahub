import { test, expect } from '@playwright/test';

test.describe('Navigation (unauthenticated)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for Vue hydration — nav buttons need event handlers attached
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-nav-button]')
      return btn && getComputedStyle(btn).cursor === 'pointer'
    }, { timeout: 15_000 })
  });

  test('should redirect to login when accessing Chat (protected)', async ({ page }) => {
    // For anonymous users, Chat is replaced by Sign in link
    await page.locator('[data-nav-path="/login"]').click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('should allow accessing Market (public)', async ({ page }) => {
    await page.locator('[data-nav-path="/market"]').click();
    await expect(page).toHaveURL(/\/market/);
  });

  test('should allow accessing Map (public)', async ({ page }) => {
    await page.locator('[data-nav-path="/map"]').click();
    await expect(page).toHaveURL(/\/map/);
  });

  test('should have site menu with about link', async ({ page }) => {
    // Open site menu and verify menu items are visible
    await page.locator('[data-nav-action="site-menu"]').click();
    const aboutLink = page.locator('[data-nav-path="/about"]');
    await expect(aboutLink).toBeVisible({ timeout: 5_000 });
  });

  test('should navigate to register via landing page CTA', async ({ page }) => {
    // Landing page "Get Started" links to /register
    await page.getByRole('link', { name: /get started/i }).click();
    await expect(page).toHaveURL(/\/register/);
  });
});
