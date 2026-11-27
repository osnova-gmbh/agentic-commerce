import { spawn, spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyModule, initializeApplication } from '@a04-agentdb/packages/deployment/src/index.ts';
import { manifestDigest, parseModuleManifest } from '@a04-agentdb/packages/module-kit/src/index.ts';
import { finalizeArtifactViaApi } from '@a04-agentdb/tests/workspace/artifact-finalize-required.helpers.ts';
import { freeResourcePort } from '@a04-agentdb/tests/workspace/resource-abi-fixture.helpers.ts';
import { startQueryWaitStack } from '@a04-agentdb/tests/workspace/query-wait-stack.helpers.ts';
import { copyPreparedCohort, publishPreparedCohort, removePreparedCohort } from './worker_cohort.ts';

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} for the installed A04 worker proof`);
  return value;
}

const bundlePath = resolve(requiredEnv('COGIT_A04_BUNDLE_PATH'));
const digest = requiredEnv('COGIT_A04_BUNDLE_DIGEST');
const moduleKey = 'cogit.reference-case-agent';
const cli = resolve(requiredEnv('COGIT_A04_RUNTIME_CLI'));
const python = resolve(dirname(cli), process.platform === 'win32' ? 'python.exe' : 'python');
const cohortSource = resolve(requiredEnv('COGIT_A04_COHORT_DIR'));
const templateRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

async function workerOnce(config: { url: string; poolId: string; installationId: string;
  manifestPath: string; receiptPath: string }) {
  const env = { ...process.env,
    COGIT_DEV_MODE: '0',
    COGIT_AGENT_API_KEY: '',
    COGIT_AGENTDB_URL: config.url,
    COGIT_AGENTDB_API_VERSION: '0.1.0',
    COGIT_AGENTDB_POOL_ID: config.poolId,
    COGIT_AGENTDB_INSTALLATION_ID: config.installationId,
    COGIT_AGENTDB_WORKER_TOKEN: 'worker-secret-2',
    COGIT_AGENTDB_COHORT_RECEIPT: config.receiptPath,
    DATABASE_URL: '',
    PYTHONPATH: '',
  };
  return await new Promise<{ code: number | null; stdout: string; stderr: string }>((done, fail) => {
    const child = spawn(python, ['-I', '-B', '-m', 'cogit_runtime', 'work',
      '--manifest', config.manifestPath, '--once'], {
      cwd: dirname(bundlePath), env, windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (bytes) => { stdout += String(bytes); });
    child.stderr.on('data', (bytes) => { stderr += String(bytes); });
    child.on('error', fail);
    const timer = setTimeout(() => { child.kill(); fail(new Error('worker timed out')); }, 90000);
    child.on('close', (code) => { clearTimeout(timer); done({ code, stdout, stderr }); });
  });
}

test('installed DatabaseReferenceAgent reuses one committed receipt after worker replacement', async () => {
  const probe = spawnSync(python, ['-I', '-B', '-c',
    'import json, reference_agent; from reference_agent.database_bundle import load_database_bundle; print(json.dumps({"path": reference_agent.__file__, "digest": load_database_bundle()[1]}))'],
    { cwd: dirname(bundlePath), env: { ...process.env, PYTHONPATH: '' }, encoding: 'utf8' });
  expect(probe.status, probe.stderr).toBe(0);
  const installedBundle = JSON.parse(probe.stdout.trim());
  expect(installedBundle.path.toLowerCase()).toContain('site-packages');
  expect(installedBundle.digest).toBe(digest);
  expect(await readFile(resolve(cohortSource, 'cogit.yaml'), 'utf8')).toContain(digest);
  const project = `a04w${randomUUID().slice(0, 8)}`;
  const port = await freeResourcePort();
  const adminPort = await freeResourcePort();
  const cohort = await copyPreparedCohort(cohortSource, 'a04', 'reference_agent.database_example:DatabaseReferenceAgent');
  let stack: Awaited<ReturnType<typeof startQueryWaitStack>>;
  try {
    stack = await startQueryWaitStack({ project, port, adminPort });
  } catch (error) {
    await removePreparedCohort(cohort);
    throw error;
  }
  let mode: 'drop' | 'pass' = 'drop';
  let committedPut = 0;
  let committedResult: unknown;
  let putCalls = 0;
  const proxy = createServer(async (request, response) => {
    try {
      const parts: Buffer[] = [];
      for await (const chunk of request) parts.push(Buffer.from(chunk));
      const headers: Record<string, string> = {};
      for (const [name, value] of Object.entries(request.headers)) {
        if (typeof value === 'string' && !['host', 'connection', 'content-length', 'transfer-encoding'].includes(name)) headers[name] = value;
      }
      const upstream = await fetch(stack.apiBaseUrl() + request.url, {
        method: request.method, headers,
        ...(parts.length ? { body: Buffer.concat(parts) } : {}),
      });
      const body = Buffer.from(await upstream.arrayBuffer());
      if (request.url?.endsWith('/commands/requests.put')) {
        putCalls += 1;
        if (mode === 'drop') {
          committedPut = upstream.status;
          committedResult = JSON.parse(body.toString('utf8'));
          response.destroy();
          return;
        }
      }
      response.writeHead(upstream.status, { 'content-type': upstream.headers.get('content-type') ?? 'application/json' });
      response.end(body);
    } catch {
      response.destroy();
    }
  });
  try {
    const published = await publishPreparedCohort(stack, cohort, python, templateRoot, project);
    const manifest = parseModuleManifest(JSON.parse(await readFile(resolve(bundlePath, 'manifest.json'), 'utf8')));
    expect(manifestDigest(manifest)).toBe(digest);
    const exports = manifest.exports.filter((item) => ['requests.put', 'requests.get'].includes(item.key))
      .map((item) => ({ kind: item.kind, key: item.key, export_version: item.version, contract_id: item.contractId }));
    expect(exports).toHaveLength(2);
    const tenantId = stack.ids['tenantA']!;
    const installationId = published.installationId;
    const config = { ...stack.apiConnection, user: 'agentdb_migrator' };
    await initializeApplication(config, { applicationKey: `test.${project}`, mode: 'attach', tenantId,
      operatorPrincipalId: stack.ids['ada']! });
    const installed = await applyModule(config, { tenantId, installationId, bundlePath,
      approvedArtifactSha256: digest, requirements: [{ module_key: moduleKey,
        version: manifest.version, artifact_sha256: digest, exports }] },
      [{ moduleKey, artifactSha256: digest }]);
    expect(installed.status).toBe('installed');
    const poolId = published.poolId;
    expect(poolId).toMatch(/^[0-9a-f-]{36}$/);
    const readiness = await stack.get(`/v1/worker/module-readiness?installationId=${installationId}`,
      stack.worker('worker-2', `${project}-readiness`));
    expect(readiness.status, JSON.stringify(readiness.body)).toBe(200);
    expect(readiness.body).toMatchObject({ ready: true, installationId,
      agentVersionId: published.versionId, deploymentId: published.deploymentId,
      poolId, cohortStatus: 'active' });
    await new Promise<void>((ok) => proxy.listen(0, '127.0.0.1', ok));
    const address = proxy.address();
    if (!address || typeof address === 'string') throw new Error('proxy address unavailable');
    const url = `http://127.0.0.1:${address.port}`;
    const requestId = `request-${project}`;
    const description = 'One durable A04 worker effect.';
    const text = JSON.stringify({ request_id: requestId, description });
    const artifact = await finalizeArtifactViaApi(stack, text, `${project}-input`, { mediaType: 'application/json' });
    const admitted = await stack.post('/v1/queries', { installationId,
      input: { text, sha256: artifact.sha256 } }, stack.ada(`${project}-admit`));
    expect(admitted.status, JSON.stringify(admitted.body)).toBe(202);
    await stack.publishPending();
    const first = await workerOnce({ url, poolId, installationId,
      manifestPath: published.manifestPath, receiptPath: published.receiptPath });
    expect(first.code).toBe(1);
    expect(first.stderr).toContain('AgentDbReconciliationRequiredError');
    const rowTable = `tenant_t_${tenantId.replaceAll('-', '')}.reference_agent_requests`;
    const rows1 = await stack.ownerQuery(`SELECT object_id,request_id,description,revision FROM ${rowTable} WHERE request_id=$1`, [requestId]);
    const receipts1 = await stack.ownerQuery("SELECT run_id,worker_request_id,encode(request_sha256,'hex') AS request_sha256,result FROM core.module_worker_receipts WHERE tenant_id=$1 AND run_id=$2 AND module_key=$3 AND export_key='requests.put'", [tenantId, String(admitted.body['runId']), moduleKey]);
    expect(committedPut).toBe(200);
    expect(rows1.rows).toHaveLength(1);
    expect(receipts1.rows).toHaveLength(1);
    expect(receipts1.rows[0]?.['result']).toEqual(committedResult);
    const attempts = await stack.ownerQuery('SELECT a.attempt_id FROM core.work_attempts a JOIN core.work_items w USING(tenant_id,work_item_id) WHERE w.run_id=$1 AND a.lifecycle=$2', [String(admitted.body['runId']), 'active']);
    expect(attempts.rows).toHaveLength(1);
    const firstAttemptId = String(attempts.rows[0]['attempt_id']);
    await stack.expireFixtureAttempt(firstAttemptId);
    await stack.projectFailedFixtureJobs();
    await stack.reconcileQueue();
    mode = 'pass';
    const second = await workerOnce({ url, poolId, installationId,
      manifestPath: published.manifestPath, receiptPath: published.receiptPath });
    const rows2 = await stack.ownerQuery(`SELECT object_id,request_id,description,revision FROM ${rowTable} WHERE request_id=$1`, [requestId]);
    const packageRowCount = await stack.ownerQuery(`SELECT count(*)::int AS count FROM ${rowTable}`);
    const receipts2 = await stack.ownerQuery("SELECT run_id,worker_request_id,encode(request_sha256,'hex') AS request_sha256,result FROM core.module_worker_receipts WHERE tenant_id=$1 AND run_id=$2 AND module_key=$3 AND export_key='requests.put'", [tenantId, String(admitted.body['runId']), moduleKey]);
    expect(rows2.rows).toEqual(rows1.rows);
    expect(packageRowCount.rows[0]?.['count']).toBe(1);
    expect(receipts2.rows).toEqual(receipts1.rows);
    expect(putCalls).toBe(2);
    expect(second.code).toBe(0);
    expect(second.stdout).toContain('claimed=1 completed=1 failed=0');
    const finalAttempts = await stack.ownerQuery('SELECT a.attempt_id,a.lifecycle,a.generation FROM core.work_attempts a JOIN core.work_items w USING(tenant_id,work_item_id) WHERE w.run_id=$1 ORDER BY a.generation,a.created_at', [String(admitted.body['runId'])]);
    expect(finalAttempts.rows).toHaveLength(2);
    expect(finalAttempts.rows[0]).toMatchObject({ attempt_id: firstAttemptId, lifecycle: 'expired' });
    expect(finalAttempts.rows[1]['lifecycle']).toBe('succeeded');
    const finalRun = await stack.ownerQuery('SELECT lifecycle FROM core.runs WHERE tenant_id=$1 AND run_id=$2', [tenantId, String(admitted.body['runId'])]);
    expect(finalRun.rows[0]?.['lifecycle']).toBe('succeeded');
    const evidence = { project, runId: admitted.body['runId'], digest,
      committedPut, putCalls, rows: rows2.rows, receiptIds: receipts2.rows.map((row) => row['worker_request_id']),
      packageRowCount: packageRowCount.rows[0]?.['count'], receipts: receipts2.rows,
      attempts: finalAttempts.rows, run: finalRun.rows[0],
      firstWorker: { exitCode: first.code, error: 'AgentDbReconciliationRequiredError' },
      replacementWorker: { exitCode: second.code, stdout: second.stdout.trim() } };
    console.log('worker-proof', JSON.stringify(evidence));
    if (process.env['COGIT_A04_EVIDENCE_PATH']) {
      await writeFile(process.env['COGIT_A04_EVIDENCE_PATH'], `${JSON.stringify(evidence, null, 2)}\n`);
    }
  } finally {
    proxy.closeAllConnections();
    if (proxy.listening) await new Promise<void>((ok) => proxy.close(() => ok()));
    try {
      await stack.stop();
    } finally {
      await removePreparedCohort(cohort);
    }
  }
}, 300000);
