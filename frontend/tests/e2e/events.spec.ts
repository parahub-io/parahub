/**
 * E2E Test: Event Creation and RSVP Flow
 *
 * Tests the event lifecycle:
 *   1. Alice creates an online event via the create form
 *   2. Event appears in the events list
 *   3. Bob logs in and RSVPs (GOING) to the event
 *   4. Participant count updates on the event detail page
 *
 * Requires: seed_test_users (alice & bob with profiles)
 */

import { test, expect, type BrowserContext, type Page } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { startCookieCapture } from './webkit-cookies'

// ─── Helpers ──────────────────────────────────────────────

function getTestUserPassword(username: string): string {
  if (process.env.TEST_USER_PASSWORD) return process.env.TEST_USER_PASSWORD
  const passwordFile = path.resolve(__dirname, '../../../.test_users_password')
  const content = fs.readFileSync(passwordFile, 'utf-8')
  const match = content.match(new RegExp(`^${username}:(.+)$`, 'm'))
  if (!match) throw new Error(`Password not found for ${username} in .test_users_password`)
  return match[1].trim()
}

async function loginUser(context: BrowserContext, username: string): Promise<Page> {
  const page = await context.newPage()

  // Skip onboarding modal
  await page.addInitScript(() => {
    localStorage.setItem('parahub_onboarding_seen', '1')
  })

  // Capture session cookies before login (WebKit drops Secure cookies over HTTP)
  const fixCookies = startCookieCapture(page)

  await page.goto('/login')
  await page.waitForLoadState('load')

  // Wait for Vue hydration
  const submitBtn = page.locator('button[type="submit"]')
  await expect(submitBtn).toBeVisible({ timeout: 15_000 })
  await page.waitForFunction(() => {
    const btn = document.querySelector('button[type="submit"]')
    return btn && getComputedStyle(btn).backgroundColor !== 'rgba(0, 0, 0, 0)'
  }, { timeout: 15_000 })

  await page.locator('input[type="text"], input[type="email"]').first().fill(`${username}@test.parahub.io`)
  await page.locator('input[type="password"]').fill(getTestUserPassword(username))
  await submitBtn.click()
  await page.waitForURL('/', { timeout: 20_000 })

  // Fix WebKit Secure cookie issue
  await fixCookies()

  await page.waitForTimeout(2000)

  // Verify session
  const sessionOk = await page.evaluate(async () => {
    try {
      const res = await fetch('/api/v1/auth/session/', { credentials: 'include' })
      return res.ok
    } catch {
      return false
    }
  })
  if (!sessionOk) throw new Error(`Authentication failed for ${username}`)

  return page
}

// ─── Test Suite ───────────────────────────────────────────

test.describe('Events — create and RSVP', () => {
  const eventTitle = `E2E-Event-${Date.now()}`
  const eventDescription = 'This is an automated E2E test event for testing the creation and RSVP flow.'

  test('full cycle: create event → verify in list → RSVP → verify participant count', async ({ browser }) => {
    test.setTimeout(120_000)

    const aliceCtx = await browser.newContext()
    const bobCtx = await browser.newContext()

    try {
      // ── Step 1: Alice logs in and creates an event ─────────────

      const alicePage = await loginUser(aliceCtx, 'alice')

      // Navigate to create event page
      await alicePage.goto('/events/create')
      await alicePage.waitForLoadState('domcontentloaded')

      // Wait for the form heading
      await expect(alicePage.locator('h1')).toContainText('Create Event', { timeout: 10_000 })

      // Scope all form interactions within the <form> element
      const form = alicePage.locator('form')

      // Fill title (use placeholder to disambiguate from category/location text inputs)
      await form.getByPlaceholder('Morning run in the park').fill(eventTitle)

      // Fill description
      await form.locator('textarea').fill(eventDescription)

      // Select ONLINE type (avoids map interaction — simpler for E2E)
      await form.locator('button[type="button"]').filter({ hasText: 'Online' }).click()

      // Fill start date (tomorrow)
      const tomorrow = new Date()
      tomorrow.setDate(tomorrow.getDate() + 1)
      tomorrow.setHours(14, 0, 0, 0)
      const dateStr = tomorrow.toISOString().slice(0, 16) // YYYY-MM-DDTHH:MM
      await form.locator('input[type="datetime-local"]').first().fill(dateStr)

      // Fill online URL (required for ONLINE events)
      await form.locator('input[type="url"]').first().fill('https://meet.jit.si/e2e-test-event')

      // Submit the form
      const submitBtn = alicePage.locator('button[type="submit"]')
      await expect(submitBtn).toBeEnabled({ timeout: 5_000 })
      await submitBtn.click()

      // Should redirect to event detail page (URL contains ULID, not /create)
      await alicePage.waitForURL(/\/events\/01[A-Z0-9]+/, { timeout: 20_000 })

      // Verify event title is shown on the detail page
      await expect(alicePage.locator('h1').filter({ hasText: eventTitle })).toBeVisible({ timeout: 10_000 })

      // Extract event URL for Bob to visit
      const eventUrl = alicePage.url()

      // ── Step 2: Verify event appears in the events list ────────

      await alicePage.goto('/events')
      await alicePage.waitForLoadState('domcontentloaded')

      // Wait for events to load (grid appears)
      await expect(alicePage.locator('h1').filter({ hasText: 'Events' })).toBeVisible({ timeout: 10_000 })

      // Our event should appear in the list
      await expect(alicePage.getByText(eventTitle).first()).toBeVisible({ timeout: 15_000 })

      // ── Step 3: Bob logs in and RSVPs to the event ─────────────

      const bobPage = await loginUser(bobCtx, 'bob')

      // Navigate to the event detail page
      await bobPage.goto(new URL(eventUrl).pathname)
      await bobPage.waitForLoadState('domcontentloaded')

      // Wait for event title to appear
      await expect(bobPage.locator('h1').filter({ hasText: eventTitle })).toBeVisible({ timeout: 15_000 })

      // Check initial participant count: should show (0)
      const participantsHeading = bobPage.locator('h2').filter({ hasText: 'Participants' })
      await expect(participantsHeading).toBeVisible({ timeout: 10_000 })

      // Click "I'm going" button
      const goingBtn = bobPage.locator('button').filter({ hasText: "I'm going" })
      await expect(goingBtn).toBeVisible({ timeout: 10_000 })
      await goingBtn.click()

      // ── Step 4: Verify RSVP succeeded ──────────────────────────

      // After joining, the button should change to "Leave event"
      await expect(bobPage.locator('button').filter({ hasText: 'Leave event' })).toBeVisible({ timeout: 15_000 })

      // Verify "You are going" text appears
      await expect(bobPage.getByText('You are going')).toBeVisible({ timeout: 5_000 })

      // Verify participant count updated — should show (1) now
      // The participants section header contains the count in format: Participants (1)
      await expect(participantsHeading).toContainText('(1', { timeout: 10_000 })

    } finally {
      await aliceCtx.close()
      await bobCtx.close()
    }
  })
})
