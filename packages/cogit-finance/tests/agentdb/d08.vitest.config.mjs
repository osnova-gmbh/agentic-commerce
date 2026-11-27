import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const templateRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const agentDbCheckout = process.env.COGIT_D08_AGENTDB_CHECKOUT;
if (!agentDbCheckout) {
  throw new Error(
    "Set COGIT_D08_AGENTDB_CHECKOUT to the final AgentDb checkout",
  );
}

export default {
  root: templateRoot,
  cacheDir: resolve(templateRoot, ".quality/d08-vitest-cache"),
  resolve: {
    alias: { "@d08-agentdb": resolve(agentDbCheckout) },
  },
  server: {
    fs: { allow: [templateRoot, resolve(agentDbCheckout)] },
  },
  test: {
    globals: true,
    include: ["tests/agentdb/module_evolution.test.ts"],
    environment: "node",
    fileParallelism: false,
    maxWorkers: 1,
    testTimeout: 300000,
    hookTimeout: 300000,
  },
};
