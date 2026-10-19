import readonlyConfig from './playwright.readonly.config.mjs';

if (process.env.VISION_E2E_ONE_CAPTURE_APPROVED !== 'true') throw new Error('EXPLICIT_ONE_CAPTURE_APPROVAL_REQUIRED');

export default {
  ...readonlyConfig,
  testMatch:'capture-edge-gv.spec.mjs',
  timeout:90_000,
  globalTimeout:180_000,
  workers:1,
  retries:0,
  use:{ ...readonlyConfig.use, storageState:undefined },
};
