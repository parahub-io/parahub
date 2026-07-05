import { test as base, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Household (open-ballot) civic polls E2E — Phase 1.5.
 *
 * Requires setup (idempotent):
 *   python3 manage.py shell < scripts in repo docs — see seed in test run notes
 * The suite logs in as charlie (no PGP key → unsigned vote path).
 */

function getTestUserPassword(username: string): string {
  const passwordFile = path.resolve(__dirname, '../../../.test_users_password');
  const content = fs.readFileSync(passwordFile, 'utf-8');
  const match = content.match(new RegExp(`^${username}:(.+)$`, 'm'));
  if (!match) throw new Error(`No ${username} in .test_users_password`);
  return match[1].trim();
}

const test = base.extend({
  charliePage: async ({ page }, use) => {
    await page.addInitScript(() => localStorage.setItem('parahub_onboarding_seen', '1'));
    await page.goto('/login');
    await page.locator('input[type="text"], input[type="email"]').first().fill('charlie@test.parahub.io');
    await page.locator('input[type="password"]').fill(getTestUserPassword('charlie'));
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL('/', { timeout: 15000 });
    await use(page);
  },
});

const POLL = 'E2E household: balcony herbs or flowers?';

test.describe('Household civic polls', () => {
  test('feed shows household scope, open vote works, ballots visible', async ({ charliePage: page }) => {
    await page.goto('/governance/polls?tab=household');
    await expect(page.getByText(POLL)).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/Home · E2E Home/).first()).toBeVisible();

    // Open the poll — decision-engine UI with civic badges
    await page.getByText(POLL).click();
    await expect(page.getByText('Opinion').first()).toBeVisible({ timeout: 20000 });

    // Vote via the identified engine (charlie has no PGP key → unsigned path).
    // Check the radio inside the option label (option text also appears in results).
    await page.locator('label', { hasText: 'Herbs' }).locator('input[type="radio"]').check();
    await page.getByRole('button', { name: 'Vote', exact: true }).click();

    // Vote persisted: the vote form is replaced by the voted state
    await expect(page.getByRole('button', { name: 'Vote', exact: true })).not.toBeVisible({ timeout: 15000 });

    // Open ballots list shows named votes (alice pre-seeded + charlie just now) —
    // scoped to the section so the poll author line can't satisfy the assertion
    const ballots = page.locator('div.card', { hasText: 'Who voted how' });
    await expect(ballots.getByText(/Alice/)).toBeVisible({ timeout: 15000 });
    await expect(ballots.getByText(/Charlie/)).toBeVisible();
    await expect(ballots.getByText('Herbs')).toBeVisible();
  });
});
