import { test, expect } from './auth-fixture';

/**
 * Civic opinion polls E2E (PK/civic-polls-system.md).
 *
 * Requires: python3 manage.py seed_test_civic --reset  (fresh polls, alice/bob
 * residency=Barbeita + consent given, votes only on the municipal poll).
 */

const PARISH_POLL = 'Saturday use of the junta hall?';
const MUNI_POLL = 'Budget remainder: solar panels or road repair?';

test.describe('Civic opinion polls', () => {
  test('feed groups by scope with real territory names, hide-voted works', async ({ authenticatedPage: page }) => {
    await page.goto('/governance/polls');

    // Municipal seed poll in the merged feed
    await expect(page.getByText(MUNI_POLL)).toBeVisible({ timeout: 20000 });
    // Sections are headed by real territory names, not generic level words
    await expect(page.locator('h2', { hasText: 'Monção' })).toBeVisible();
    await expect(page.locator('h2', { hasText: 'Barbeita' })).toBeVisible();
    // Opinion badge present
    await expect(page.getByText('Opinion').first()).toBeVisible();
    // Parish poll sits in the same feed — no tab switching needed
    await expect(page.getByText(PARISH_POLL)).toBeVisible();

    // Hide-voted: alice's seeded municipal vote disappears, unvoted parish poll stays
    await page.getByRole('button', { name: 'Hide voted' }).click();
    await expect(page.getByText(MUNI_POLL)).not.toBeVisible();
    await expect(page.getByText(PARISH_POLL)).toBeVisible();
    await page.getByRole('button', { name: 'Show voted' }).click();
    await expect(page.getByText(MUNI_POLL)).toBeVisible();
  });

  test('hide-until-vote, voting, live bars and receipt verification', async ({ authenticatedPage: page }) => {
    await page.goto('/governance/polls');
    await page.getByText(PARISH_POLL).click({ timeout: 20000 });

    // Fresh parish poll: alice has not voted → distribution hidden (U2)
    await expect(page.getByText('Vote to see the results')).toBeVisible({ timeout: 20000 });

    // Vote
    await page.getByRole('button', { name: 'Kids activities' }).click();

    // Distribution unlocks, quantized note shows (n < threshold), receipt appears
    await expect(page.getByText('Vote to see the results')).not.toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Few votes so far/)).toBeVisible();
    await expect(page.getByRole('button', { name: /Verify my vote is counted/ })).toBeVisible();

    // Receipt verifies against the audit chain
    await page.getByRole('button', { name: /Verify my vote is counted/ }).click();
    await expect(page.getByText(/Your vote is in the audit chain/)).toBeVisible({ timeout: 10000 });

    // Change vote (cooldown message tolerated): selected option is highlighted
    await expect(page.getByRole('button', { name: 'Kids activities' })).toBeDisabled();
  });

  test('voted municipal poll shows my selection and dual split', async ({ authenticatedPage: page }) => {
    await page.goto('/governance/polls');
    await page.getByText(MUNI_POLL).click({ timeout: 20000 });

    // Seeded vote exists → results visible immediately with verified split row
    await expect(page.getByText('Results')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/Verified:/).first()).toBeVisible();
    // Where-this-goes efficacy line from seed
    await expect(page.getByText(/Camara Municipal de Moncao/)).toBeVisible();
  });

  test('profile has civic residency section', async ({ authenticatedPage: page }) => {
    await page.goto('/profile?section=civic');
    await expect(page.getByText('My location (civic)').first()).toBeVisible({ timeout: 20000 });
  });

  test('slider poll: anchors, submit, medians', async ({ authenticatedPage: page }) => {
    await page.goto('/governance/polls');
    await page.getByText('Norte funding priorities (sliders)').click({ timeout: 20000 });

    // Hidden until own submission (U2)
    await expect(page.getByText('Vote to see the results')).toBeVisible({ timeout: 20000 });

    // Status-quo-relative anchors render
    await expect(page.getByText('Relative to today’s status quo')).toBeVisible();

    // Move first axis to +2, second to -1, keep third at 0, submit
    const sliders = page.locator('input[type="range"]');
    await sliders.nth(0).fill('2');
    await sliders.nth(1).fill('-1');
    await page.getByRole('button', { name: 'Submit my positions' }).click();

    // Results open: medians appear with anchor wording
    await expect(page.getByText('Vote to see the results')).not.toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Median:/).first()).toBeVisible();
    await expect(page.getByText(/much more/).first()).toBeVisible(); // +2 median anchor on Healthcare
    await expect(page.getByRole('button', { name: /Verify my vote is counted/ })).toBeVisible();
  });
});
