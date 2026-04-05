/**
 * E2E Test: Contract Creation + Dual Signing Flow
 *
 * Tests the full contract lifecycle:
 *   1. Alice creates a contract with Bob (PGP-signed)
 *   2. Bob sees the contract in his pending list
 *   3. Bob signs the contract (file verification + PGP signature)
 *   4. Contract status changes to SIGNED (Active tab)
 *   5. Alice marks as completed with review
 *   6. Bob marks as completed with review
 *   7. Contract status changes to COMPLETED
 *
 * Requires: seed_test_users (alice & bob with WoT-verified profiles)
 */

import { test, expect, type BrowserContext, type Page } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { startCookieCapture } from './webkit-cookies'

// ─── Types ────────────────────────────────────────────────

interface PGPKeyPair {
  publicKey: string
  privateKey: string
  fingerprint: string
}

// ─── Helpers ──────────────────────────────────────────────

const TEST_FILE = '/tmp/e2e-contract-test.txt'

function getTestUserPassword(username: string): string {
  if (process.env.TEST_USER_PASSWORD) return process.env.TEST_USER_PASSWORD
  const passwordFile = path.resolve(__dirname, '../../../.test_users_password')
  const content = fs.readFileSync(passwordFile, 'utf-8')
  const match = content.match(new RegExp(`^${username}:(.+)$`, 'm'))
  if (!match) throw new Error(`Password not found for ${username} in .test_users_password`)
  return match[1].trim()
}

/**
 * Generate PGP key pair using openpgp in Node.js context.
 * Ed25519/Curve25519 — same type as the frontend generates.
 */
async function generateKeyPair(name: string, email: string): Promise<PGPKeyPair> {
  const openpgp = await import('openpgp')
  const { privateKey, publicKey } = await openpgp.generateKey({
    type: 'ecc',
    curve: 'curve25519',
    userIDs: [{ name, email }],
    format: 'armored',
  })
  const keyObj = await openpgp.readKey({ armoredKey: publicKey })
  const fingerprint = keyObj.getFingerprint()
  return { publicKey, privateKey, fingerprint }
}

/**
 * Login user via UI, inject PGP keys into localStorage, upload public key to server.
 * Returns Page + profile ID ready for contract operations.
 */
async function setupUser(
  context: BrowserContext,
  username: string,
  keys: PGPKeyPair,
): Promise<{ page: Page; profileId: string }> {
  const page = await context.newPage()

  // Inject PGP keys + skip onboarding before any navigation
  await page.addInitScript(
    (pgpKeys: { publicKey: string; privateKey: string; fingerprint: string }) => {
      localStorage.setItem('parahub_onboarding_seen', '1')
      localStorage.setItem('parahub_pgp_keys', JSON.stringify(pgpKeys))
    },
    { publicKey: keys.publicKey, privateKey: keys.privateKey, fingerprint: keys.fingerprint },
  )

  // Capture session cookies before login (WebKit drops Secure cookies over HTTP)
  const fixCookies = startCookieCapture(page)

  // Login through UI — wait for hydration before interacting
  await page.goto('/login')
  await page.waitForLoadState('load')
  // Wait for Vue hydration: the styled submit button indicates client JS is ready
  const submitBtn = page.locator('button[type="submit"]')
  await expect(submitBtn).toBeVisible({ timeout: 15_000 })
  // Wait for hydration by checking for a styled element (Nuxt injects CSS classes)
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

  // Get profile ID + upload PGP key
  const result = await page.evaluate(async (pubKey: string) => {
    // Get JWT token from session
    const tokenRes = await fetch('/api/v1/auth/session/token/', { credentials: 'include' })
    const { access_token } = await tokenRes.json()

    // Get profile ID
    const sessionRes = await fetch('/api/v1/auth/session/', { credentials: 'include' })
    const session = await sessionRes.json()
    const profileId = session.user?.profile?.id || ''

    // Upload PGP public key to server
    const uploadRes = await fetch('/api/v1/profiles/me/keys/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ public_key: pubKey }),
    })

    return { profileId, uploadOk: uploadRes.ok, uploadStatus: uploadRes.status }
  }, keys.publicKey)

  if (!result.uploadOk) {
    throw new Error(`PGP key upload failed for ${username}: HTTP ${result.uploadStatus}`)
  }

  return { page, profileId: result.profileId }
}

// ─── Test Suite ───────────────────────────────────────────

