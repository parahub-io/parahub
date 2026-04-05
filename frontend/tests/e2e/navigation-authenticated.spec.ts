import { test, expect } from './auth-fixture';

test.describe('Navigation (authenticated)', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await page.goto('/');
  });

  test('should navigate to Chat page when authenticated', async ({ authenticatedPage: page }) => {
    await page.locator('[data-nav-path="/chat"]').click();
    await expect(page).toHaveURL(/\/chat/);
  });

  test('should navigate to Market page when authenticated', async ({ authenticatedPage: page }) => {
    await page.locator('[data-nav-path="/market"]').click();
    await expect(page).toHaveURL(/\/market/);
  });

  test('should navigate to Map page when authenticated', async ({ authenticatedPage: page }) => {
    await page.locator('[data-nav-path="/map"]').click();
    await expect(page).toHaveURL(/\/map/);
  });

  test('should navigate to Profile page when authenticated', async ({ authenticatedPage: page }) => {
    // Profile link is inside the site menu dropdown
    await page.locator('[data-nav-action="site-menu"]').click();
    await page.locator('[data-nav-path="/profile"]').click();
    await expect(page).toHaveURL(/\/profile/);
  });

  test('should navigate between pages when authenticated', async ({ authenticatedPage: page }) => {
    await page.locator('[data-nav-path="/market"]').click();
    await expect(page).toHaveURL(/\/market/);
    await page.locator('[data-nav-path="/map"]').click();
    await expect(page).toHaveURL(/\/map/);
  });
});
