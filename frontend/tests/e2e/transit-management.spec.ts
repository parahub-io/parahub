/**
 * E2E Test: Transit Management CRUD Flow
 *
 * Tests the transit management lifecycle:
 *   1. Alice (as staff) creates a new transit agency
 *   2. Creates stops for the agency
 *   3. Creates a route and assigns stops to it
 *   4. Verifies the route appears in the listing with correct stop count
 *   5. Cleans up created test data via API
 *
 * Requires: seed_test_users (alice with profile)
 */

import { test, expect } from '@playwright/test'
import { execSync } from 'child_process'
import * as fs from 'fs'
import * as path from 'path'
import { startCookieCapture } from './webkit-cookies'

const PROJECT_ROOT = '/opt/parahub'

// ─── Helpers ──────────────────────────────────────────────

function getTestUserPassword(username: string): string {
  if (process.env.TEST_USER_PASSWORD) return process.env.TEST_USER_PASSWORD
  const passwordFile = path.resolve(__dirname, '../../../.test_users_password')
  const content = fs.readFileSync(passwordFile, 'utf-8')
  const match = content.match(new RegExp(`^${username}:(.+)$`, 'm'))
  if (!match) throw new Error(`Password not found for ${username} in .test_users_password`)
  return match[1].trim()
}

function djangoShell(code: string): string {
  return execSync(
    `python3 manage.py shell -c "${code.replace(/"/g, '\\"')}"`,
    { cwd: PROJECT_ROOT, stdio: 'pipe' },
  ).toString().trim()
}

// ─── Test Suite ───────────────────────────────────────────