test.describe('Contract lifecycle', () => {
  let aliceKeys: PGPKeyPair
  let bobKeys: PGPKeyPair

  test.beforeAll(async () => {
    // Generate PGP key pairs for both users
    aliceKeys = await generateKeyPair('Alice Anderson', 'alice@test.parahub.io')
    bobKeys = await generateKeyPair('Bob Builder', 'bob@test.parahub.io')

    // Create a deterministic test file
    fs.writeFileSync(TEST_FILE, `E2E contract test file\nTimestamp: ${Date.now()}\n`)
  })

  test.afterAll(() => {
    try { fs.unlinkSync(TEST_FILE) } catch { /* ignore */ }
  })

  test('full cycle: create → dual-sign → dual-complete', async ({ browser }) => {
    test.setTimeout(180_000)

    const aliceCtx = await browser.newContext()
    const bobCtx = await browser.newContext()

    try {
      // ── Setup: login both users + upload PGP keys ────────────

      const { page: alicePage, profileId: aliceId } = await setupUser(aliceCtx, 'alice', aliceKeys)
      const { page: bobPage, profileId: bobId } = await setupUser(bobCtx, 'bob', bobKeys)

      expect(aliceId).toBeTruthy()
      expect(bobId).toBeTruthy()

      const contractTitle = `E2E-Test-${Date.now()}`

      // ── Step 1: Alice creates a contract with Bob ────────────

      // Navigate with ?partner=bobId — auto-opens create modal with Bob pre-selected
      await alicePage.goto(`/contracts?partner=${bobId}`)
      // Don't use networkidle — contracts page has WebSocket connections
      await alicePage.waitForLoadState('domcontentloaded')

      // Create modal should auto-open
      const createModal = alicePage.locator('.fixed.inset-0').first()
      await expect(createModal).toBeVisible({ timeout: 10_000 })

      // Fill contract title (clear pre-filled "F1" placeholder)
      const titleInput = createModal.locator('input[type="text"]').first()
      await titleInput.clear()
      await titleInput.fill(contractTitle)

      // Partner is pre-selected from query param — verify select has value
      const partnerSelect = createModal.locator('select').first()
      await expect(partnerSelect).toHaveValue(bobId, { timeout: 5000 })

      // Switch to "Upload file" mode (default is "Write terms" which hides file input)
      const uploadModeBtn = createModal.locator('button').filter({ hasText: 'Upload file' })
      await uploadModeBtn.click()

      // Upload test file
      const fileInput = createModal.locator('input[type="file"]')
      await fileInput.setInputFiles(TEST_FILE)

      // Wait for SHA256 hash computation to finish (progress bar disappears, hash shows)
      await expect(createModal.locator('text=SHA256:')).toBeVisible({ timeout: 15_000 })

      // Submit — "Create & Sign" button
      const createBtn = createModal.locator('button[type="submit"]')
      await expect(createBtn).toBeEnabled({ timeout: 5000 })
      await createBtn.click()

      // Wait for modal to close — contract created successfully
      await expect(createModal).not.toBeVisible({ timeout: 20_000 })

      // Verify contract appears in alice's pending tab
      await alicePage.waitForTimeout(1000)
      await expect(alicePage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 5000 })

      // ── Step 2: Bob sees the pending contract ────────────────

      await bobPage.goto('/contracts')
      await bobPage.waitForLoadState('domcontentloaded')
      // Wait for the page heading to confirm contracts page loaded
      await expect(bobPage.locator('h1').filter({ hasText: 'Contracts' })).toBeVisible({ timeout: 10_000 })

      // Default tab is "Pending Signature" — contract should be visible
      await expect(bobPage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 15_000 })

      // ── Step 3: Bob signs the contract ───────────────────────

      // Find the contract card containing our title, then find its Sign button
      const bobContractCard = bobPage.locator('.rounded-lg.overflow-hidden').filter({ hasText: contractTitle }).first()
      const signBtn = bobContractCard.locator('button').filter({ hasText: 'Sign' }).first()
      await expect(signBtn).toBeVisible({ timeout: 5000 })
      await signBtn.click()

      // Sign modal opens
      const signModal = bobPage.locator('.fixed.inset-0').first()
      await expect(signModal).toBeVisible({ timeout: 5000 })

      // Verify contract info is shown in modal
      await expect(signModal.locator(`text=${contractTitle}`)).toBeVisible()

      // Upload same file for hash verification
      const verifyFileInput = signModal.locator('input[type="file"]')
      await verifyFileInput.setInputFiles(TEST_FILE)

      // Wait for hash verification — "File verified! Hashes match." text appears
      await expect(signModal.getByText('File verified! Hashes match.')).toBeVisible({ timeout: 15_000 })

      // Click "Sign Contract" button (now enabled after hash match)
      const confirmSignBtn = signModal.locator('button').filter({ hasText: 'Sign Contract' }).first()
      await expect(confirmSignBtn).toBeEnabled({ timeout: 5000 })
      await confirmSignBtn.click()

      // Wait for modal to close — signing succeeded
      await expect(signModal).not.toBeVisible({ timeout: 20_000 })

      // ── Step 4: Verify SIGNED status (Active tab) ────────────

      // Contract should now be in "Active" tab (i18n: contracts.tabs.signed = "Active")
      const bobActiveTab = bobPage.locator('button[role="tab"]').filter({ hasText: 'Active' })
      await bobActiveTab.click()
      await bobPage.waitForTimeout(1000)
      await expect(bobPage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 5000 })

      // Verify from Alice's side too
      await alicePage.reload()
      await alicePage.waitForLoadState('domcontentloaded')
      const aliceActiveTab = alicePage.locator('button[role="tab"]').filter({ hasText: 'Active' })
      await aliceActiveTab.click()
      await alicePage.waitForTimeout(1000)
      await expect(alicePage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 5000 })

      // ── Step 5: Alice marks as completed ─────────────────────

      const aliceContractCard = alicePage.locator('.rounded-lg.overflow-hidden').filter({ hasText: contractTitle }).first()
      const aliceCompleteBtn = aliceContractCard.locator('button').filter({ hasText: 'Complete Contract' }).first()
      await expect(aliceCompleteBtn).toBeVisible({ timeout: 5000 })
      await aliceCompleteBtn.click()

      // Complete modal opens
      const aliceCompleteModal = alicePage.locator('.fixed.inset-0').first()
      await expect(aliceCompleteModal).toBeVisible({ timeout: 5000 })

      // Click 4th star (rating = 4)
      const aliceStars = aliceCompleteModal.locator('button').filter({ hasText: '★' })
      await aliceStars.nth(3).click()

      // Enter review text
      await aliceCompleteModal.locator('textarea').fill('Great collaboration on this E2E test contract!')

      // Submit — "Complete & Submit Review"
      const aliceCompleteSubmit = aliceCompleteModal.locator('button[type="submit"]')
      await aliceCompleteSubmit.click()
      await expect(aliceCompleteModal).not.toBeVisible({ timeout: 15_000 })

      // ── Step 6: Bob marks as completed ───────────────────────

      await bobPage.reload()
      await bobPage.waitForLoadState('domcontentloaded')

      // Contract is still in "Active" tab (needs both to complete for COMPLETED)
      const bobActiveTab2 = bobPage.locator('button[role="tab"]').filter({ hasText: 'Active' })
      await bobActiveTab2.click()
      await bobPage.waitForTimeout(1000)

      const bobContractCard2 = bobPage.locator('.rounded-lg.overflow-hidden').filter({ hasText: contractTitle }).first()
      const bobCompleteBtn = bobContractCard2.locator('button').filter({ hasText: 'Complete Contract' }).first()
      await expect(bobCompleteBtn).toBeVisible({ timeout: 5000 })
      await bobCompleteBtn.click()

      // Complete modal
      const bobCompleteModal = bobPage.locator('.fixed.inset-0').first()
      await expect(bobCompleteModal).toBeVisible({ timeout: 5000 })

      // Click 5th star (rating = 5)
      const bobStars = bobCompleteModal.locator('button').filter({ hasText: '★' })
      await bobStars.nth(4).click()

      // Enter review
      await bobCompleteModal.locator('textarea').fill('Excellent partner. Smooth E2E test.')

      // Submit
      const bobCompleteSubmit = bobCompleteModal.locator('button[type="submit"]')
      await bobCompleteSubmit.click()
      await expect(bobCompleteModal).not.toBeVisible({ timeout: 15_000 })

      // ── Step 7: Verify COMPLETED status ──────────────────────

      // Contract should now be in "Completed" tab
      const bobCompletedTab = bobPage.locator('button[role="tab"]').filter({ hasText: 'Completed' })
      await bobCompletedTab.click()
      await bobPage.waitForTimeout(1000)
      await expect(bobPage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 5000 })

      // Verify from Alice's side
      await alicePage.reload()
      await alicePage.waitForLoadState('domcontentloaded')
      const aliceCompletedTab = alicePage.locator('button[role="tab"]').filter({ hasText: 'Completed' })
      await aliceCompletedTab.click()
      await alicePage.waitForTimeout(1000)
      await expect(alicePage.locator(`text=${contractTitle}`).first()).toBeVisible({ timeout: 5000 })

    } finally {
      await aliceCtx.close()
      await bobCtx.close()
    }
  })
})
