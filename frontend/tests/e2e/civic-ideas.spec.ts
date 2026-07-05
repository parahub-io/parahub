import { test, expect } from './auth-fixture';

/**
 * Ideas pipeline E2E — Phase 3.
 * alice proposes an idea for her parish, supports counter shows, bob supports it.
 * Requires seed_test_civic --reset (residency + consent for seed users).
 */

test.describe('Civic ideas', () => {
  test('propose and support an idea', async ({ authenticatedPage: page }) => {
    const title = `E2E idea ${Date.now() % 100000}: shade sails for the playground`;

    await page.goto('/governance/ideas');
    await expect(page.getByText('Ideas', { exact: true }).first()).toBeVisible({ timeout: 20000 });

    // Propose
    await page.getByRole('button', { name: /Propose an idea/ }).click();
    await page.locator('input[maxlength="200"]').fill(title);
    await page.locator('textarea').fill('Summer sun makes the playground unusable after 11am.');
    await page.getByRole('button', { name: 'Submit idea', exact: true }).click();

    // Listed with author auto-support 1/N and Supported state
    await expect(page.getByText(title)).toBeVisible({ timeout: 15000 });
    const card = page.locator('div.card', { hasText: title });
    await expect(card.getByText(/1 of \d+/)).toBeVisible();
    await expect(card.getByRole('button', { name: 'Supported', exact: true })).toBeVisible();

    // Toggle off and on
    await card.getByRole('button', { name: 'Supported', exact: true }).click();
    await expect(card.getByText(/0 of \d+/)).toBeVisible({ timeout: 10000 });
    await card.getByRole('button', { name: 'Support', exact: true }).click();
    await expect(card.getByText(/1 of \d+/)).toBeVisible({ timeout: 10000 });
  });
});
