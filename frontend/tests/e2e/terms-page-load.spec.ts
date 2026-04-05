import { test, expect } from '@playwright/test'

test.describe('Terms Page', () => {
  test('should load /terms in Russian without i18n errors', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', error => pageErrors.push(`${error.name}: ${error.message}`))

    // Use prefix URL for Russian locale (strategy: prefix_except_default)
    await page.goto('/ru/about/terms')
    await page.waitForLoadState('networkidle')

    // No 500 error overlay
    await expect(page.locator('text=500')).not.toBeVisible()

    // No i18n SyntaxError (@ escaping issue)
    const syntaxError = pageErrors.find(e => e.includes('SyntaxError'))
    expect(syntaxError, `i18n SyntaxError found: ${syntaxError}`).toBeUndefined()

    // Page content loaded in Russian
    await expect(page.locator('h1')).toContainText('Условия', { timeout: 5000 })
  })

  test('should load /terms in English without i18n errors', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', error => pageErrors.push(`${error.name}: ${error.message}`))

    await page.goto('/about/terms')
    await page.waitForLoadState('networkidle')

    // No 500 error overlay
    await expect(page.locator('text=500')).not.toBeVisible()

    // No i18n SyntaxError
    const syntaxError = pageErrors.find(e => e.includes('SyntaxError'))
    expect(syntaxError, `i18n SyntaxError found: ${syntaxError}`).toBeUndefined()

    // Page content loaded in English
    await expect(page.locator('h1')).toContainText('Terms', { timeout: 5000 })
  })
})
