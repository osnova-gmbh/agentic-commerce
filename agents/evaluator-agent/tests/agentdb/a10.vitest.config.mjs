import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const templateRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const agentDbCheckout = process.env.COGIT_A10_AGENTDB_CHECKOUT;
if (!agentDbCheckout) {
  throw new Error('Set COGIT_A10_AGENTDB_CHECKOUT to a read-only AgentDb checkout matching the selected client');
}

export default {
  root: templateRoot,
  cacheDir: resolve(templateRoot, '.quality/a10-vitest-cache'),
  resolve: {
    alias: { '@a10-agentdb': resolve(agentDbCheckout) },
  },
  server: {
    fs: { allow: [templateRoot, resolve(agentDbCheckout)] },
  },
  test: {
    globals: true,
    include: ['tests/agentdb/canonical_root.test.ts'],
    environment: 'node',
    fileParallelism: false,
    maxWorkers: 1,
    testTimeout: 300000,
    hookTimeout: 300000,
  },
};
