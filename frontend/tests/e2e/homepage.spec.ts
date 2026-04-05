import { test, expect } from '@playwright/test';

test.describe('Homepage', () => {
  test('should display the homepage with navigation', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveTitle(/Parahub/);
    await expect(page.locator('nav').first()).toBeVisible();

    // Primary nav items visible for anonymous users (Sign in replaces Chat)
    await expect(page.locator('[data-nav-path="/login"]')).toBeVisible();
    await expect(page.locator('[data-nav-path="/market"]')).toBeVisible();
    await expect(page.locator('[data-nav-path="/map"]')).toBeVisible();

    // Site menu button visible
    await expect(page.locator('[data-nav-action="site-menu"]')).toBeVisible();
  });

  test('should navigate to register page when not authenticated', async ({ page }) => {
    await page.goto('/');
    // Landing page has "Get Started" CTA linking to /register
    const ctaLink = page.getByRole('link', { name: /get started/i });
    await expect(ctaLink).toBeVisible();
    await ctaLink.click();
    await expect(page).toHaveURL(/\/register/);
  });

  test('should be responsive on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await expect(page.locator('nav').first()).toBeVisible();
    await expect(page.locator('[data-nav-path="/login"]')).toBeVisible();
  });
});
