const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  // Set viewport size for desktop
  await page.setViewportSize({ width: 1920, height: 1080 });
  
  // Navigate to the homepage
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  
  // Wait a bit for any animations to complete
  await page.waitForTimeout(2000);
  
  // Take a screenshot
  await page.screenshot({ path: '/tmp/s.png', fullPage: true });
  
  console.log('Screenshot saved to /tmp/s.png');
  
  await browser.close();
})();