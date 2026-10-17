import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('agentic exploration of Web Scanner module and controls', async ({ app, agent, screen, browser }) => {
  await app.open('/');
  await expect(screen.getByText('SignalScanner')).toBeVisible();

  // Agentic Step: Navigate to Web Scanner
  await agent.act('click on the Web Scanner link in the header navigation');
  await expect(browser).toHaveURL(/\/web-scanner/);

  // Agentic Judgment: Confirm Web Scanner banner and controls
  await agent.assert('the page displays Ghost Web Scanner Domain with security scanner controls');
});
