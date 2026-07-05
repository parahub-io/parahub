import { test as base, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Standing delegations E2E — Phase 2.5.
 *
 * Setup (run before): seed_test_civic --reset + a pending charlie→alice delegation
 * on the Monção municipality (see repo scripts / test runner notes). The creation
 * form itself can't be driven with seed users — profile search excludes test
 * accounts by design — so creation is covered by unit tests + form render.
 *
 * Covers: alice accepts via UI → alice's existing municipal vote materializes for
 * charlie → charlie sees the locked ballot → override unlocks his own ballot.
 */

function pw(username: string): string {
  const content = fs.readFileSync(path.resolve(__dirname, '../../../.test_users_password'), 'utf-8');
  const m = content.match(new RegExp(`^${username}:(.+)$`, 'm'));
  if (!m) throw new Error(`no ${username} password`);
  return m[1].trim();
}

async function login(page: Page, user: string) {
  await page.addInitScript(() => localStorage.setItem('parahub_onboarding_seen', '1'));
  await page.goto('/login');
  await page.locator('input[type="text"], input[type="email"]').first().fill(`${user}@test.parahub.io`);
  await page.locator('input[type="password"]').fill(pw(user));
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL('/', { timeout: 15000 });
}

// The parish poll: seed votes only on the municipal one, so charlie has no own
// ballot here (an own vote would rightly beat the delegation — engine invariant).
const PARISH_POLL = 'Saturday use of the junta hall?';

base.describe('Standing delegations', () => {
  base('accept → materialized vote → locked ballot → override', async ({ browser }) => {
    base.setTimeout(120000);

    // --- alice accepts the pending delegation (idempotent: retries land after accept) ---
    const aliceCtx = await browser.newContext();
    const alice = await aliceCtx.newPage();
    await login(alice, 'alice');
    await alice.goto('/governance/delegations');
    await expect(alice.getByText('My delegations')).toBeVisible({ timeout: 20000 });
    // Wait for the list to load into one of the two valid states, then converge
    const acceptBtn = alice.getByRole('button', { name: 'Accept', exact: true }).first();
    const represents = alice.getByText('You represent');
    const deadline = Date.now() + 25000;
    while (Date.now() < deadline) {
      if (await represents.isVisible().catch(() => false)) break;
      if (await acceptBtn.isVisible().catch(() => false)) { await acceptBtn.click(); break; }
      await alice.waitForTimeout(500);
    }
    await expect(represents).toBeVisible({ timeout: 15000 });

    // --- alice votes on the parish poll → materializes charlie's delegated row ---
    await alice.goto('/governance/polls');
    await alice.getByText(PARISH_POLL).click({ timeout: 20000 });
    const kidsBtn = alice.getByRole('button', { name: 'Kids activities' });
    if (await kidsBtn.isEnabled({ timeout: 10000 }).catch(() => false)) {
      await kidsBtn.click();
      await expect(alice.getByText('Vote to see the results')).not.toBeVisible({ timeout: 15000 });
    }

    // --- charlie sees the locked ballot ---
    const charlieCtx = await browser.newContext();
    const charlie = await charlieCtx.newPage();
    await login(charlie, 'charlie');
    await charlie.goto('/governance/polls');
    await charlie.getByText(PARISH_POLL).click({ timeout: 20000 });
    await expect(charlie.getByText(/Delegated to Alice/i)).toBeVisible({ timeout: 20000 });
    await expect(charlie.getByText(/voted,/)).toBeVisible();

    // Results are open for charlie (his delegated voice counts as cast)
    await expect(charlie.getByText('Vote to see the results')).not.toBeVisible();

    // Override unlocks his own ballot
    await charlie.getByRole('button', { name: 'Vote myself', exact: true }).click();
    await expect(charlie.getByText('Your voice')).toBeVisible();

    // Charlie's delegation dashboard shows his voice in use
    await charlie.goto('/governance/delegations');
    await expect(charlie.getByText(/Your voice is currently cast in \d+ poll/)).toBeVisible({ timeout: 15000 });

    await charlieCtx.close();
    await aliceCtx.close();
  });
});
