import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('agentic exploration of Live Scan modes and controls', async ({ app, agent, screen, browser }) => {
  await app.open('/');

  // Verify baseline application load
  await expect(screen.getByText('SignalScanner')).toBeVisible();
  await expect(screen.getByText('Mode Pemindaian')).toBeVisible();

  // Agentic Step: Switch scanning mode
  await agent.act('click the Bluetooth LE mode button');
  await expect(screen.getByText('Bluetooth LE')).toBeVisible();

  // Agentic Step: Switch to Radio SDR mode
  await agent.act('click the Radio SDR mode button');
  await expect(screen.getByText('Radio SDR')).toBeVisible();

  // Agentic Judgment: Validate telemetry & canvas presence
  await agent.assert('the application presents the signal scanning dashboard with mode options and start controls');
});
