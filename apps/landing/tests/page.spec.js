// @ts-check
import { test, expect } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

test('local assets load with no browser errors, external requests, or broken anchors', async ({ page, request }) => {
  /** @type {string[]} */
  const errors = [];
  /** @type {string[]} */
  const external = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('request', (sent) => { if (!sent.url().startsWith('http://127.0.0.1:4173/')) external.push(sent.url()); });
  await page.goto('/');
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveTitle(/Cogit Finance/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Trust closes');
  const missing = await page.locator('a[href^="#"]').evaluateAll((links) => links
    .map((link) => link.getAttribute('href') || '')
    .filter((href) => href.length > 1 && !document.getElementById(href.slice(1))));
  expect(missing).toEqual([]);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
  const spec = await request.get('/SPEC.md');
  expect(spec.status()).toBe(200);
  expect(await spec.text()).toContain('# Spec: Agentic Commerce escrow');
  expect((await request.get('/package.json')).status()).toBe(404);
  expect((await request.get('/.env')).status()).toBe(404);
  expect((await request.get('/constructor')).status()).toBe(404);
  expect((await request.post('/')).status()).toBe(405);
});

test('preview meets automated WCAG AA checks in both scenarios and the receipt', async ({ page }) => {
  await page.goto('/');
  const scan = async () => {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(results.violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) }))).toEqual([]);
  };
  await scan();
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await scan();
  await page.getByRole('button', { name: 'Missed deadline', exact: true }).click();
  await page.locator('.stage').last().click();
  await scan();
  await page.getByRole('button', { name: 'View receipt' }).click();
  await scan();
});

test('navigation and FAQ work, including the mobile menu', async ({ page, isMobile }) => {
  await page.goto('/');
  if (isMobile) {
    await page.getByRole('button', { name: 'Menu' }).click();
    await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'true');
    await page.getByRole('navigation').getByRole('link', { name: 'For operators' }).click();
    await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false');
    await page.getByRole('button', { name: 'Menu' }).click();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Menu' })).toBeFocused();
    await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false');
  } else {
    await page.getByRole('navigation').getByRole('link', { name: 'For operators' }).click();
  }
  await expect(page).toHaveURL(/#operators$/);
  const question = page.locator('summary').filter({ hasText: 'When would I use this?' });
  await question.click();
  await expect(page.locator('details[open]')).toContainText('buy a service from another company');
  await question.click();
  await expect(page.locator('details[open]')).toHaveCount(0);
});

test('responsive layout has no horizontal overflow and reduced motion is respected', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  for (const width of [320, 390, 600, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
});

test('copy explains the use case without disclaimer clutter', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#how-it-works')).toContainText('competitor research before a launch');
  await expect(page.locator('#how-it-works')).toContainText('Northstar gets its money back');
  await expect(page.locator('body')).not.toContainText(/handshake|illustrative|simulated|not a live financial service|not real funds/i);
  await page.locator('.stage').last().click();
  await expect(page.locator('body')).not.toContainText(/simulated|sample checks/i);
});

test('capture the visual concept', async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: testInfo.outputPath('landing-full.png'), fullPage: true, animations: 'disabled' });
  await page.locator('.hero').screenshot({ path: testInfo.outputPath('landing-hero.png'), animations: 'disabled' });
  await page.locator('.workspace').screenshot({ path: testInfo.outputPath('deal-workspace.png'), animations: 'disabled' });
});
