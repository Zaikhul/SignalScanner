import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('Signal Scanner loads and navigation links are visible', async ({ app, screen, browser }) => {
  await app.open('/');

  // Verify core app branding and header
  await expect(browser.locator('header')).toBeVisible();
  await expect(screen.getByText('SignalScanner')).toBeVisible();

  // Verify main navigation links
  await expect(screen.getByRole('link', { name: /Live Scan/i })).toBeVisible();
  await expect(screen.getByRole('link', { name: /Channel Health/i })).toBeVisible();
  await expect(screen.getByRole('link', { name: /Web Scanner/i })).toBeVisible();
});