test.describe('Transit Management — CRUD flow', () => {
  const agencyName = `E2E-Transit-${Date.now()}`
  const routeShortName = `E${Date.now().toString().slice(-4)}`
  const routeLongName = 'E2E Alpha — Beta'
  const stopData = [
    { name: `E2E Stop Alpha ${Date.now()}`, lat: 38.7169, lon: -9.1399 },
    { name: `E2E Stop Beta ${Date.now()}`, lat: 38.7223, lon: -9.1393 },
  ]

  test.beforeAll(() => {
    // Make alice a staff user for transit management access
    djangoShell(
      "from identity.models import Account; a = Account.objects.get(username='alice'); a.is_staff = True; a.save(update_fields=['is_staff'])",
    )
    // Clean up any existing managed agencies owned by alice
    djangoShell(
      "from geo.models import Agency; from identity.models import Profile; p = Profile.objects.get(account__username='alice'); Agency.objects.filter(owner=p, is_managed=True).delete()",
    )
  })

  test.afterAll(() => {
    // Delete any remaining e2e data sources (cascades to Agency, Shape, Stop, Route, Vehicle, CalendarDate)
    djangoShell(
      "from geo.models import TransitDataSource; TransitDataSource.objects.filter(slug__startswith='e2e-transit-').delete()",
    )
    // Revert alice's staff status
    djangoShell(
      "from identity.models import Account; a = Account.objects.get(username='alice'); a.is_staff = False; a.save(update_fields=['is_staff'])",
    )
  })

  test('create agency → stops → route with stops → verify listing → cleanup', async ({ page }) => {
    test.setTimeout(120_000)

    // Skip onboarding modal
    await page.addInitScript(() => {
      localStorage.setItem('parahub_onboarding_seen', '1')
    })

    // Capture session cookies before login (WebKit drops Secure cookies over HTTP)
    const fixCookies = startCookieCapture(page)

    // ── Step 1: Login as alice ─────────────────────────────────

    await page.goto('/login')
    await page.waitForLoadState('load')

    const loginBtn = page.locator('button[type="submit"]')
    await expect(loginBtn).toBeVisible({ timeout: 15_000 })
    await page.waitForFunction(() => {
      const btn = document.querySelector('button[type="submit"]')
      return btn && getComputedStyle(btn).backgroundColor !== 'rgba(0, 0, 0, 0)'
    }, { timeout: 15_000 })

    await page.locator('input[type="text"], input[type="email"]').first().fill('alice@test.parahub.io')
    await page.locator('input[type="password"]').fill(getTestUserPassword('alice'))
    await loginBtn.click()
    await page.waitForURL('/', { timeout: 20_000 })

    // Fix WebKit Secure cookie issue
    await fixCookies()

    await page.waitForTimeout(2000)

    const sessionOk = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/v1/auth/session/', { credentials: 'include' })
        return res.ok
      } catch {
        return false
      }
    })
    if (!sessionOk) throw new Error('Authentication failed for alice')

    // ── Step 2: Navigate to transit management ─────────────────

    await page.goto('/dispatch/routes')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    // Verify we have staff access (heading visible, not staff-only message)
    await expect(page.locator('h1').filter({ hasText: 'Route Management' })).toBeVisible({ timeout: 10_000 })

    // ── Step 3: Create transit agency ──────────────────────────

    const createAgencyBtn = page.getByRole('button', { name: 'Create Agency' })
    await expect(createAgencyBtn).toBeVisible({ timeout: 10_000 })
    await createAgencyBtn.click()

    // Fill agency form in modal
    const agencyModal = page.locator('[role="dialog"]')
    await expect(agencyModal).toBeVisible({ timeout: 5_000 })
    await agencyModal.locator('input[type="text"]').first().fill(agencyName)

    // Submit (the submit button inside the modal)
    await agencyModal.locator('button[type="submit"]').click()

    // Modal should close
    await expect(agencyModal).not.toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(1000)

    // Should now see empty routes state with "No routes yet"
    await expect(page.getByText('No routes yet')).toBeVisible({ timeout: 10_000 })

    // ── Step 4: Navigate to stops page and create stops ────────

    await page.goto('/dispatch/stops')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    for (const stop of stopData) {
      const newStopBtn = page.getByRole('button', { name: 'New Stop' })
      await expect(newStopBtn).toBeVisible({ timeout: 10_000 })
      await newStopBtn.click()

      // Fill stop form in modal
      const stopModal = page.locator('[role="dialog"]')
      await expect(stopModal).toBeVisible({ timeout: 5_000 })

      // Stop name
      await stopModal.locator('input[type="text"]').fill(stop.name)

      // Latitude and Longitude
      const numInputs = stopModal.locator('input[type="number"]')
      await numInputs.first().fill(String(stop.lat))
      await numInputs.last().fill(String(stop.lon))

      // Submit
      await stopModal.locator('button[type="submit"]').click()
      await expect(stopModal).not.toBeVisible({ timeout: 10_000 })
      await page.waitForTimeout(500)
    }

    // Verify both stops appear in the list
    for (const stop of stopData) {
      await expect(page.getByText(stop.name)).toBeVisible({ timeout: 5_000 })
    }

    // ── Step 5: Navigate back to routes and create a route ─────

    await page.goto('/dispatch/routes')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    const newRouteBtn = page.getByRole('button', { name: 'New Route' }).first()
    await expect(newRouteBtn).toBeVisible({ timeout: 10_000 })
    await newRouteBtn.click()

    // Fill route form in modal
    const routeModal = page.locator('[role="dialog"]')
    await expect(routeModal).toBeVisible({ timeout: 5_000 })

    // Short name (placeholder: "e.g. 42")
    await routeModal.locator('input[placeholder="e.g. 42"]').fill(routeShortName)

    // Long name (placeholder contains "Airport")
    await routeModal.locator('input[placeholder*="Airport"]').fill(routeLongName)

    // Submit
    await routeModal.locator('button[type="submit"]').click()
    await expect(routeModal).not.toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(1000)

    // ── Step 6: Open route editor and add stops ────────────────

    // Click the route card to open editor
    const routeCard = page.locator('.card').filter({ hasText: routeShortName })
    await expect(routeCard).toBeVisible({ timeout: 10_000 })
    await routeCard.click()

    // Route editor modal opens
    const editorModal = page.locator('[role="dialog"]').filter({
      has: page.locator('h3', { hasText: /Edit Route/ }),
    })
    await expect(editorModal).toBeVisible({ timeout: 5_000 })

    // Add each stop to the outbound direction (default)
    for (const stop of stopData) {
      // Click "Add Stop" button in the editor
      await editorModal.getByRole('button', { name: 'Add Stop' }).click()

      // Add-stop modal opens (separate dialog)
      const addStopDialog = page.locator('[role="dialog"]').filter({
        has: page.locator('h3', { hasText: 'Add Stop' }),
      })
      await expect(addStopDialog).toBeVisible({ timeout: 5_000 })

      // Click the stop by name
      await addStopDialog.locator('button').filter({ hasText: stop.name }).click()

      // Add-stop modal closes
      await expect(addStopDialog).not.toBeVisible({ timeout: 5_000 })
    }

    // Verify stops are in the sequence
    await expect(editorModal.getByText(`Stop sequence (${stopData.length})`)).toBeVisible({ timeout: 5_000 })

    // Save the route
    await editorModal.getByRole('button', { name: 'Save' }).click()

    // Editor modal closes (may take time due to Valhalla shape generation)
    await expect(editorModal).not.toBeVisible({ timeout: 20_000 })
    await page.waitForTimeout(1000)

    // ── Step 7: Verify route in listing ────────────────────────

    const routeEntry = page.locator('.card').filter({ hasText: routeShortName })
    await expect(routeEntry).toBeVisible({ timeout: 10_000 })
    await expect(routeEntry).toContainText(`${stopData.length} outbound`)

    // ── Cleanup: Delete route and stops via API ────────────────

    const stopNames = stopData.map(s => s.name)
    await page.evaluate(async ({ agencyName, stopNames }) => {
      const tokenRes = await fetch('/api/v1/auth/session/token/', { credentials: 'include' })
      const { access_token } = await tokenRes.json()
      const headers: Record<string, string> = {
        'Authorization': `Bearer ${access_token}`,
        'Content-Type': 'application/json',
      }

      // Find our test agency
      const agenciesRes = await fetch('/api/v1/geo/transit/manage/agencies/', {
        credentials: 'include', headers,
      })
      const agencies = await agenciesRes.json()
      const agency = agencies.find((a: any) => a.name === agencyName)
      if (!agency) return

      // Delete routes first
      const routesRes = await fetch(`/api/v1/geo/transit/manage/routes/?agency_id=${agency.id}`, {
        credentials: 'include', headers,
      })
      const routes = await routesRes.json()
      for (const r of routes) {
        await fetch(`/api/v1/geo/transit/manage/routes/${r.id}/`, {
          method: 'DELETE', credentials: 'include', headers,
        })
      }

      // Delete stops
      const stopsRes = await fetch(`/api/v1/geo/transit/manage/stops/?agency_id=${agency.id}`, {
        credentials: 'include', headers,
      })
      const stops = await stopsRes.json()
      for (const s of stops) {
        if (stopNames.includes(s.name)) {
          await fetch(`/api/v1/geo/transit/manage/stops/${s.id}/`, {
            method: 'DELETE', credentials: 'include', headers,
          })
        }
      }
    }, { agencyName, stopNames })
  })
})
