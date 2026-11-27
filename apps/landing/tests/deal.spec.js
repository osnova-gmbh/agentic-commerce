// @ts-check
import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('approved delivery keeps funds held until bank-confirmed settlement', async ({ page }) => {
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await expect(page.locator('#held-amount')).toHaveText('€0.00');
  await expect(page.locator('#payout-amount')).toHaveText('€1,237.50');
  await expect(page.locator('#receipt-button')).toBeHidden();
  await page.getByRole('button', { name: 'Stage 1: Terms agreed', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await expect(page.locator('#held-amount')).toHaveText('€0.00');
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('EVALUATING');
  await expect(page.locator('#checks-list')).toContainText('Checking');
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('RELEASING');
  await expect(page.locator('#held-amount')).toHaveText('€1,250.00');
  await expect(page.locator('#checks-list .passed')).toHaveCount(3);
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('SETTLED');
  await expect(page.locator('#held-amount')).toHaveText('€0.00');
  await expect(page.locator('#payout-label')).toHaveText('Seller received');
  await page.getByRole('button', { name: 'View receipt' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('#receipt-details')).toContainText('€12.50');
  await expect(page.getByRole('dialog')).toContainText('DEMO RECEIPT');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'View receipt' })).toBeFocused();
  await page.getByRole('button', { name: 'Replay deal' }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
});

test('missed deadline returns the entire price without a fee', async ({ page }) => {
  await page.getByRole('button', { name: 'Missed deadline', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Missed deadline', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.stage')).toHaveCount(4);
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('REFUNDING');
  await expect(page.locator('#held-amount')).toHaveText('€1,250.00');
  await expect(page.locator('#checks-list')).toContainText('No delivery');
  await expect(page.locator('#checks-note')).toContainText('full refund');
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('REFUNDED');
  await expect(page.locator('#held-amount')).toHaveText('€0.00');
  await expect(page.locator('#payout-label')).toHaveText('Buyer refunded');
  await expect(page.locator('#payout-amount')).toHaveText('€1,250.00');
  await expect(page.locator('#payout-note')).toContainText('no fee');
  await page.getByRole('button', { name: 'Approved delivery', exact: true }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await expect(page.locator('#checks-list .passed')).toHaveCount(0);
  await expect(page.locator('#receipt-button')).toBeHidden();
});

for (const scenario of ['success', 'refund']) {
  test(`${scenario} receipt is explicitly fictional and balances in integer cents`, async ({ page }) => {
    if (scenario === 'refund') await page.getByRole('button', { name: 'Missed deadline', exact: true }).click();
    await page.locator('.stage').last().click();
    await page.getByRole('button', { name: 'View receipt' }).click();
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download JSON' }).click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(`cogit-sample-${scenario}-receipt.json`);
    const path = await download.path();
    expect(path).toBeTruthy();
    if (!path) throw new Error('Receipt download has no local path');
    const receipt = JSON.parse(await readFile(path, 'utf8'));
    expect(receipt).toMatchObject({ illustrative: true, signed: false, real_money: false, currency: 'EUR', held_minor: 0 });
    expect(receipt.seller_minor + receipt.fee_minor + receipt.buyer_refund_minor).toBe(receipt.price_minor);
    expect(receipt.price_minor).toBe(125000);
    expect(receipt.fee_minor).toBe(scenario === 'success' ? 1250 : 0);
    expect(receipt.state).toBe(scenario === 'success' ? 'SETTLED' : 'REFUNDED');
  });
}

test('stages are keyboard accessible and keep focus after rendering', async ({ page }) => {
  const first = page.getByRole('button', { name: 'Stage 1: Terms agreed', exact: true });
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(first).toBeFocused();
  await expect(first).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Space');
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await expect(page.locator('#demo-announcement')).toContainText('Funds held');
});
