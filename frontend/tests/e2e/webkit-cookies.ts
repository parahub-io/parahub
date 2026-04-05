/**
 * WebKit Secure Cookie Fix for E2E Tests
 *
 * Root cause: Django sets SESSION_COOKIE_SECURE=True (production mode).
 * Chromium/Firefox treat localhost as a secure context, so Secure cookies
 * work over HTTP. WebKit does NOT — it silently drops Secure cookies
 * on plain HTTP connections, breaking session auth in E2E tests.
 *
 * Fix: intercept Set-Cookie response headers during login, capture the
 * sessionid/csrftoken values, and re-inject them via Playwright's
 * addCookies() API without the Secure flag.
 */
import type { Page, Response } from '@playwright/test';

interface CapturedCookies {
  sessionid?: string;
  csrftoken?: string;
}

/**
 * Start capturing session cookies from HTTP responses.
 * Call this BEFORE the login form submission.
 * Returns a fixup function to call AFTER login completes.
 */
export function startCookieCapture(page: Page): () => Promise<void> {
  const captured: CapturedCookies = {};

  const handler = (response: Response) => {
    const setCookie = response.headers()['set-cookie'];
    if (!setCookie) return;
    // Multiple Set-Cookie headers are joined with \n by Playwright
    for (const line of setCookie.split('\n')) {
      const m = line.match(/^(sessionid|csrftoken)=([^;]+)/);
      if (m) captured[m[1] as keyof CapturedCookies] = m[2];
    }
  };

  page.on('response', handler);

  return async () => {
    page.off('response', handler);

    // Only needed for WebKit — Chromium/Firefox handle Secure cookies on localhost
    const browserName = page.context().browser()?.browserType().name();
    if (browserName !== 'webkit') return;

    // Check if browser already has the session cookie (no fix needed)
    const existing = await page.context().cookies();
    if (existing.some(c => c.name === 'sessionid')) return;

    // Inject captured cookies without the Secure flag
    const toAdd: Array<{
      name: string; value: string; domain: string; path: string;
      httpOnly: boolean; secure: boolean; sameSite: 'Lax';
    }> = [];

    if (captured.sessionid) {
      toAdd.push({
        name: 'sessionid',
        value: captured.sessionid,
        domain: 'localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      });
    }

    if (captured.csrftoken) {
      toAdd.push({
        name: 'csrftoken',
        value: captured.csrftoken,
        domain: 'localhost',
        path: '/',
        httpOnly: false,
        secure: false,
        sameSite: 'Lax',
      });
    }

    if (toAdd.length) {
      await page.context().addCookies(toAdd);
    }
  };
}
