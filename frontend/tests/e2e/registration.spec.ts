import { test, expect } from '@playwright/test';

/**
 * Registration → Login → Profile flow E2E test.
 *
 * Creates a real user in the database on each run (unique timestamp-based username).
 * Backend rate limit: 3 registrations/hour per IP — run sparingly.
 * PoW (scrypt) runs client-side in the browser; ~1-2s on server hardware.
 */

function uniqueUsername() {
  return `e2etest${Date.now()}`;
}

const TEST_PASSWORD = 'TestPass123!secure';

test.describe('Registration → Login → Profile', () => {
  // Run only on desktop chromium to avoid hitting rate limits (3/hour per IP).
  // Mobile Chrome also uses chromium engine — skip it to conserve the rate budget.
  test.skip(({ browserName, isMobile }) => browserName !== 'chromium' || isMobile,
    'Registration test runs on desktop chromium only (rate limit: 3/hour)');

  let username: string;

  test.beforeAll(() => {
    username = uniqueUsername();
  });

  test('register new user, login, and verify profile', async ({ page }) => {
    // Increase timeout — PoW computation + registration can take a while
    test.setTimeout(60_000);

    // --- STEP 1: Register ---
    await page.goto('/register');
    await page.waitForLoadState('domcontentloaded');

    // Verify registration form is visible (not disabled)
    await expect(page.locator('#username')).toBeVisible();

    // Fill registration form
    await page.locator('#username').fill(username);
    await page.locator('#password').fill(TEST_PASSWORD);
    await page.locator('#password_confirm').fill(TEST_PASSWORD);

    // Submit — triggers PoW computation + API call
    await page.locator('button[type="submit"]').click();

    // Wait for success state (PoW + registration may take several seconds)
    // Success state shows a checkmark icon and success title
    await expect(page.locator('text=/success|registered|account created/i')).toBeVisible({ timeout: 30_000 });

    // Verify "go to login" link is present (in main content, not nav)
    const loginLink = page.locator('main a').filter({ hasText: /sign in|log in|login/i });
    await expect(loginLink).toBeVisible();

    // --- STEP 2: Navigate to login and authenticate ---
    await loginLink.click();
    await expect(page).toHaveURL(/\/login/);

    // Fill login form
    await page.locator('#username').fill(username);
    await page.locator('#password').fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').click();

    // Wait for redirect to homepage after login
    await page.waitForURL('/', { timeout: 15_000 });

    // Verify authenticated session
    const sessionOk = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/v1/auth/session/', { credentials: 'include' });
        return res.ok;
      } catch {
        return false;
      }
    });
    expect(sessionOk).toBe(true);

    // --- STEP 3: Dismiss onboarding modal if present ---
    const onboardingModal = page.locator('text=/welcome to parahub/i');
    if (await onboardingModal.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Click dismiss button or the profile action card
      const dismissBtn = page.locator('button').filter({ hasText: /let.*go|dismiss|close/i });
      if (await dismissBtn.isVisible({ timeout: 1_000 }).catch(() => false)) {
        await dismissBtn.click();
      }
    }

    // --- STEP 4: Navigate to profile and verify ---
    await page.goto('/profile');

    // Dismiss onboarding modal again if it reappeared on profile page
    const onboardingAgain = page.locator('text=/welcome to parahub/i');
    if (await onboardingAgain.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await page.locator('button').filter({ hasText: /let.*go/i }).click();
    }

    // Profile page should show the user's HNA (username@parahub.io)
    // Desktop and mobile layouts have separate elements — verify text appears on page
    await expect(page.locator('body')).toContainText(`${username}@parahub.io`, { timeout: 10_000 });
  });
});
