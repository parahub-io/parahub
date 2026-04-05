import { test, expect } from './auth-fixture';

// Directory page: /directory
// Establishment detail: /org/{slug|id}
// Test data: seeded via `python3 manage.py seed_test_establishments --location lisbon`
// Establishments: Café Central, Pizzeria Napoli, Sushi Garden (all at Rua Augusta 123, Lisboa)

test.describe('Directory — unauthenticated', () => {
  test('shows organizations by default', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Organizations chip should be active (public, no auth needed)
    const orgChip = page.locator('button').filter({ hasText: /organizations|organizações/i });
    await expect(orgChip).toBeVisible({ timeout: 10_000 });

    // People chip should NOT be visible (requires auth)
    const peopleChip = page.locator('button').filter({ hasText: /^people$|^pessoas$/i });
    await expect(peopleChip).not.toBeVisible();

    // Should show organization cards
    const cards = page.locator('a[href*="/org/"]');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
  });

  test('search filters establishments', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Wait for initial results
    const cards = page.locator('a[href*="/org/"]');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });

    // Search for a specific establishment
    const searchInput = page.locator('input[type="text"]');
    await searchInput.fill('Pizzeria');

    // Press Enter to trigger immediate search
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    // Should show only Pizzeria Napoli
    await expect(page.getByText('Pizzeria Napoli')).toBeVisible({ timeout: 10_000 });

    // Other establishments should not be visible
    await expect(page.getByText('Café Central')).not.toBeVisible();
  });

  test('clicking organization navigates to detail page', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Wait for cards
    const cards = page.locator('a[href*="/org/"]');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });

    // Click Café Central card
    const cafeCard = cards.filter({ hasText: 'Café Central' });
    await expect(cafeCard).toBeVisible();
    await cafeCard.click();

    // Should navigate to org detail page
    await page.waitForURL(/\/org\//, { timeout: 10_000 });

    // Detail page should show establishment name
    const heading = page.locator('h1');
    await expect(heading).toContainText('Café Central', { timeout: 10_000 });
  });
});

test.describe('Directory — authenticated', () => {
  test('shows people and organization chips', async ({ authenticatedPage: page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Both chips visible for authenticated users
    const orgChip = page.getByRole('button', { name: /organizations/i });
    await expect(orgChip).toBeVisible({ timeout: 10_000 });

    const peopleChip = page.getByRole('button', { name: /people/i });
    await expect(peopleChip).toBeVisible({ timeout: 10_000 });

    // Partner and membership chips also visible
    const partnersChip = page.getByRole('button', { name: /partners/i });
    await expect(partnersChip).toBeVisible();

    const membershipsChip = page.getByRole('button', { name: /memberships/i });
    await expect(membershipsChip).toBeVisible();
  });

  test('people chip shows user cards', async ({ authenticatedPage: page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Click people chip (use exact match to avoid "My Partners")
    const peopleChip = page.getByRole('button', { name: /^people$/i });
    await expect(peopleChip).toBeVisible({ timeout: 10_000 });
    await peopleChip.click();
    await page.waitForTimeout(1500);

    // Should show user cards with @parahub.io HNA
    const userCards = page.locator('a[href*="/u/"]');
    await expect(userCards.first()).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('Establishment detail page', () => {
  test('shows full establishment info', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Wait for and click Café Central
    const card = page.locator('a[href*="/org/"]').filter({ hasText: 'Café Central' });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    await page.waitForURL(/\/org\//, { timeout: 10_000 });

    // Heading
    const heading = page.locator('h1');
    await expect(heading).toContainText('Café Central', { timeout: 10_000 });

    // Description
    await expect(page.getByText(/pastéis de nata/i)).toBeVisible();

    // Address info
    await expect(page.getByText(/Rua Augusta/)).toBeVisible();

    // Category
    await expect(page.getByText('Cafe & Restaurant')).toBeVisible();

    // Phone
    await expect(page.getByText('+351 21 123 4567')).toBeVisible();
  });

  test('back button navigates to directory', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Navigate to detail
    const card = page.locator('a[href*="/org/"]').filter({ hasText: 'Café Central' });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    await page.waitForURL(/\/org\//, { timeout: 10_000 });

    // Wait for page to load
    await expect(page.locator('h1')).toContainText('Café Central', { timeout: 10_000 });

    // Click back button
    const backButton = page.locator('button').filter({ hasText: /organizations|organizações/i });
    await backButton.click();

    // Should return to directory
    await page.waitForURL(/\/directory/, { timeout: 10_000 });
  });

  test('establishment detail shows address on map', async ({ page }) => {
    await page.goto('/directory');
    await page.waitForLoadState('domcontentloaded');

    // Navigate to Café Central detail
    const card = page.locator('a[href*="/org/"]').filter({ hasText: 'Café Central' });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    await page.waitForURL(/\/org\//, { timeout: 10_000 });

    // Wait for page content
    await expect(page.locator('h1')).toContainText('Café Central', { timeout: 10_000 });

    // Map section should be present (MapLibre canvas or map container)
    const mapContainer = page.locator('.maplibregl-map, [class*="map"]').first();
    await expect(mapContainer).toBeVisible({ timeout: 15_000 });
  });
});
