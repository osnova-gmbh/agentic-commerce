/** Verify native artifacts with the installed AgentDb module-kit itself. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const source = resolve(process.argv[2] || process.env.AGENTDB_ROOT || 'C:/cogit/cogit-core/agent-db');
const {parseModuleManifest,manifestDigest,loadModuleBundle,assertTransactionalModuleSql} = await import(pathToFileURL(resolve(source,'packages/module-kit/dist/index.js')).href);
for (const key of ['cogit-finance-catalog','cogit-finance-deals','cogit-messaging']) {
  const directory=resolve('modules',key,'agentdb');
  const manifest=parseModuleManifest(JSON.parse(readFileSync(resolve(directory,'manifest.json'),'utf8')));
  const bundle=await loadModuleBundle(directory,manifestDigest(manifest));
  for (const migration of bundle.manifest.migrations) assertTransactionalModuleSql(Buffer.from(bundle.files.get(migration.path)).toString('utf8'));
  console.log(`${key}: ${bundle.manifest.exports.length} exports; ${bundle.artifactSha256}`);
}
