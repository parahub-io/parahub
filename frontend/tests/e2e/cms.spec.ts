/**
 * E2E Test: CMS Blog Post Lifecycle
 *
 * Tests the blog post happy path:
 *   1. Alice navigates to the blog create page
 *   2. Creates a new post with title + markdown content and publishes it
 *   3. Post appears on the public /blog feed
 *   4. Edits the post title — verifies changes persist
 *   5. RSS feed includes the published post
 *   6. Deletes the post from manage panel — verifies removal
 *
 * Requires: seed_test_users (alice with WoT 2+)
 */

import { test, expect, type Page } from '@playwright/test'
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

async function loginAsAlice(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('parahub_onboarding_seen', '1')
  })

  const fixCookies = startCookieCapture(page)

  await page.goto('/login')
  await page.waitForLoadState('load')

  const submitBtn = page.locator('button[type="submit"]')
  await expect(submitBtn).toBeVisible({ timeout: 15_000 })
  await page.waitForFunction(() => {
    const btn = document.querySelector('button[type="submit"]')
    return btn && getComputedStyle(btn).backgroundColor !== 'rgba(0, 0, 0, 0)'
  }, { timeout: 15_000 })

  await page.locator('input[type="text"], input[type="email"]').first().fill('alice@test.parahub.io')
  await page.locator('input[type="password"]').fill(getTestUserPassword('alice'))
  await submitBtn.click()
  await page.waitForURL('/', { timeout: 20_000 })

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
}

// ─── Test Suite ───────────────────────────────────────────

test.describe('CMS — blog post lifecycle', () => {
  const postTitle = `E2E-Blog-${Date.now()}`
  const postContent = 'This is automated **E2E test** content for the CMS blog flow.'
  const updatedTitle = `${postTitle}-edited`

  test('create → verify in feed → edit → RSS check → delete', async ({ page }) => {
    test.setTimeout(120_000)

    await loginAsAlice(page)

    // ── Step 1: Navigate to blog create page ──────────────────

    await page.goto('/blog/create')
    await page.waitForLoadState('domcontentloaded')

    // Wait for the form heading
    await expect(page.locator('h1')).toContainText(/Create post|New post|Criar post/i, { timeout: 10_000 })

    // ── Step 2: Fill and publish ──────────────────────────────

    // Fill title
    await page.locator('input[type="text"]').first().fill(postTitle)

    // Fill content in code-mode textarea (default editor mode)
    const textarea = page.locator('.blog-editor textarea')
    await expect(textarea).toBeVisible({ timeout: 5_000 })
    await textarea.fill(postContent)

    // Click Publish button
    const publishBtn = page.locator('button').filter({ hasText: /Publish|Publicar/i })
    await expect(publishBtn).toBeVisible({ timeout: 5_000 })
    await publishBtn.click()

    // Should redirect to the published post detail page /blog/{slug}
    await page.waitForURL(/\/blog\/e2e-blog-/, { timeout: 20_000 })

    // Verify post title on the detail page
    await expect(page.locator('h1').filter({ hasText: postTitle })).toBeVisible({ timeout: 10_000 })

    // Verify rendered content contains the bold text
    await expect(page.locator('.prose')).toContainText('E2E test', { timeout: 5_000 })

    // Save the post URL for later
    const postDetailUrl = page.url()
    const postSlug = new URL(postDetailUrl).pathname.split('/').pop()

    // ── Step 3: Verify post appears on /blog feed ─────────────

    await page.goto('/blog')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.locator('h1').first()).toContainText(/Blog/i, { timeout: 10_000 })
    await expect(page.getByText(postTitle).first()).toBeVisible({ timeout: 15_000 })

    // ── Step 4: Edit the post ─────────────────────────────────

    // Navigate to the post detail and click Edit
    await page.goto(new URL(postDetailUrl).pathname)
    await page.waitForLoadState('domcontentloaded')
    await expect(page.locator('h1').filter({ hasText: postTitle })).toBeVisible({ timeout: 10_000 })

    // Click the edit button/link
    const editLink = page.locator('a').filter({ hasText: /Edit post|Editar post/i })
    await expect(editLink).toBeVisible({ timeout: 5_000 })
    await editLink.click()

    // Should navigate to /blog/create?edit=ULID
    await page.waitForURL(/\/blog\/create\?edit=/, { timeout: 15_000 })

    // Wait for form to load with existing data
    const titleInput = page.locator('input[type="text"]').first()
    await expect(titleInput).toHaveValue(postTitle, { timeout: 10_000 })

    // Clear and type new title
    await titleInput.fill(updatedTitle)

    // Click Publish to save changes
    const publishEditBtn = page.locator('button').filter({ hasText: /Publish|Publicar/i })
    await publishEditBtn.click()

    // Should redirect to the post detail page
    await page.waitForURL(/\/blog\/e2e-blog-/, { timeout: 20_000 })

    // Reload to bypass SPA cache (slug may not change, so useAsyncData returns stale data)
    await page.reload({ waitUntil: 'domcontentloaded' })

    // Verify updated title
    await expect(page.locator('h1').filter({ hasText: updatedTitle })).toBeVisible({ timeout: 10_000 })

    // ── Step 5: Verify RSS feed includes the post ─────────────

    const rssContainsPost = await page.evaluate(async (title) => {
      try {
        const res = await fetch('/api/v1/cms/posts/rss/')
        const xml = await res.text()
        return xml.includes(title)
      } catch {
        return false
      }
    }, updatedTitle)

    expect(rssContainsPost).toBe(true)

    // ── Step 6: Delete the post from manage panel ─────────────

    await page.goto('/u/alice/manage')
    await page.waitForLoadState('domcontentloaded')

    // Wait for the manage page posts list to load
    await expect(page.locator('h1').first()).toContainText(/Manage|Gerenciar/i, { timeout: 10_000 })

    // Find the post row containing our title link
    const postLink = page.locator('a').filter({ hasText: updatedTitle }).first()
    await expect(postLink).toBeVisible({ timeout: 10_000 })

    // Navigate from the link up to the row div (has class p-4), then find the delete button
    // In the row, edit is an <a> (NuxtLink) and delete is the only <button>
    const postRow = postLink.locator('xpath=ancestor::div[contains(@class, "p-4")][1]')
    const deleteBtn = postRow.locator('button').first()
    await deleteBtn.click()

    // Confirm deletion in the modal
    const confirmBtn = page.getByRole('button', { name: /Delete post|Excluir post|Eliminar post/i })
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
    await confirmBtn.click()

    // Wait for deletion to complete — the post should disappear from the list
    await expect(page.getByText(updatedTitle)).toBeHidden({ timeout: 10_000 })

    // ── Step 7: Verify post is gone from /blog feed ───────────

    await page.goto('/blog')
    await page.waitForLoadState('domcontentloaded')

    // Post should no longer appear
    await expect(page.getByText(updatedTitle)).toBeHidden({ timeout: 10_000 })
  })
})
