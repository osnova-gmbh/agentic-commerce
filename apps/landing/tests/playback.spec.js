// @ts-check
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') });
  await page.clock.pauseAt(new Date('2026-01-01T01:00:00Z'));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
});

test('play is opt-in and advances exactly one stage every six seconds', async ({ page }) => {
  await page.clock.runFor(30000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Pause demo' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#play-demo')).not.toHaveAttribute('aria-describedby', /.+/);
  await page.clock.runFor(5999);
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await page.clock.runFor(1);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await expect(page.locator('#held-amount')).toHaveText('€1,250.00');
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('EVALUATING');
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('RELEASING');
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('SETTLED');
  await expect(page.getByRole('button', { name: 'Replay demo' })).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('button', { name: 'View receipt' })).toBeVisible();
  await page.clock.runFor(30000);
  await expect(page.locator('#deal-state')).toHaveText('SETTLED');
});

test('pause, resume, and replay preserve a single playback timer', async ({ page }) => {
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await page.getByRole('button', { name: 'Pause demo' }).click();
  await page.clock.runFor(20000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('EVALUATING');
  await page.clock.runFor(12000);
  await expect(page.locator('#deal-state')).toHaveText('SETTLED');
  await page.getByRole('button', { name: 'Replay demo' }).click();
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await expect(page.locator('#receipt-button')).toBeHidden();
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
});

test('manual stages and next step pause playback rather than racing the timer', async ({ page }) => {
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(3000);
  await page.getByRole('button', { name: 'Stage 3: Work delivered', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Play demo', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await page.clock.runFor(15000);
  await expect(page.locator('#deal-state')).toHaveText('EVALUATING');
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await page.clock.runFor(15000);
  await expect(page.locator('#deal-state')).toHaveText('RELEASING');
  await expect(page.getByRole('button', { name: 'Play demo', exact: true })).toHaveAttribute('aria-pressed', 'false');
});

test('switching scenarios stops the previous timer and refund playback stops at its own outcome', async ({ page }) => {
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await page.getByRole('button', { name: 'Missed deadline', exact: true }).click();
  await page.clock.runFor(20000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDING_REQUESTED');
  await expect(page.locator('.stage')).toHaveCount(4);
  await expect(page.locator('.stage').first()).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('REFUNDING');
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('REFUNDED');
  await expect(page.locator('#payout-amount')).toHaveText('€1,250.00');
  await expect(page.locator('#play-demo')).toHaveAttribute('aria-pressed', 'false');
  await page.clock.runFor(30000);
  await expect(page.locator('#deal-state')).toHaveText('REFUNDED');
});

test('backgrounding the page pauses playback until the visitor plays again', async ({ page }) => {
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.runFor(20000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await expect(page.locator('#play-demo')).toHaveAttribute('aria-pressed', 'false');
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.runFor(10000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(6000);
  await expect(page.locator('#deal-state')).toHaveText('EVALUATING');
});

test('no step counters or playback instructions appear in either scenario', async ({ page }) => {
  await expect(page.locator('#step-counter, #playback-timing, .playback-status')).toHaveCount(0);
  for (const scenario of ['Approved delivery', 'Missed deadline']) {
    await page.getByRole('button', { name: scenario, exact: true }).click();
    await page.getByRole('button', { name: 'Play demo', exact: true }).click();
    const stages = await page.locator('.stage').count();
    for (let index = 0; index < stages; index += 1) {
      await expect(page.locator('body')).not.toContainText(/STEP \d OF \d|seconds per step|advances every|explore at your pace|replay or explore|press play/i);
      if (index < stages - 1) await page.clock.runFor(6000);
    }
  }
});

test('play and pause are keyboard accessible without moving focus', async ({ page }) => {
  const play = page.locator('#play-demo');
  await play.focus();
  await page.keyboard.press('Enter');
  await expect(play).toHaveAccessibleName('Pause demo');
  await page.clock.runFor(6000);
  await expect(play).toBeFocused();
  await page.keyboard.press('Space');
  await expect(play).toHaveAccessibleName('Play demo');
  await page.clock.runFor(10000);
  await expect(page.locator('#deal-state')).toHaveText('FUNDED');
});
