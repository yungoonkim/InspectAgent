import { defineConfig } from '@playwright/test';
import path from 'node:path';

const output = process.env.VISION_E2E_OUTPUT;
if (!output) throw new Error('Use npm run test:e2e:readonly for preflight and isolated output');

export default defineConfig({
  testDir: './playwright',
  testMatch: 'readonly.spec.mjs',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 45_000,
  globalTimeout: 240_000,
  expect: { timeout: 8_000 },
  outputDir: path.join(output, 'artifacts'),
  reporter: [['list'], ['json', { outputFile: path.join(output, 'results.json') }],
    ['html', { outputFolder: path.join(output, 'html'), open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1600, height: 1000 },
    serviceWorkers: 'block',
    actionTimeout: 8_000,
    navigationTimeout: 15_000,
    screenshot: 'only-on-failure',
    trace: 'off',
    video: 'off',
    storageState: process.env.VISION_E2E_STORAGE_STATE || undefined,
    launchOptions: { args: ['--disable-gpu', '--no-proxy-server', '--disable-background-networking'] },
  },
});
