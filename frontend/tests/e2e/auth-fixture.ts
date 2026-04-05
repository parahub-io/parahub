import { test as base } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { startCookieCapture } from './webkit-cookies';

function getTestUserPassword(username = 'alice'): string {
  if (process.env.TEST_USER_PASSWORD) {
    return process.env.TEST_USER_PASSWORD;
  }
  const passwordFile = path.resolve(__dirname, '../../../.test_users_password');
  const content = fs.readFileSync(passwordFile, 'utf-8');
  const match = content.match(new RegExp(`^${username}:(.+)$`, 'm'));
  if (!match) throw new Error(`Could not find ${username} password in .test_users_password`);
  return match[1].trim();
}

export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    // Dismiss onboarding modal for first-time users
    await page.addInitScript(() => {
      localStorage.setItem('parahub_onboarding_seen', '1');
    });

    // Capture session cookies before login (WebKit drops Secure cookies over HTTP)
    const fixCookies = startCookieCapture(page);

    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    const emailInput = page.locator('input[type="text"], input[type="email"]').first();
    await emailInput.fill('alice@test.parahub.io');

    const passwordInput = page.locator('input[type="password"]');
    await passwordInput.fill(getTestUserPassword('alice'));

    const loginButton = page.locator('button[type="submit"]').first();
    await loginButton.click();

    await page.waitForURL('/', { timeout: 15000 });

    // Fix WebKit Secure cookie issue (re-injects cookies without Secure flag)
    await fixCookies();

    await page.waitForTimeout(2000);

    const sessionCheck = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/v1/auth/session/', { credentials: 'include' });
        return res.ok;
      } catch {
        return false;
      }
    });

    if (!sessionCheck) {
      throw new Error('Authentication failed - session check returned false');
    }

    await use(page);
  },
});

export { expect } from '@playwright/test';
