import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { gateway } from 'ai';
import { openai } from '@ai-sdk/openai';

function resolveModel() {
  if (process.env.OPENAI_API_KEY) {
    return openai(process.env.AI_MODEL ?? 'gpt-4o-mini');
  }
  return gateway(process.env.AI_MODEL ?? 'openai/gpt-4o-mini');
}

export default {
  agents: {
    default: {
      model: resolveModel(),
      system: 'You are an autonomous QA agent for the Signal Scanner application. You understand RF measurements, WiFi channels, and security scanner dashboards. Verify every outcome on screen.',
      context: 'SignalScanner is a real-time signal monitoring application with Live Scan, Channel Health, Sessions, Collectors, and Web Scanner tabs.',
    },
  },
  targets: [
    {
      name: 'chromium',
      engine: web({
        browser: 'chromium',
        viewport: { width: 1280, height: 720 },
      }),
      app: {
        url: process.env.APP_URL ?? 'http://127.0.0.1:3000',
        command: {
          executable: 'node',
          args: ['frontend/node_modules/next/dist/bin/next', 'dev', 'frontend'],
          reuseExisting: true,
          startupTimeout: 120_000,
          log: '.e2e/logs/app.log',
        },
      },
    },
  ],
} satisfies E2EConfig;
