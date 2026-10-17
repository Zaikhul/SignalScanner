import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('agentic navigation and evaluation of Channel Health diagnostics', async ({ app, agent, screen, browser }) => {
  await app.open('/');
  await expect(screen.getByText('SignalScanner')).toBeVisible();

  // Agentic Step: Navigate to Channel Health from the navigation bar
  await agent.act('navigate to the Channel Health page via header link');
  await expect(browser).toHaveURL(/\/channel-health/);

  // Agentic Step: Toggle frequency band to 5 GHz
  await agent.act('click the 5 GHz band button');
  await expect(screen.getByText('5 GHz')).toBeVisible();

  // Agentic Judgment: Confirm diagnostic engine interface
  await agent.assert('the Channel Health recommendation engine displays band controls and diagnostic views');
});
