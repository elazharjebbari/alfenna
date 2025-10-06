const { test, expect } = require('@playwright/test');

test('product page no console errors', async ({ page }) => {
  const errors = [];
  page.on('console', msg => {
    const type = msg.type(); const text = msg.text();
    if (type === 'error') errors.push(text);
  });
  await page.goto(process.env.E2E_BASE_URL || 'http://localhost:8000/produits/');
  await page.waitForSelector('[data-cmp="product"]');
  await page.evaluate(() => {
    const consent = document.getElementById('tarteaucitronRoot');
    if (consent && typeof consent.remove === 'function') {
      consent.remove();
    }
  });
  const next = page.locator('[data-product-nav="next"]').first();
  if (await next.count()) {
    await next.evaluate(el => {
      if (el && typeof el.click === 'function') {
        el.click();
      }
    });
  }
  expect(errors, 'Console errors should be empty').toEqual([]);
});
